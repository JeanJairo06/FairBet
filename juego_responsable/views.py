from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.choices import PeriodoLimite, TipoAutoexclusion
from core.decorators import verified_player_required
from juego_responsable.models import LimiteJuegoResponsable, Autoexclusion

@verified_player_required
def panel_juego_responsable_view(request):
    usuario = request.user
    
    limites_usuario = LimiteJuegoResponsable.objects.filter(usuario=usuario)
    for limite in limites_usuario:
        limite.actualizar_limites_si_procede()

    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'cambiar_limite':
            periodo = request.POST.get('periodo')
            monto_str = request.POST.get('monto')
            
            try:
                monto = float(monto_str)
                if monto < 0:
                    raise ValueError("El monto no puede ser negativo.")

                limite_obj, created = LimiteJuegoResponsable.objects.get_or_create(
                    usuario=usuario,
                    periodo=periodo,
                    defaults={'limite_actual': monto}
                )

                if not created:
                    if monto < limite_obj.limite_actual:
                        limite_obj.limite_actual = monto
                        limite_obj.limite_pendiente = None
                        limite_obj.pendiente_aplicar_en = None
                        messages.success(request, f"Su límite {periodo} se ha reducido exitosamente.")
                    else:
                        limite_obj.limite_pendiente = monto
                        limite_obj.pendiente_aplicar_en = timezone.now() + timezone.timedelta(hours=24)
                        messages.warning(request, f"Al tratarse de un aumento, se aplicará automáticamente después del período de espera de 24 horas.")
                    
                    limite_obj.save()
                    
            except (ValueError, TypeError):
                messages.error(request, "Por favor, ingrese un monto numérico válido.")
            except ValidationError as e:
                messages.error(request, f"Error de validación: {e.message}")
                
            return redirect('juego_responsable:panel')

        elif accion == 'autoexcluirse':
            tipo = request.POST.get('tipo_autoexclusion')
            motivo = request.POST.get('motivo', '')
            
            try:
                finaliza_en = None
                if tipo == TipoAutoexclusion.TEMPORAL:
                    finaliza_en = timezone.now() + timezone.timedelta(days=30)

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
        'limites': limites_usuario,
        'choices_periodo': PeriodoLimite.choices,
        'choices_autoexclusion': TipoAutoexclusion.choices,
    }
    return render(request, 'juego_responsable/panel.html', context)