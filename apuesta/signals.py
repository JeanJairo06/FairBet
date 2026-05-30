import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from apuesta.models import Apuesta
from cuentas.consumers import nombre_grupo_usuario

logger = logging.getLogger(__name__)


def _broadcast_usuario(user_id, mensaje):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(nombre_grupo_usuario(user_id), mensaje)
    except Exception as exc:
        logger.warning("WebSocket broadcast usuario falló: %s", exc)


@receiver(post_save, sender=Apuesta)
def on_apuesta_guardada(sender, instance, **kwargs):
    estados_finales = {"WON", "LOST", "VOID", "CASHED_OUT", "CANCELLED"}
    if instance.estado_apuesta not in estados_finales:
        return

    payout = None
    if hasattr(instance, "liquidacion"):
        payout = str(instance.liquidacion.payout)

    _broadcast_usuario(
        instance.usuario_id,
        {
            "type": "apuesta.liquidada",
            "id_apuesta": instance.id_apuesta,
            "estado": instance.estado_apuesta,
            "payout": payout,
            "odds_total": str(instance.odds_total),
            "stake": str(instance.stake),
        },
    )

    # Emitir también actualización de saldo para que el header se refresque
    _emitir_saldo(instance.usuario_id)


def _emitir_saldo(user_id):
    """Calcula el saldo actual y lo emite al canal del usuario."""
    try:
        from billetera.services.balance_service import calcular_saldo_usuario
        from cuentas.models import Usuario
        usuario = Usuario.objects.get(pk=user_id)
        saldo = calcular_saldo_usuario(usuario)
        _broadcast_usuario(
            user_id,
            {
                "type": "saldo.actualizado",
                "saldo": str(saldo),
            },
        )
    except Exception as exc:
        logger.warning("No se pudo emitir saldo: %s", exc)
