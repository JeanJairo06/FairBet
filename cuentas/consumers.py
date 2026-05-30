from channels.generic.websocket import AsyncJsonWebsocketConsumer


def nombre_grupo_usuario(user_id):
    return f"usuario_{user_id}"


class UsuarioConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.grupo = nombre_grupo_usuario(user.pk)
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "grupo"):
            await self.channel_layer.group_discard(self.grupo, self.channel_name)

    # ── handlers del channel layer ────────────────────────────────────────

    async def saldo_actualizado(self, event):
        await self.send_json(event)

    async def apuesta_liquidada(self, event):
        await self.send_json(event)
