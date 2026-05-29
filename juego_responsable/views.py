from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from core.choices import PeriodoLimite, TipoAutoexclusion
from core.decorators import verified_player_required
from juego_responsable.models import LimiteJuegoResponsable, Autoexclusion
from django.conf import settings
from decimal import Decimal

@verified_player_required
def panel_juego_responsable_view(request):
    usuario = request.user
    
    limites_pantalla = []
    periodos_evaluar = [PeriodoLimite.DIARIO, PeriodoLimite.SEMANAL, PeriodoLimite.MENSUAL]
    for per in periodos_evaluar:
        limite_obj = LimiteJuegoResponsable.objects.filter(usuario=usuario, periodo=per).first()
        
        if limite_obj:
            limite_obj.actualizar_limites_si_procede()
            limites_pantalla.append({
                'periodo_upper': per.upper(),
                'periodo_display': limite_obj.get_periodo_display(),
                'monto_actual': limite_obj.limite_actual,  
                'limite_actual': limite_obj.limite_actual, 
                'limite_pendiente': limite_obj.limite_pendiente,
                'pendiente_aplicar_en': limite_obj.pendiente_aplicar_en,
                'es_default': False
            })
        else:
            monto_defecto = settings.JUEGO_RESPONSABLE_LIMITES_DEFAULT.get(per.upper(), 0.00)
            limites_pantalla.append({
                'periodo_upper': per.upper(),
                'periodo_display': per.capitalize(),
                'monto_actual': Decimal(str(monto_defecto)),
                'limite_actual': Decimal(str(monto_defecto)),
                'limite_pendiente': None,
                'pendiente_aplicar_en': None,
                'es_default': True
            })

    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'cambiar_limite':
            periodos_formulario = [PeriodoLimite.DIARIO, PeriodoLimite.SEMANAL, PeriodoLimite.MENSUAL]
            errores_detectados = False
            campos_modificados = 0
            for per in periodos_formulario:
                monto_str = request.POST.get(f'monto_{per.lower()}')
                if not monto_str or monto_str.strip() == "":
                    continue
                try:
                    monto = Decimal(monto_str)
                    if monto < 0:
                        raise ValueError("El monto no puede ser negativo.")
                    campos_modificados += 1
                    limite_obj, created = LimiteJuegoResponsable.objects.get_or_create(
                        usuario=usuario,
                        periodo=per,
                        defaults={'limite_actual': monto}
                    )

                    if not created:
                        if monto < limite_obj.limite_actual:
                            limite_obj.limite_actual = monto
                            limite_obj.limite_pendiente = None
                            limite_obj.pendiente_aplicar_en = None
                            limite_obj.save()
                        elif monto > limite_obj.limite_actual:
                            limite_obj.limite_pendiente = monto
                            limite_obj.pendiente_aplicar_en = timezone.now() + timezone.timedelta(hours=24)
                            limite_obj.save()
                        
                except (ValueError, TypeError) as e:
                    errores_detectados = True
                    messages.error(request, f"Error en el límite {per.lower()}: {str(e)}")
            
            if campos_modificados == 0 and not errores_detectados:
                messages.warning(request, "No has ingresado ningún monto para modificar en el formulario.")
            elif not errores_detectados:
                messages.success(request, f"Solicitud de actualización de límites procesada exitosamente (los aumentos requieren 24 horas de cooldown).")
            return redirect('juego_responsable:panel')

        elif accion == 'autoexcluirse':
            tipo = request.POST.get('tipo_autoexclusion')
            motivo = request.POST.get('motivo', '')
            
            try:
                finaliza_en = None
                if tipo == TipoAutoexclusion.TEMPORAL:
                    dias_str = request.POST.get('duracion_dias', '30')
                    if dias_str not in ['7', '30', '90']:
                        messages.error(request, "La duración de la autoexclusión temporal seleccionada es inválida.")
                        return redirect('juego_responsable:panel')

                    dias_excluir = int(dias_str)
                    finaliza_en = timezone.now() + timezone.timedelta(days=dias_excluir)

                Autoexclusion.objects.create(
                    usuario=usuario,
                    tipo_autoexclusion=tipo,
                    inicia_en=timezone.now(),
                    finaliza_en=finaliza_en,
                    activa=True,
                    motivo=motivo
                )
                
                messages.success(request, "Su solicitud de autoexclusión se ha procesado. Su sesión se cerrará.")
                return redirect('cuentas:logout')
                
            except Exception as e:
                messages.error(request, "No se pudo procesar la autoexclusión en este momento.")
                
            return redirect('juego_responsable:panel')

    context = {
        'limites': limites_pantalla,
        'choices_periodo': PeriodoLimite.choices,
        'choices_autoexclusion': TipoAutoexclusion.choices,
    }
    return render(request, 'juego_responsable/panel.html', context)
