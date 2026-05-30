from decimal import Decimal, InvalidOperation

from django.db.models import Sum

from billetera.exceptions import CuentaNoEncontradaError, MontoInvalidoError, SaldoInsuficienteError
from billetera.models import Cuenta, LedgerEntry
from core.choices import DirectionLedger, TipoCuentaContable


def _normalizar_monto(monto):
    try:
        monto = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MontoInvalidoError('El monto debe ser un Decimal valido.') from exc

    if monto <= 0:
        raise MontoInvalidoError('El monto debe ser mayor que cero.')

    return monto

# Obtiene el saldo acumulado de una cuenta según sus movimientos ledger.
def calcular_saldo(cuenta):
    total_credit = LedgerEntry.objects.filter(
        cuenta=cuenta,
        direction=DirectionLedger.CREDIT,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

    total_debit = LedgerEntry.objects.filter(
        cuenta=cuenta,
        direction=DirectionLedger.DEBIT,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

    return total_credit - total_debit

# Calcula el saldo disponible de la wallet contable de un usuario.
def calcular_saldo_usuario(usuario):
    cuenta = Cuenta.objects.filter(
        usuario=usuario,
        tipo_cuenta=TipoCuentaContable.WALLET_USUARIO,
    ).first()

    if cuenta is None:
        raise CuentaNoEncontradaError('El usuario no tiene una wallet contable.')

    return calcular_saldo(cuenta)

# Valida que la cuenta tenga saldo suficiente para cubrir el monto solicitado.
def validar_saldo_suficiente(cuenta, monto):
    monto = _normalizar_monto(monto)
    saldo = calcular_saldo(cuenta)

    if saldo < monto:
        raise SaldoInsuficienteError('Saldo insuficiente.')

    return True
