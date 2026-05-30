from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from billetera.services.account_service import crear_cuenta_wallet_usuario, obtener_o_crear_cuenta_sistema
from billetera.services.wallet_service import recargar_fichas
from core.choices import RolUsuario, TipoCuentaContable


class HeaderWalletTests(TestCase):
    def test_jugador_con_wallet_ve_saldo_disponible(self):
        usuario = get_user_model().objects.create_user(
            username='header_jugador',
            email='header_jugador@test.com',
            password='test12345',
            rol=RolUsuario.PLAYER,
        )
        crear_cuenta_wallet_usuario(usuario)
        obtener_o_crear_cuenta_sistema(TipoCuentaContable.CASA)
        recargar_fichas(usuario, Decimal('150.0000'), idempotency_key='header-jugador-recarga')
        self.client.force_login(usuario)

        response = self.client.get(reverse('apuesta:apuestas_web'))

        self.assertContains(response, '150.00 monedas')
        self.assertNotContains(response, 'Administrador')

    def test_jugador_sin_wallet_no_rompe_header(self):
        usuario = get_user_model().objects.create_user(
            username='header_sin_wallet',
            email='header_sin_wallet@test.com',
            password='test12345',
            rol=RolUsuario.PLAYER,
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse('apuesta:apuestas_web'))

        self.assertContains(response, 'Sin wallet')

    def test_admin_ve_rol_y_no_saldo_casa(self):
        admin = get_user_model().objects.create_user(
            username='header_admin',
            email='header_admin@test.com',
            password='test12345',
            rol=RolUsuario.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('deporte:eventos_lista'))

        self.assertContains(response, 'Administrador')
        self.assertNotContains(response, 'monedas')

    def test_operador_ve_rol(self):
        operador = get_user_model().objects.create_user(
            username='header_operador',
            email='header_operador@test.com',
            password='test12345',
            rol=RolUsuario.OPERATOR,
            is_staff=True,
        )
        self.client.force_login(operador)

        response = self.client.get(reverse('deporte:eventos_lista'))

        self.assertContains(response, 'Operador')
        self.assertNotContains(response, 'monedas')


class HomeRedirectTests(TestCase):
    def test_anonimo_redirige_a_login(self):
        response = self.client.get(reverse('home'))

        self.assertRedirects(response, reverse('login'))

    def test_jugador_redirige_a_apuestas(self):
        usuario = get_user_model().objects.create_user(
            username='home_jugador',
            email='home_jugador@test.com',
            password='test12345',
            rol=RolUsuario.PLAYER,
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse('home'))

        self.assertRedirects(response, reverse('apuesta:apuestas_web'))

    def test_operador_redirige_a_deporte(self):
        usuario = get_user_model().objects.create_user(
            username='home_operador',
            email='home_operador@test.com',
            password='test12345',
            rol=RolUsuario.OPERATOR,
            is_staff=True,
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse('home'))

        self.assertRedirects(response, reverse('deporte:eventos_lista'))

    def test_admin_redirige_a_deporte(self):
        usuario = get_user_model().objects.create_user(
            username='home_admin',
            email='home_admin@test.com',
            password='test12345',
            rol=RolUsuario.ADMIN,
            is_staff=True,
        )
        self.client.force_login(usuario)

        response = self.client.get(reverse('home'))

        self.assertRedirects(response, reverse('deporte:eventos_lista'))
