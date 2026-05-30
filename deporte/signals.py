import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

from deporte.models import EventoDeportivo, HistorialOdds, Mercado


def _nombre_grupo(id_evento):
    return f"evento_{id_evento}"


def _broadcast(id_evento, mensaje):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(_nombre_grupo(id_evento), mensaje)
    except Exception as exc:
        logger.warning("WebSocket broadcast falló (Redis no disponible?): %s", exc)


@receiver(post_save, sender=HistorialOdds)
def on_odds_guardada(sender, instance, created, **kwargs):
    if not created:
        return
    seleccion = instance.seleccion
    id_evento = seleccion.mercado.evento_id
    _broadcast(
        id_evento,
        {
            "type": "odds.update",
            "id_seleccion": seleccion.id_seleccion,
            "id_mercado": seleccion.mercado_id,
            "codigo": seleccion.codigo_seleccion,
            "odds": str(instance.odds),
            "version": instance.numero_version,
        },
    )


@receiver(post_save, sender=Mercado)
def on_mercado_guardado(sender, instance, **kwargs):
    _broadcast(
        instance.evento_id,
        {
            "type": "mercado.estado",
            "id_mercado": instance.id_mercado,
            "estado": instance.estado_mercado,
            "suspendido_hasta": (
                instance.suspendido_hasta.isoformat() if instance.suspendido_hasta else None
            ),
        },
    )


@receiver(post_save, sender=EventoDeportivo)
def on_evento_guardado(sender, instance, **kwargs):
    _broadcast(
        instance.id_evento,
        {
            "type": "evento.estado",
            "id_evento": instance.id_evento,
            "estado": instance.estado_evento,
            "marcador_local": instance.marcador_local,
            "marcador_visitante": instance.marcador_visitante,
        },
    )
