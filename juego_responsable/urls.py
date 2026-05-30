from django.urls import path
from juego_responsable.views import panel_juego_responsable_view

app_name = 'juego_responsable'

urlpatterns = [
    path('panel/', panel_juego_responsable_view, name='panel'),
]