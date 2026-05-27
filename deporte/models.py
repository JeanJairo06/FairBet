from django.db import models
from django.db.models import Q

from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion, TipoMercado
from core.models import TimeStampedModel


class EventoDeportivo(TimeStampedModel):
    id_evento = models.BigAutoField(primary_key=True)
    deporte = models.CharField(max_length=80)
    competicion = models.CharField(max_length=120)
    equipo_local = models.CharField(max_length=120)
    equipo_visitante = models.CharField(max_length=120)
    inicia_en = models.DateTimeField()
    estado_evento = models.CharField(
        max_length=16,
        choices=EstadoEvento.choices,
        default=EstadoEvento.PROGRAMADO,
    )
    marcador_local = models.PositiveSmallIntegerField(default=0)
    marcador_visitante = models.PositiveSmallIntegerField(default=0)
    resultado_confirmado = models.BooleanField(default=False)

    class Meta:
        db_table = 'eventos_deportivos'
        indexes = [models.Index(fields=['estado_evento', 'inicia_en'], name='idx_evento_estado_inicio')]
        constraints = [
            models.CheckConstraint(check=~Q(equipo_local=models.F('equipo_visitante')), name='ck_evento_equipos_distintos'),
        ]

    def __str__(self):
        return f'{self.equipo_local} vs {self.equipo_visitante}'


class Mercado(models.Model):
    id_mercado = models.BigAutoField(primary_key=True)
    evento = models.ForeignKey(
        'deporte.EventoDeportivo',
        on_delete=models.CASCADE,
        related_name='mercados',
        db_column='id_evento',
    )
    tipo_mercado = models.CharField(max_length=32, choices=TipoMercado.choices)
    nombre = models.CharField(max_length=120)
    estado_mercado = models.CharField(
        max_length=16,
        choices=EstadoMercado.choices,
        default=EstadoMercado.ABIERTO,
    )
    margen_operador = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    stake_minimo = models.DecimalField(max_digits=18, decimal_places=4)
    stake_maximo = models.DecimalField(max_digits=18, decimal_places=4)
    permite_in_play = models.BooleanField(default=False)
    suspendido_hasta = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mercados'
        constraints = [
            models.CheckConstraint(check=Q(stake_minimo__gt=0), name='ck_mercado_stake_minimo_positivo'),
            models.CheckConstraint(check=Q(stake_maximo__gte=models.F('stake_minimo')), name='ck_mercado_stake_rango'),
            models.CheckConstraint(check=Q(margen_operador__gte=0), name='ck_mercado_margen_no_negativo'),
        ]

    def __str__(self):
        return f'{self.evento} - {self.nombre}'


class SeleccionMercado(models.Model):
    id_seleccion = models.BigAutoField(primary_key=True)
    mercado = models.ForeignKey(
        'deporte.Mercado',
        on_delete=models.CASCADE,
        related_name='selecciones',
        db_column='id_mercado',
    )
    codigo_seleccion = models.CharField(max_length=40)
    nombre = models.CharField(max_length=120)
    estado_seleccion = models.CharField(
        max_length=16,
        choices=EstadoSeleccion.choices,
        default=EstadoSeleccion.ACTIVA,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'selecciones_mercado'
        constraints = [
            models.UniqueConstraint(fields=['mercado', 'codigo_seleccion'], name='uq_seleccion_codigo_por_mercado'),
        ]

    def __str__(self):
        return f'{self.mercado} - {self.nombre}'


class HistorialOdds(models.Model):
    id_historial_odds = models.BigAutoField(primary_key=True)
    seleccion = models.ForeignKey(
        'deporte.SeleccionMercado',
        on_delete=models.CASCADE,
        related_name='historial_odds',
        db_column='id_seleccion',
    )
    odds = models.DecimalField(max_digits=18, decimal_places=4)
    numero_version = models.PositiveIntegerField()
    activa = models.BooleanField(default=True)
    valido_desde = models.DateTimeField()
    valido_hasta = models.DateTimeField(null=True, blank=True)
    cambiado_por = models.ForeignKey(
        'cuentas.Usuario',
        on_delete=models.PROTECT,
        related_name='odds_modificadas',
        db_column='cambiado_por',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'historial_odds'
        constraints = [
            models.CheckConstraint(check=Q(odds__gt=1), name='ck_odds_mayor_que_uno'),
            models.UniqueConstraint(fields=['seleccion', 'numero_version'], name='uq_odds_version_por_seleccion'),
            models.UniqueConstraint(
                fields=['seleccion'],
                condition=Q(activa=True),
                name='uq_odds_activa_por_seleccion',
            ),
        ]

    def __str__(self):
        return f'{self.seleccion} @ {self.odds}'
