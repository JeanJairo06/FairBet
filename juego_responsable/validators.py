from datetime import datetime, time
from django.utils import timezone
from core.choices import PeriodoLimite
from django.db.models import Sum
from django.core.exceptions import ValidationError
from juego_responsable.models import LimiteJuegoResponsable

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

    limites = LimiteJuegoResponsable.objects.filter(usuario=usuario)
    
    for limite in limites:
        limite.actualizar_limites_si_procede()
        fecha_inicio = obtener_fecha_inicio_periodo(limite.periodo)
        total_recargado = usuario.transacciones_billetera.filter(
            tipo_transaccion='recarga',
            estado='completado',
            created_at__gte=fecha_inicio
        ).aggregate(total=Sum('monto'))['total'] or 0
        
        monto_proyectado = total_recargado + monto_a_recargar

        if monto_proyectado > limite.limite_actual:
            raise ValidationError(
                f"Operación rechazada por Juego Responsable. Su límite {limite.periodo} es de "
                f"{limite.limite_actual} fichas. Al procesar esta solicitud, su consumo total "
                f"llegaría a {monto_proyectado} fichas (Ya consumido: {total_recargado} | "
                f"Solicitado: {monto_a_recargar}), excediendo el tope permitido."
            )