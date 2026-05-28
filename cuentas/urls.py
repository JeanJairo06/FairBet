from django.urls import path

from cuentas.views import CuentasView


app_name = 'cuentas'

urlpatterns = [
    path('', CuentasView.as_view(), name='cuentas'),
]
