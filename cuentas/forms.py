from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from core.choices import EstadoCuentaJugador, RolUsuario
from cuentas.models import PerfilJugador, Usuario
from cuentas.services import get_adult_date_limit, resolve_kyc_status


def _decorate_fields(fields):
    for field in fields.values():
        field.widget.attrs.setdefault('class', 'account-form__input')
    return fields


def get_admin_assignable_roles(user):
    if user and user.is_authenticated and user.is_superuser:
        return RolUsuario.choices

    return (
        (RolUsuario.PLAYER, RolUsuario.PLAYER.label),
        (RolUsuario.OPERATOR, RolUsuario.OPERATOR.label),
        (RolUsuario.ADMIN, RolUsuario.ADMIN.label),
    )


class CuentaSearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=120)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['q'].widget.attrs.update(
            {
                'placeholder': 'Buscar usuario, correo, DNI o rol',
                'class': 'accounts-search__input',
            }
        )


class UsuarioRegistroForm(UserCreationForm):
    rol = forms.ChoiceField(label='Tipo de usuario', choices=())
    nombres = forms.CharField(max_length=150)
    apellidos = forms.CharField(max_length=150)
    dni = forms.CharField(max_length=8, required=False)
    fecha_nacimiento = forms.DateField(
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    telefono = forms.CharField(max_length=30, required=False)

    class Meta:
        model = Usuario
        fields = (
            'rol',
            'username',
            'email',
            'nombres',
            'apellidos',
            'dni',
            'fecha_nacimiento',
            'telefono',
            'password1',
            'password2',
        )

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_user = current_user
        self.fields['rol'].choices = get_admin_assignable_roles(current_user)
        _decorate_fields(self.fields)
        self.fields['fecha_nacimiento'].widget.attrs['max'] = get_adult_date_limit().isoformat()
        self.fields['rol'].widget.attrs['data-role-select'] = 'true'
        self.fields['username'].widget.attrs.setdefault('placeholder', 'usuario_demo')
        self.fields['email'].widget.attrs.setdefault('placeholder', 'usuario@fairbet.local')
        self.fields['nombres'].widget.attrs.setdefault('placeholder', 'Nombres')
        self.fields['apellidos'].widget.attrs.setdefault('placeholder', 'Apellidos')
        self.fields['dni'].widget.attrs.setdefault('placeholder', '12345678')
        self.fields['telefono'].widget.attrs.setdefault('placeholder', '999999999')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe un usuario registrado con este correo.')
        return email

    def clean_rol(self):
        rol = self.cleaned_data['rol']
        if rol not in dict(get_admin_assignable_roles(self.current_user)):
            raise forms.ValidationError('No tienes permisos para asignar ese rol.')
        return rol

    def clean_dni(self):
        dni = self.cleaned_data.get('dni', '').strip()
        if dni and PerfilJugador.objects.filter(dni=dni).exists():
            raise forms.ValidationError('Ya existe un perfil registrado con este DNI.')
        return dni

    def clean(self):
        cleaned_data = super().clean()
        rol = cleaned_data.get('rol')
        dni = cleaned_data.get('dni')
        fecha_nacimiento = cleaned_data.get('fecha_nacimiento')

        if rol == RolUsuario.PLAYER:
            if not dni:
                self.add_error('dni', 'El DNI es obligatorio para registrar jugadores.')
            if not fecha_nacimiento:
                self.add_error(
                    'fecha_nacimiento',
                    'La fecha de nacimiento es obligatoria para registrar jugadores.',
                )
            if dni and fecha_nacimiento:
                kyc_result = resolve_kyc_status(dni, fecha_nacimiento)
                cleaned_data['kyc_result'] = kyc_result
                if not kyc_result.is_valid:
                    raise forms.ValidationError(kyc_result.message)

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['nombres']
        user.last_name = self.cleaned_data['apellidos']
        user.rol = self.cleaned_data['rol']
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()
            if user.rol == RolUsuario.PLAYER:
                kyc_result = self.cleaned_data.get('kyc_result')
                PerfilJugador.objects.create(
                    usuario=user,
                    nombres=self.cleaned_data['nombres'],
                    apellidos=self.cleaned_data['apellidos'],
                    dni=self.cleaned_data['dni'],
                    fecha_nacimiento=self.cleaned_data['fecha_nacimiento'],
                    telefono=self.cleaned_data.get('telefono', ''),
                    estado_cuenta=(
                        kyc_result.estado_cuenta
                        if kyc_result
                        else EstadoCuentaJugador.PENDIENTE_VERIFICACION
                    ),
                    kyc_verificado_en=(
                        None
                        if not kyc_result or not kyc_result.is_valid
                        else timezone.now()
                    ),
                )

        return user


class CuentaAdminUpdateForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    nombres = forms.CharField(max_length=150, required=False)
    apellidos = forms.CharField(max_length=150, required=False)
    dni = forms.CharField(max_length=8, required=False)
    fecha_nacimiento = forms.DateField(
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    telefono = forms.CharField(max_length=30, required=False)
    is_active = forms.BooleanField(required=False)
    is_staff = forms.BooleanField(required=False)
    is_superuser = forms.BooleanField(required=False)
    estado_cuenta = forms.ChoiceField(choices=EstadoCuentaJugador.choices, required=False)
    password1 = forms.CharField(
        label='Nueva contrasena',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Confirmar contrasena',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, current_user=None, target_user=None, **kwargs):
        self.current_user = current_user
        self.target_user = target_user
        super().__init__(*args, **kwargs)
        if current_user and not current_user.is_superuser:
            self.fields['is_staff'].widget.attrs['disabled'] = 'disabled'
            self.fields['is_superuser'].widget.attrs['disabled'] = 'disabled'
        self.fields['fecha_nacimiento'].widget.attrs['max'] = get_adult_date_limit().isoformat()
        self.fields['password1'].widget.attrs.setdefault('placeholder', 'Opcional')
        self.fields['password2'].widget.attrs.setdefault('placeholder', 'Repite la nueva contrasena')
        _decorate_fields(
            {
                name: field
                for name, field in self.fields.items()
                if name not in {'is_active', 'is_staff', 'is_superuser'}
            }
        )

    def _is_protected_admin(self):
        return bool(
            self.current_user
            and self.target_user
            and self.target_user.is_superuser
            and (self.current_user.pk == self.target_user.pk or not self.current_user.is_superuser)
        )

    def _can_manage_admin_permissions(self):
        return bool(
            self.current_user
            and self.current_user.is_superuser
            and not self._is_protected_admin()
        )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        qs = Usuario.objects.filter(username=username)
        if self.target_user:
            qs = qs.exclude(pk=self.target_user.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este nombre.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        qs = Usuario.objects.filter(email=email)
        if self.target_user:
            qs = qs.exclude(pk=self.target_user.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get('dni', '').strip()
        if not dni:
            return dni

        qs = PerfilJugador.objects.filter(dni=dni)
        perfil = getattr(self.target_user, 'perfil_jugador', None)
        if perfil:
            qs = qs.exclude(pk=perfil.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un perfil registrado con este DNI.')
        return dni

    def clean(self):
        cleaned_data = super().clean()
        if not self.target_user:
            return cleaned_data

        if self._is_protected_admin():
            cleaned_data['is_active'] = self.target_user.is_active
            cleaned_data['is_staff'] = self.target_user.is_staff
            cleaned_data['is_superuser'] = self.target_user.is_superuser
        elif self.target_user.rol == RolUsuario.ADMIN and not self._can_manage_admin_permissions():
            cleaned_data['is_active'] = self.target_user.is_active
            cleaned_data['is_staff'] = self.target_user.is_staff
            cleaned_data['is_superuser'] = self.target_user.is_superuser

        if self.target_user.pk == self.current_user.pk and not cleaned_data.get('is_active'):
            self.add_error('is_active', 'No puedes desactivar tu propia cuenta.')

        if not self._can_manage_admin_permissions():
            cleaned_data['is_staff'] = self.target_user.is_staff
            cleaned_data['is_superuser'] = self.target_user.is_superuser

        if self.target_user.rol != RolUsuario.ADMIN:
            cleaned_data['is_staff'] = False
            cleaned_data['is_superuser'] = False

        if self.target_user.pk == self.current_user.pk and not cleaned_data.get('is_superuser'):
            cleaned_data['is_superuser'] = self.target_user.is_superuser

        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 or password2:
            if self.target_user.pk != self.current_user.pk:
                self.add_error('password1', 'Solo puedes cambiar la contrasena de tu propia cuenta.')
            elif password1 != password2:
                self.add_error('password2', 'Las contrasenas no coinciden.')
            else:
                try:
                    validate_password(password1, self.target_user)
                except DjangoValidationError as exc:
                    self.add_error('password1', exc)

        perfil = getattr(self.target_user, 'perfil_jugador', None)
        if perfil:
            if not cleaned_data.get('dni'):
                self.add_error('dni', 'El DNI es obligatorio para jugadores.')
            if not cleaned_data.get('fecha_nacimiento'):
                self.add_error(
                    'fecha_nacimiento',
                    'La fecha de nacimiento es obligatoria para jugadores.',
                )
            if cleaned_data.get('dni') and cleaned_data.get('fecha_nacimiento'):
                kyc_result = resolve_kyc_status(
                    cleaned_data['dni'],
                    cleaned_data['fecha_nacimiento'],
                )
                if not kyc_result.is_valid:
                    raise forms.ValidationError(kyc_result.message)

        return cleaned_data

    def apply(self):
        user = self.target_user
        update_fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'is_active',
            'is_staff',
            'is_superuser',
        ]
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('nombres', '')
        user.last_name = self.cleaned_data.get('apellidos', '')
        user.is_active = self.cleaned_data['is_active']
        user.is_staff = self.cleaned_data['is_staff']
        user.is_superuser = self.cleaned_data['is_superuser']
        if user.pk == self.current_user.pk and self.cleaned_data.get('password1'):
            user.set_password(self.cleaned_data['password1'])
            update_fields.append('password')

        user.save(update_fields=update_fields)

        perfil = getattr(user, 'perfil_jugador', None)
        if perfil:
            perfil.nombres = self.cleaned_data.get('nombres', '')
            perfil.apellidos = self.cleaned_data.get('apellidos', '')
            perfil.dni = self.cleaned_data['dni']
            perfil.fecha_nacimiento = self.cleaned_data['fecha_nacimiento']
            perfil.telefono = self.cleaned_data.get('telefono', '')
            if self.cleaned_data.get('estado_cuenta'):
                perfil.estado_cuenta = self.cleaned_data['estado_cuenta']
            if (
                perfil.estado_cuenta == EstadoCuentaJugador.VERIFICADO
                and perfil.kyc_verificado_en is None
            ):
                perfil.kyc_verificado_en = timezone.now()
            perfil.save(
                update_fields=[
                    'nombres',
                    'apellidos',
                    'dni',
                    'fecha_nacimiento',
                    'telefono',
                    'estado_cuenta',
                    'kyc_verificado_en',
                    'updated_at',
                ]
            )

        return user


class CuentaSelfUpdateForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    nombres = forms.CharField(max_length=150, required=False)
    apellidos = forms.CharField(max_length=150, required=False)
    dni = forms.CharField(max_length=8, required=False)
    fecha_nacimiento = forms.DateField(
        required=False,
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    telefono = forms.CharField(max_length=30, required=False)
    password1 = forms.CharField(
        label='Nueva contrasena',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Confirmar contrasena',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        _decorate_fields(self.fields)
        self.fields['fecha_nacimiento'].widget.attrs['max'] = get_adult_date_limit().isoformat()
        self.fields['password1'].widget.attrs.setdefault('placeholder', 'Opcional')
        self.fields['password2'].widget.attrs.setdefault('placeholder', 'Repite la nueva contrasena')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        qs = Usuario.objects.filter(username=username)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este nombre.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        qs = Usuario.objects.filter(email=email)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get('dni', '').strip()
        if not dni:
            return dni

        qs = PerfilJugador.objects.filter(dni=dni)
        perfil = getattr(self.user, 'perfil_jugador', None)
        if perfil:
            qs = qs.exclude(pk=perfil.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe un perfil registrado con este DNI.')
        return dni

    def clean(self):
        cleaned_data = super().clean()
        perfil = getattr(self.user, 'perfil_jugador', None)
        if perfil:
            if not cleaned_data.get('dni'):
                self.add_error('dni', 'El DNI es obligatorio para jugadores.')
            if not cleaned_data.get('fecha_nacimiento'):
                self.add_error(
                    'fecha_nacimiento',
                    'La fecha de nacimiento es obligatoria para jugadores.',
                )
            if cleaned_data.get('dni') and cleaned_data.get('fecha_nacimiento'):
                kyc_result = resolve_kyc_status(
                    cleaned_data['dni'],
                    cleaned_data['fecha_nacimiento'],
                )
                if not kyc_result.is_valid:
                    raise forms.ValidationError(kyc_result.message)

        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 or password2:
            if password1 != password2:
                self.add_error('password2', 'Las contrasenas no coinciden.')
            elif password1:
                try:
                    validate_password(password1, self.user)
                except DjangoValidationError as exc:
                    self.add_error('password1', exc)
        return cleaned_data

    def apply(self):
        user = self.user
        perfil = getattr(user, 'perfil_jugador', None)
        update_fields = ['username', 'email', 'first_name', 'last_name']

        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('nombres', '')
        user.last_name = self.cleaned_data.get('apellidos', '')

        if self.cleaned_data.get('password1'):
            user.set_password(self.cleaned_data['password1'])
            update_fields.append('password')

        user.save(update_fields=update_fields)

        if perfil:
            perfil.nombres = self.cleaned_data.get('nombres', '')
            perfil.apellidos = self.cleaned_data.get('apellidos', '')
            perfil.dni = self.cleaned_data['dni']
            perfil.fecha_nacimiento = self.cleaned_data['fecha_nacimiento']
            perfil.telefono = self.cleaned_data.get('telefono', '')
            perfil.save(
                update_fields=[
                    'nombres',
                    'apellidos',
                    'dni',
                    'fecha_nacimiento',
                    'telefono',
                    'updated_at',
                ]
            )

        return user


PerfilJugadorSelfForm = CuentaSelfUpdateForm


RegistroJugadorForm = UsuarioRegistroForm
CuentaRegistroForm = UsuarioRegistroForm
CuentaGestionForm = CuentaAdminUpdateForm
