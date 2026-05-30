from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apuesta.models import LiquidacionApuesta
from apuesta.servicios import crear_apuesta_simple
from billetera.services.account_service import crear_cuenta_wallet_usuario, obtener_o_crear_cuenta_sistema
from billetera.services.balance_service import calcular_saldo
from billetera.services.wallet_service import recargar_fichas
from core.choices import (
    EstadoApuesta,
    EstadoCuentaJugador,
    EstadoEvento,
    EstadoMercado,
    EstadoSeleccion,
    TipoCuentaContable,
    TipoMercado,
)
from cuentas.models import PerfilJugador
from deporte.forms import ActualizarOddsForm, EventoDeportivoForm, MercadoForm
from deporte.exceptions import ResultadoEventoError, SeleccionNoApostableError
from deporte.models import HistorialOdds
from deporte.services import (
    actualizar_odds,
    anular_evento_y_liquidar,
    confirmar_resultado_evento,
    crear_evento,
    crear_mercado,
    crear_mercado_rapido,
    crear_seleccion,
    finalizar_evento_y_liquidar,
    marcar_seleccion_ganadora,
    obtener_odds_vigente,
    pasar_evento_en_vivo,
    reactivar_evento,
    suspender_evento,
    validar_seleccion_apostable,
)


class CatalogoDeportivoServiceTests(TestCase):
    def setUp(self):
        self.evento = crear_evento(
            {
                'deporte': 'Futbol',
                'competicion': 'Liga 1',
                'equipo_local': 'Alianza Lima',
                'equipo_visitante': 'Universitario',
                'inicia_en': timezone.now() + timedelta(days=1),
            }
        )
        self.mercado = crear_mercado(
            self.evento,
            {
                'tipo_mercado': TipoMercado.UNO_X_DOS,
                'nombre': 'Resultado final',
                'stake_minimo': Decimal('1.0000'),
                'stake_maximo': Decimal('100.0000'),
            },
        )
        self.local = crear_seleccion(
            self.mercado,
            {
                'codigo_seleccion': 'HOME',
                'nombre': 'Gana local',
            },
        )
        self.empate = crear_seleccion(
            self.mercado,
            {
                'codigo_seleccion': 'DRAW',
                'nombre': 'Empate',
            },
        )

    def test_actualizar_odds_mantiene_solo_una_vigente(self):
        primera = actualizar_odds(self.local, Decimal('1.8000'))
        segunda = actualizar_odds(self.local, Decimal('1.9500'))

        primera.refresh_from_db()

        self.assertFalse(primera.activa)
        self.assertIsNotNone(primera.valido_hasta)
        self.assertEqual(segunda.numero_version, 2)
        self.assertEqual(obtener_odds_vigente(self.local), segunda)
        self.assertEqual(HistorialOdds.objects.filter(seleccion=self.local, activa=True).count(), 1)

    def test_validar_seleccion_apostable_retorna_true_con_catalogo_activo(self):
        actualizar_odds(self.local, Decimal('2.1000'))

        self.assertTrue(validar_seleccion_apostable(self.local))

    def test_validar_seleccion_apostable_falla_si_mercado_cerrado(self):
        actualizar_odds(self.local, Decimal('2.1000'))
        self.mercado.estado_mercado = EstadoMercado.CERRADO
        self.mercado.save(update_fields=['estado_mercado'])

        with self.assertRaises(SeleccionNoApostableError):
            validar_seleccion_apostable(self.local)

    def test_confirmar_resultado_cierra_evento_y_mercado(self):
        self.evento.inicia_en = timezone.now() - timedelta(hours=2)
        self.evento.save(update_fields=['inicia_en'])

        evento = confirmar_resultado_evento(
            self.evento,
            {
                'marcador_local': 2,
                'marcador_visitante': 1,
            },
        )
        self.mercado.refresh_from_db()

        self.assertEqual(evento.estado_evento, EstadoEvento.FINALIZADO)
        self.assertTrue(evento.resultado_confirmado)
        self.assertEqual(self.mercado.estado_mercado, EstadoMercado.CERRADO)

    def test_marcar_seleccion_ganadora_liquida_mercado_y_pierde_las_demas(self):
        self.evento.inicia_en = timezone.now() - timedelta(hours=2)
        self.evento.save(update_fields=['inicia_en'])

        confirmar_resultado_evento(
            self.evento,
            {
                'marcador_local': 2,
                'marcador_visitante': 1,
            },
        )
        marcar_seleccion_ganadora(self.local)
        self.local.refresh_from_db()
        self.empate.refresh_from_db()
        self.mercado.refresh_from_db()

        self.assertEqual(self.local.estado_seleccion, EstadoSeleccion.GANADORA)
        self.assertEqual(self.empate.estado_seleccion, EstadoSeleccion.PERDEDORA)
        self.assertEqual(self.mercado.estado_mercado, EstadoMercado.LIQUIDADO)

    def test_vista_confirmar_resultado_liquida_apuestas_del_evento(self):
        jugador = get_user_model().objects.create_user(
            username='jugador_resultado',
            email='jugador_resultado@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=jugador,
            nombres='Jugador',
            apellidos='Resultado',
            dni='56781234',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        operador = get_user_model().objects.create_user(
            username='operador_resultado',
            email='operador_resultado@test.com',
            password='test12345',
        )
        wallet = crear_cuenta_wallet_usuario(jugador)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        recargar_fichas(jugador, Decimal('100.0000'), idempotency_key='vista-confirmar-resultado')
        actualizar_odds(self.local, Decimal('2.5000'))
        apuesta = crear_apuesta_simple(
            usuario=jugador,
            seleccion_id=self.local.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key='vista-confirmar-resultado-apuesta',
        )
        self.evento.inicia_en = timezone.now() - timedelta(hours=2)
        self.evento.save(update_fields=['inicia_en'])
        self.client.login(username='operador_resultado', password='test12345')

        response = self.client.post(
            reverse('deporte:evento_confirmar_resultado', args=[self.evento.pk]),
            {
                'marcador_local': 2,
                'marcador_visitante': 1,
                'seleccion_ganadora': self.local.pk,
            },
        )

        apuesta.refresh_from_db()
        self.assertRedirects(response, reverse('deporte:evento_detalle', args=[self.evento.pk]))
        self.assertEqual(apuesta.estado_apuesta, EstadoApuesta.WON)
        self.assertEqual(LiquidacionApuesta.objects.count(), 1)
        self.assertEqual(calcular_saldo(wallet), Decimal('115.0000'))

    def test_finalizar_evento_liquida_todos_los_mercados_por_marcador(self):
        jugador = get_user_model().objects.create_user(
            username='jugador_multimercado',
            email='jugador_multimercado@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=jugador,
            nombres='Jugador',
            apellidos='Multimercado',
            dni='66781234',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        wallet = crear_cuenta_wallet_usuario(jugador)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        recargar_fichas(jugador, Decimal('100.0000'), idempotency_key='multimercado-recarga')

        mercado_btts = crear_mercado_rapido(
            self.evento,
            'ambos_anotan',
            stake_minimo=Decimal('1.0000'),
            stake_maximo=Decimal('100.0000'),
            odds_iniciales={'YES': Decimal('1.8000'), 'NO': Decimal('2.1000')},
        )
        mercado_goles = crear_mercado_rapido(
            self.evento,
            'total_goles',
            linea=Decimal('2.5'),
            stake_minimo=Decimal('1.0000'),
            stake_maximo=Decimal('100.0000'),
            odds_iniciales={'OVER_2_5': Decimal('1.9000'), 'UNDER_2_5': Decimal('1.9500')},
        )
        actualizar_odds(self.local, Decimal('2.5000'))
        apuesta_1x2 = crear_apuesta_simple(jugador, self.local.pk, Decimal('10.0000'), 'multimercado-1x2')
        apuesta_btts = crear_apuesta_simple(
            jugador,
            mercado_btts.selecciones.get(codigo_seleccion='YES').pk,
            Decimal('10.0000'),
            'multimercado-btts',
        )
        apuesta_goles = crear_apuesta_simple(
            jugador,
            mercado_goles.selecciones.get(codigo_seleccion='OVER_2_5').pk,
            Decimal('10.0000'),
            'multimercado-over',
        )
        self.evento.inicia_en = timezone.now() - timedelta(hours=2)
        self.evento.save(update_fields=['inicia_en'])

        evento, liquidaciones = finalizar_evento_y_liquidar(
            self.evento,
            {'marcador_local': 2, 'marcador_visitante': 1},
            liquidado_por=None,
        )

        apuesta_1x2.refresh_from_db()
        apuesta_btts.refresh_from_db()
        apuesta_goles.refresh_from_db()
        self.mercado.refresh_from_db()
        mercado_btts.refresh_from_db()
        mercado_goles.refresh_from_db()
        self.assertEqual(evento.estado_evento, EstadoEvento.FINALIZADO)
        self.assertEqual(len(liquidaciones), 3)
        self.assertEqual(apuesta_1x2.estado_apuesta, EstadoApuesta.WON)
        self.assertEqual(apuesta_btts.estado_apuesta, EstadoApuesta.WON)
        self.assertEqual(apuesta_goles.estado_apuesta, EstadoApuesta.WON)
        self.assertEqual(self.mercado.estado_mercado, EstadoMercado.LIQUIDADO)
        self.assertEqual(mercado_btts.estado_mercado, EstadoMercado.LIQUIDADO)
        self.assertEqual(mercado_goles.estado_mercado, EstadoMercado.LIQUIDADO)
        self.assertEqual(calcular_saldo(wallet), Decimal('132.0000'))

    def test_anular_evento_devuelve_stakes_bloqueados(self):
        jugador = get_user_model().objects.create_user(
            username='jugador_anulacion',
            email='jugador_anulacion@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=jugador,
            nombres='Jugador',
            apellidos='Anulacion',
            dni='76781234',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        wallet = crear_cuenta_wallet_usuario(jugador)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        recargar_fichas(jugador, Decimal('50.0000'), idempotency_key='anulacion-recarga')
        actualizar_odds(self.local, Decimal('2.0000'))
        apuesta = crear_apuesta_simple(jugador, self.local.pk, Decimal('10.0000'), 'anulacion-apuesta')

        evento, liquidaciones = anular_evento_y_liquidar(self.evento, liquidado_por=None)

        apuesta.refresh_from_db()
        self.local.refresh_from_db()
        self.mercado.refresh_from_db()
        self.assertEqual(evento.estado_evento, EstadoEvento.ANULADO)
        self.assertEqual(self.mercado.estado_mercado, EstadoMercado.ANULADO)
        self.assertEqual(self.local.estado_seleccion, EstadoSeleccion.ANULADA)
        self.assertEqual(apuesta.estado_apuesta, EstadoApuesta.VOID)
        self.assertEqual(len(liquidaciones), 1)
        self.assertEqual(calcular_saldo(wallet), Decimal('50.0000'))

    def test_paginas_visuales_deporte_renderizan(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')
        actualizar_odds(self.local, Decimal('2.1000'))

        urls = [
            reverse('deporte:eventos_lista'),
            reverse('deporte:mercados_lista'),
            reverse('deporte:selecciones_lista'),
            reverse('deporte:odds_lista'),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_detalle_partido_muestra_workspace_de_configuracion(self):
        get_user_model().objects.create_user(username='operador_detalle', email='op_detalle@test.com', password='test12345')
        self.client.login(username='operador_detalle', password='test12345')
        actualizar_odds(self.local, Decimal('2.1000'))
        actualizar_odds(self.empate, Decimal('3.2000'))

        response = self.client.get(reverse('deporte:evento_detalle', args=[self.evento.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Configurar partido')
        self.assertContains(response, 'Resultado final')
        self.assertContains(response, 'Guardar odds')

    def test_crear_mercado_rapido_resultado_final_crea_selecciones_base(self):
        mercado = crear_mercado_rapido(self.evento, 'resultado_final')

        self.assertEqual(mercado.tipo_mercado, TipoMercado.UNO_X_DOS)
        self.assertEqual(set(mercado.selecciones.values_list('codigo_seleccion', flat=True)), {'HOME', 'DRAW', 'AWAY'})

    def test_crear_mercado_rapido_resultado_final_configura_stake_y_odds(self):
        mercado = crear_mercado_rapido(
            self.evento,
            'resultado_final',
            stake_minimo=Decimal('5.0000'),
            stake_maximo=Decimal('250.0000'),
            odds_iniciales={
                'HOME': Decimal('2.0000'),
                'DRAW': Decimal('3.5000'),
                'AWAY': Decimal('3.0000'),
            },
        )

        self.assertEqual(mercado.stake_minimo, Decimal('5.0000'))
        self.assertEqual(mercado.stake_maximo, Decimal('250.0000'))
        self.assertEqual(obtener_odds_vigente(mercado.selecciones.get(codigo_seleccion='HOME')).odds, Decimal('2.0000'))
        self.assertEqual(obtener_odds_vigente(mercado.selecciones.get(codigo_seleccion='DRAW')).odds, Decimal('3.5000'))
        self.assertEqual(obtener_odds_vigente(mercado.selecciones.get(codigo_seleccion='AWAY')).odds, Decimal('3.0000'))

    def test_crear_mercado_rapido_ambos_anotan_crea_si_no(self):
        mercado = crear_mercado_rapido(self.evento, 'ambos_anotan')

        self.assertEqual(mercado.tipo_mercado, TipoMercado.BTTS)
        self.assertEqual(set(mercado.selecciones.values_list('codigo_seleccion', flat=True)), {'YES', 'NO'})

    def test_crear_mercado_rapido_total_goles_crea_over_under(self):
        mercado = crear_mercado_rapido(self.evento, 'total_goles', linea=Decimal('2.5'))

        self.assertEqual(mercado.tipo_mercado, TipoMercado.OVER_UNDER)
        self.assertEqual(set(mercado.selecciones.values_list('codigo_seleccion', flat=True)), {'OVER_2_5', 'UNDER_2_5'})

    def test_crear_mercado_rapido_handicap_crea_local_visitante(self):
        mercado = crear_mercado_rapido(self.evento, 'handicap', linea=Decimal('0'))

        self.assertEqual(mercado.tipo_mercado, TipoMercado.HANDICAP)
        self.assertEqual(set(mercado.selecciones.values_list('codigo_seleccion', flat=True)), {'HOME_0', 'AWAY_0'})

    def test_vista_actualiza_odds_inline_desde_detalle(self):
        get_user_model().objects.create_user(username='operador_odds_inline', email='op_odds_inline@test.com', password='test12345')
        self.client.login(username='operador_odds_inline', password='test12345')

        response = self.client.post(
            reverse('deporte:evento_odds_actualizar', args=[self.evento.pk]),
            {
                f'odds_{self.local.pk}': '2.4000',
                f'odds_{self.empate.pk}': '3.1000',
            },
        )

        self.assertRedirects(response, reverse('deporte:evento_detalle', args=[self.evento.pk]))
        self.assertEqual(obtener_odds_vigente(self.local).odds, Decimal('2.4000'))
        self.assertEqual(obtener_odds_vigente(self.empate).odds, Decimal('3.1000'))

    def test_vista_crea_mercado_total_goles_con_stake_y_odds_iniciales(self):
        get_user_model().objects.create_user(username='operador_builder', email='op_builder@test.com', password='test12345')
        self.client.login(username='operador_builder', password='test12345')

        response = self.client.post(
            reverse('deporte:evento_mercado_rapido', args=[self.evento.pk]),
            {
                'plantilla': 'total_goles',
                'linea': '2.5',
                'stake_minimo': '3.0000',
                'stake_maximo': '150.0000',
                'odds_OVER': '1.9000',
                'odds_UNDER': '1.9500',
            },
        )

        mercado = self.evento.mercados.get(nombre='Total de goles 2.5')
        self.assertRedirects(response, reverse('deporte:evento_detalle', args=[self.evento.pk]))
        self.assertEqual(mercado.stake_minimo, Decimal('3.0000'))
        self.assertEqual(mercado.stake_maximo, Decimal('150.0000'))
        self.assertEqual(obtener_odds_vigente(mercado.selecciones.get(codigo_seleccion='OVER_2_5')).odds, Decimal('1.9000'))
        self.assertEqual(obtener_odds_vigente(mercado.selecciones.get(codigo_seleccion='UNDER_2_5')).odds, Decimal('1.9500'))

    def test_selector_evento_en_mercado_muestra_fecha(self):
        form = MercadoForm()
        label = form.fields['evento'].label_from_instance(self.evento)
        fecha = timezone.localtime(self.evento.inicia_en).strftime('%d/%m/%Y %H:%M')

        self.assertIn('Alianza Lima vs Universitario', label)
        self.assertIn(fecha, label)

    def test_formulario_evento_no_expone_marcador(self):
        form = EventoDeportivoForm()

        self.assertNotIn('marcador_local', form.fields)
        self.assertNotIn('marcador_visitante', form.fields)

    def test_editar_evento_mantiene_fecha_en_input(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')

        response = self.client.get(reverse('deporte:evento_editar', args=[self.evento.pk]))
        valor_fecha = timezone.localtime(self.evento.inicia_en).strftime('%Y-%m-%dT%H:%M')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{valor_fecha}"')

    def test_formulario_evento_guarda_futbol_por_defecto(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')

        response = self.client.post(
            reverse('deporte:evento_crear'),
            {
                'competicion': 'Copa Peru',
                'equipo_local': 'Equipo A',
                'equipo_visitante': 'Equipo B',
                'inicia_en': (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
            },
        )

        evento_creado = self.evento.__class__.objects.get(competicion='Copa Peru')
        self.assertRedirects(response, reverse('deporte:evento_detalle', args=[evento_creado.pk]))
        self.assertTrue(
            self.evento.__class__.objects.filter(
                competicion='Copa Peru',
                deporte='Futbol',
            ).exists()
        )

    def test_crear_evento_valida_equipos_distintos(self):
        with self.assertRaises(ValidationError):
            crear_evento(
                {
                    'competicion': 'Liga 1',
                    'equipo_local': 'Mismo Equipo',
                    'equipo_visitante': 'mismo equipo',
                    'inicia_en': timezone.now() + timedelta(days=1),
                }
            )

    def test_crear_evento_no_permite_programar_fecha_pasada(self):
        with self.assertRaisesMessage(ValidationError, 'No se puede programar un evento en una fecha pasada.'):
            crear_evento(
                {
                    'competicion': 'Liga 1',
                    'equipo_local': 'Sporting Cristal',
                    'equipo_visitante': 'Melgar',
                    'inicia_en': timezone.now() - timedelta(days=1),
                    'estado_evento': EstadoEvento.PROGRAMADO,
                }
            )

    def test_crear_evento_no_permite_mismo_partido_en_misma_fecha(self):
        with self.assertRaisesMessage(ValidationError, 'No puede existir el mismo partido en la misma fecha.'):
            crear_evento(
                {
                    'competicion': 'Liga 1',
                    'equipo_local': 'alianza lima',
                    'equipo_visitante': 'UNIVERSITARIO',
                    'inicia_en': self.evento.inicia_en + timedelta(minutes=10),
                    'estado_evento': EstadoEvento.PROGRAMADO,
                }
            )

    def test_crear_mercado_no_permite_abierto_en_evento_finalizado(self):
        self.evento.inicia_en = timezone.now() - timedelta(hours=2)
        self.evento.save(update_fields=['inicia_en'])

        confirmar_resultado_evento(
            self.evento,
            {
                'marcador_local': 1,
                'marcador_visitante': 0,
            },
        )
        self.evento.refresh_from_db()

        with self.assertRaises(ValidationError):
            crear_mercado(
                self.evento,
                {
                    'tipo_mercado': TipoMercado.UNO_X_DOS,
                    'nombre': 'Resultado final extra',
                    'estado_mercado': EstadoMercado.ABIERTO,
                    'stake_minimo': Decimal('1.0000'),
                    'stake_maximo': Decimal('100.0000'),
                },
            )

    def test_actualizar_odds_requiere_seleccion_activa_apostable(self):
        self.local.estado_seleccion = EstadoSeleccion.SUSPENDIDA
        self.local.save(update_fields=['estado_seleccion'])

        with self.assertRaises(ValidationError):
            actualizar_odds(self.local, Decimal('2.1000'))

    def test_evento_programado_mantiene_marcador_cero(self):
        with self.assertRaisesMessage(ValidationError, 'Un evento programado debe mantener marcador 0 - 0.'):
            crear_evento(
                {
                    'competicion': 'Liga 1',
                    'equipo_local': 'Equipo Marcador A',
                    'equipo_visitante': 'Equipo Marcador B',
                    'inicia_en': timezone.now() + timedelta(days=1),
                    'estado_evento': EstadoEvento.PROGRAMADO,
                    'marcador_local': 2,
                    'marcador_visitante': 1,
                }
            )

    def test_no_permite_finalizar_evento_futuro(self):
        with self.assertRaisesMessage(ResultadoEventoError, 'No se puede finalizar un evento que aun no inicia.'):
            confirmar_resultado_evento(
                self.evento,
                {
                    'marcador_local': 1,
                    'marcador_visitante': 0,
                },
            )

    def test_no_permite_pasar_a_en_vivo_evento_futuro(self):
        with self.assertRaisesMessage(ResultadoEventoError, 'No se puede pasar a en vivo un evento que aun no inicia.'):
            pasar_evento_en_vivo(self.evento)

    def test_no_permite_finalizar_evento_suspendido(self):
        suspender_evento(self.evento)

        with self.assertRaisesMessage(ResultadoEventoError, 'Solo un evento programado o en vivo puede finalizarse.'):
            confirmar_resultado_evento(
                self.evento,
                {
                    'marcador_local': 1,
                    'marcador_visitante': 0,
                },
            )

    def test_reactivar_evento_suspendido_futuro_vuelve_a_programado(self):
        suspender_evento(self.evento)

        evento = reactivar_evento(self.evento)
        self.mercado.refresh_from_db()

        self.assertEqual(evento.estado_evento, EstadoEvento.PROGRAMADO)
        self.assertEqual(self.mercado.estado_mercado, EstadoMercado.ABIERTO)

    def test_reactivar_evento_suspendido_iniciado_vuelve_a_en_vivo(self):
        self.evento.inicia_en = timezone.now() - timedelta(hours=1)
        self.evento.save(update_fields=['inicia_en'])
        suspender_evento(self.evento)

        evento = reactivar_evento(self.evento)
        self.mercado.refresh_from_db()

        self.assertEqual(evento.estado_evento, EstadoEvento.EN_VIVO)
        self.assertEqual(self.mercado.estado_mercado, EstadoMercado.SUSPENDIDO)

    def test_evento_futuro_muestra_acciones_de_inicio_o_finalizacion_deshabilitadas(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')
        self.evento.__class__.objects.filter(pk=self.evento.pk).update(marcador_local=5, marcador_visitante=5)

        response = self.client.get(reverse('deporte:eventos_lista'))

        self.assertContains(response, 'En vivo')
        self.assertContains(response, 'Finalizar')
        self.assertContains(response, 'disabled title="Disponible cuando inicie el evento"', count=2)
        self.assertContains(response, 'Suspender')
        self.assertContains(response, 'Anular')
        self.assertContains(response, '0 - 0')
        self.assertNotContains(response, '5 - 5')

    def test_evento_suspendido_muestra_editar_reactivar_y_anular(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')
        suspender_evento(self.evento)

        response = self.client.get(reverse('deporte:eventos_lista'))

        self.assertContains(response, reverse('deporte:evento_editar', args=[self.evento.pk]))
        self.assertContains(response, 'Reactivar')
        self.assertContains(response, 'Anular')
        self.assertNotContains(response, 'Finalizar')

    def test_evento_en_vivo_muestra_suspender_anular_y_finalizar(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')
        self.evento.inicia_en = timezone.now() - timedelta(hours=1)
        self.evento.save(update_fields=['inicia_en'])
        pasar_evento_en_vivo(self.evento)

        response = self.client.get(reverse('deporte:eventos_lista'))

        self.assertContains(response, 'Suspender')
        self.assertContains(response, 'Anular')
        self.assertContains(response, 'Finalizar')

    def test_formulario_odds_solo_muestra_selecciones_apostables(self):
        self.evento.estado_evento = EstadoEvento.ANULADO
        self.evento.save(update_fields=['estado_evento'])

        form = ActualizarOddsForm()

        self.assertNotIn(self.local, list(form.fields['seleccion'].queryset))

    def test_vista_odds_devuelve_error_de_formulario_sin_traceback(self):
        get_user_model().objects.create_user(username='operador', email='op@test.com', password='test12345')
        self.client.login(username='operador', password='test12345')

        self.evento.estado_evento = EstadoEvento.ANULADO
        self.evento.save(update_fields=['estado_evento'])

        response = self.client.post(
            reverse('deporte:odds_actualizar'),
            {
                'seleccion': self.local.pk,
                'odds': '2.5000',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
