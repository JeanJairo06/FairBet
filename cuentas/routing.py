from django.urls import re_path

from cuentas.consumers import UsuarioConsumer

websocket_urlpatterns = [
    re_path(r"ws/usuario/$", UsuarioConsumer.as_asgi()),
]
