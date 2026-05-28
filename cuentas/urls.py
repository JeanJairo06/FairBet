from django.urls import path

from cuentas.views import (
    CrearAdminView,
    CrearJugadorView,
    CrearOperadorView,
    CuentasView,
    EditarCuentaView,
    EliminarCuentaView,
    PerfilJugadorView,
)


app_name = 'cuentas'

urlpatterns = [
    path('', CuentasView.as_view(), name='cuentas'),
    path('crear/jugador/', CrearJugadorView.as_view(), name='crear_jugador'),
    path('crear/operador/', CrearOperadorView.as_view(), name='crear_operador'),
    path('crear/admin/', CrearAdminView.as_view(), name='crear_admin'),
    path('<int:pk>/editar/', EditarCuentaView.as_view(), name='editar_cuenta'),
    path('<int:pk>/eliminar/', EliminarCuentaView.as_view(), name='eliminar_cuenta'),
    path('perfil/', PerfilJugadorView.as_view(), name='perfil_jugador'),
]
