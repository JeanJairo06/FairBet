from django.test import TestCase
from django.urls import reverse

from billetera.models import Cuenta
from core.choices import RolUsuario, TipoCuentaContable
from cuentas.forms import RegistroJugadorForm, UsuarioRegistroForm
from cuentas.models import PerfilJugador


class UsuarioRegistroFormWalletTests(TestCase):
    def _build_form(self, rol, username, extra_data=None):
        data = {
            'rol': rol,
            'username': username,
            'email': f'{username}@fairbet.local',
            'nombres': 'Usuario',
            'apellidos': 'Prueba',
            'dni': '',
            'fecha_nacimiento': '',
            'telefono': '',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        }
        if extra_data:
            data.update(extra_data)

        return UsuarioRegistroForm(data=data)

    def test_crear_jugador_crea_wallet_contable(self):
        form = self._build_form(
            RolUsuario.PLAYER,
            'jugador_wallet',
            {
                'dni': '12345678',
                'fecha_nacimiento': '1990-01-01',
                'telefono': '999999999',
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()

        cuenta = Cuenta.objects.get(usuario=usuario)
        self.assertEqual(cuenta.tipo_cuenta, TipoCuentaContable.WALLET_USUARIO)
        self.assertEqual(cuenta.codigo, f'WALLET-USUARIO-{usuario.pk}')

    def test_crear_operador_no_crea_wallet_contable(self):
        form = self._build_form(RolUsuario.OPERATOR, 'operador_sin_wallet')

        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()

        self.assertFalse(
            Cuenta.objects.filter(
                usuario=usuario,
                tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            ).exists()
        )

    def test_crear_administrador_no_crea_wallet_contable(self):
        form = self._build_form(RolUsuario.ADMIN, 'admin_sin_wallet')

        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()

        self.assertFalse(
            Cuenta.objects.filter(
                usuario=usuario,
                tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            ).exists()
        )


class RegistroJugadorFormTests(TestCase):
    def _build_form(self, extra_data=None):
        data = {
            'nombres': 'Juan',
            'apellidos': 'Perez',
            'dni': '12345678',
            'digito_verificador': '0',
            'fecha_nacimiento': '1990-05-15',
            'username': 'juan_perez',
            'email': 'juan@test.com',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
            'terminos': True,
        }
        if extra_data:
            data.update(extra_data)
        return RegistroJugadorForm(data=data)

    def test_registro_exitoso_crea_usuario_y_perfil(self):
        from core.services import calcular_digito_verificador
        dv = calcular_digito_verificador('12345678')
        form = self._build_form({'digito_verificador': str(dv)})
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.rol, RolUsuario.PLAYER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        perfil = PerfilJugador.objects.get(usuario=user)
        self.assertEqual(perfil.dni, '12345678')
        self.assertEqual(perfil.nombres, 'Juan')
        self.assertEqual(perfil.apellidos, 'Perez')

    def test_registro_crea_wallet(self):
        from core.services import calcular_digito_verificador
        dv = calcular_digito_verificador('12345678')
        form = self._build_form({'digito_verificador': str(dv)})
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertTrue(
            Cuenta.objects.filter(
                usuario=user,
                tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
            ).exists()
        )

    def test_registro_rechaza_duplicado(self):
        from core.services import calcular_digito_verificador
        dv = calcular_digito_verificador('12345678')
        form = self._build_form({'digito_verificador': str(dv)})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        form2 = self._build_form({'username': 'otro', 'email': 'otro@test.com', 'digito_verificador': str(dv)})
        self.assertFalse(form2.is_valid())
        self.assertIn('dni', form2.errors)

    def test_registro_rechaza_contrasenas_distintas(self):
        from core.services import calcular_digito_verificador
        dv = calcular_digito_verificador('12345678')
        form = self._build_form({'password2': 'OtraPass123!', 'digito_verificador': str(dv)})
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_registro_rechaza_sin_terminos(self):
        from core.services import calcular_digito_verificador
        dv = calcular_digito_verificador('12345678')
        form = self._build_form({'terminos': False, 'digito_verificador': str(dv)})
        self.assertFalse(form.is_valid())
        self.assertIn('terminos', form.errors)

    def test_registro_dv_incorrecto_rechaza(self):
        form = self._build_form({'digito_verificador': '9'})
        self.assertFalse(form.is_valid())
        self.assertIn('digito_verificador', form.errors)

    def test_registro_dv_letra_correcto(self):
        from core.services import calcular_digito_verificador, SERIE_LETRA
        dv_num = calcular_digito_verificador('17801146')
        dv_let = SERIE_LETRA[dv_num]
        form = self._build_form({'dni': '17801146', 'digito_verificador': dv_let})
        self.assertTrue(form.is_valid(), form.errors)

    def test_registro_dni_corto_rechaza(self):
        form = self._build_form({'dni': '1234567'})
        self.assertFalse(form.is_valid())
        self.assertIn('dni', form.errors)


class RegistroJugadorViewTests(TestCase):
    def test_get_registro_renderiza_formulario(self):
        response = self.client.get(reverse('registro_jugador'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registro de jugador')

    def test_post_registro_exitoso(self):
        from core.services import calcular_digito_verificador
        dv = calcular_digito_verificador('87654321')
        data = {
            'nombres': 'Maria',
            'apellidos': 'Lopez',
            'dni': '87654321',
            'digito_verificador': str(dv),
            'fecha_nacimiento': '1985-03-20',
            'username': 'maria_lopez',
            'email': 'maria@test.com',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
            'terminos': True,
        }
        response = self.client.post(reverse('registro_jugador'), data)
        self.assertRedirects(response, reverse('registro_exitoso'))
        self.assertTrue(PerfilJugador.objects.filter(dni='87654321').exists())

    def test_usuario_autenticado_redirige(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            username='ya_logueado', email='ya@test.com', password='test12345', rol=RolUsuario.PLAYER
        )
        self.client.force_login(user)
        response = self.client.get(reverse('registro_jugador'))
        self.assertRedirects(response, reverse('cuentas:cuentas'))
