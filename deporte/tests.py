from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion, TipoMercado
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
