from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apuesta.models import Apuesta, DetalleApuesta
from billetera.models import TransaccionLedger
from core.choices import (
    EstadoMercado,
    EstadoSeleccion,
    EstadoTransaccionLedger,
    TipoApuesta,
    TipoTransaccionLedger,
)
from deporte.models import SeleccionMercado


def obtener_odds_activa(seleccion):
    return seleccion.historial_odds.filter(activa=True).order_by('-numero_version').first()


def validar_apuesta_simple(seleccion, odds_activa, stake):
    mercado = seleccion.mercado

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
    seleccion = SeleccionMercado.objects.select_related('mercado').get(pk=seleccion_id)
    odds_activa = obtener_odds_activa(seleccion)

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
