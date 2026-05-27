from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.choices import EstadoApuesta, EstadoDetalleApuesta, ResultadoLiquidacion, TipoApuesta


class Apuesta(models.Model):
    id_apuesta = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.PROTECT,
        related_name='apuestas',
        db_column='id_usuario',
    )
    tipo_apuesta = models.CharField(max_length=16, choices=TipoApuesta.choices, default=TipoApuesta.SIMPLE)
    stake = models.DecimalField(max_digits=18, decimal_places=4)
    odds_total = models.DecimalField(max_digits=18, decimal_places=4)
    payout_potencial = models.DecimalField(max_digits=18, decimal_places=4)
    estado_apuesta = models.CharField(
        max_length=16,
        choices=EstadoApuesta.choices,
        default=EstadoApuesta.DRAFT,
    )
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    transaction_bloqueo = models.ForeignKey(
        'billetera.TransaccionLedger',
        on_delete=models.PROTECT,
        related_name='apuestas_bloqueadas',
        db_column='transaction_id_bloqueo',
        null=True,
        blank=True,
    )
    aceptada_en = models.DateTimeField(null=True, blank=True)
    liquidada_en = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'apuestas'
        indexes = [
            models.Index(fields=['usuario', 'estado_apuesta'], name='idx_apuesta_usuario_estado'),
            models.Index(fields=['created_at'], name='idx_apuesta_created_at'),
        ]
        constraints = [
            models.CheckConstraint(check=Q(stake__gt=0), name='ck_apuesta_stake_positivo'),
            models.CheckConstraint(check=Q(odds_total__gt=1), name='ck_apuesta_odds_total_mayor_uno'),
            models.CheckConstraint(check=Q(payout_potencial__gte=models.F('stake')), name='ck_apuesta_payout_potencial'),
            models.CheckConstraint(
                check=~Q(estado_apuesta=EstadoApuesta.ACCEPTED) | Q(transaction_bloqueo__isnull=False),
                name='ck_apuesta_accepted_con_bloqueo',
            ),
        ]

    def aceptar(self, transaction_bloqueo):
        self.estado_apuesta = EstadoApuesta.ACCEPTED
        self.transaction_bloqueo = transaction_bloqueo
        self.aceptada_en = timezone.now()

    def __str__(self):
        return f'Apuesta {self.id_apuesta} - {self.usuario}'


class DetalleApuesta(models.Model):
    id_detalle_apuesta = models.BigAutoField(primary_key=True)
    apuesta = models.ForeignKey(
        'apuesta.Apuesta',
        on_delete=models.CASCADE,
        related_name='detalles',
        db_column='id_apuesta',
    )
    seleccion = models.ForeignKey(
        'deporte.SeleccionMercado',
        on_delete=models.PROTECT,
        related_name='detalles_apuesta',
        db_column='id_seleccion',
    )
    odds_snapshot = models.DecimalField(max_digits=18, decimal_places=4)
    version_odds = models.PositiveIntegerField()
    estado_detalle = models.CharField(
        max_length=16,
        choices=EstadoDetalleApuesta.choices,
        default=EstadoDetalleApuesta.PENDING,
    )
    resultada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'detalles_apuesta'
        constraints = [
            models.CheckConstraint(check=Q(odds_snapshot__gt=1), name='ck_detalle_odds_snapshot_mayor_uno'),
        ]

    def __str__(self):
        return f'{self.apuesta_id} - {self.seleccion_id}'


class LiquidacionApuesta(models.Model):
    id_liquidacion = models.BigAutoField(primary_key=True)
    apuesta = models.OneToOneField(
        'apuesta.Apuesta',
        on_delete=models.PROTECT,
        related_name='liquidacion',
        db_column='id_apuesta',
    )
    resultado_liquidacion = models.CharField(max_length=16, choices=ResultadoLiquidacion.choices)
    payout = models.DecimalField(max_digits=18, decimal_places=4)
    transaction_liquidacion = models.ForeignKey(
        'billetera.TransaccionLedger',
        on_delete=models.PROTECT,
        related_name='liquidaciones_apuesta',
        db_column='transaction_id_liquidacion',
        null=True,
        blank=True,
    )
    liquidado_por = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.PROTECT,
        related_name='liquidaciones_realizadas',
        db_column='liquidado_por',
        null=True,
        blank=True,
    )
    liquidado_en = models.DateTimeField(default=timezone.now)
    observacion = models.TextField(blank=True)

    class Meta:
        db_table = 'liquidaciones_apuesta'
        constraints = [
            models.CheckConstraint(check=Q(payout__gte=0), name='ck_liquidacion_payout_no_negativo'),
        ]

    def __str__(self):
        return f'Liquidacion {self.id_liquidacion} - {self.resultado_liquidacion}'
