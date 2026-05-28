from django.urls import path

from cuentas.views import (
    ActualizarPermisosCuentaView,
    CrearUsuarioView,
    CuentasView,
    EditarCuentaView,
    PerfilJugadorView,
)


app_name = 'cuentas'

urlpatterns = [
    path('', CuentasView.as_view(), name='cuentas'),
    path('crear/usuario/', CrearUsuarioView.as_view(), name='crear_usuario'),
    path('<int:pk>/editar/', EditarCuentaView.as_view(), name='editar_cuenta'),
    path('<int:pk>/permisos/', ActualizarPermisosCuentaView.as_view(), name='actualizar_permisos'),
    path('perfil/', PerfilJugadorView.as_view(), name='perfil_jugador'),
]
