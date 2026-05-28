from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from core.choices import EstadoCuentaJugador, RolUsuario
from cuentas.forms import (
    AdministradorRegistroForm,
    CuentaAdminUpdateForm,
    CuentaSearchForm,
    JugadorRegistroForm,
    OperadorRegistroForm,
    PerfilJugadorSelfForm,
    get_admin_assignable_roles,
)
from cuentas.models import Usuario


def can_admin_accounts(user):
    if not user.is_authenticated:
        return False

    return user.is_staff or user.is_superuser or user.rol == RolUsuario.ADMIN


class AdminAccountRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_admin_accounts(request.user):
            messages.error(request, 'Solo administradores pueden gestionar cuentas.')
            return redirect('cuentas:cuentas')

        return super().dispatch(request, *args, **kwargs)


class CuentasView(LoginRequiredMixin, TemplateView):
    template_name = 'cuentas/cuentas.html'

    def dispatch(self, request, *args, **kwargs):
        self.can_admin_accounts = can_admin_accounts(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_form = CuentaSearchForm(self.request.GET or None)

        context.update(
            {
                'search_form': search_form,
                'usuarios': self._get_usuarios(search_form),
                'can_admin_accounts': self.can_admin_accounts,
                'self_profile': getattr(self.request.user, 'perfil_jugador', None),
                'stats': self._build_stats(),
            }
        )
        return context

    def _get_usuarios(self, search_form):
        usuarios = Usuario.objects.select_related('perfil_jugador').order_by('-date_joined')

        if not self.can_admin_accounts:
            usuarios = usuarios.filter(pk=self.request.user.pk)

        if search_form.is_valid():
            q = search_form.cleaned_data.get('q', '').strip()
            if q:
                usuarios = usuarios.filter(
                    Q(username__icontains=q)
                    | Q(email__icontains=q)
                    | Q(rol__icontains=q)
                    | Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(perfil_jugador__dni__icontains=q)
                    | Q(perfil_jugador__nombres__icontains=q)
                    | Q(perfil_jugador__apellidos__icontains=q)
                )

        return usuarios

    def _build_stats(self):
        usuarios = Usuario.objects.select_related('perfil_jugador')

        if not self.can_admin_accounts:
            usuarios = usuarios.filter(pk=self.request.user.pk)

        aggregate = usuarios.aggregate(
            total=Count('id_usuario'),
            jugadores=Count('id_usuario', filter=Q(rol=RolUsuario.PLAYER)),
            operadores=Count('id_usuario', filter=Q(rol=RolUsuario.OPERATOR)),
            administradores=Count('id_usuario', filter=Q(rol=RolUsuario.ADMIN)),
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
            'jugadores': aggregate['jugadores'] or 0,
            'operadores': aggregate['operadores'] or 0,
            'administradores': aggregate['administradores'] or 0,
            'verificados': aggregate['verificados'] or 0,
            'pendientes': aggregate['pendientes'] or 0,
            'bloqueados': aggregate['bloqueados'] or 0,
            'autoexcluidos': aggregate['autoexcluidos'] or 0,
        }


class CrearCuentaBaseView(AdminAccountRequiredMixin, TemplateView):
    form_class = None
    success_message = ''
    success_url = reverse_lazy('cuentas:cuentas')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = kwargs.get('form') or self.form_class()
        return context

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)

        if form.is_valid():
            user = form.save()
            messages.success(request, self.success_message.format(username=user.username))
            return redirect(self.success_url)

        messages.error(request, 'Revisa los datos del formulario antes de continuar.')
        return self.render_to_response(self.get_context_data(form=form))


class CrearJugadorView(CrearCuentaBaseView):
    template_name = 'cuentas/crear_jugador.html'
    form_class = JugadorRegistroForm
    success_message = 'Jugador {username} creado con perfil KYC.'


class CrearOperadorView(CrearCuentaBaseView):
    template_name = 'cuentas/crear_operador.html'
    form_class = OperadorRegistroForm
    success_message = 'Operador {username} creado correctamente.'


class CrearAdminView(CrearCuentaBaseView):
    template_name = 'cuentas/crear_admin.html'
    form_class = AdministradorRegistroForm
    success_message = 'Administrador interno {username} creado con permisos limitados.'


class EditarCuentaView(AdminAccountRequiredMixin, TemplateView):
    template_name = 'cuentas/editar_cuenta.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self._get_usuario()
        context.update(
            {
                'usuario': usuario,
                'form': kwargs.get('form') or self._build_form(usuario),
                'assignable_roles': get_admin_assignable_roles(self.request.user),
                'estados_kyc': EstadoCuentaJugador.choices,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        usuario = self._get_usuario()
        form = CuentaAdminUpdateForm(
            request.POST,
            current_user=request.user,
            target_user=usuario,
        )

        if form.is_valid():
            form.apply()
            messages.success(request, f'Cuenta {usuario.username} actualizada correctamente.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'No se pudo actualizar la cuenta. Revisa los datos ingresados.')
        return self.render_to_response(self.get_context_data(form=form))

    def _get_usuario(self):
        return get_object_or_404(
            Usuario.objects.select_related('perfil_jugador'),
            pk=self.kwargs['pk'],
        )

    def _build_form(self, usuario):
        perfil = getattr(usuario, 'perfil_jugador', None)
        return CuentaAdminUpdateForm(
            current_user=self.request.user,
            target_user=usuario,
            initial={
                'username': usuario.username,
                'email': usuario.email,
                'nombres': perfil.nombres if perfil else usuario.first_name,
                'apellidos': perfil.apellidos if perfil else usuario.last_name,
                'rol': usuario.rol,
                'is_active': usuario.is_active,
                'estado_cuenta': perfil.estado_cuenta if perfil else '',
            },
        )


class EliminarCuentaView(AdminAccountRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        target_user = get_object_or_404(Usuario, pk=kwargs['pk'])

        if target_user.pk == request.user.pk:
            messages.error(request, 'No puedes eliminar tu propia cuenta desde este modulo.')
            return redirect('cuentas:cuentas')

        username = target_user.username
        try:
            target_user.delete()
        except ProtectedError:
            target_user.is_active = False
            target_user.save(update_fields=['is_active'])
            messages.warning(
                request,
                f'La cuenta {username} tiene registros protegidos; se desactivo en lugar de eliminarse.',
            )
            return redirect('cuentas:cuentas')

        messages.success(request, f'Cuenta {username} eliminada correctamente.')
        return redirect('cuentas:cuentas')


class PerfilJugadorView(LoginRequiredMixin, TemplateView):
    template_name = 'cuentas/perfil_jugador.html'

    def dispatch(self, request, *args, **kwargs):
        if getattr(request.user, 'perfil_jugador', None) is None:
            messages.error(request, 'Tu cuenta no tiene un perfil de jugador editable.')
            return redirect('cuentas:cuentas')

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = kwargs.get('form') or PerfilJugadorSelfForm(
            instance=self.request.user.perfil_jugador
        )
        return context

    def post(self, request, *args, **kwargs):
        form = PerfilJugadorSelfForm(request.POST, instance=request.user.perfil_jugador)

        if form.is_valid():
            form.save()
            messages.success(request, 'Tus datos personales fueron actualizados.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa tus datos personales.')
        return self.render_to_response(self.get_context_data(form=form))
