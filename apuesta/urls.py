from django.urls import path

from apuesta.views import ApuestaListCreateView


app_name = 'apuesta'

urlpatterns = [
    path('apuestas/', ApuestaListCreateView.as_view(), name='apuesta-list-create'),
]
