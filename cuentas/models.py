from datetime import date

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from core.choices import EstadoCuentaJugador, RolUsuario
from core.models import TimeStampedModel


def validate_minimum_age(value):
    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < 18:
        raise ValidationError('El jugador debe ser mayor de edad.')


class Usuario(AbstractUser):
    id_usuario = models.BigAutoField(primary_key=True)
    username = models.CharField('nombre de usuario', db_column='nombre_usuario', max_length=150, unique=True)
    email = models.EmailField('correo', db_column='correo', unique=True)
    password = models.CharField('password hash', db_column='password_hash', max_length=128)
    rol = models.CharField(max_length=20, choices=RolUsuario.choices, default=RolUsuario.PLAYER)
    is_active = models.BooleanField('activo', db_column='activo', default=True)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def __str__(self):
        return self.username


class PerfilJugador(TimeStampedModel):
    id_perfil = models.BigAutoField(primary_key=True)
    usuario = models.OneToOneField(
        'cuentas.Usuario',
        on_delete=models.CASCADE,
        related_name='perfil_jugador',
        db_column='id_usuario',
    )
    nombres = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150)
    dni = models.CharField(
        max_length=8,
        unique=True,
        validators=[RegexValidator(r'^\d{8}$', 'El DNI debe tener 8 digitos numericos.')],
    )
    fecha_nacimiento = models.DateField(validators=[validate_minimum_age])
    telefono = models.CharField(max_length=30, blank=True)
    estado_cuenta = models.CharField(
        max_length=32,
        choices=EstadoCuentaJugador.choices,
        default=EstadoCuentaJugador.PENDIENTE_VERIFICACION,
    )
    kyc_verificado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'perfiles_jugador'
        verbose_name = 'perfil de jugador'
        verbose_name_plural = 'perfiles de jugador'

    def clean(self):
        super().clean()
        if self.estado_cuenta == EstadoCuentaJugador.VERIFICADO and self.kyc_verificado_en is None:
            self.kyc_verificado_en = timezone.now()

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'.strip()

    def __str__(self):
        return f'{self.nombre_completo} ({self.dni})'
