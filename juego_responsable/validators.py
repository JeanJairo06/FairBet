from datetime import datetime, time
from django.utils import timezone
from core.choices import PeriodoLimite
from django.db.models import Sum
from django.core.exceptions import ValidationError
from juego_responsable.models import LimiteJuegoResponsable
from django.conf import settings
from decimal import Decimal
from billetera.models import TransaccionLedger
from core.choices import TipoTransaccionLedger, EstadoTransaccionLedger

def obtener_fecha_inicio_periodo(periodo):

    ahora = timezone.now()
    hoy_local = timezone.localtime(ahora)
    
    if periodo == PeriodoLimite.DIARIO:
        inicio = datetime.combine(hoy_local.date(), time.min)
        return timezone.make_aware(inicio, hoy_local.tzinfo)
        
    elif periodo == PeriodoLimite.SEMANAL:
        dias_desde_lunes = hoy_local.weekday()  # 0=Lunes, 1=Martes...
        lunes = hoy_local.date() - timezone.timedelta(days=dias_desde_lunes)
        inicio = datetime.combine(lunes, time.min)
        return timezone.make_aware(inicio, hoy_local.tzinfo)
        
    elif periodo == PeriodoLimite.MENSUAL:
        primer_dia_mes = hoy_local.date().replace(day=1)
        inicio = datetime.combine(primer_dia_mes, time.min)
        return timezone.make_aware(inicio, hoy_local.tzinfo)
        
    return ahora

def validar_limite_recarga(usuario, monto_a_recargar):

    periodos_obligatorios = [PeriodoLimite.DIARIO, PeriodoLimite.SEMANAL, PeriodoLimite.MENSUAL]
    
    for per in periodos_obligatorios:
        limite = LimiteJuegoResponsable.objects.filter(usuario=usuario, periodo=per).first()
        if limite:
            limite.actualizar_limites_si_procede()
            limite_maximo = limite.limite_actual
        else:
            val_default = settings.JUEGO_RESPONSABLE_LIMITES_DEFAULT.get(per.upper(), 10000.00)
            limite_maximo = Decimal(str(val_default))

        fecha_inicio = obtener_fecha_inicio_periodo(per)
        total_recargado = TransaccionLedger.objects.filter(
            usuario=usuario,
            tipo_transaccion=TipoTransaccionLedger.RECARGA,
            estado=EstadoTransaccionLedger.COMPLETED,
            created_at__gte=fecha_inicio
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        
        monto_proyectado = total_recargado + monto_a_recargar

        if monto_proyectado > limite.limite_actual:
            raise ValidationError(
                f"Operación rechazada por Juego Responsable. Su límite {per.lower()} es de {limite_maximo} fichas."
            )