from billetera.services.account_service import obtener_cuenta_sistema, obtener_cuenta_wallet
from billetera.services.balance_service import validar_saldo_suficiente
from billetera.services.ledger_service import crear_transaccion_ledger, obtener_transaccion_por_idempotency_key
from core.choices import DirectionLedger, TipoCuentaContable, TipoTransaccionLedger

# Combina la operación con la clave base para evitar duplicados por tipo de proceso.
def _idempotency_key_operacion(operacion, idempotency_key):
    if not idempotency_key:
        return None

    return f'{operacion}-{idempotency_key}'

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
