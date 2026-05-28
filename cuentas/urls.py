from django.urls import path

from cuentas.views import (
    CrearUsuarioView,
    CuentasView,
    EditarCuentaView,
    EliminarCuentaView,
    PerfilJugadorView,
)


app_name = 'cuentas'

urlpatterns = [
    path('', CuentasView.as_view(), name='cuentas'),
    path('crear/usuario/', CrearUsuarioView.as_view(), name='crear_usuario'),
    path('<int:pk>/editar/', EditarCuentaView.as_view(), name='editar_cuenta'),
    path('<int:pk>/eliminar/', EliminarCuentaView.as_view(), name='eliminar_cuenta'),
    path('perfil/', PerfilJugadorView.as_view(), name='perfil_jugador'),
]
