from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from billetera.services.account_service import crear_cuenta_wallet_usuario, obtener_o_crear_cuenta_sistema
from billetera.services.wallet_service import recargar_fichas
from core.choices import EstadoCuentaJugador, PeriodoLimite, TipoCuentaContable
from cuentas.models import PerfilJugador
from juego_responsable.models import LimiteJuegoResponsable
from juego_responsable.validators import validar_limite_recarga


class JuegoResponsableTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username='jr_user',
            email='jr_user@test.com',
            password='test12345',
        )
        PerfilJugador.objects.create(
            usuario=self.usuario,
            nombres='Jugador',
            apellidos='Responsable',
            dni='82345678',
            fecha_nacimiento='2000-01-01',
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
        )

    def test_actualiza_limite_pendiente_si_ya_corresponde(self):
        limite = LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.DIARIO,
            limite_actual=Decimal('100.0000'),
            limite_pendiente=Decimal('200.0000'),
            pendiente_aplicar_en=timezone.now() - timezone.timedelta(minutes=1),
        )

        limite.actualizar_limites_si_procede()
        limite.refresh_from_db()

        self.assertEqual(limite.limite_actual, Decimal('200.0000'))
        self.assertIsNone(limite.limite_pendiente)
        self.assertIsNone(limite.pendiente_aplicar_en)

    def test_no_actualiza_limite_pendiente_antes_del_cooldown(self):
        limite = LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.DIARIO,
            limite_actual=Decimal('100.0000'),
            limite_pendiente=Decimal('200.0000'),
            pendiente_aplicar_en=timezone.now() + timezone.timedelta(hours=1),
        )

        limite.actualizar_limites_si_procede()
        limite.refresh_from_db()

        self.assertEqual(limite.limite_actual, Decimal('100.0000'))
        self.assertEqual(limite.limite_pendiente, Decimal('200.0000'))

    def test_panel_no_falla_con_limites_existentes(self):
        LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.DIARIO,
            limite_actual=Decimal('100.0000'),
        )
        self.client.force_login(self.usuario)

        response = self.client.get('/juego-responsable/panel/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Juego Responsable')

    def test_validar_limite_recarga_usa_ledger_actual(self):
        crear_cuenta_wallet_usuario(self.usuario)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.DIARIO,
            limite_actual=Decimal('100.0000'),
        )
        LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.SEMANAL,
            limite_actual=Decimal('1000.0000'),
        )
        LimiteJuegoResponsable.objects.create(
            usuario=self.usuario,
            periodo=PeriodoLimite.MENSUAL,
            limite_actual=Decimal('1000.0000'),
        )
        recargar_fichas(self.usuario, Decimal('80.0000'), idempotency_key='jr-recarga-base')

        with self.assertRaises(ValidationError):
            validar_limite_recarga(self.usuario, Decimal('30.0000'))
