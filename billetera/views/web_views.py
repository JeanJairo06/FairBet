from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone

from apuesta.models import Apuesta
from billetera.exceptions import BilleteraError, CuentaNoEncontradaError
from billetera.models import LedgerEntry
from billetera.services.account_service import obtener_cuenta_wallet
from billetera.services.balance_service import calcular_saldo, calcular_saldo_usuario
from billetera.services.wallet_service import recargar_fichas, retirar_fichas
from core.choices import DirectionLedger, EstadoApuesta, TipoTransaccionLedger
from core.decorators import verified_player_required
from juego_responsable.services import obtener_autoexclusion_activa, obtener_limites_pantalla
from juego_responsable.validators import validar_limite_recarga


def _decimal_from_post(value):
    try:
        monto = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError('Ingresa un monto valido.') from exc

    if monto <= 0:
        raise ValidationError('El monto debe ser mayor que cero.')

    return monto


def _inicio_mes_actual():
    ahora_local = timezone.localtime(timezone.now())
    inicio = ahora_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return inicio


def _sumar_movimientos(cuenta, inicio_mes, tipo=None, direction=None):
    queryset = LedgerEntry.objects.filter(cuenta=cuenta, created_at__gte=inicio_mes)
    if tipo:
        queryset = queryset.filter(transaccion__tipo_transaccion=tipo)
    if direction:
        queryset = queryset.filter(direction=direction)
    return queryset.aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')


def _obtener_contexto_billetera(usuario, page_number):
    wallet = obtener_cuenta_wallet(usuario)
    inicio_mes = _inicio_mes_actual()
    total_creditos = _sumar_movimientos(wallet, inicio_mes, direction=DirectionLedger.CREDIT)
    total_debitos = _sumar_movimientos(wallet, inicio_mes, direction=DirectionLedger.DEBIT)
    bloqueado = Apuesta.objects.filter(
        usuario=usuario,
        estado_apuesta=EstadoApuesta.ACCEPTED,
    ).aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

    movimientos_queryset = LedgerEntry.objects.filter(cuenta=wallet).select_related('transaccion').order_by('-created_at')
    paginator = Paginator(movimientos_queryset, 10)
    page_obj = paginator.get_page(page_number)

    return {
        'saldo_disponible': calcular_saldo(wallet),
        'saldo_usuario': calcular_saldo_usuario(usuario),
        'fichas_bloqueadas': bloqueado,
        'metricas_mes': {
            'recargado': _sumar_movimientos(wallet, inicio_mes, TipoTransaccionLedger.RECARGA, DirectionLedger.CREDIT),
            'retirado': _sumar_movimientos(wallet, inicio_mes, TipoTransaccionLedger.RETIRO, DirectionLedger.DEBIT),
            'apostado': _sumar_movimientos(wallet, inicio_mes, TipoTransaccionLedger.BLOQUEO_APUESTA, DirectionLedger.DEBIT),
            'ganado': _sumar_movimientos(wallet, inicio_mes, TipoTransaccionLedger.LIQUIDACION, DirectionLedger.CREDIT),
            'balance_neto': total_creditos - total_debitos,
        },
        'movimientos': page_obj.object_list,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'limites': obtener_limites_pantalla(usuario),
        'autoexclusion_activa': obtener_autoexclusion_activa(usuario),
    }


@verified_player_required
def panel_billetera_view(request):
    usuario = request.user

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'recargar':
            try:
                monto = _decimal_from_post(request.POST.get('monto'))
                validar_limite_recarga(usuario, monto)
                recargar_fichas(usuario, monto, idempotency_key=f'web-recarga-{usuario.pk}-{uuid4()}')
                messages.success(request, 'Recarga registrada correctamente.')
            except (ValidationError, BilleteraError) as exc:
                mensaje = exc.messages[0] if hasattr(exc, 'messages') else str(exc)
                messages.error(request, mensaje)
            return redirect('billetera:panel')

        if accion == 'retirar':
            try:
                monto = _decimal_from_post(request.POST.get('monto'))
                retirar_fichas(usuario, monto, idempotency_key=f'web-retiro-{usuario.pk}-{uuid4()}')
                messages.success(request, 'Retiro registrado correctamente.')
            except (ValidationError, BilleteraError) as exc:
                mensaje = exc.messages[0] if hasattr(exc, 'messages') else str(exc)
                messages.error(request, mensaje)
            return redirect('billetera:panel')

    try:
        context = _obtener_contexto_billetera(usuario, request.GET.get('page'))
    except CuentaNoEncontradaError:
        messages.error(request, 'Tu usuario no tiene una billetera contable asociada.')
        return redirect('home')

    return render(request, 'billetera/panel.html', context)
