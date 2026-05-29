from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.choices import PeriodoLimite, TipoAutoexclusion
from juego_responsable.models import Autoexclusion, LimiteJuegoResponsable


PERIODOS_LIMITES = [PeriodoLimite.DIARIO, PeriodoLimite.SEMANAL, PeriodoLimite.MENSUAL]
DURACIONES_AUTOEXCLUSION_TEMPORAL = ['7', '30', '90']


def obtener_limites_pantalla(usuario):
    limites_pantalla = []

    for periodo in PERIODOS_LIMITES:
        limite_obj = LimiteJuegoResponsable.objects.filter(usuario=usuario, periodo=periodo).first()

        if limite_obj:
            limite_obj.actualizar_limites_si_procede()
            limites_pantalla.append({
                'periodo': periodo,
                'periodo_upper': periodo.upper(),
                'periodo_display': limite_obj.get_periodo_display(),
                'monto_actual': limite_obj.limite_actual,
                'limite_actual': limite_obj.limite_actual,
                'limite_pendiente': limite_obj.limite_pendiente,
                'pendiente_aplicar_en': limite_obj.pendiente_aplicar_en,
                'es_default': False,
            })
            continue

        monto_defecto = settings.JUEGO_RESPONSABLE_LIMITES_DEFAULT.get(periodo.upper(), 0.00)
        limites_pantalla.append({
            'periodo': periodo,
            'periodo_upper': periodo.upper(),
            'periodo_display': periodo.capitalize(),
            'monto_actual': Decimal(str(monto_defecto)),
            'limite_actual': Decimal(str(monto_defecto)),
            'limite_pendiente': None,
            'pendiente_aplicar_en': None,
            'es_default': True,
        })

    return limites_pantalla


def procesar_cambio_limites(usuario, data):
    errores = []
    campos_modificados = 0

    for periodo in PERIODOS_LIMITES:
        monto_str = data.get(f'monto_{periodo.lower()}')
        if not monto_str or monto_str.strip() == '':
            continue

        try:
            monto = Decimal(monto_str)
            if monto < 0:
                raise ValueError('El monto no puede ser negativo.')
        except (ValueError, TypeError) as exc:
            errores.append(f'Error en el limite {periodo.lower()}: {exc}')
            continue

        campos_modificados += 1
        limite_obj, created = LimiteJuegoResponsable.objects.get_or_create(
            usuario=usuario,
            periodo=periodo,
            defaults={'limite_actual': monto},
        )

        if created:
            continue

        if monto < limite_obj.limite_actual:
            limite_obj.limite_actual = monto
            limite_obj.limite_pendiente = None
            limite_obj.pendiente_aplicar_en = None
            limite_obj.save()
        elif monto > limite_obj.limite_actual:
            limite_obj.limite_pendiente = monto
            limite_obj.pendiente_aplicar_en = timezone.now() + timezone.timedelta(hours=24)
            limite_obj.save()

    return campos_modificados, errores


def crear_autoexclusion(usuario, tipo, duracion_dias='30', motivo=''):
    finaliza_en = None

    if tipo == TipoAutoexclusion.TEMPORAL:
        if duracion_dias not in DURACIONES_AUTOEXCLUSION_TEMPORAL:
            raise ValidationError('La duracion de la autoexclusion temporal seleccionada es invalida.')
        finaliza_en = timezone.now() + timezone.timedelta(days=int(duracion_dias))

    if tipo not in [choice[0] for choice in TipoAutoexclusion.choices]:
        raise ValidationError('El tipo de autoexclusion seleccionado es invalido.')

    return Autoexclusion.objects.create(
        usuario=usuario,
        tipo_autoexclusion=tipo,
        inicia_en=timezone.now(),
        finaliza_en=finaliza_en,
        activa=True,
        motivo=motivo,
    )


def obtener_autoexclusion_activa(usuario):
    return Autoexclusion.objects.filter(usuario=usuario, activa=True).order_by('-created_at').first()
