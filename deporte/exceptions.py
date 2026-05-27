class DeporteError(Exception):
    """Error base del dominio deportivo."""


class OddsNoDisponibleError(DeporteError):
    pass


class SeleccionNoApostableError(DeporteError):
    pass


class ResultadoEventoError(DeporteError):
    pass
