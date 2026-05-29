from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion, TipoMercado
from deporte.forms import ActualizarOddsForm, MercadoForm
from deporte.exceptions import SeleccionNoApostableError
from deporte.models import HistorialOdds
from deporte.services import (
    actualizar_odds,
    confirmar_resultado_evento,
    crear_evento,
    crear_mercado,
    crear_seleccion,
    marcar_seleccion_ganadora,
    obtener_odds_vigente,
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

    def test_selector_evento_en_mercado_muestra_fecha(self):
        form = MercadoForm()
        label = form.fields['evento'].label_from_instance(self.evento)
        fecha = timezone.localtime(self.evento.inicia_en).strftime('%d/%m/%Y %H:%M')

        self.assertIn('Alianza Lima vs Universitario', label)
        self.assertIn(fecha, label)

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
                'estado_evento': EstadoEvento.PROGRAMADO,
                'marcador_local': 0,
                'marcador_visitante': 0,
            },
        )

        self.assertRedirects(response, reverse('deporte:eventos_lista'))
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
