from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from core.choices import EstadoCuentaJugador, RolUsuario


def _deny(request, message, redirect_url, raise_exception):
    if raise_exception:
        raise PermissionDenied(message)
    messages.error(request, message)
    return redirect(redirect_url)


def login_required_view(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url=None):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                return func(request, *args, **kwargs)
            return redirect_to_login(
                request.get_full_path(),
                login_url or settings.LOGIN_URL,
                redirect_field_name,
            )

        return wrapper

    if view_func is None:
        return decorator
    return decorator(view_func)


def role_required(*roles, redirect_url='home', message=None, raise_exception=False):
    allowed_roles = set(roles)

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL, REDIRECT_FIELD_NAME)

            if request.user.is_superuser or request.user.rol in allowed_roles:
                return func(request, *args, **kwargs)

            return _deny(
                request,
                message or 'No tienes permisos para acceder a esta seccion.',
                redirect_url,
                raise_exception,
            )

        return wrapper

    return decorator


def staff_required(view_func=None, redirect_url='home', raise_exception=False):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL, REDIRECT_FIELD_NAME)

            if request.user.is_staff or request.user.is_superuser:
                return func(request, *args, **kwargs)

            return _deny(
                request,
                'Solo el personal autorizado puede acceder a esta seccion.',
                redirect_url,
                raise_exception,
            )

        return wrapper

    if view_func is None:
        return decorator
    return decorator(view_func)


def admin_required(view_func=None, redirect_url='home', raise_exception=False):
    decorator = role_required(
        RolUsuario.ADMIN,
        redirect_url=redirect_url,
        message='Solo administradores pueden acceder a esta seccion.',
        raise_exception=raise_exception,
    )
    if view_func is None:
        return decorator
    return decorator(view_func)


def operator_required(view_func=None, redirect_url='home', raise_exception=False):
    decorator = role_required(
        RolUsuario.ADMIN,
        RolUsuario.OPERATOR,
        redirect_url=redirect_url,
        message='Solo operadores o administradores pueden acceder a esta seccion.',
        raise_exception=raise_exception,
    )
    if view_func is None:
        return decorator
    return decorator(view_func)


def player_required(view_func=None, redirect_url='home', raise_exception=False):
    decorator = role_required(
        RolUsuario.PLAYER,
        redirect_url=redirect_url,
        message='Solo jugadores pueden acceder a esta seccion.',
        raise_exception=raise_exception,
    )
    if view_func is None:
        return decorator
    return decorator(view_func)


def verified_player_required(view_func=None, redirect_url='home', raise_exception=False):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL, REDIRECT_FIELD_NAME)

            perfil = getattr(request.user, 'perfil_jugador', None)
            is_verified_player = (
                request.user.rol == RolUsuario.PLAYER
                and perfil is not None
                and perfil.estado_cuenta == EstadoCuentaJugador.VERIFICADO
            )

            if request.user.is_superuser or is_verified_player:
                return func(request, *args, **kwargs)

            return _deny(
                request,
                'Tu perfil de jugador debe estar verificado para acceder a esta seccion.',
                redirect_url,
                raise_exception,
            )

        return wrapper

    if view_func is None:
        return decorator
    return decorator(view_func)
