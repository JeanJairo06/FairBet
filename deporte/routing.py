from django.urls import re_path

from deporte.consumers import EventoConsumer, ListaEventosConsumer

websocket_urlpatterns = [
    re_path(r"ws/eventos/(?P<id_evento>\d+)/$", EventoConsumer.as_asgi()),
    re_path(r"ws/eventos/$", ListaEventosConsumer.as_asgi()),
]
