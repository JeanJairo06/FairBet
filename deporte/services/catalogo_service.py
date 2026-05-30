from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion, TipoMercado
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
def crear_mercado_con_selecciones(evento, datos_mercado, selecciones, odds_iniciales=None, cambiado_por=None):
    mercado = crear_mercado(evento, datos_mercado)
    odds_iniciales = odds_iniciales or {}
    for seleccion in selecciones:
        nueva_seleccion = crear_seleccion(mercado, seleccion)
        odds = odds_iniciales.get(nueva_seleccion.codigo_seleccion)
        if odds not in [None, '']:
            actualizar_odds(nueva_seleccion, odds, cambiado_por=cambiado_por)
    return mercado


def _codigo_linea(linea):
    return str(linea).replace('-', 'M').replace('+', 'P').replace('.', '_')


def _linea_desde_codigo(codigo):
    codigo = str(codigo).replace('M', '-').replace('P', '+').replace('_', '.')
    return Decimal(codigo)


def _resolver_codigo_seleccion(mercado, seleccion, marcador_local, marcador_visitante):
    codigo = seleccion.codigo_seleccion.upper()
    total_goles = Decimal(marcador_local + marcador_visitante)

    if mercado.tipo_mercado == TipoMercado.UNO_X_DOS:
        if marcador_local > marcador_visitante:
            return EstadoSeleccion.GANADORA if codigo == 'HOME' else EstadoSeleccion.PERDEDORA
        if marcador_local < marcador_visitante:
            return EstadoSeleccion.GANADORA if codigo == 'AWAY' else EstadoSeleccion.PERDEDORA
        return EstadoSeleccion.GANADORA if codigo == 'DRAW' else EstadoSeleccion.PERDEDORA

    if mercado.tipo_mercado == TipoMercado.BTTS:
        ambos_anotan = marcador_local > 0 and marcador_visitante > 0
        if codigo == 'YES':
            return EstadoSeleccion.GANADORA if ambos_anotan else EstadoSeleccion.PERDEDORA
        if codigo == 'NO':
            return EstadoSeleccion.PERDEDORA if ambos_anotan else EstadoSeleccion.GANADORA
        return EstadoSeleccion.ANULADA

    if mercado.tipo_mercado == TipoMercado.OVER_UNDER:
        if codigo.startswith('OVER_'):
            linea = _linea_desde_codigo(codigo.removeprefix('OVER_'))
            if total_goles == linea:
                return EstadoSeleccion.ANULADA
            return EstadoSeleccion.GANADORA if total_goles > linea else EstadoSeleccion.PERDEDORA
        if codigo.startswith('UNDER_'):
            linea = _linea_desde_codigo(codigo.removeprefix('UNDER_'))
            if total_goles == linea:
                return EstadoSeleccion.ANULADA
            return EstadoSeleccion.GANADORA if total_goles < linea else EstadoSeleccion.PERDEDORA
        return EstadoSeleccion.ANULADA

    if mercado.tipo_mercado == TipoMercado.HANDICAP:
        if codigo.startswith('HOME_'):
            linea = _linea_desde_codigo(codigo.removeprefix('HOME_'))
            local_ajustado = Decimal(marcador_local) + linea
            visitante = Decimal(marcador_visitante)
            if local_ajustado == visitante:
                return EstadoSeleccion.ANULADA
            return EstadoSeleccion.GANADORA if local_ajustado > visitante else EstadoSeleccion.PERDEDORA
        if codigo.startswith('AWAY_'):
            linea = _linea_desde_codigo(codigo.removeprefix('AWAY_'))
            visitante_ajustado = Decimal(marcador_visitante) + linea
            local = Decimal(marcador_local)
            if visitante_ajustado == local:
                return EstadoSeleccion.ANULADA
            return EstadoSeleccion.GANADORA if visitante_ajustado > local else EstadoSeleccion.PERDEDORA
        return EstadoSeleccion.ANULADA

    return EstadoSeleccion.ANULADA


def crear_mercado_rapido(
    evento,
    plantilla,
    linea=None,
    datos_personalizados=None,
    stake_minimo=None,
    stake_maximo=None,
    odds_iniciales=None,
    cambiado_por=None,
):
    evento = _resolver_evento(evento)
    stake_minimo = _to_decimal(stake_minimo or '1.0000', 'stake_minimo')
    stake_maximo = _to_decimal(stake_maximo or '100.0000', 'stake_maximo')

    if plantilla == 'resultado_final':
        return crear_mercado_con_selecciones(
            evento,
            {
                'tipo_mercado': TipoMercado.UNO_X_DOS,
                'nombre': 'Resultado final',
                'stake_minimo': stake_minimo,
                'stake_maximo': stake_maximo,
            },
            [
                {'codigo_seleccion': 'HOME', 'nombre': f'Gana {evento.equipo_local}'},
                {'codigo_seleccion': 'DRAW', 'nombre': 'Empate'},
                {'codigo_seleccion': 'AWAY', 'nombre': f'Gana {evento.equipo_visitante}'},
            ],
            odds_iniciales=odds_iniciales,
            cambiado_por=cambiado_por,
        )

    if plantilla == 'ambos_anotan':
        return crear_mercado_con_selecciones(
            evento,
            {
                'tipo_mercado': TipoMercado.BTTS,
                'nombre': 'Ambos equipos anotan',
                'stake_minimo': stake_minimo,
                'stake_maximo': stake_maximo,
            },
            [
                {'codigo_seleccion': 'YES', 'nombre': 'Si'},
                {'codigo_seleccion': 'NO', 'nombre': 'No'},
            ],
            odds_iniciales=odds_iniciales,
            cambiado_por=cambiado_por,
        )

    if plantilla == 'total_goles':
        linea = _to_decimal(linea, 'linea')
        codigo = _codigo_linea(linea)
        return crear_mercado_con_selecciones(
            evento,
            {
                'tipo_mercado': TipoMercado.OVER_UNDER,
                'nombre': f'Total de goles {linea}',
                'stake_minimo': stake_minimo,
                'stake_maximo': stake_maximo,
            },
            [
                {'codigo_seleccion': f'OVER_{codigo}', 'nombre': f'Mas de {linea} goles'},
                {'codigo_seleccion': f'UNDER_{codigo}', 'nombre': f'Menos de {linea} goles'},
            ],
            odds_iniciales=odds_iniciales,
            cambiado_por=cambiado_por,
        )

    if plantilla == 'handicap':
        linea = _to_decimal(linea, 'linea')
        codigo = _codigo_linea(linea)
        return crear_mercado_con_selecciones(
            evento,
            {
                'tipo_mercado': TipoMercado.HANDICAP,
                'nombre': f'Handicap {linea}',
                'stake_minimo': stake_minimo,
                'stake_maximo': stake_maximo,
            },
            [
                {'codigo_seleccion': f'HOME_{codigo}', 'nombre': f'{evento.equipo_local} handicap {linea}'},
                {'codigo_seleccion': f'AWAY_{codigo}', 'nombre': f'{evento.equipo_visitante} handicap {linea}'},
            ],
            odds_iniciales=odds_iniciales,
            cambiado_por=cambiado_por,
        )

    if plantilla == 'personalizado':
        datos_personalizados = datos_personalizados or {}
        return crear_mercado(evento, datos_personalizados)

    raise ValueError('Plantilla de mercado no soportada.')


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
    if evento.inicia_en > timezone.now():
        raise ResultadoEventoError('No se puede pasar a en vivo un evento que aun no inicia.')

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
def reactivar_evento(evento):
    evento = EventoDeportivo.objects.select_for_update().get(pk=_resolver_evento(evento).pk)
    if evento.estado_evento != EstadoEvento.SUSPENDIDO:
        raise ResultadoEventoError('Solo un evento suspendido puede reactivarse.')
    if evento.resultado_confirmado:
        raise ResultadoEventoError('No se puede reactivar un evento con resultado confirmado.')

    evento.estado_evento = EstadoEvento.EN_VIVO if evento.ha_iniciado else EstadoEvento.PROGRAMADO
    evento.full_clean()
    evento.save(update_fields=['estado_evento', 'updated_at'])
    mercados_suspendidos = evento.mercados.filter(estado_mercado=EstadoMercado.SUSPENDIDO)
    if evento.estado_evento == EstadoEvento.EN_VIVO:
        mercados_suspendidos.filter(permite_in_play=True).update(estado_mercado=EstadoMercado.ABIERTO)
    else:
        mercados_suspendidos.update(estado_mercado=EstadoMercado.ABIERTO)
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
    if evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
        raise ResultadoEventoError('Solo un evento programado o en vivo puede finalizarse.')
    if evento.inicia_en > timezone.now():
        raise ResultadoEventoError('No se puede finalizar un evento que aun no inicia.')

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


def resolver_mercados_por_marcador(evento, marcador_local, marcador_visitante):
    evento = _resolver_evento(evento)
    mercados_resueltos = []
    ahora = timezone.now()

    mercados = Mercado.objects.select_for_update().filter(evento=evento).prefetch_related('selecciones')
    for mercado in mercados:
        estados = []
        for seleccion in mercado.selecciones.all():
            try:
                estado = _resolver_codigo_seleccion(mercado, seleccion, marcador_local, marcador_visitante)
            except (InvalidOperation, ValueError):
                estado = EstadoSeleccion.ANULADA

            seleccion.estado_seleccion = estado
            seleccion.save(update_fields=['estado_seleccion'])
            estados.append(estado)

        if estados and any(estado != EstadoSeleccion.ANULADA for estado in estados):
            mercado.estado_mercado = EstadoMercado.LIQUIDADO
        else:
            mercado.estado_mercado = EstadoMercado.ANULADO
        mercado.save(update_fields=['estado_mercado'])
        mercados_resueltos.append(mercado)

    HistorialOdds.objects.filter(seleccion__mercado__evento=evento, activa=True).update(
        activa=False,
        valido_hasta=ahora,
    )
    return mercados_resueltos


@transaction.atomic
def finalizar_evento_y_liquidar(evento, resultado, liquidado_por=None):
    from apuesta.servicios import liquidar_apuestas_de_evento

    evento = confirmar_resultado_evento(evento, resultado)
    resolver_mercados_por_marcador(
        evento,
        resultado.get('marcador_local'),
        resultado.get('marcador_visitante'),
    )
    liquidaciones = liquidar_apuestas_de_evento(
        evento,
        liquidado_por=liquidado_por,
        observacion='Liquidacion automatica por marcador final.',
    )
    return evento, liquidaciones


@transaction.atomic
def anular_evento_y_liquidar(evento, liquidado_por=None):
    from apuesta.servicios import liquidar_apuestas_de_evento

    evento = anular_evento(evento)
    liquidaciones = liquidar_apuestas_de_evento(
        evento,
        liquidado_por=liquidado_por,
        observacion='Liquidacion automatica por anulacion de evento.',
    )
    return evento, liquidaciones
