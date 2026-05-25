from django.db import models


class AuditoriaInmutable(models.Model):
    id_auditoria = models.BigAutoField(primary_key=True)
    numero_secuencia = models.PositiveBigIntegerField(unique=True)
    hash_anterior = models.CharField(max_length=64, blank=True)
    payload_json = models.JSONField()
    hash_actual = models.CharField(max_length=64)
    usuario_actor = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.PROTECT,
        related_name='eventos_auditoria',
        db_column='id_usuario_actor',
        null=True,
        blank=True,
    )
    accion = models.CharField(max_length=80)
    tipo_entidad = models.CharField(max_length=80)
    id_entidad = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'auditoria_inmutable'
        indexes = [
            models.Index(fields=['tipo_entidad', 'id_entidad'], name='idx_audit_entidad'),
            models.Index(fields=['numero_secuencia'], name='idx_audit_secuencia'),
        ]

    def __str__(self):
        return f'{self.numero_secuencia} - {self.accion}'
