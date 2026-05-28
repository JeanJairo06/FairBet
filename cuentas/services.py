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
    CHECKSUM_WEIGHTS = (3, 2, 7, 6, 5, 4, 3)

    def validate(self, dni, fecha_nacimiento):
        if not self._has_valid_dni_format(dni):
            return KYCResult(
                is_valid=False,
                estado_cuenta=EstadoCuentaJugador.PENDIENTE_VERIFICACION,
                message='El DNI debe contener exactamente 8 digitos numericos.',
            )

        if self._is_repeated_sequence(dni):
            return KYCResult(
                is_valid=False,
                estado_cuenta=EstadoCuentaJugador.PENDIENTE_VERIFICACION,
                message='El DNI no puede estar formado por un unico digito repetido.',
            )

        if not self._has_valid_local_checksum(dni):
            return KYCResult(
                is_valid=False,
                estado_cuenta=EstadoCuentaJugador.PENDIENTE_VERIFICACION,
                message='El DNI no supera el digito verificador local simulado.',
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

    def _is_repeated_sequence(self, dni):
        return len(set(dni)) == 1

    def _has_valid_local_checksum(self, dni):
        digits = [int(value) for value in dni]
        weighted_sum = sum(
            digit * weight
            for digit, weight in zip(digits[:7], self.CHECKSUM_WEIGHTS)
        )
        return weighted_sum % 10 == digits[-1]

    def _is_adult(self, fecha_nacimiento):
        today = date.today()
        age = today.year - fecha_nacimiento.year - (
            (today.month, today.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
        )
        return age >= 18


def resolve_kyc_status(dni, fecha_nacimiento, validator=None):
    validator = validator or LocalKYCValidator()
    return validator.validate(dni=dni, fecha_nacimiento=fecha_nacimiento)


def mark_profile_verified(profile):
    profile.estado_cuenta = EstadoCuentaJugador.VERIFICADO
    profile.kyc_verificado_en = timezone.now()
    return profile
