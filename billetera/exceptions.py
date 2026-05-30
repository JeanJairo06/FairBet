class BilleteraError(Exception):
    """Base para errores de dominio del modulo billetera."""


class MontoInvalidoError(BilleteraError):
    pass


class CuentaNoEncontradaError(BilleteraError):
    pass


class CuentaBloqueadaError(BilleteraError):
    pass


class SaldoInsuficienteError(BilleteraError):
    pass


class TransaccionNoBalanceadaError(BilleteraError):
    pass


class TransaccionDuplicadaError(BilleteraError):
    pass
