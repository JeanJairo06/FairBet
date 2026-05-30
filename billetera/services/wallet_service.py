from decimal import Decimal, InvalidOperation

from billetera.exceptions import MontoInvalidoError
from billetera.services.account_service import obtener_cuenta_sistema, obtener_cuenta_wallet
from billetera.services.balance_service import validar_saldo_suficiente
from billetera.services.ledger_service import crear_transaccion_ledger, obtener_transaccion_por_idempotency_key
from core.choices import DirectionLedger, TipoCuentaContable, TipoTransaccionLedger

# Combina la operación con la clave base para evitar duplicados por tipo de proceso.
def _idempotency_key_operacion(operacion, idempotency_key):
    if not idempotency_key:
        return None

    return f'{operacion}-{idempotency_key}'


def _normalizar_monto(monto):
    try:
        monto = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MontoInvalidoError('El monto debe ser un Decimal valido.') from exc

    if monto <= 0:
        raise MontoInvalidoError('El monto debe ser mayor que cero.')

    return monto

# Registra una recarga de fichas en la wallet del usuario mediante una transacción ledger balanceada.
def recargar_fichas(usuario, monto, idempotency_key=None):
    wallet = obtener_cuenta_wallet(usuario)
    casa = obtener_cuenta_sistema(TipoCuentaContable.CASA)

    return crear_transaccion_ledger(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.RECARGA,
        entries=[
            {
                'cuenta': wallet,
                'direction': DirectionLedger.CREDIT,
                'amount': monto,
            },
            {
                'cuenta': casa,
                'direction': DirectionLedger.DEBIT,
                'amount': monto,
            },
        ],
        idempotency_key=_idempotency_key_operacion('recarga', idempotency_key),
        metadata={
            'operacion': 'recarga',
            'monto': str(monto),
        },
    )

# Registra un retiro de fichas desde la wallet del usuario mediante una transacción ledger balanceada.
def retirar_fichas(usuario, monto, idempotency_key=None):
    wallet = obtener_cuenta_wallet(usuario)
    casa = obtener_cuenta_sistema(TipoCuentaContable.CASA)
    idempotency_key = _idempotency_key_operacion('retiro', idempotency_key)

    transaccion_existente = obtener_transaccion_por_idempotency_key(idempotency_key)
    if transaccion_existente:
        return transaccion_existente

    validar_saldo_suficiente(wallet, monto)

    return crear_transaccion_ledger(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.RETIRO,
        entries=[
            {
                'cuenta': wallet,
                'direction': DirectionLedger.DEBIT,
                'amount': monto,
            },
            {
                'cuenta': casa,
                'direction': DirectionLedger.CREDIT,
                'amount': monto,
            },
        ],
        idempotency_key=idempotency_key,
        metadata={
            'operacion': 'retiro',
            'monto': str(monto),
        },
    )

# Registra el bloqueo del monto apostado mediante una transacción ledger balanceada.
def bloquear_stake(usuario, apuesta_id, monto, idempotency_key=None):
    wallet = obtener_cuenta_wallet(usuario)
    apuestas_pendientes = obtener_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
    idempotency_key = _idempotency_key_operacion('bloqueo-apuesta', idempotency_key)

    transaccion_existente = obtener_transaccion_por_idempotency_key(idempotency_key)
    if transaccion_existente:
        return transaccion_existente

    validar_saldo_suficiente(wallet, monto)

    return crear_transaccion_ledger(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.BLOQUEO_APUESTA,
        entries=[
            {
                'cuenta': wallet,
                'direction': DirectionLedger.DEBIT,
                'amount': monto,
            },
            {
                'cuenta': apuestas_pendientes,
                'direction': DirectionLedger.CREDIT,
                'amount': monto,
            },
        ],
        idempotency_key=idempotency_key,
        tipo_referencia='apuesta',
        id_referencia=apuesta_id,
        metadata={
            'operacion': 'bloqueo_apuesta',
            'apuesta_id': str(apuesta_id),
            'monto': str(monto),
        },
    )

# Liquida una apuesta ganada liberando el stake y acreditando el payout al usuario.
def liquidar_apuesta_ganada(usuario, apuesta_id, stake, payout, idempotency_key=None):
    wallet = obtener_cuenta_wallet(usuario)
    casa = obtener_cuenta_sistema(TipoCuentaContable.CASA)
    apuestas_pendientes = obtener_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
    stake = _normalizar_monto(stake)
    payout = _normalizar_monto(payout)

    if payout < stake:
        raise MontoInvalidoError('El payout no puede ser menor que el stake.')

    idempotency_key = _idempotency_key_operacion('liquidacion-ganada', idempotency_key or f'apuesta-{apuesta_id}')
    transaccion_existente = obtener_transaccion_por_idempotency_key(idempotency_key)
    if transaccion_existente:
        return transaccion_existente

    entries = [
        {
            'cuenta': apuestas_pendientes,
            'direction': DirectionLedger.DEBIT,
            'amount': stake,
        },
        {
            'cuenta': wallet,
            'direction': DirectionLedger.CREDIT,
            'amount': payout,
        },
    ]
    ganancia_adicional = payout - stake
    if ganancia_adicional > 0:
        entries.append(
            {
                'cuenta': casa,
                'direction': DirectionLedger.DEBIT,
                'amount': ganancia_adicional,
            }
        )

    return crear_transaccion_ledger(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.LIQUIDACION,
        entries=entries,
        idempotency_key=idempotency_key,
        tipo_referencia='apuesta',
        id_referencia=apuesta_id,
        metadata={
            'operacion': 'liquidacion_apuesta_ganada',
            'apuesta_id': str(apuesta_id),
            'stake': str(stake),
            'payout': str(payout),
        },
    )

# Liquida una apuesta perdida trasladando el stake bloqueado hacia la cuenta de la casa.
def liquidar_apuesta_perdida(usuario, apuesta_id, stake, idempotency_key=None):
    casa = obtener_cuenta_sistema(TipoCuentaContable.CASA)
    apuestas_pendientes = obtener_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
    stake = _normalizar_monto(stake)
    idempotency_key = _idempotency_key_operacion('liquidacion-perdida', idempotency_key or f'apuesta-{apuesta_id}')

    transaccion_existente = obtener_transaccion_por_idempotency_key(idempotency_key)
    if transaccion_existente:
        return transaccion_existente

    return crear_transaccion_ledger(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.LIQUIDACION,
        entries=[
            {
                'cuenta': apuestas_pendientes,
                'direction': DirectionLedger.DEBIT,
                'amount': stake,
            },
            {
                'cuenta': casa,
                'direction': DirectionLedger.CREDIT,
                'amount': stake,
            },
        ],
        idempotency_key=idempotency_key,
        tipo_referencia='apuesta',
        id_referencia=apuesta_id,
        metadata={
            'operacion': 'liquidacion_apuesta_perdida',
            'apuesta_id': str(apuesta_id),
            'stake': str(stake),
        },
    )

# Liquida una apuesta anulada devolviendo el stake bloqueado a la wallet del usuario.
def liquidar_apuesta_void(usuario, apuesta_id, stake, idempotency_key=None):
    wallet = obtener_cuenta_wallet(usuario)
    apuestas_pendientes = obtener_cuenta_sistema(TipoCuentaContable.APUESTAS_PENDIENTES)
    stake = _normalizar_monto(stake)
    idempotency_key = _idempotency_key_operacion('liquidacion-void', idempotency_key or f'apuesta-{apuesta_id}')

    transaccion_existente = obtener_transaccion_por_idempotency_key(idempotency_key)
    if transaccion_existente:
        return transaccion_existente

    return crear_transaccion_ledger(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.LIQUIDACION,
        entries=[
            {
                'cuenta': apuestas_pendientes,
                'direction': DirectionLedger.DEBIT,
                'amount': stake,
            },
            {
                'cuenta': wallet,
                'direction': DirectionLedger.CREDIT,
                'amount': stake,
            },
        ],
        idempotency_key=idempotency_key,
        tipo_referencia='apuesta',
        id_referencia=apuesta_id,
        metadata={
            'operacion': 'liquidacion_apuesta_void',
            'apuesta_id': str(apuesta_id),
            'stake': str(stake),
        },
    )
