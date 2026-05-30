from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import ListView
from rest_framework.generics import ListCreateAPIView

from apuesta.models import Apuesta
from apuesta.servicios import crear_apuesta_simple
from apuesta.serializers import ApuestaSerializer, CrearApuestaSimpleSerializer
from billetera.exceptions import BilleteraError
from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado


class ApuestaListCreateView(ListCreateAPIView):
    def get_queryset(self):
        return Apuesta.objects.filter(usuario=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CrearApuestaSimpleSerializer
        return ApuestaSerializer


class ApuestasWebView(LoginRequiredMixin, ListView):
    template_name = 'apuestas/lista.html'
    context_object_name = 'eventos'
    login_url = 'login'

    def get_queryset(self):
        ahora = timezone.now()
        selecciones_apostables = SeleccionMercado.objects.filter(
            estado_seleccion=EstadoSeleccion.ACTIVA,
            historial_odds__activa=True,
        ).prefetch_related('historial_odds').distinct()
        mercados_apostables = Mercado.objects.filter(
            estado_mercado=EstadoMercado.ABIERTO,
        ).filter(
            Q(evento__estado_evento=EstadoEvento.PROGRAMADO, evento__inicia_en__gt=ahora)
            | Q(evento__estado_evento=EstadoEvento.EN_VIVO, permite_in_play=True)
        ).prefetch_related(
            Prefetch('selecciones', queryset=selecciones_apostables)
        )

        return EventoDeportivo.objects.filter(
            mercados__estado_mercado=EstadoMercado.ABIERTO,
            mercados__selecciones__estado_seleccion=EstadoSeleccion.ACTIVA,
            mercados__selecciones__historial_odds__activa=True,
        ).filter(
            Q(estado_evento=EstadoEvento.PROGRAMADO, inicia_en__gt=ahora)
            | Q(estado_evento=EstadoEvento.EN_VIVO, mercados__permite_in_play=True)
        ).distinct().prefetch_related(
            Prefetch('mercados', queryset=mercados_apostables),
        ).order_by('inicia_en')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        odds_activas = {
            odds.seleccion_id: odds
            for odds in HistorialOdds.objects.filter(activa=True).select_related('seleccion')
        }
        for evento in context['eventos']:
            for mercado in evento.mercados.all():
                mercado.selecciones_activas = [
                    seleccion
                    for seleccion in mercado.selecciones.all()
                    if seleccion.estado_seleccion == EstadoSeleccion.ACTIVA and odds_activas.get(seleccion.id_seleccion)
                ]
                for seleccion in mercado.selecciones_activas:
                    seleccion.odds_activa = odds_activas[seleccion.id_seleccion]
        context['mis_apuestas'] = Apuesta.objects.filter(usuario=self.request.user).order_by('-created_at')[:8]
        return context

    def post(self, request, *args, **kwargs):
        seleccion_ids_raw = request.POST.get('seleccion_ids', '').strip()
        stake = request.POST.get('stake')

        if not seleccion_ids_raw:
            messages.error(request, 'Selecciona al menos una cuota.')
            return redirect('apuesta:apuestas_web')

        try:
            stake = Decimal(str(stake))
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, 'Ingresa un monto valido para la apuesta.')
            return redirect('apuesta:apuestas_web')

        ids = [s.strip() for s in seleccion_ids_raw.split(',') if s.strip()]
        creadas = 0
        errores = []
        for seleccion_id in ids:
            try:
                apuesta = crear_apuesta_simple(
                    usuario=request.user,
                    seleccion_id=seleccion_id,
                    stake=stake,
                    idempotency_key=f'web-{request.user.pk}-{seleccion_id}-{stake}-{timezone.now().timestamp()}',
                )
                creadas += 1
            except (ValidationError, BilleteraError) as exc:
                errores.append(str(exc))

        if creadas:
            messages.success(request, f'{creadas} apuesta(s) registrada(s) correctamente.')
        for err in errores:
            messages.error(request, err)
        return redirect('apuesta:mis_apuestas_web')


class MisApuestasWebView(LoginRequiredMixin, ListView):
    model = Apuesta
    template_name = 'apuestas/mis_apuestas.html'
    context_object_name = 'apuestas'
    login_url = 'login'
    paginate_by = 10

    def get_queryset(self):
        return Apuesta.objects.filter(usuario=self.request.user).order_by('-created_at')
