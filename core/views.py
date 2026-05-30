from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView

from core.choices import RolUsuario
from cuentas.forms import RegistroJugadorForm


class HomeView(View):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        if request.user.is_superuser or request.user.rol in {RolUsuario.ADMIN, RolUsuario.OPERATOR}:
            return redirect('deporte:eventos_lista')

        return redirect('apuesta:apuestas_web')


class RegistroJugadorView(FormView):
    template_name = 'registration/registro.html'
    form_class = RegistroJugadorForm
    success_url = reverse_lazy('registro_exitoso')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('cuentas:cuentas')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Cuenta creada correctamente. Ya puedes iniciar sesion.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Revisa los datos del formulario antes de continuar.')
        return super().form_invalid(form)


class RegistroExitosoView(TemplateView):
    template_name = 'registration/registro_exitoso.html'
