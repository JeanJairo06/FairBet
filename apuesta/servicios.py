from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apuesta.models import Apuesta, DetalleApuesta, LiquidacionApuesta
from billetera.services.wallet_service import (
    bloquear_stake,
    liquidar_apuesta_ganada,
    liquidar_apuesta_perdida,
    liquidar_apuesta_void,
)
from core.choices import (
    EstadoApuesta,
    EstadoCuentaJugador,
    EstadoDetalleApuesta,
    EstadoEvento,
    EstadoMercado,
    EstadoSeleccion,
    ResultadoLiquidacion,
    TipoApuesta,
)
from deporte.models import SeleccionMercado


def validar_usuario_puede_apostar(usuario):
    perfil = getattr(usuario, 'perfil_jugador', None)

    if perfil is None:
        raise ValidationError('El usuario no tiene perfil de jugador.')

    if perfil.estado_cuenta != EstadoCuentaJugador.VERIFICADO:
        raise ValidationError('El usuario no esta habilitado para apostar.')


def obtener_odds_activa(seleccion):
    return seleccion.historial_odds.filter(activa=True).order_by('-numero_version').first()


def validar_apuesta_simple(seleccion, odds_activa, stake, usuario=None):
    mercado = seleccion.mercado
    evento = mercado.evento

    if evento.estado_evento not in {EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO}:
        raise ValidationError('El evento no esta disponible para nuevas apuestas.')

    if evento.estado_evento == EstadoEvento.PROGRAMADO and evento.inicia_en <= timezone.now():
        raise ValidationError('No se puede apostar sobre un evento que ya inicio.')

    if evento.estado_evento == EstadoEvento.EN_VIVO and not mercado.permite_in_play:
        raise ValidationError('El mercado no permite apuestas en vivo.')

    if seleccion.estado_seleccion != EstadoSeleccion.ACTIVA:
        raise ValidationError('La seleccion no esta activa para apostar.')

    if mercado.estado_mercado != EstadoMercado.ABIERTO:
        raise ValidationError('El mercado no esta abierto para apostar.')

    if odds_activa is None:
        raise ValidationError('La seleccion no tiene una cuota activa.')

    if stake < mercado.stake_minimo or stake > mercado.stake_maximo:
        raise ValidationError('El monto de la apuesta esta fuera de los limites del mercado.')


@transaction.atomic
def crear_apuesta_ticket(usuario, seleccion_ids, stake, idempotency_key=None):
    """
    Crea UNA apuesta (ticket) con una o múltiples selecciones.
    Si hay varias, es una combinada: odds_total = producto de todas las cuotas.
    Regla: máximo una selección por mercado en el ticket.
    """
    if idempotency_key:
        apuesta_existente = Apuesta.objects.filter(idempotency_key=idempotency_key).first()
        if apuesta_existente:
            return apuesta_existente

    stake = Decimal(stake)
    selecciones = list(
        SeleccionMercado.objects.select_related('mercado__evento')
        .filter(pk__in=seleccion_ids)
    )

    if not selecciones:
        raise ValidationError('No se encontraron selecciones validas.')

    validar_usuario_puede_apostar(usuario)

    # Validar cada seleccion y calcular odds combinada
    mercados_vistos = {}
    odds_total = Decimal('1')
    detalles_data = []

    for seleccion in selecciones:
        mid = seleccion.mercado_id

        # Una sola seleccion por mercado en el mismo ticket
        if mid in mercados_vistos:
            raise ValidationError(
                f'Solo puedes elegir una opcion del mercado "{seleccion.mercado.nombre}".'
            )
        mercados_vistos[mid] = True

        odds_activa = obtener_odds_activa(seleccion)
        validar_apuesta_simple(seleccion, odds_activa, stake, usuario=None)

        odds_total *= odds_activa.odds
        detalles_data.append((seleccion, odds_activa))

    tipo = TipoApuesta.SIMPLE if len(selecciones) == 1 else TipoApuesta.COMBINADA

    apuesta = Apuesta.objects.create(
        usuario=usuario,
        tipo_apuesta=tipo,
        stake=stake,
        odds_total=odds_total,
        payout_potencial=stake * odds_total,
        idempotency_key=idempotency_key,
    )

    for seleccion, odds_activa in detalles_data:
        DetalleApuesta.objects.create(
            apuesta=apuesta,
            seleccion=seleccion,
            odds_snapshot=odds_activa.odds,
            version_odds=odds_activa.numero_version,
        )

    transaccion_bloqueo = bloquear_stake(
        usuario=usuario,
        apuesta_id=apuesta.id_apuesta,
        monto=stake,
        idempotency_key=idempotency_key or f'apuesta-{apuesta.id_apuesta}',
    )
    apuesta.aceptar(transaccion_bloqueo)
    apuesta.save(update_fields=['estado_apuesta', 'transaction_bloqueo', 'aceptada_en'])

    return apuesta


@transaction.atomic
def crear_apuesta_simple(usuario, seleccion_id, stake, idempotency_key=None):
    """Mantiene compatibilidad con la API REST existente."""
    return crear_apuesta_ticket(
        usuario=usuario,
        seleccion_ids=[seleccion_id],
        stake=stake,
        idempotency_key=idempotency_key,
    )


@transaction.atomic
def liquidar_apuesta(apuesta, resultado, liquidado_por=None, observacion=''):
    if apuesta.estado_apuesta != EstadoApuesta.ACCEPTED:
        raise ValidationError('Solo se pueden liquidar apuestas aceptadas.')

    if resultado == ResultadoLiquidacion.WON:
        estado_apuesta = EstadoApuesta.WON
        payout = apuesta.stake * apuesta.odds_total
        transaccion_liquidacion = liquidar_apuesta_ganada(
            usuario=apuesta.usuario,
            apuesta_id=apuesta.id_apuesta,
            stake=apuesta.stake,
            payout=payout,
        )
    elif resultado == ResultadoLiquidacion.LOST:
        estado_apuesta = EstadoApuesta.LOST
        payout = apuesta.stake * 0
        transaccion_liquidacion = liquidar_apuesta_perdida(
            usuario=apuesta.usuario,
            apuesta_id=apuesta.id_apuesta,
            stake=apuesta.stake,
        )
    elif resultado == ResultadoLiquidacion.VOID:
        estado_apuesta = EstadoApuesta.VOID
        payout = apuesta.stake
        transaccion_liquidacion = liquidar_apuesta_void(
            usuario=apuesta.usuario,
            apuesta_id=apuesta.id_apuesta,
            stake=apuesta.stake,
        )
    else:
        raise ValidationError('Resultado de liquidacion no soportado.')

    liquidado_en = timezone.now()
    liquidacion = LiquidacionApuesta.objects.create(
        apuesta=apuesta,
        resultado_liquidacion=resultado,
        payout=payout,
        transaction_liquidacion=transaccion_liquidacion,
        liquidado_por=liquidado_por,
        liquidado_en=liquidado_en,
        observacion=observacion,
    )

    apuesta.estado_apuesta = estado_apuesta
    apuesta.liquidada_en = liquidado_en
    apuesta.save(update_fields=['estado_apuesta', 'liquidada_en'])

    return liquidacion


def _resultado_liquidacion_desde_seleccion(seleccion):
    if seleccion.estado_seleccion == EstadoSeleccion.GANADORA:
        return ResultadoLiquidacion.WON
    if seleccion.estado_seleccion == EstadoSeleccion.PERDEDORA:
        return ResultadoLiquidacion.LOST
    if seleccion.estado_seleccion == EstadoSeleccion.ANULADA:
        return ResultadoLiquidacion.VOID
    raise ValidationError('La seleccion de la apuesta aun no tiene resultado liquidable.')


def _estado_detalle_desde_resultado(resultado):
    if resultado == ResultadoLiquidacion.WON:
        return EstadoDetalleApuesta.WON
    if resultado == ResultadoLiquidacion.LOST:
        return EstadoDetalleApuesta.LOST
    return EstadoDetalleApuesta.VOID


@transaction.atomic
def liquidar_apuestas_de_evento(evento, liquidado_por=None, observacion='Liquidacion automatica por resultado de evento.'):
    evento_id = evento.pk if hasattr(evento, 'pk') else evento
    apuesta_ids = (
        Apuesta.objects.filter(
            estado_apuesta=EstadoApuesta.ACCEPTED,
            detalles__seleccion__mercado__evento_id=evento_id,
        )
        .values_list('pk', flat=True)
        .distinct()
    )
    apuestas = (
        Apuesta.objects.select_for_update()
        .filter(pk__in=apuesta_ids)
        .prefetch_related('detalles__seleccion')
    )

    liquidaciones = []
    for apuesta in apuestas:
        detalles = list(apuesta.detalles.all())

        if len(detalles) == 1:
            resultado = _resultado_liquidacion_desde_seleccion(detalles[0].seleccion)
        else:
            # Combinada: pierde si cualquier seleccion pierde; anula si todas anuladas; gana si el resto gana
            resultados = [_resultado_liquidacion_desde_seleccion(d.seleccion) for d in detalles]
            if any(r == ResultadoLiquidacion.LOST for r in resultados):
                resultado = ResultadoLiquidacion.LOST
            elif all(r == ResultadoLiquidacion.VOID for r in resultados):
                resultado = ResultadoLiquidacion.VOID
            else:
                resultado = ResultadoLiquidacion.WON

        liquidacion = liquidar_apuesta(
            apuesta=apuesta,
            resultado=resultado,
            liquidado_por=liquidado_por,
            observacion=observacion,
        )
        for detalle in detalles:
            resultado_detalle = _resultado_liquidacion_desde_seleccion(detalle.seleccion)
            detalle.estado_detalle = _estado_detalle_desde_resultado(resultado_detalle)
            detalle.resultada_en = liquidacion.liquidado_en
            detalle.save(update_fields=['estado_detalle', 'resultada_en'])
        liquidaciones.append(liquidacion)

    return liquidaciones
