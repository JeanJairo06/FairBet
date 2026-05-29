from django.test import TestCase

from billetera.models import Cuenta
from core.choices import RolUsuario, TipoCuentaContable
from cuentas.forms import UsuarioRegistroForm


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
