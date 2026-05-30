from billetera.exceptions import CuentaNoEncontradaError
from billetera.services.balance_service import calcular_saldo_usuario
from core.choices import RolUsuario


def wallet_header(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    user_role = getattr(user, 'rol', None)

    if user_role == RolUsuario.PLAYER:
        try:
            saldo = calcular_saldo_usuario(user)
            return {
                'header_wallet_available': True,
                'header_wallet_balance': saldo,
                'header_wallet_balance_display': f'{saldo:.2f}',
                'header_wallet_label': 'Monedas',
            }
        except CuentaNoEncontradaError:
            return {
                'header_wallet_available': False,
                'header_wallet_balance': None,
                'header_wallet_balance_display': None,
                'header_wallet_label': 'Sin wallet',
            }

    if user_role == RolUsuario.ADMIN or user.is_superuser:
        return {
            'header_wallet_available': False,
            'header_wallet_balance': None,
            'header_wallet_balance_display': None,
            'header_wallet_label': 'Administrador',
        }

    if user_role == RolUsuario.OPERATOR:
        return {
            'header_wallet_available': False,
            'header_wallet_balance': None,
            'header_wallet_balance_display': None,
            'header_wallet_label': 'Operador',
        }

    return {}
