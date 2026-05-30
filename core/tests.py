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

        self.assertContains(response, '150.00')
        self.assertContains(response, 'monedas')
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


class DigitoVerificadorDniTests(TestCase):
    def test_calcular_digito_verificador_17801146(self):
        from core.services import calcular_digito_verificador
        resultado = calcular_digito_verificador('17801146')
        self.assertEqual(resultado, 0)

    def test_calcular_digito_verificador_40000000(self):
        from core.services import calcular_digito_verificador
        resultado = calcular_digito_verificador('40000000')
        self.assertIsInstance(resultado, int)
        self.assertIn(resultado, range(11))

    def test_calcular_digito_verificador_longitud_incorrecta(self):
        from core.services import calcular_digito_verificador
        with self.assertRaises(ValueError):
            calcular_digito_verificador('1234567')

    def test_calcular_digito_verificador_no_numerico(self):
        from core.services import calcular_digito_verificador
        with self.assertRaises(ValueError):
            calcular_digito_verificador('1234ABCD')

    def test_digito_verificador_letra(self):
        from core.services import digito_verificador_letra
        letra = digito_verificador_letra('17801146')
        self.assertIn(letra, ('K', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'))

    def test_validar_dni_8_digitos_valido(self):
        from core.services import validar_dni_peruano
        self.assertTrue(validar_dni_peruano('17801146'))

    def test_validar_dni_8_digitos_secuencia_trivial(self):
        from core.services import validar_dni_peruano
        self.assertFalse(validar_dni_peruano('00000000'))

    def test_validar_dni_8_digitos_no_numerico(self):
        from core.services import validar_dni_peruano
        self.assertFalse(validar_dni_peruano('1234ABCD'))

    def test_validar_dni_9_con_verificador_correcto(self):
        from core.services import validar_dni_peruano
        self.assertTrue(validar_dni_peruano('178011460'))

    def test_validar_dni_9_con_verificador_incorrecto(self):
        from core.services import validar_dni_peruano
        self.assertFalse(validar_dni_peruano('178011461'))

    def test_validar_dni_longitud_incorrecta(self):
        from core.services import validar_dni_peruano
        self.assertFalse(validar_dni_peruano('1234567'))
        self.assertFalse(validar_dni_peruano('1234567890'))
