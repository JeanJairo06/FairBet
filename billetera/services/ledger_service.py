from decimal import Decimal, InvalidOperation

from django.db import transaction

from billetera.exceptions import CuentaBloqueadaError, MontoInvalidoError, TransaccionNoBalanceadaError
from billetera.models import LedgerEntry, TransaccionLedger
from core.choices import DirectionLedger, EstadoCuentaContable, EstadoTransaccionLedger


def _normalizar_monto(monto):
    try:
        monto = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MontoInvalidoError('El monto debe ser un Decimal valido.') from exc

    if monto <= 0:
        raise MontoInvalidoError('El monto debe ser mayor que cero.')

    return monto

# Valida y normaliza los movimientos contables de una transacción antes de registrarla.
def validar_entries(entries):
    if not entries:
        raise TransaccionNoBalanceadaError('La transaccion debe tener movimientos.')

    if len(entries) < 2:
        raise TransaccionNoBalanceadaError('La transaccion debe tener al menos dos movimientos.')

    entries_normalizados = []
    direcciones_validas = {DirectionLedger.DEBIT, DirectionLedger.CREDIT}

    for entry in entries:
        cuenta = entry.get('cuenta')
        direction = entry.get('direction')
        amount = _normalizar_monto(entry.get('amount'))

        if cuenta is None:
            raise TransaccionNoBalanceadaError('Cada movimiento debe tener una cuenta.')

        if cuenta.estado != EstadoCuentaContable.ACTIVA:
            raise CuentaBloqueadaError('La cuenta no esta activa.')

        if direction not in direcciones_validas:
            raise TransaccionNoBalanceadaError('La direccion del movimiento no es valida.')

        entries_normalizados.append(
            {
                'cuenta': cuenta,
                'direction': direction,
                'amount': amount,
            }
        )

    return entries_normalizados

# Calcula los totales del Debe y Haber de los movimientos contables.
def calcular_totales(entries):
    total_debit = Decimal('0')
    total_credit = Decimal('0')

    for entry in entries:
        if entry['direction'] == DirectionLedger.DEBIT:
            total_debit += entry['amount']
        elif entry['direction'] == DirectionLedger.CREDIT:
            total_credit += entry['amount']

    return total_debit, total_credit

# Valida que los movimientos contables de la transacción estén balanceados.
def validar_entries_balanceados(entries):
    total_debit, total_credit = calcular_totales(entries)

    if total_debit != total_credit:
        raise TransaccionNoBalanceadaError('La suma de debitos debe ser igual a la suma de creditos.')

# Obtiene una transacción existente a partir de su clave de idempotencia.
def obtener_transaccion_por_idempotency_key(idempotency_key):
    if not idempotency_key:
        return None

    return TransaccionLedger.objects.filter(idempotency_key=idempotency_key).first()

# Registra una transacción ledger de forma atómica, evitando duplicados y creando sus movimientos contables.
@transaction.atomic
def crear_transaccion_ledger(
    *,
    usuario,
    tipo_transaccion,
    entries,
    idempotency_key=None,
    tipo_referencia='',
    id_referencia='',
    metadata=None,
):
    transaccion_existente = obtener_transaccion_por_idempotency_key(idempotency_key)
    if transaccion_existente:
        return transaccion_existente

    entries = validar_entries(entries)
    validar_entries_balanceados(entries)

    transaccion_ledger = TransaccionLedger.objects.create(
        usuario=usuario,
        tipo_transaccion=tipo_transaccion,
        idempotency_key=idempotency_key or None,
        tipo_referencia=tipo_referencia,
        id_referencia=str(id_referencia) if id_referencia else '',
        estado=EstadoTransaccionLedger.PENDING,
        metadata_json=metadata or {},
    )

    LedgerEntry.objects.bulk_create(
        [
            LedgerEntry(
                transaccion=transaccion_ledger,
                cuenta=entry['cuenta'],
                amount=entry['amount'],
                direction=entry['direction'],
            )
            for entry in entries
        ]
    )

    transaccion_ledger.estado = EstadoTransaccionLedger.COMPLETED
    transaccion_ledger.save(update_fields=['estado'])

    return transaccion_ledger

# Valida que una transacción existente tenga movimientos válidos y balanceados.
def validar_transaccion_balanceada(transaccion):
    entries = [
        {
            'cuenta': entry.cuenta,
            'direction': entry.direction,
            'amount': entry.amount,
        }
        for entry in transaccion.entries.select_related('cuenta')
    ]
    entries = validar_entries(entries)
    validar_entries_balanceados(entries)
    return True
