from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

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


class ApuestaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.usuario = get_user_model().objects.create_user(
            username='daniel_api',
            email='daniel_api@test.com',
            password='test12345',
        )
        self.otro_usuario = get_user_model().objects.create_user(
            username='otro_usuario',
            email='otro@test.com',
            password='test12345',
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
