import uuid

from django.db import models
from django.db.models import Q

from core.choices import (
    DirectionLedger,
    EstadoCuentaContable,
    EstadoTransaccionLedger,
    TipoCuentaContable,
    TipoTransaccionLedger,
)


class Cuenta(models.Model):
    id_cuenta = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.PROTECT,
        related_name='cuentas_contables',
        db_column='id_usuario',
        null=True,
        blank=True,
    )
    tipo_cuenta = models.CharField(max_length=32, choices=TipoCuentaContable.choices)
    codigo = models.CharField(max_length=80, unique=True)
    nombre = models.CharField(max_length=150)
    estado = models.CharField(
        max_length=16,
        choices=EstadoCuentaContable.choices,
        default=EstadoCuentaContable.ACTIVA,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cuentas'
        constraints = [
            models.CheckConstraint(
                check=Q(tipo_cuenta=TipoCuentaContable.WALLET_USUARIO, usuario__isnull=False)
                | ~Q(tipo_cuenta=TipoCuentaContable.WALLET_USUARIO),
                name='ck_wallet_usuario_requiere_usuario',
            ),
        ]

    def __str__(self):
        return self.codigo


class TransaccionLedger(models.Model):
    transaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.PROTECT,
        related_name='transacciones_ledger',
        db_column='id_usuario',
        null=True,
        blank=True,
    )
    tipo_transaccion = models.CharField(max_length=32, choices=TipoTransaccionLedger.choices)
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    tipo_referencia = models.CharField(max_length=80, blank=True)
    id_referencia = models.CharField(max_length=80, blank=True)
    estado = models.CharField(
        max_length=16,
        choices=EstadoTransaccionLedger.choices,
        default=EstadoTransaccionLedger.PENDING,
    )
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transacciones_ledger'

    def __str__(self):
        return str(self.transaction_id)


class LedgerEntry(models.Model):
    id_ledger_entry = models.BigAutoField(primary_key=True)
    transaccion = models.ForeignKey(
        'billetera.TransaccionLedger',
        on_delete=models.PROTECT,
        related_name='entries',
        db_column='transaction_id',
    )
    cuenta = models.ForeignKey(
        'billetera.Cuenta',
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        db_column='id_cuenta',
    )
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    direction = models.CharField(max_length=6, choices=DirectionLedger.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ledger_entries'
        indexes = [
            models.Index(fields=['transaccion', 'direction'], name='idx_ledger_tx_direction'),
            models.Index(fields=['cuenta', 'created_at'], name='idx_ledger_cuenta_fecha'),
        ]
        constraints = [
            models.CheckConstraint(check=Q(amount__gt=0), name='ck_ledger_amount_positivo'),
        ]

    def __str__(self):
        return f'{self.transaccion_id} {self.direction} {self.amount}'
