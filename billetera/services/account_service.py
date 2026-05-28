from billetera.exceptions import CuentaNoEncontradaError
from billetera.models import Cuenta
from core.choices import EstadoCuentaContable, TipoCuentaContable


CUENTAS_SISTEMA = {
    TipoCuentaContable.CASA: {
        'codigo': 'SISTEMA-CASA',
        'nombre': 'Casa',
    },
    TipoCuentaContable.APUESTAS_PENDIENTES: {
        'codigo': 'SISTEMA-APUESTAS-PENDIENTES',
        'nombre': 'Apuestas pendientes',
    },
    TipoCuentaContable.BONOS: {
        'codigo': 'SISTEMA-BONOS',
        'nombre': 'Bonos',
    },
}

# Valida que el tipo de cuenta corresponda a una cuenta interna del sistema.
def _validar_tipo_cuenta_sistema(tipo_cuenta):
    if tipo_cuenta not in CUENTAS_SISTEMA:
        raise ValueError('El tipo de cuenta no corresponde a una cuenta interna del sistema.')

# Crea u obtiene la wallet contable asociada a un usuario.
def crear_cuenta_wallet_usuario(usuario):
    cuenta, _ = Cuenta.objects.get_or_create(
        usuario=usuario,
        tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
        defaults={
            'codigo': f'WALLET-USUARIO-{usuario.pk}',
            'nombre': f'Wallet de {usuario}',
            'estado': EstadoCuentaContable.ACTIVA,
        },
    )
    return cuenta

# Obtiene la wallet contable asociada a un usuario.
def obtener_cuenta_wallet(usuario):
    cuenta = Cuenta.objects.filter(
        usuario=usuario,
        tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
    ).first()

    if cuenta is None:
        raise CuentaNoEncontradaError('El usuario no tiene una wallet contable.')

    return cuenta

# Obtiene o crea una cuenta contable interna del sistema.
def obtener_o_crear_cuenta_sistema(tipo_cuenta):
    _validar_tipo_cuenta_sistema(tipo_cuenta)
    datos = CUENTAS_SISTEMA[tipo_cuenta]

    cuenta, _ = Cuenta.objects.get_or_create(
        tipo_cuenta=tipo_cuenta,
        usuario=None,
        defaults={
            'codigo': datos['codigo'],
            'nombre': datos['nombre'],
            'estado': EstadoCuentaContable.ACTIVA,
        },
    )
    return cuenta

# Busca y retorna una cuenta contable del sistema previamente creada.
def obtener_cuenta_sistema(tipo_cuenta):
    _validar_tipo_cuenta_sistema(tipo_cuenta)

    cuenta = Cuenta.objects.filter(
        tipo_cuenta=tipo_cuenta,
        usuario=None,
    ).first()

    if cuenta is None:
        raise CuentaNoEncontradaError('La cuenta interna del sistema no existe.')

    return cuenta

# Asegura la existencia de todas las cuentas contables internas del sistema.
def asegurar_cuentas_sistema():
    return {
        tipo_cuenta: obtener_o_crear_cuenta_sistema(tipo_cuenta)
        for tipo_cuenta in CUENTAS_SISTEMA
    }
