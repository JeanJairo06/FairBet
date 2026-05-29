from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apuesta.models import Apuesta, DetalleApuesta, LiquidacionApuesta
from apuesta.servicios import crear_apuesta_simple, liquidar_apuesta, liquidar_apuestas_de_evento
from billetera.exceptions import SaldoInsuficienteError
from billetera.services.account_service import crear_cuenta_wallet_usuario, obtener_o_crear_cuenta_sistema
from billetera.services.balance_service import calcular_saldo
from billetera.services.wallet_service import recargar_fichas
from core.choices import (
    EstadoApuesta,
    EstadoCuentaJugador,
    EstadoDetalleApuesta,
    EstadoEvento,
    EstadoMercado,
    EstadoSeleccion,
    TipoCuentaContable,
    TipoTransaccionLedger,
    ResultadoLiquidacion,
    TipoMercado,
)
from cuentas.models import PerfilJugador
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado
from deporte.services import confirmar_resultado_evento, marcar_seleccion_ganadora


class CrearApuestaSimpleTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='daniel',
            email='daniel@test.com',
            password='test12345',
        )
        self.perfil = PerfilJugador.objects.create(
            usuario=self.usuario,
            nombres='Daniel',
            apellidos='Escribano',
            dni='12345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        self.evento = EventoDeportivo.objects.create(
            deporte='Futbol',
            competicion='Mundial 2026',
            equipo_local='Peru',
            equipo_visitante='Brasil',
            inicia_en=timezone.now() + timezone.timedelta(days=1),
        )
        self.mercado = Mercado.objects.create(
            evento=self.evento,
            tipo_mercado=TipoMercado.UNO_X_DOS,
            nombre='Resultado final',
            estado_mercado=EstadoMercado.ABIERTO,
            stake_minimo=Decimal('5.0000'),
            stake_maximo=Decimal('100.0000'),
        )
        self.seleccion = SeleccionMercado.objects.create(
            mercado=self.mercado,
            codigo_seleccion='HOME_WIN',
            nombre='Gana Peru',
            estado_seleccion=EstadoSeleccion.ACTIVA,
        )
        self.odds = HistorialOdds.objects.create(
            seleccion=self.seleccion,
            odds=Decimal('2.5000'),
            numero_version=1,
            activa=True,
            valido_desde=timezone.now(),
        )
        self.wallet = crear_cuenta_wallet_usuario(self.usuario)
        self.casa = obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        self.apuestas_pendientes = obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        recargar_fichas(self.usuario, Decimal('200.0000'), idempotency_key='setup-apuesta-simple')

    def test_crea_apuesta_simple_con_detalle_y_payout(self):
        apuesta = crear_apuesta_simple(
            usuario=self.usuario,
            seleccion_id=self.seleccion.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key='apuesta-simple-1',
        )

        self.assertEqual(Apuesta.objects.count(), 1)
        self.assertEqual(DetalleApuesta.objects.count(), 1)
        self.assertEqual(apuesta.usuario, self.usuario)
        self.assertEqual(apuesta.estado_apuesta, EstadoApuesta.ACCEPTED)
        self.assertEqual(apuesta.odds_total, Decimal('2.5000'))
        self.assertEqual(apuesta.payout_potencial, Decimal('25.0000'))
        self.assertEqual(apuesta.transaction_bloqueo.tipo_transaccion, TipoTransaccionLedger.BLOQUEO_APUESTA)
        self.assertEqual(apuesta.transaction_bloqueo.tipo_referencia, 'apuesta')
        self.assertEqual(apuesta.transaction_bloqueo.id_referencia, str(apuesta.id_apuesta))
        self.assertEqual(calcular_saldo(self.wallet), Decimal('190.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('10.0000'))

        detalle = apuesta.detalles.get()
        self.assertEqual(detalle.seleccion, self.seleccion)
        self.assertEqual(detalle.odds_snapshot, Decimal('2.5000'))
        self.assertEqual(detalle.version_odds, 1)

    def test_no_crea_apuesta_si_mercado_no_esta_abierto(self):
        self.mercado.estado_mercado = EstadoMercado.CERRADO
        self.mercado.save(update_fields=['estado_mercado'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_seleccion_no_esta_activa(self):
        self.seleccion.estado_seleccion = EstadoSeleccion.SUSPENDIDA
        self.seleccion.save(update_fields=['estado_seleccion'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_no_existe_odds_activa(self):
        self.odds.activa = False
        self.odds.save(update_fields=['activa'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_stake_es_menor_al_minimo(self):
        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('4.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_stake_es_mayor_al_maximo(self):
        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('101.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_evento_ya_inicio(self):
        self.evento.inicia_en = timezone.now() - timezone.timedelta(minutes=1)
        self.evento.save(update_fields=['inicia_en'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_evento_no_esta_programado(self):
        self.evento.estado_evento = EstadoEvento.SUSPENDIDO
        self.evento.save(update_fields=['estado_evento'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_usuario_no_esta_verificado(self):
        self.perfil.estado_cuenta = EstadoCuentaJugador.PENDIENTE_VERIFICACION
        self.perfil.save(update_fields=['estado_cuenta'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_no_crea_apuesta_si_usuario_esta_autoexcluido(self):
        self.perfil.estado_cuenta = EstadoCuentaJugador.AUTOEXCLUIDO
        self.perfil.save(update_fields=['estado_cuenta'])

        with self.assertRaises(ValidationError):
            crear_apuesta_simple(
                usuario=self.usuario,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
            )

        self.assertEqual(Apuesta.objects.count(), 0)

    def test_reutiliza_apuesta_si_idempotency_key_ya_existe(self):
        primera_apuesta = crear_apuesta_simple(
            usuario=self.usuario,
            seleccion_id=self.seleccion.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key='misma-apuesta',
        )

        segunda_apuesta = crear_apuesta_simple(
            usuario=self.usuario,
            seleccion_id=self.seleccion.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key='misma-apuesta',
        )

        self.assertEqual(primera_apuesta, segunda_apuesta)
        self.assertEqual(Apuesta.objects.count(), 1)

    def test_no_crea_apuesta_si_no_tiene_saldo_suficiente(self):
        usuario_sin_saldo = get_user_model().objects.create_user(
            username='sin_saldo',
            email='sin_saldo@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=usuario_sin_saldo,
            nombres='Sin',
            apellidos='Saldo',
            dni='52345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        crear_cuenta_wallet_usuario(usuario_sin_saldo)

        with self.assertRaises(SaldoInsuficienteError):
            crear_apuesta_simple(
                usuario=usuario_sin_saldo,
                seleccion_id=self.seleccion.id_seleccion,
                stake=Decimal('10.0000'),
                idempotency_key='apuesta-sin-saldo',
            )

        self.assertFalse(Apuesta.objects.filter(usuario=usuario_sin_saldo).exists())


class ApuestaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.usuario = get_user_model().objects.create_user(
            username='daniel_api',
            email='daniel_api@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=self.usuario,
            nombres='Daniel',
            apellidos='Api',
            dni='22345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        self.otro_usuario = get_user_model().objects.create_user(
            username='otro_usuario',
            email='otro@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=self.otro_usuario,
            nombres='Otro',
            apellidos='Usuario',
            dni='32345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        self.client.force_authenticate(user=self.usuario)

        self.evento = EventoDeportivo.objects.create(
            deporte='Futbol',
            competicion='Mundial 2026',
            equipo_local='Peru',
            equipo_visitante='Brasil',
            inicia_en=timezone.now() + timezone.timedelta(days=1),
        )
        self.mercado = Mercado.objects.create(
            evento=self.evento,
            tipo_mercado=TipoMercado.UNO_X_DOS,
            nombre='Resultado final',
            estado_mercado=EstadoMercado.ABIERTO,
            stake_minimo=Decimal('5.0000'),
            stake_maximo=Decimal('100.0000'),
        )
        self.seleccion = SeleccionMercado.objects.create(
            mercado=self.mercado,
            codigo_seleccion='HOME_WIN',
            nombre='Gana Peru',
            estado_seleccion=EstadoSeleccion.ACTIVA,
        )
        HistorialOdds.objects.create(
            seleccion=self.seleccion,
            odds=Decimal('2.5000'),
            numero_version=1,
            activa=True,
            valido_desde=timezone.now(),
        )
        crear_cuenta_wallet_usuario(self.usuario)
        crear_cuenta_wallet_usuario(self.otro_usuario)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        recargar_fichas(self.usuario, Decimal('200.0000'), idempotency_key='setup-api-usuario')
        recargar_fichas(self.otro_usuario, Decimal('200.0000'), idempotency_key='setup-api-otro')

    def test_api_crea_apuesta_simple(self):
        response = self.client.post(
            '/api/v1/apuestas/',
            {
                'seleccion_id': self.seleccion.id_seleccion,
                'stake': '10.0000',
                'idempotency_key': 'api-apuesta-simple-1',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Apuesta.objects.count(), 1)
        self.assertEqual(response.data['estado_apuesta'], EstadoApuesta.ACCEPTED)
        self.assertEqual(response.data['payout_potencial'], '25.0000')

    def test_api_lista_solo_apuestas_del_usuario_autenticado(self):
        apuesta_usuario = crear_apuesta_simple(
            usuario=self.usuario,
            seleccion_id=self.seleccion.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key='api-lista-usuario',
        )
        crear_apuesta_simple(
            usuario=self.otro_usuario,
            seleccion_id=self.seleccion.id_seleccion,
            stake=Decimal('15.0000'),
            idempotency_key='api-lista-otro',
        )

        response = self.client.get('/api/v1/apuestas/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id_apuesta'], apuesta_usuario.id_apuesta)


class LiquidarApuestaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='daniel_liquidacion',
            email='daniel_liquidacion@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=self.usuario,
            nombres='Daniel',
            apellidos='Liquidacion',
            dni='42345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )
        self.admin = get_user_model().objects.create_user(
            username='admin_liquidacion',
            email='admin_liquidacion@test.com',
            password='test12345',
            is_staff=True,
        )
        self.evento = EventoDeportivo.objects.create(
            deporte='Futbol',
            competicion='Mundial 2026',
            equipo_local='Peru',
            equipo_visitante='Brasil',
            inicia_en=timezone.now() + timezone.timedelta(days=1),
        )
        self.mercado = Mercado.objects.create(
            evento=self.evento,
            tipo_mercado=TipoMercado.UNO_X_DOS,
            nombre='Resultado final',
            estado_mercado=EstadoMercado.ABIERTO,
            stake_minimo=Decimal('5.0000'),
            stake_maximo=Decimal('100.0000'),
        )
        self.seleccion = SeleccionMercado.objects.create(
            mercado=self.mercado,
            codigo_seleccion='HOME_WIN',
            nombre='Gana Peru',
            estado_seleccion=EstadoSeleccion.ACTIVA,
        )
        self.seleccion_visitante = SeleccionMercado.objects.create(
            mercado=self.mercado,
            codigo_seleccion='AWAY_WIN',
            nombre='Gana Brasil',
            estado_seleccion=EstadoSeleccion.ACTIVA,
        )
        HistorialOdds.objects.create(
            seleccion=self.seleccion,
            odds=Decimal('2.5000'),
            numero_version=1,
            activa=True,
            valido_desde=timezone.now(),
        )
        HistorialOdds.objects.create(
            seleccion=self.seleccion_visitante,
            odds=Decimal('3.0000'),
            numero_version=1,
            activa=True,
            valido_desde=timezone.now(),
        )
        self.wallet = crear_cuenta_wallet_usuario(self.usuario)
        self.casa = obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        self.apuestas_pendientes = obtener_o_crear_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
        recargar_fichas(self.usuario, Decimal('200.0000'), idempotency_key='setup-liquidacion')

    def crear_apuesta_aceptada(self, idempotency_key):
        return crear_apuesta_simple(
            usuario=self.usuario,
            seleccion_id=self.seleccion.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key=idempotency_key,
        )

    def test_liquida_apuesta_ganadora(self):
        apuesta = self.crear_apuesta_aceptada('liquidacion-ganada')

        liquidacion = liquidar_apuesta(
            apuesta=apuesta,
            resultado=ResultadoLiquidacion.WON,
            liquidado_por=self.admin,
            observacion='Seleccion ganadora confirmada.',
        )

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado_apuesta, EstadoApuesta.WON)
        self.assertEqual(apuesta.liquidada_en, liquidacion.liquidado_en)
        self.assertEqual(liquidacion.payout, Decimal('25.0000'))
        self.assertEqual(liquidacion.resultado_liquidacion, ResultadoLiquidacion.WON)
        self.assertEqual(liquidacion.transaction_liquidacion.tipo_transaccion, TipoTransaccionLedger.LIQUIDACION)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('215.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))
        self.assertEqual(LiquidacionApuesta.objects.count(), 1)

    def test_liquida_apuesta_perdida(self):
        apuesta = self.crear_apuesta_aceptada('liquidacion-perdida')

        liquidacion = liquidar_apuesta(
            apuesta=apuesta,
            resultado=ResultadoLiquidacion.LOST,
            liquidado_por=self.admin,
        )

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado_apuesta, EstadoApuesta.LOST)
        self.assertEqual(liquidacion.payout, Decimal('0.0000'))
        self.assertEqual(liquidacion.resultado_liquidacion, ResultadoLiquidacion.LOST)
        self.assertEqual(liquidacion.transaction_liquidacion.tipo_transaccion, TipoTransaccionLedger.LIQUIDACION)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('190.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))

    def test_liquida_apuesta_anulada_devolviendo_stake(self):
        apuesta = self.crear_apuesta_aceptada('liquidacion-anulada')

        liquidacion = liquidar_apuesta(
            apuesta=apuesta,
            resultado=ResultadoLiquidacion.VOID,
            liquidado_por=self.admin,
        )

        apuesta.refresh_from_db()
        self.assertEqual(apuesta.estado_apuesta, EstadoApuesta.VOID)
        self.assertEqual(liquidacion.payout, Decimal('10.0000'))
        self.assertEqual(liquidacion.resultado_liquidacion, ResultadoLiquidacion.VOID)
        self.assertEqual(liquidacion.transaction_liquidacion.tipo_transaccion, TipoTransaccionLedger.LIQUIDACION)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('200.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))

    def test_no_liquida_dos_veces_la_misma_apuesta(self):
        apuesta = self.crear_apuesta_aceptada('liquidacion-doble')

        liquidar_apuesta(
            apuesta=apuesta,
            resultado=ResultadoLiquidacion.LOST,
            liquidado_por=self.admin,
        )
        apuesta.refresh_from_db()

        with self.assertRaises(ValidationError):
            liquidar_apuesta(
                apuesta=apuesta,
                resultado=ResultadoLiquidacion.LOST,
                liquidado_por=self.admin,
            )

        self.assertEqual(LiquidacionApuesta.objects.count(), 1)

    def test_liquida_apuestas_de_evento_ganadora_y_perdedora(self):
        apuesta_ganadora = self.crear_apuesta_aceptada('liquidacion-evento-ganadora')
        apuesta_perdedora = crear_apuesta_simple(
            usuario=self.usuario,
            seleccion_id=self.seleccion_visitante.id_seleccion,
            stake=Decimal('10.0000'),
            idempotency_key='liquidacion-evento-perdedora',
        )
        self.evento.inicia_en = timezone.now() - timezone.timedelta(hours=2)
        self.evento.save(update_fields=['inicia_en'])

        confirmar_resultado_evento(
            self.evento,
            {
                'marcador_local': 2,
                'marcador_visitante': 1,
            },
        )
        marcar_seleccion_ganadora(self.seleccion)

        liquidaciones = liquidar_apuestas_de_evento(self.evento, liquidado_por=self.admin)

        apuesta_ganadora.refresh_from_db()
        apuesta_perdedora.refresh_from_db()
        detalle_ganador = apuesta_ganadora.detalles.get()
        detalle_perdedor = apuesta_perdedora.detalles.get()
        self.assertEqual(len(liquidaciones), 2)
        self.assertEqual(apuesta_ganadora.estado_apuesta, EstadoApuesta.WON)
        self.assertEqual(apuesta_perdedora.estado_apuesta, EstadoApuesta.LOST)
        self.assertEqual(detalle_ganador.estado_detalle, EstadoDetalleApuesta.WON)
        self.assertEqual(detalle_perdedor.estado_detalle, EstadoDetalleApuesta.LOST)
        self.assertEqual(calcular_saldo(self.wallet), Decimal('205.0000'))
        self.assertEqual(calcular_saldo(self.apuestas_pendientes), Decimal('0.0000'))
