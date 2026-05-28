from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apuesta.models import Apuesta, DetalleApuesta
from apuesta.servicios import crear_apuesta_simple
from core.choices import EstadoApuesta, EstadoMercado, EstadoSeleccion, TipoMercado
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado


class CrearApuestaSimpleTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='daniel',
            email='daniel@test.com',
            password='test12345',
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

        detalle = apuesta.detalles.get()
        self.assertEqual(detalle.seleccion, self.seleccion)
        self.assertEqual(detalle.odds_snapshot, Decimal('2.5000'))
        self.assertEqual(detalle.version_odds, 1)
