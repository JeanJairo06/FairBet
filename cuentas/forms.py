from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.utils import timezone

from core.choices import EstadoCuentaJugador, RolUsuario
from cuentas.models import PerfilJugador, Usuario
from cuentas.services import resolve_kyc_status


class RegistroJugadorForm(UserCreationForm):
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
        placeholders = {
            'username': 'usuario_demo',
            'email': 'jugador@fairbet.local',
            'nombres': 'Nombres',
            'apellidos': 'Apellidos',
            'dni': '12345672',
            'telefono': '999999999',
        }

        for name, field in self.fields.items():
            field.widget.attrs.setdefault('class', 'account-form__input')
            if name in placeholders:
                field.widget.attrs.setdefault('placeholder', placeholders[name])

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
