from django.db import models


class RolUsuario(models.TextChoices):
    PLAYER = 'PLAYER', 'Jugador'
    ADMIN = 'ADMIN', 'Administrador'
    OPERATOR = 'OPERATOR', 'Operador'


class EstadoCuentaJugador(models.TextChoices):
    PENDIENTE_VERIFICACION = 'pendiente_verificacion', 'Pendiente de verificacion'
    VERIFICADO = 'verificado', 'Verificado'
    BLOQUEADO = 'bloqueado', 'Bloqueado'
    AUTOEXCLUIDO = 'autoexcluido', 'Autoexcluido'


class PeriodoLimite(models.TextChoices):
    DIARIO = 'diario', 'Diario'
    SEMANAL = 'semanal', 'Semanal'
    MENSUAL = 'mensual', 'Mensual'


class TipoAutoexclusion(models.TextChoices):
    TEMPORAL = 'temporal', 'Temporal'
    INDEFINIDA = 'indefinida', 'Indefinida'


class TipoCuentaContable(models.TextChoices):
    WALLET_USUARIO = 'wallet_usuario', 'Wallet de usuario'
    CASA = 'casa', 'Casa'
    APUESTAS_PENDIENTES = 'apuestas_pendientes', 'Apuestas pendientes'
    BONOS = 'bonos', 'Bonos'


class EstadoCuentaContable(models.TextChoices):
    ACTIVA = 'activa', 'Activa'
    BLOQUEADA = 'bloqueada', 'Bloqueada'
    CERRADA = 'cerrada', 'Cerrada'


class TipoTransaccionLedger(models.TextChoices):
    RECARGA = 'recarga', 'Recarga'
    RETIRO = 'retiro', 'Retiro'
    TRANSFERENCIA = 'transferencia', 'Transferencia'
    BLOQUEO_APUESTA = 'bloqueo_apuesta', 'Bloqueo de apuesta'
    LIQUIDACION = 'liquidacion', 'Liquidacion'
    CASH_OUT = 'cash_out', 'Cash-out'
    BONO = 'bono', 'Bono'
    REVERSION = 'reversion', 'Reversion'


class EstadoTransaccionLedger(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    COMPLETED = 'completed', 'Completada'
    FAILED = 'failed', 'Fallida'
    REVERSED = 'reversed', 'Revertida'


class DirectionLedger(models.TextChoices):
    DEBIT = 'DEBIT', 'Debito'
    CREDIT = 'CREDIT', 'Credito'


class EstadoEvento(models.TextChoices):
    PROGRAMADO = 'programado', 'Programado'
    EN_VIVO = 'en_vivo', 'En vivo'
    FINALIZADO = 'finalizado', 'Finalizado'
    SUSPENDIDO = 'suspendido', 'Suspendido'
    ANULADO = 'anulado', 'Anulado'


class TipoMercado(models.TextChoices):
    UNO_X_DOS = '1X2', '1X2'
    OVER_UNDER = 'OVER_UNDER', 'Over/Under'
    BTTS = 'BTTS', 'Ambos anotan'
    HANDICAP = 'HANDICAP', 'Handicap'
    GOLEADOR_EXACTO = 'GOLEADOR_EXACTO', 'Goleador exacto'


class EstadoMercado(models.TextChoices):
    ABIERTO = 'abierto', 'Abierto'
    SUSPENDIDO = 'suspendido', 'Suspendido'
    CERRADO = 'cerrado', 'Cerrado'
    LIQUIDADO = 'liquidado', 'Liquidado'
    ANULADO = 'anulado', 'Anulado'


class EstadoSeleccion(models.TextChoices):
    ACTIVA = 'activa', 'Activa'
    SUSPENDIDA = 'suspendida', 'Suspendida'
    GANADORA = 'ganadora', 'Ganadora'
    PERDEDORA = 'perdedora', 'Perdedora'
    ANULADA = 'anulada', 'Anulada'


class TipoApuesta(models.TextChoices):
    SIMPLE = 'simple', 'Simple'
    COMBINADA = 'combinada', 'Combinada'


class EstadoApuesta(models.TextChoices):
    DRAFT = 'draft', 'Borrador'
    ACCEPTED = 'accepted', 'Aceptada'
    WON = 'won', 'Ganada'
    LOST = 'lost', 'Perdida'
    VOID = 'void', 'Anulada'
    CASHED_OUT = 'cashed_out', 'Cash-out'
    CANCELLED = 'cancelled', 'Cancelada'


class EstadoDetalleApuesta(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    WON = 'won', 'Ganado'
    LOST = 'lost', 'Perdido'
    VOID = 'void', 'Anulado'


class ResultadoLiquidacion(models.TextChoices):
    WON = 'won', 'Ganada'
    LOST = 'lost', 'Perdida'
    VOID = 'void', 'Anulada'
    CASH_OUT = 'cash_out', 'Cash-out'
