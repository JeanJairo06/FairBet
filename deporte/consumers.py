from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

from deporte.models import EventoDeportivo


def _nombre_grupo(id_evento):
    return f"evento_{id_evento}"


GRUPO_LISTA_EVENTOS = "lista_eventos"


class ListaEventosConsumer(AsyncJsonWebsocketConsumer):
    """Canal global: notifica cuando se crea, activa o finaliza un evento."""

    async def connect(self):
        await self.channel_layer.group_add(GRUPO_LISTA_EVENTOS, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GRUPO_LISTA_EVENTOS, self.channel_name)

    async def lista_eventos_cambio(self, event):
        await self.send_json(event)


class EventoConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.id_evento = self.scope["url_route"]["kwargs"]["id_evento"]
        self.grupo = _nombre_grupo(self.id_evento)

        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

        snapshot = await self._snapshot_odds()
        await self.send_json({"type": "snapshot", "data": snapshot})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.grupo, self.channel_name)

    # ── handlers de mensajes entrantes del channel layer ──────────────────

    async def odds_update(self, event):
        await self.send_json(event)

    async def mercado_estado(self, event):
        await self.send_json(event)

    async def evento_estado(self, event):
        await self.send_json(event)

    # ── helpers ───────────────────────────────────────────────────────────

    @database_sync_to_async
    def _snapshot_odds(self):
        try:
            evento = EventoDeportivo.objects.get(pk=self.id_evento)
        except EventoDeportivo.DoesNotExist:
            return {}

        mercados = []
        for mercado in evento.mercados.filter(estado_mercado="abierto").prefetch_related(
            "selecciones__historial_odds"
        ):
            selecciones = []
            for sel in mercado.selecciones.all():
                odds_activa = sel.historial_odds.filter(activa=True).order_by("-numero_version").first()
                selecciones.append(
                    {
                        "id_seleccion": sel.id_seleccion,
                        "codigo": sel.codigo_seleccion,
                        "nombre": sel.nombre,
                        "estado": sel.estado_seleccion,
                        "odds": str(odds_activa.odds) if odds_activa else None,
                        "version": odds_activa.numero_version if odds_activa else None,
                    }
                )
            mercados.append(
                {
                    "id_mercado": mercado.id_mercado,
                    "nombre": mercado.nombre,
                    "tipo": mercado.tipo_mercado,
                    "estado": mercado.estado_mercado,
                    "permite_in_play": mercado.permite_in_play,
                    "selecciones": selecciones,
                }
            )

        return {
            "id_evento": evento.id_evento,
            "estado_evento": evento.estado_evento,
            "marcador_local": evento.marcador_local,
            "marcador_visitante": evento.marcador_visitante,
            "mercados": mercados,
        }
