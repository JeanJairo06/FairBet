from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion
from deporte.exceptions import OddsNoDisponibleError, ResultadoEventoError, SeleccionNoApostableError
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado


def _to_decimal(valor, nombre_campo):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'{nombre_campo} debe ser un numero decimal valido.') from exc


def _resolver_evento(evento):
    if isinstance(evento, EventoDeportivo):
        return evento
    return EventoDeportivo.objects.get(pk=evento)


def _resolver_mercado(mercado):
    if isinstance(mercado, Mercado):
        return mercado
    return Mercado.objects.select_related('evento').get(pk=mercado)


def _resolver_seleccion(seleccion):
    if isinstance(seleccion, SeleccionMercado):
        return seleccion
    return SeleccionMercado.objects.select_related('mercado__evento').get(pk=seleccion)


def crear_evento(datos):
    datos = {**datos, 'deporte': 'Futbol'}
    evento = EventoDeportivo(**datos)
    evento.full_clean()
    evento.save()
    return evento


def crear_mercado(evento, datos):
    evento = _resolver_evento(evento)
    mercado = Mercado(evento=evento, **datos)
    mercado.full_clean()
    mercado.save()
    return mercado


def crear_seleccion(mercado, datos):
    mercado = _resolver_mercado(mercado)
    seleccion = SeleccionMercado(mercado=mercado, **datos)
    seleccion.full_clean()
    seleccion.save()
    return seleccion


@transaction.atomic
def actualizar_odds(seleccion, odds, cambiado_por=None):
    seleccion = SeleccionMercado.objects.select_for_update().get(pk=_resolver_seleccion(seleccion).pk)
    odds = _to_decimal(odds, 'odds')
    if odds <= Decimal('1'):
        raise ValueError('odds debe ser mayor que 1.')

    ahora = timezone.now()
    HistorialOdds.objects.select_for_update().filter(seleccion=seleccion, activa=True).update(
        activa=False,
        valido_hasta=ahora,
    )
    ultima_version = (
        HistorialOdds.objects.filter(seleccion=seleccion).aggregate(max_version=Max('numero_version'))['max_version']
        or 0
    )

    nueva_odds = HistorialOdds(
        seleccion=seleccion,
        odds=odds,
        numero_version=ultima_version + 1,
        activa=True,
        valido_desde=ahora,
        cambiado_por=cambiado_por,
    )
    nueva_odds.full_clean()
    nueva_odds.save()
    return nueva_odds


def obtener_odds_vigente(seleccion):
    seleccion = _resolver_seleccion(seleccion)
    ahora = timezone.now()
    odds = (
        HistorialOdds.objects.filter(
            seleccion=seleccion,
            activa=True,
            valido_desde__lte=ahora,
        )
        .filter(Q(valido_hasta__isnull=True) | Q(valido_hasta__gt=ahora))
        .order_by('-numero_version')
        .first()
    )
    if odds is None:
        raise OddsNoDisponibleError('La seleccion no tiene odds vigente.')
    return odds


def validar_seleccion_apostable(seleccion):
    seleccion = _resolver_seleccion(seleccion)
    mercado = seleccion.mercado
    evento = mercado.evento
    ahora = timezone.now()

    if evento.resultado_confirmado:
        raise SeleccionNoApostableError('El resultado del evento ya fue confirmado.')
    if evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
        raise SeleccionNoApostableError('El evento no esta disponible para apostar.')
    if evento.estado_evento == EstadoEvento.EN_VIVO and not mercado.permite_in_play:
        raise SeleccionNoApostableError('El mercado no permite apuestas en vivo.')
    if mercado.estado_mercado != EstadoMercado.ABIERTO:
        raise SeleccionNoApostableError('El mercado no esta abierto.')
    if mercado.suspendido_hasta and mercado.suspendido_hasta > ahora:
        raise SeleccionNoApostableError('El mercado esta suspendido temporalmente.')
    if seleccion.estado_seleccion != EstadoSeleccion.ACTIVA:
        raise SeleccionNoApostableError('La seleccion no esta activa.')

    obtener_odds_vigente(seleccion)
    return True


@transaction.atomic
def pasar_evento_en_vivo(evento):
    evento = EventoDeportivo.objects.select_for_update().get(pk=_resolver_evento(evento).pk)
    if evento.resultado_confirmado:
        raise ResultadoEventoError('No se puede pasar a en vivo un evento con resultado confirmado.')
    if evento.estado_evento != EstadoEvento.PROGRAMADO:
        raise ResultadoEventoError('Solo un evento programado puede pasar a en vivo.')

    evento.estado_evento = EstadoEvento.EN_VIVO
    evento.full_clean()
    evento.save(update_fields=['estado_evento', 'updated_at'])
    return evento


@transaction.atomic
def suspender_evento(evento):
    evento = EventoDeportivo.objects.select_for_update().get(pk=_resolver_evento(evento).pk)
    if evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
        raise ResultadoEventoError('Solo un evento programado o en vivo puede suspenderse.')

    evento.estado_evento = EstadoEvento.SUSPENDIDO
    evento.full_clean()
    evento.save(update_fields=['estado_evento', 'updated_at'])
    evento.mercados.filter(estado_mercado=EstadoMercado.ABIERTO).update(estado_mercado=EstadoMercado.SUSPENDIDO)
    return evento


@transaction.atomic
def anular_evento(evento):
    evento = EventoDeportivo.objects.select_for_update().get(pk=_resolver_evento(evento).pk)
    if evento.resultado_confirmado:
        raise ResultadoEventoError('No se puede anular un evento con resultado confirmado.')
    if evento.estado_evento == EstadoEvento.FINALIZADO:
        raise ResultadoEventoError('No se puede anular un evento finalizado.')

    evento.estado_evento = EstadoEvento.ANULADO
    evento.resultado_confirmado = False
    evento.full_clean()
    evento.save(update_fields=['estado_evento', 'resultado_confirmado', 'updated_at'])
    evento.mercados.exclude(estado_mercado=EstadoMercado.LIQUIDADO).update(estado_mercado=EstadoMercado.ANULADO)
    SeleccionMercado.objects.filter(mercado__evento=evento).exclude(
        estado_seleccion__in=[EstadoSeleccion.GANADORA, EstadoSeleccion.PERDEDORA]
    ).update(estado_seleccion=EstadoSeleccion.ANULADA)
    HistorialOdds.objects.filter(seleccion__mercado__evento=evento, activa=True).update(
        activa=False,
        valido_hasta=timezone.now(),
    )
    return evento


@transaction.atomic
def confirmar_resultado_evento(evento, resultado):
    evento = EventoDeportivo.objects.select_for_update().get(pk=_resolver_evento(evento).pk)
    if evento.resultado_confirmado:
        raise ResultadoEventoError('El resultado del evento ya fue confirmado.')

    marcador_local = resultado.get('marcador_local')
    marcador_visitante = resultado.get('marcador_visitante')
    if marcador_local is not None:
        evento.marcador_local = marcador_local
    if marcador_visitante is not None:
        evento.marcador_visitante = marcador_visitante

    evento.estado_evento = EstadoEvento.FINALIZADO
    evento.resultado_confirmado = True
    evento.full_clean()
    evento.save(
        update_fields=[
            'marcador_local',
            'marcador_visitante',
            'estado_evento',
            'resultado_confirmado',
            'updated_at',
        ]
    )

    evento.mercados.filter(estado_mercado__in=[EstadoMercado.ABIERTO, EstadoMercado.SUSPENDIDO]).update(
        estado_mercado=EstadoMercado.CERRADO
    )
    return evento


@transaction.atomic
def marcar_seleccion_ganadora(seleccion):
    seleccion = SeleccionMercado.objects.select_for_update().select_related('mercado').get(
        pk=_resolver_seleccion(seleccion).pk
    )
    mercado = seleccion.mercado
    evento = mercado.evento

    if evento.estado_evento != EstadoEvento.FINALIZADO or not evento.resultado_confirmado:
        raise ResultadoEventoError('Para marcar una seleccion ganadora, el evento debe estar finalizado y confirmado.')

    mercado.selecciones.select_for_update().exclude(pk=seleccion.pk).filter(
        estado_seleccion__in=[EstadoSeleccion.ACTIVA, EstadoSeleccion.SUSPENDIDA]
    ).update(estado_seleccion=EstadoSeleccion.PERDEDORA)

    seleccion.estado_seleccion = EstadoSeleccion.GANADORA
    seleccion.full_clean()
    seleccion.save(update_fields=['estado_seleccion'])

    mercado.estado_mercado = EstadoMercado.LIQUIDADO
    mercado.full_clean()
    mercado.save(update_fields=['estado_mercado'])
    return seleccion
