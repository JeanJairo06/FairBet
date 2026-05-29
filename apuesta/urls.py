from django.urls import path

from apuesta.views import ApuestasWebView, MisApuestasWebView


app_name = 'apuesta'

urlpatterns = [
    path('', ApuestasWebView.as_view(), name='apuestas_web'),
    path('mis-apuestas/', MisApuestasWebView.as_view(), name='mis_apuestas_web'),
]
