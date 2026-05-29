from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from core.choices import EstadoCuentaJugador, RolUsuario
from cuentas.forms import (
    CuentaAdminUpdateForm,
    CuentaSelfUpdateForm,
    CuentaSearchForm,
    UsuarioRegistroForm,
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
                'self_user': self.request.user,
                'self_can_edit': self.request.user.is_authenticated,
                'stats': self._build_stats() if self.can_admin_accounts else None,
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


class CrearUsuarioView(AdminAccountRequiredMixin, TemplateView):
    template_name = 'cuentas/crear_usuario.html'
    success_url = reverse_lazy('cuentas:cuentas')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = kwargs.get('form') or UsuarioRegistroForm(
            current_user=self.request.user
        )
        return context

    def post(self, request, *args, **kwargs):
        form = UsuarioRegistroForm(request.POST, current_user=request.user)

        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f'Usuario {user.username} creado correctamente como {user.get_rol_display()}.',
            )
            return redirect(self.success_url)

        messages.error(request, 'Revisa los datos del formulario antes de continuar.')
        return self.render_to_response(self.get_context_data(form=form))


class EditarCuentaView(AdminAccountRequiredMixin, TemplateView):
    template_name = 'cuentas/editar_cuenta.html'

    def dispatch(self, request, *args, **kwargs):
        self.target_user = self._get_usuario()
        if self._is_protected_admin(self.target_user) and self.target_user.pk != request.user.pk:
            messages.error(request, 'La cuenta principal esta protegida y no puede ser editada por administradores secundarios.')
            return redirect('cuentas:cuentas')

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.target_user
        context.update(
            {
                'usuario': usuario,
                'form': kwargs.get('form') or self._build_form(usuario),
                'estados_kyc': EstadoCuentaJugador.choices,
                'is_protected_admin': self._is_protected_admin(usuario),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        usuario = self.target_user
        form = CuentaAdminUpdateForm(
            request.POST,
            current_user=request.user,
            target_user=usuario,
        )

        if form.is_valid():
            form.apply()
            if usuario.pk == request.user.pk and form.cleaned_data.get('password1'):
                update_session_auth_hash(request, request.user)
            messages.success(request, f'Cuenta {usuario.username} actualizada correctamente.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'No se pudo actualizar la cuenta. Revisa los datos ingresados.')
        return self.render_to_response(self.get_context_data(form=form))

    def _get_usuario(self):
        if hasattr(self, 'target_user'):
            return self.target_user

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
                'dni': perfil.dni if perfil else '',
                'fecha_nacimiento': perfil.fecha_nacimiento.isoformat()
                if perfil and perfil.fecha_nacimiento
                else '',
                'telefono': perfil.telefono if perfil else '',
                'is_active': usuario.is_active,
                'is_staff': usuario.is_staff,
                'is_superuser': usuario.is_superuser,
                'estado_cuenta': perfil.estado_cuenta if perfil else '',
            },
        )

    def _is_protected_admin(self, usuario):
        return (
            usuario.is_superuser
            and (usuario.pk == self.request.user.pk or not self.request.user.is_superuser)
        )


class PerfilJugadorView(LoginRequiredMixin, TemplateView):
    template_name = 'cuentas/perfil_jugador.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        perfil = getattr(self.request.user, 'perfil_jugador', None)
        context['form'] = kwargs.get('form') or CuentaSelfUpdateForm(
            user=self.request.user,
            initial={
                'username': self.request.user.username,
                'email': self.request.user.email,
                'nombres': perfil.nombres if perfil else self.request.user.first_name,
                'apellidos': perfil.apellidos if perfil else self.request.user.last_name,
                'dni': perfil.dni if perfil else '',
                'fecha_nacimiento': perfil.fecha_nacimiento.isoformat()
                if perfil and perfil.fecha_nacimiento
                else '',
                'telefono': perfil.telefono if perfil else '',
            },
        )
        context['perfil'] = perfil
        return context

    def post(self, request, *args, **kwargs):
        form = CuentaSelfUpdateForm(request.POST, user=request.user)

        if form.is_valid():
            form.apply()
            if form.cleaned_data.get('password1'):
                update_session_auth_hash(request, request.user)
            messages.success(request, 'Tus datos personales fueron actualizados.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa tus datos personales.')
        return self.render_to_response(self.get_context_data(form=form))
