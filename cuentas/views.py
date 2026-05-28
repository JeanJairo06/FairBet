from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
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


class CuentasView(LoginRequiredMixin, TemplateView):
    template_name = 'cuentas/cuentas.html'

    def dispatch(self, request, *args, **kwargs):
        self.can_admin_accounts = self._can_admin_accounts(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_form = CuentaSearchForm(self.request.GET or None)

        context.update(
            {
                'administrador_form': kwargs.get('administrador_form') or AdministradorRegistroForm(),
                'operador_form': kwargs.get('operador_form') or OperadorRegistroForm(),
                'jugador_form': kwargs.get('jugador_form') or JugadorRegistroForm(),
                'self_profile_form': kwargs.get('self_profile_form') or self._get_self_profile_form(),
                'search_form': search_form,
                'usuarios': self._get_usuarios(search_form),
                'can_admin_accounts': self.can_admin_accounts,
                'assignable_roles': get_admin_assignable_roles(self.request.user),
                'estados_kyc': EstadoCuentaJugador.choices,
                'stats': self._build_stats(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')

        handlers = {
            'create_admin': self._handle_create_admin,
            'create_operator': self._handle_create_operator,
            'create_player': self._handle_create_player,
            'update_account': self._handle_update_account,
            'delete_account': self._handle_delete_account,
            'update_self_profile': self._handle_update_self_profile,
        }

        handler = handlers.get(action)
        if handler is None:
            messages.error(request, 'La accion solicitada no es valida.')
            return redirect('cuentas:cuentas')

        return handler(request)

    def _handle_create_admin(self, request):
        if not self.can_admin_accounts:
            messages.error(request, 'Solo administradores pueden crear cuentas administrativas.')
            return redirect('cuentas:cuentas')

        form = AdministradorRegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f'Administrador interno {user.username} creado con permisos limitados.',
            )
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa los datos del formulario de administrador.')
        return self.render_to_response(self.get_context_data(administrador_form=form))

    def _handle_create_operator(self, request):
        if not self.can_admin_accounts:
            messages.error(request, 'Solo administradores pueden crear operadores.')
            return redirect('cuentas:cuentas')

        form = OperadorRegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Operador {user.username} creado correctamente.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa los datos del formulario de operador.')
        return self.render_to_response(self.get_context_data(operador_form=form))

    def _handle_create_player(self, request):
        if not self.can_admin_accounts:
            messages.error(request, 'Solo administradores pueden crear jugadores.')
            return redirect('cuentas:cuentas')

        form = JugadorRegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Jugador {user.username} creado con perfil KYC.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa los datos del formulario de jugador.')
        return self.render_to_response(self.get_context_data(jugador_form=form))

    def _handle_update_account(self, request):
        if not self.can_admin_accounts:
            messages.error(request, 'Solo administradores pueden editar cuentas.')
            return redirect('cuentas:cuentas')

        target_user = get_object_or_404(Usuario, pk=request.POST.get('user_id'))
        form = CuentaAdminUpdateForm(
            request.POST,
            current_user=request.user,
            target_user=target_user,
        )

        if form.is_valid():
            form.apply()
            messages.success(request, f'Cuenta {target_user.username} actualizada correctamente.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'No se pudo actualizar la cuenta. Revisa valores duplicados o permisos.')
        return redirect('cuentas:cuentas')

    def _handle_delete_account(self, request):
        if not self.can_admin_accounts:
            messages.error(request, 'Solo administradores pueden eliminar cuentas.')
            return redirect('cuentas:cuentas')

        target_user = get_object_or_404(Usuario, pk=request.POST.get('user_id'))
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

    def _handle_update_self_profile(self, request):
        perfil = getattr(request.user, 'perfil_jugador', None)
        if perfil is None:
            messages.error(request, 'Tu cuenta no tiene un perfil de jugador editable.')
            return redirect('cuentas:cuentas')

        form = PerfilJugadorSelfForm(request.POST, instance=perfil)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tus datos personales fueron actualizados.')
            return redirect('cuentas:cuentas')

        messages.error(request, 'Revisa tus datos personales.')
        return self.render_to_response(self.get_context_data(self_profile_form=form))

    def _can_admin_accounts(self, user):
        if not user.is_authenticated:
            return False

        return user.is_staff or user.is_superuser or user.rol == RolUsuario.ADMIN

    def _get_self_profile_form(self):
        perfil = getattr(self.request.user, 'perfil_jugador', None)
        if perfil is None:
            return None
        return PerfilJugadorSelfForm(instance=perfil)

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
