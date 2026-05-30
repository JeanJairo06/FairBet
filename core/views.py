from django.shortcuts import redirect
from django.views import View

from core.choices import RolUsuario


class HomeView(View):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        if request.user.is_superuser or request.user.rol in {RolUsuario.ADMIN, RolUsuario.OPERATOR}:
            return redirect('deporte:eventos_lista')

        return redirect('apuesta:apuestas_web')
