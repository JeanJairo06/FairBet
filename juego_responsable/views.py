from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from core.choices import TipoAutoexclusion
from core.decorators import verified_player_required
from juego_responsable.services import crear_autoexclusion, obtener_limites_pantalla, procesar_cambio_limites

@verified_player_required
def panel_juego_responsable_view(request):
    usuario = request.user

    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        if accion == 'cambiar_limite':
            campos_modificados, errores = procesar_cambio_limites(usuario, request.POST)
            for error in errores:
                messages.error(request, error)
            
            if campos_modificados == 0 and not errores:
                messages.warning(request, "No has ingresado ningún monto para modificar en el formulario.")
            elif not errores:
                messages.success(request, f"Solicitud de actualización de límites procesada exitosamente (los aumentos requieren 24 horas de cooldown).")
            return redirect('juego_responsable:panel')

        elif accion == 'autoexcluirse':
            tipo = request.POST.get('tipo_autoexclusion')
            motivo = request.POST.get('motivo', '')
            
            try:
                crear_autoexclusion(usuario, tipo, request.POST.get('duracion_dias', '30'), motivo)
                
                messages.success(request, "Su solicitud de autoexclusión se ha procesado. Su sesión se cerrará.")
                return redirect('logout')
                
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            except Exception:
                messages.error(request, "No se pudo procesar la autoexclusión en este momento.")
                
            return redirect('juego_responsable:panel')

    context = {
        'limites': obtener_limites_pantalla(usuario),
        'choices_autoexclusion': TipoAutoexclusion.choices,
    }
    return render(request, 'juego_responsable/panel.html', context)
