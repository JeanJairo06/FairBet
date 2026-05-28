from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apuesta.models import Apuesta, DetalleApuesta, LiquidacionApuesta
from billetera.models import TransaccionLedger
from core.choices import (
    EstadoApuesta,
    EstadoCuentaJugador,
    EstadoEvento,
    EstadoMercado,
    EstadoSeleccion,
    EstadoTransaccionLedger,
    ResultadoLiquidacion,
    TipoApuesta,
    TipoTransaccionLedger,
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


def validar_apuesta_simple(seleccion, odds_activa, stake):
    mercado = seleccion.mercado
    evento = mercado.evento

    if evento.estado_evento != EstadoEvento.PROGRAMADO:
        raise ValidationError('El evento no esta disponible para nuevas apuestas.')

    if evento.inicia_en <= timezone.now():
        raise ValidationError('No se puede apostar sobre un evento que ya inicio.')

    if seleccion.estado_seleccion != EstadoSeleccion.ACTIVA:
        raise ValidationError('La seleccion no esta activa para apostar.')

    if mercado.estado_mercado != EstadoMercado.ABIERTO:
        raise ValidationError('El mercado no esta abierto para apostar.')

    if odds_activa is None:
        raise ValidationError('La seleccion no tiene una cuota activa.')

    if stake < mercado.stake_minimo or stake > mercado.stake_maximo:
        raise ValidationError('El monto de la apuesta esta fuera de los limites del mercado.')


@transaction.atomic
def crear_apuesta_simple(usuario, seleccion_id, stake, idempotency_key=None):
    stake = Decimal(stake)
    seleccion = SeleccionMercado.objects.select_related('mercado__evento').get(pk=seleccion_id)
    odds_activa = obtener_odds_activa(seleccion)

    validar_usuario_puede_apostar(usuario)
    validar_apuesta_simple(seleccion, odds_activa, stake)

    odds_total = odds_activa.odds
    payout_potencial = stake * odds_total

    transaccion_bloqueo = TransaccionLedger.objects.create(
        usuario=usuario,
        tipo_transaccion=TipoTransaccionLedger.BLOQUEO_APUESTA,
        idempotency_key=f'bloqueo-{idempotency_key}' if idempotency_key else None,
        tipo_referencia='apuesta',
        estado=EstadoTransaccionLedger.COMPLETED,
    )

    apuesta = Apuesta.objects.create(
        usuario=usuario,
        tipo_apuesta=TipoApuesta.SIMPLE,
        stake=stake,
        odds_total=odds_total,
        payout_potencial=payout_potencial,
        idempotency_key=idempotency_key,
    )
    apuesta.aceptar(transaccion_bloqueo)
    apuesta.save(update_fields=['estado_apuesta', 'transaction_bloqueo', 'aceptada_en'])

    transaccion_bloqueo.id_referencia = str(apuesta.id_apuesta)
    transaccion_bloqueo.save(update_fields=['id_referencia'])

    DetalleApuesta.objects.create(
        apuesta=apuesta,
        seleccion=seleccion,
        odds_snapshot=odds_activa.odds,
        version_odds=odds_activa.numero_version,
    )

    return apuesta


@transaction.atomic
def liquidar_apuesta(apuesta, resultado, liquidado_por=None, observacion=''):
    if apuesta.estado_apuesta != EstadoApuesta.ACCEPTED:
        raise ValidationError('Solo se pueden liquidar apuestas aceptadas.')

    if resultado == ResultadoLiquidacion.WON:
        estado_apuesta = EstadoApuesta.WON
        payout = apuesta.stake * apuesta.odds_total
    elif resultado == ResultadoLiquidacion.LOST:
        estado_apuesta = EstadoApuesta.LOST
        payout = apuesta.stake * 0
    elif resultado == ResultadoLiquidacion.VOID:
        estado_apuesta = EstadoApuesta.VOID
        payout = apuesta.stake
    else:
        raise ValidationError('Resultado de liquidacion no soportado.')

    transaccion_liquidacion = TransaccionLedger.objects.create(
        usuario=apuesta.usuario,
        tipo_transaccion=TipoTransaccionLedger.LIQUIDACION,
        tipo_referencia='apuesta',
        id_referencia=str(apuesta.id_apuesta),
        estado=EstadoTransaccionLedger.COMPLETED,
    )

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
