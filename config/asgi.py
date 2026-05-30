"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_asgi_app = get_asgi_application()

import deporte.routing  # noqa: E402 — importar después de setup de Django

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': AuthMiddlewareStack(
            URLRouter(deporte.routing.websocket_urlpatterns)
        ),
    }
)
