from datetime import datetime, time
from django.utils import timezone
from core.choices import PeriodoLimite

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