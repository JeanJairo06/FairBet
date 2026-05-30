from django.urls import re_path

from deporte.consumers import EventoConsumer

websocket_urlpatterns = [
    re_path(r"ws/eventos/(?P<id_evento>\d+)/$", EventoConsumer.as_asgi()),
]
