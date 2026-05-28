from django import forms
from django.contrib.auth.forms import UserCreationForm
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


class OperadorRegistroForm(UserCreationForm):
    target_role = RolUsuario.OPERATOR
    username_placeholder = 'operador_demo'
    email_placeholder = 'operador@fairbet.local'

    nombres = forms.CharField(max_length=150)
    apellidos = forms.CharField(max_length=150)

    class Meta:
        model = Usuario
        fields = (
            'username',
            'email',
            'nombres',
            'apellidos',
            'password1',
            'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _decorate_fields(self.fields)
        self.fields['username'].widget.attrs.setdefault('placeholder', self.username_placeholder)
        self.fields['email'].widget.attrs.setdefault('placeholder', self.email_placeholder)
        self.fields['nombres'].widget.attrs.setdefault('placeholder', 'Nombres')
        self.fields['apellidos'].widget.attrs.setdefault('placeholder', 'Apellidos')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe un usuario registrado con este correo.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['nombres']
        user.last_name = self.cleaned_data['apellidos']
        user.rol = self.target_role
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()

        return user


class AdministradorRegistroForm(OperadorRegistroForm):
    target_role = RolUsuario.ADMIN
    username_placeholder = 'admin_interno'
    email_placeholder = 'admin@fairbet.local'


class JugadorRegistroForm(UserCreationForm):
    nombres = forms.CharField(max_length=150)
    apellidos = forms.CharField(max_length=150)
    dni = forms.CharField(max_length=8)
    fecha_nacimiento = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    telefono = forms.CharField(max_length=30, required=False)

    class Meta:
        model = Usuario
        fields = (
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _decorate_fields(self.fields)
        self.fields['fecha_nacimiento'].widget.attrs['max'] = get_adult_date_limit().isoformat()
        self.fields['username'].widget.attrs.setdefault('placeholder', 'jugador_demo')
        self.fields['email'].widget.attrs.setdefault('placeholder', 'jugador@fairbet.local')
        self.fields['nombres'].widget.attrs.setdefault('placeholder', 'Nombres')
        self.fields['apellidos'].widget.attrs.setdefault('placeholder', 'Apellidos')
        self.fields['dni'].widget.attrs.setdefault('placeholder', '12345672')
        self.fields['telefono'].widget.attrs.setdefault('placeholder', '999999999')

    def clean_dni(self):
        dni = self.cleaned_data['dni'].strip()
        if PerfilJugador.objects.filter(dni=dni).exists():
            raise forms.ValidationError('Ya existe un perfil registrado con este DNI.')
        return dni

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe un usuario registrado con este correo.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        dni = cleaned_data.get('dni')
        fecha_nacimiento = cleaned_data.get('fecha_nacimiento')

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
        user.rol = RolUsuario.PLAYER

        if commit:
            user.save()
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
    rol = forms.ChoiceField(choices=())
    is_active = forms.BooleanField(required=False)
    estado_cuenta = forms.ChoiceField(choices=EstadoCuentaJugador.choices, required=False)

    def __init__(self, *args, current_user=None, target_user=None, **kwargs):
        self.current_user = current_user
        self.target_user = target_user
        super().__init__(*args, **kwargs)
        self.fields['rol'].choices = get_admin_assignable_roles(current_user)
        _decorate_fields(
            {
                name: field
                for name, field in self.fields.items()
                if name != 'is_active'
            }
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

    def clean_rol(self):
        rol = self.cleaned_data['rol']
        if rol not in dict(get_admin_assignable_roles(self.current_user)):
            raise forms.ValidationError('No tienes permisos para asignar ese rol.')
        return rol

    def apply(self):
        user = self.target_user
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('nombres', '')
        user.last_name = self.cleaned_data.get('apellidos', '')
        user.rol = self.cleaned_data['rol']
        user.is_active = self.cleaned_data['is_active']
        user.save(update_fields=['username', 'email', 'first_name', 'last_name', 'rol', 'is_active'])

        perfil = getattr(user, 'perfil_jugador', None)
        if perfil:
            perfil.nombres = self.cleaned_data.get('nombres', '')
            perfil.apellidos = self.cleaned_data.get('apellidos', '')
            if self.cleaned_data.get('estado_cuenta'):
                perfil.estado_cuenta = self.cleaned_data['estado_cuenta']
            perfil.save(update_fields=['nombres', 'apellidos', 'estado_cuenta', 'updated_at'])

        return user


class PerfilJugadorSelfForm(forms.ModelForm):
    class Meta:
        model = PerfilJugador
        fields = ('nombres', 'apellidos', 'telefono')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _decorate_fields(self.fields)


RegistroJugadorForm = JugadorRegistroForm
CuentaRegistroForm = JugadorRegistroForm
CuentaGestionForm = CuentaAdminUpdateForm
