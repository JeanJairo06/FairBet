from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from core.choices import EstadoCuentaJugador


@dataclass(frozen=True)
class KYCResult:
    is_valid: bool
    estado_cuenta: str
    message: str


class LocalKYCValidator:
    """
    Validador local y reemplazable para el KYC inicial.

    En una fase posterior esta clase puede convertirse en adapter hacia un
    proveedor externo de identidad sin cambiar formularios ni vistas.
    """

    DNI_LENGTH = 8

    def validate(self, dni, fecha_nacimiento):
        if not self._has_valid_dni_format(dni):
            return KYCResult(
                is_valid=False,
                estado_cuenta=EstadoCuentaJugador.PENDIENTE_VERIFICACION,
                message='El DNI debe contener exactamente 8 digitos numericos.',
            )

        if not self._is_adult(fecha_nacimiento):
            return KYCResult(
                is_valid=False,
                estado_cuenta=EstadoCuentaJugador.PENDIENTE_VERIFICACION,
                message='El jugador debe ser mayor de edad.',
            )

        return KYCResult(
            is_valid=True,
            estado_cuenta=EstadoCuentaJugador.VERIFICADO,
            message='KYC local validado correctamente.',
        )

    def _has_valid_dni_format(self, dni):
        return bool(dni and dni.isdigit() and len(dni) == self.DNI_LENGTH)

    def _is_adult(self, fecha_nacimiento):
        return fecha_nacimiento <= get_adult_date_limit()


def resolve_kyc_status(dni, fecha_nacimiento, validator=None):
    validator = validator or LocalKYCValidator()
    return validator.validate(dni=dni, fecha_nacimiento=fecha_nacimiento)


def mark_profile_verified(profile):
    profile.estado_cuenta = EstadoCuentaJugador.VERIFICADO
    profile.kyc_verificado_en = timezone.now()
    return profile


def get_adult_date_limit(today=None, minimum_age=18):
    today = today or date.today()
    try:
        return today.replace(year=today.year - minimum_age)
    except ValueError:
        return today.replace(month=2, day=28, year=today.year - minimum_age)
