from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.choices import PeriodoLimite, TipoAutoexclusion
from core.models import TimeStampedModel


class LimiteJuegoResponsable(TimeStampedModel):
    id_limite = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.CASCADE,
        related_name='limites_juego_responsable',
        db_column='id_usuario',
    )
    periodo = models.CharField(max_length=16, choices=PeriodoLimite.choices)
    limite_actual = models.DecimalField(max_digits=18, decimal_places=4)
    limite_pendiente = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    pendiente_aplicar_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'limites_juego_responsable'
        constraints = [
            models.UniqueConstraint(fields=['usuario', 'periodo'], name='uq_limite_usuario_periodo'),
            models.CheckConstraint(check=Q(limite_actual__gte=0), name='ck_limite_actual_no_negativo'),
            models.CheckConstraint(
                check=Q(limite_pendiente__isnull=True) | Q(limite_pendiente__gte=0),
                name='ck_limite_pendiente_no_negativo',
            ),
        ]

    def __str__(self):
        return f'{self.usuario} - {self.periodo}: {self.limite_actual}'


class Autoexclusion(models.Model):
    id_autoexclusion = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.CASCADE,
        related_name='autoexclusiones',
        db_column='id_usuario',
    )
    tipo_autoexclusion = models.CharField(max_length=16, choices=TipoAutoexclusion.choices)
    inicia_en = models.DateTimeField(default=timezone.now)
    finaliza_en = models.DateTimeField(null=True, blank=True)
    activa = models.BooleanField(default=True)
    motivo = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'autoexclusiones'
        constraints = [
            models.UniqueConstraint(
                fields=['usuario'],
                condition=Q(activa=True),
                name='uq_autoexclusion_activa_por_usuario',
            ),
            models.CheckConstraint(
                check=Q(tipo_autoexclusion=TipoAutoexclusion.INDEFINIDA, finaliza_en__isnull=True)
                | Q(tipo_autoexclusion=TipoAutoexclusion.TEMPORAL, finaliza_en__isnull=False),
                name='ck_autoexclusion_fecha_por_tipo',
            ),
        ]

    def esta_vigente(self):
        if not self.activa:
            return False
        if self.tipo_autoexclusion == TipoAutoexclusion.INDEFINIDA:
            return True
        return self.finaliza_en is not None and self.finaliza_en > timezone.now()

    def __str__(self):
        return f'{self.usuario} - {self.tipo_autoexclusion}'
