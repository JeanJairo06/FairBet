from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.views.generic import TemplateView

from core.choices import EstadoCuentaJugador, RolUsuario
from cuentas.forms import RegistroJugadorForm
from cuentas.models import Usuario


class CuentasView(LoginRequiredMixin, TemplateView):
    template_name = 'cuentas/cuentas.html'

    def dispatch(self, request, *args, **kwargs):
        self.can_manage_accounts = self._can_manage_accounts(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuarios = self._get_usuarios()

        context.update(
            {
                'form': kwargs.get('form') or RegistroJugadorForm(),
                'usuarios': usuarios,
                'q': self.request.GET.get('q', '').strip(),
                'can_manage_accounts': self.can_manage_accounts,
                'stats': self._build_stats(),
                'roles': RolUsuario.choices,
                'estados_kyc': EstadoCuentaJugador.choices,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        if not self.can_manage_accounts:
            messages.error(request, 'No tienes permisos para registrar cuentas de jugador.')
            return redirect('cuentas:cuentas')

        form = RegistroJugadorForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Cuenta de jugador {user.username} registrada y validada localmente.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa los datos del formulario de registro.')
        return self.render_to_response(self.get_context_data(form=form))

    def _can_manage_accounts(self, user):
        return user.is_staff or user.is_superuser or user.rol in {
            RolUsuario.ADMIN,
            RolUsuario.OPERATOR,
        }

    def _get_usuarios(self):
        usuarios = Usuario.objects.select_related('perfil_jugador').order_by('-date_joined')

        if not self.can_manage_accounts:
            usuarios = usuarios.filter(pk=self.request.user.pk)

        q = self.request.GET.get('q', '').strip()
        if q:
            usuarios = usuarios.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(perfil_jugador__dni__icontains=q)
                | Q(perfil_jugador__nombres__icontains=q)
                | Q(perfil_jugador__apellidos__icontains=q)
            )

        return usuarios

    def _build_stats(self):
        perfiles = Usuario.objects.select_related('perfil_jugador')

        if not self.can_manage_accounts:
            perfiles = perfiles.filter(pk=self.request.user.pk)

        aggregate = perfiles.aggregate(
            total=Count('id_usuario'),
            verificados=Count(
                'perfil_jugador',
                filter=Q(perfil_jugador__estado_cuenta=EstadoCuentaJugador.VERIFICADO),
            ),
            pendientes=Count(
                'perfil_jugador',
                filter=Q(perfil_jugador__estado_cuenta=EstadoCuentaJugador.PENDIENTE_VERIFICACION),
            ),
            bloqueados=Count(
                'perfil_jugador',
                filter=Q(perfil_jugador__estado_cuenta=EstadoCuentaJugador.BLOQUEADO),
            ),
            autoexcluidos=Count(
                'perfil_jugador',
                filter=Q(perfil_jugador__estado_cuenta=EstadoCuentaJugador.AUTOEXCLUIDO),
            ),
        )

        return {
            'total': aggregate['total'] or 0,
            'verificados': aggregate['verificados'] or 0,
            'pendientes': aggregate['pendientes'] or 0,
            'bloqueados': aggregate['bloqueados'] or 0,
            'autoexcluidos': aggregate['autoexcluidos'] or 0,
        }
