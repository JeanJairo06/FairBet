from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

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

    def clean(self):
        super().clean()
        errores = {}

        if self.deporte and self.deporte.strip().lower() != 'futbol':
            errores['deporte'] = 'FairBet solo permite eventos de Futbol.'

        if self.equipo_local and self.equipo_visitante:
            if self.equipo_local.strip().lower() == self.equipo_visitante.strip().lower():
                errores['equipo_visitante'] = 'El equipo visitante debe ser distinto al equipo local.'

        if self.inicia_en and self.estado_evento == EstadoEvento.PROGRAMADO and self.inicia_en < timezone.now():
            errores['inicia_en'] = 'No se puede programar un evento en una fecha pasada.'

        if self.equipo_local and self.equipo_visitante and self.inicia_en:
            fecha_evento = timezone.localtime(self.inicia_en).date() if timezone.is_aware(self.inicia_en) else self.inicia_en.date()
            partido_duplicado = EventoDeportivo.objects.filter(
                equipo_local__iexact=self.equipo_local.strip(),
                equipo_visitante__iexact=self.equipo_visitante.strip(),
                inicia_en__date=fecha_evento,
            )
            if self.pk:
                partido_duplicado = partido_duplicado.exclude(pk=self.pk)
            if partido_duplicado.exists():
                errores['inicia_en'] = 'No puede existir el mismo partido en la misma fecha.'

        if self.estado_evento in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO} and self.resultado_confirmado:
            errores['resultado_confirmado'] = 'Solo un evento finalizado puede tener resultado confirmado.'

        if self.estado_evento == EstadoEvento.FINALIZADO and not self.resultado_confirmado:
            errores['resultado_confirmado'] = 'Un evento finalizado debe tener resultado confirmado.'

        if self.estado_evento == EstadoEvento.ANULADO and self.resultado_confirmado:
            errores['resultado_confirmado'] = 'Un evento anulado no debe tener resultado confirmado.'

        if errores:
            raise ValidationError(errores)

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

    def clean(self):
        super().clean()
        errores = {}

        if self.stake_minimo is not None and self.stake_minimo <= 0:
            errores['stake_minimo'] = 'El stake minimo debe ser mayor que cero.'

        if (
            self.stake_minimo is not None
            and self.stake_maximo is not None
            and self.stake_maximo < self.stake_minimo
        ):
            errores['stake_maximo'] = 'El stake maximo debe ser mayor o igual al stake minimo.'

        if self.margen_operador is not None and self.margen_operador < 0:
            errores['margen_operador'] = 'El margen del operador no puede ser negativo.'

        if self.evento_id:
            evento = self.evento
            if self.estado_mercado == EstadoMercado.ABIERTO:
                if evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
                    errores['estado_mercado'] = 'Solo eventos programados o en vivo pueden tener mercados abiertos.'
                elif evento.estado_evento == EstadoEvento.EN_VIVO and not self.permite_in_play:
                    errores['permite_in_play'] = 'Un mercado abierto en vivo debe permitir in-play.'

            if self.estado_mercado in {EstadoMercado.LIQUIDADO, EstadoMercado.ANULADO}:
                if evento.estado_evento not in {EstadoEvento.FINALIZADO, EstadoEvento.ANULADO}:
                    errores['estado_mercado'] = 'Un mercado liquidado o anulado requiere un evento finalizado o anulado.'

        if self.suspendido_hasta and self.estado_mercado != EstadoMercado.SUSPENDIDO:
            errores['suspendido_hasta'] = 'La fecha de suspension solo aplica a mercados suspendidos.'

        if self.suspendido_hasta and self.suspendido_hasta <= timezone.now():
            errores['suspendido_hasta'] = 'La suspension temporal debe terminar en una fecha futura.'

        if errores:
            raise ValidationError(errores)

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

    def clean(self):
        super().clean()
        errores = {}

        if self.codigo_seleccion:
            self.codigo_seleccion = self.codigo_seleccion.strip().upper()

        if self.mercado_id:
            mercado = self.mercado
            if self.estado_seleccion == EstadoSeleccion.ACTIVA:
                if mercado.estado_mercado != EstadoMercado.ABIERTO:
                    errores['estado_seleccion'] = 'Solo mercados abiertos pueden tener selecciones activas.'
                elif mercado.evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
                    errores['estado_seleccion'] = 'Solo eventos programados o en vivo pueden tener selecciones activas.'

            if self.estado_seleccion in {EstadoSeleccion.GANADORA, EstadoSeleccion.PERDEDORA}:
                if mercado.evento.estado_evento != EstadoEvento.FINALIZADO or not mercado.evento.resultado_confirmado:
                    errores['estado_seleccion'] = 'Una seleccion ganadora o perdedora requiere un evento finalizado y confirmado.'

            if self.estado_seleccion == EstadoSeleccion.ANULADA and mercado.estado_mercado != EstadoMercado.ANULADO:
                errores['estado_seleccion'] = 'Una seleccion anulada requiere que el mercado este anulado.'

        if errores:
            raise ValidationError(errores)

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

    def clean(self):
        super().clean()
        errores = {}

        if self.odds is not None and self.odds <= 1:
            errores['odds'] = 'La odds debe ser mayor que 1.'

        if self.valido_desde and self.valido_hasta and self.valido_hasta <= self.valido_desde:
            errores['valido_hasta'] = 'La fecha de fin debe ser posterior al inicio de vigencia.'

        if self.activa and self.valido_hasta:
            errores['valido_hasta'] = 'Una odds activa no debe tener fecha de fin.'

        if not self.activa and not self.valido_hasta:
            errores['valido_hasta'] = 'Una odds historica debe tener fecha de fin.'

        if self.seleccion_id and self.activa:
            seleccion = self.seleccion
            mercado = seleccion.mercado
            evento = mercado.evento
            if seleccion.estado_seleccion != EstadoSeleccion.ACTIVA:
                errores['seleccion'] = 'Solo selecciones activas pueden tener odds vigente.'
            elif mercado.estado_mercado != EstadoMercado.ABIERTO:
                errores['seleccion'] = 'Solo mercados abiertos pueden tener odds vigente.'
            elif evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
                errores['seleccion'] = 'Solo eventos programados o en vivo pueden tener odds vigente.'

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f'{self.seleccion} @ {self.odds}'
