from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from apuesta.servicios import liquidar_apuestas_de_evento
from core.choices import EstadoEvento, EstadoMercado, TipoMercado
from core.decorators import operator_required
from deporte.forms import (
    ActualizarMarcadorEventoForm,
    ConfirmarResultadoEventoForm,
    EventoDeportivoForm,
    MercadoPersonalizadoEventoForm,
    MercadoRapidoForm,
)
from deporte.exceptions import ResultadoEventoError
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado
from deporte.services import (
    actualizar_marcador_en_vivo,
    actualizar_odds,
    anular_evento,
    anular_evento_y_liquidar,
    confirmar_resultado_evento,
    crear_mercado_rapido,
    crear_seleccion,
    finalizar_evento_y_liquidar,
    marcar_seleccion_ganadora,
    pasar_evento_en_vivo,
    reactivar_evento,
    suspender_evento,
    validar_evento_configurable,
    validar_mercado_configurable,
)


class DeporteOperadorRequiredMixin:
    @method_decorator(operator_required(raise_exception=True))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class EventoListView(DeporteOperadorRequiredMixin, ListView):
    model = EventoDeportivo
    template_name = 'deporte/eventos/lista.html'
    context_object_name = 'eventos'
    paginate_by = 12

    def get_queryset(self):
        queryset = EventoDeportivo.objects.prefetch_related(
            Prefetch('mercados', queryset=Mercado.objects.order_by('nombre'))
        ).annotate(
            mercados_total=Count('mercados', distinct=True),
            selecciones_total=Count('mercados__selecciones', distinct=True),
            odds_vigentes_total=Count(
                'mercados__selecciones__historial_odds',
                filter=Q(mercados__selecciones__historial_odds__activa=True),
                distinct=True,
            ),
        ).order_by('-id_evento')
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(competicion__icontains=q)
                | Q(equipo_local__icontains=q)
                | Q(equipo_visitante__icontains=q)
            )
        return queryset


class EventoCreateView(DeporteOperadorRequiredMixin, CreateView):
    model = EventoDeportivo
    form_class = EventoDeportivoForm
    template_name = 'deporte/eventos/formulario.html'

    def form_valid(self, form):
        messages.success(self.request, 'Partido creado correctamente. Ahora configura sus mercados y odds.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('deporte:evento_detalle', args=[self.object.pk])


class EventoUpdateView(DeporteOperadorRequiredMixin, UpdateView):
    model = EventoDeportivo
    form_class = EventoDeportivoForm
    template_name = 'deporte/eventos/formulario.html'
    success_url = reverse_lazy('deporte:eventos_lista')

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            validar_evento_configurable(self.object)
        except ValidationError as exc:
            messages.error(request, EventoEstadoActionView._format_error(exc))
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[self.object.pk]))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Evento deportivo actualizado correctamente.')
        return super().form_valid(form)


class EventoDetailView(DeporteOperadorRequiredMixin, DetailView):
    model = EventoDeportivo
    template_name = 'deporte/eventos/detalle.html'
    context_object_name = 'evento'

    def get_queryset(self):
        selecciones = SeleccionMercado.objects.prefetch_related(
            Prefetch('historial_odds', queryset=HistorialOdds.objects.order_by('-activa', '-created_at'))
        ).order_by('created_at')
        return EventoDeportivo.objects.prefetch_related(
            Prefetch(
                'mercados',
                queryset=Mercado.objects.prefetch_related(Prefetch('selecciones', queryset=selecciones)).order_by('created_at'),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        evento = self.object
        mercados = list(evento.mercados.all())
        evento_configurable = evento.estado_evento not in {EstadoEvento.FINALIZADO, EstadoEvento.ANULADO} and not evento.resultado_confirmado

        template_map = {
            'resultado_final': TipoMercado.UNO_X_DOS,
            'ambos_anotan': TipoMercado.BTTS,
            'total_goles': TipoMercado.OVER_UNDER,
            'handicap': TipoMercado.HANDICAP,
        }

        tipos_plantilla = set(template_map.values())
        selecciones_total = 0
        odds_vigentes_total = 0

        for mercado in mercados:
            mercado.selecciones_workspace = list(mercado.selecciones.all())
            for seleccion in mercado.selecciones_workspace:
                historial = list(seleccion.historial_odds.all())
                seleccion.odds_vigente = next((odds for odds in historial if odds.activa), None)
                seleccion.historial_reciente = historial[:4]
                if mercado.tipo_mercado in tipos_plantilla:
                    selecciones_total += 1
                    if seleccion.odds_vigente:
                        odds_vigentes_total += 1

        tiene_mercados = bool(mercados)
        tiene_selecciones = selecciones_total > 0
        tiene_odds = tiene_selecciones and odds_vigentes_total >= selecciones_total
        listo = tiene_mercados and tiene_selecciones and tiene_odds

        mercados_data = {}
        for template, tipo in template_map.items():
            mercado = next((m for m in mercados if m.tipo_mercado == tipo), None)
            if mercado:
                selections = []
                for sel in mercado.selecciones_workspace:
                    selections.append({
                        'pk': sel.pk,
                        'codigo': sel.codigo_seleccion,
                        'nombre': sel.nombre,
                        'odds': sel.odds_vigente.odds if sel.odds_vigente else None,
                    })
                mercados_data[template] = {
                    'exists': True,
                    'mercado_pk': mercado.pk,
                    'estado_mercado': mercado.estado_mercado,
                    'permite_in_play': mercado.permite_in_play,
                    'selections': selections,
                    'editable': evento_configurable and mercado.estado_mercado not in {EstadoMercado.LIQUIDADO, EstadoMercado.ANULADO},
                }
            else:
                mercados_data[template] = {'exists': False, 'editable': evento_configurable}

        context.update(
            {
                'mercados': mercados,
                'mercados_data': mercados_data,
                'evento_configurable': evento_configurable,
                'historial_odds_reciente': HistorialOdds.objects.select_related('seleccion__mercado').filter(
                    seleccion__mercado__evento=evento
                ).order_by('-created_at')[:12],
                'mercado_rapido_form': MercadoRapidoForm(),
                'mercado_personalizado_form': MercadoPersonalizadoEventoForm(
                    initial={'stake_minimo': '1.00', 'stake_maximo': '100.00'}
                ),
                'resultado_form': ConfirmarResultadoEventoForm(evento=evento),
                'marcador_form': ActualizarMarcadorEventoForm(
                    initial={
                        'marcador_local': evento.marcador_local,
                        'marcador_visitante': evento.marcador_visitante,
                    }
                ),
                'checklist': [
                    ('Datos del partido completos', True),
                    ('Tiene mercados creados', tiene_mercados),
                    ('Tiene selecciones configuradas', tiene_selecciones),
                    ('Tiene odds vigentes', tiene_odds),
                    ('Partido listo para apostar', listo),
                ],
                'partido_listo': listo,
                'mercados_total': len(mercados),
                'selecciones_total': selecciones_total,
                'odds_vigentes_total': odds_vigentes_total,
            }
        )
        return context


class OddsListView(DeporteOperadorRequiredMixin, ListView):
    model = HistorialOdds
    template_name = 'deporte/odds/lista.html'
    context_object_name = 'odds'
    paginate_by = 10

    def get_queryset(self):
        queryset = HistorialOdds.objects.select_related(
            'seleccion__mercado__evento',
            'cambiado_por',
        ).order_by('-activa', '-created_at')
        seleccion_id = self.request.GET.get('seleccion')
        if seleccion_id:
            queryset = queryset.filter(seleccion_id=seleccion_id)
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(seleccion__nombre__icontains=q)
                | Q(seleccion__codigo_seleccion__icontains=q)
                | Q(seleccion__mercado__nombre__icontains=q)
                | Q(seleccion__mercado__evento__equipo_local__icontains=q)
                | Q(seleccion__mercado__evento__equipo_visitante__icontains=q)
            )
        return queryset


class EventoMercadoRapidoView(DeporteOperadorRequiredMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
        form = MercadoRapidoForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'No se pudo crear el mercado. Verifica los datos ingresados.')
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))

        try:
            validar_evento_configurable(evento)
            mercado = crear_mercado_rapido(
                evento,
                form.cleaned_data['plantilla'],
                linea=form.cleaned_data.get('linea'),
                stake_minimo=form.cleaned_data.get('stake_minimo'),
                stake_maximo=form.cleaned_data.get('stake_maximo'),
                odds_iniciales=self._odds_iniciales(
                    request.POST,
                    form.cleaned_data['plantilla'],
                    form.cleaned_data.get('linea'),
                ),
                cambiado_por=request.user if request.user.is_authenticated else None,
            )
        except (ValueError, ValidationError) as exc:
            messages.error(request, self._format_error(exc))
        else:
            messages.success(request, f'Mercado {mercado.nombre} creado correctamente.')
        return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))

    @staticmethod
    def _odds_iniciales(post_data, plantilla, linea):
        if plantilla == 'total_goles' and linea is not None:
            codigo = str(linea).replace('-', 'M').replace('+', 'P').replace('.', '_')
            return {
                f'OVER_{codigo}': post_data.get('odds_OVER', ''),
                f'UNDER_{codigo}': post_data.get('odds_UNDER', ''),
            }
        if plantilla == 'handicap' and linea is not None:
            codigo = str(linea).replace('-', 'M').replace('+', 'P').replace('.', '_')
            return {
                f'HOME_{codigo}': post_data.get('odds_HOME_HANDICAP', ''),
                f'AWAY_{codigo}': post_data.get('odds_AWAY_HANDICAP', ''),
            }

        odds = {}
        for key, value in post_data.items():
            if key.startswith('odds_') and value != '':
                odds[key.removeprefix('odds_')] = value
        return odds

    @staticmethod
    def _format_error(exc):
        if hasattr(exc, 'message_dict'):
            return ' '.join(error for errors in exc.message_dict.values() for error in errors)
        if hasattr(exc, 'messages'):
            return ' '.join(exc.messages)
        return str(exc)


class EventoMercadoPersonalizadoView(DeporteOperadorRequiredMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
        form = MercadoPersonalizadoEventoForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'No se pudo crear el mercado personalizado. Revisa los campos.')
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))

        try:
            validar_evento_configurable(evento)
            mercado = crear_mercado_rapido(
                evento,
                'personalizado',
                datos_personalizados=form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, EventoEstadoActionView._format_error(exc))
        else:
            messages.success(request, f'Mercado {mercado.nombre} creado correctamente.')
        return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))


class EventoOddsActualizarView(DeporteOperadorRequiredMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
        try:
            validar_evento_configurable(evento)
        except ValidationError as exc:
            messages.error(request, self._format_error(exc))
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))
        selecciones = SeleccionMercado.objects.select_related('mercado').filter(mercado__evento=evento)
        selecciones_por_id = {str(seleccion.pk): seleccion for seleccion in selecciones}
        actualizadas = 0
        errores = []

        for key, value in request.POST.items():
            if not key.startswith('odds_') or value == '':
                continue
            seleccion_id = key.removeprefix('odds_')
            seleccion = selecciones_por_id.get(seleccion_id)
            if seleccion is None:
                errores.append('Una seleccion no pertenece a este partido.')
                continue
            try:
                actualizar_odds(seleccion, value, cambiado_por=request.user if request.user.is_authenticated else None)
            except (ValueError, ValidationError) as exc:
                errores.append(str(exc))
            else:
                actualizadas += 1

        if errores:
            messages.error(request, 'No se pudo actualizar la odds. Verifica que el valor sea valido.')
        elif actualizadas:
            messages.success(request, 'Odds actualizadas correctamente.')
        else:
            messages.warning(request, 'No ingresaste odds para actualizar.')
        return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))

    @staticmethod
    def _format_error(exc):
        if hasattr(exc, 'message_dict'):
            return ' '.join(error for errors in exc.message_dict.values() for error in errors)
        if hasattr(exc, 'messages'):
            return ' '.join(exc.messages)
        return str(exc)


class EventoMercadoOddsActualizarView(DeporteOperadorRequiredMixin, View):
    def post(self, request, pk, mercado_pk):
        mercado = get_object_or_404(Mercado.objects.select_related('evento'), pk=mercado_pk, evento_id=pk)
        try:
            validar_mercado_configurable(mercado)
        except ValidationError as exc:
            messages.error(request, EventoEstadoActionView._format_error(exc))
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[mercado.evento_id]))
        selecciones = SeleccionMercado.objects.filter(mercado=mercado)
        actualizadas = 0
        for key, value in request.POST.items():
            if not key.startswith('odds_') or value == '':
                continue
            seleccion_id = key.removeprefix('odds_')
            try:
                seleccion = selecciones.get(pk=seleccion_id)
            except SeleccionMercado.DoesNotExist:
                continue
            try:
                actualizar_odds(seleccion, value, cambiado_por=request.user if request.user.is_authenticated else None)
                actualizadas += 1
            except (ValueError, ValidationError):
                pass

        # Actualizar config del mercado si se enviaron campos
        config_changed = False
        estado = request.POST.get('estado_mercado')
        if estado and estado in dict(EstadoMercado.choices):
            mercado.estado_mercado = estado
            config_changed = True
        permite = request.POST.get('permite_in_play')
        if permite is not None:
            mercado.permite_in_play = permite == 'on'
            config_changed = True
        if config_changed:
            try:
                mercado.full_clean()
                mercado.save(update_fields=['estado_mercado', 'permite_in_play'])
            except ValidationError:
                messages.warning(request, 'Configuracion del mercado no valida, solo se actualizaron las odds.')

        if actualizadas:
            messages.success(request, f'Odds de {mercado.nombre} actualizadas correctamente.')
        else:
            messages.warning(request, 'No se ingresaron odds para actualizar.')
        return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[mercado.evento_id]))


class EventoMarcadorUpdateView(DeporteOperadorRequiredMixin, View):
    """Actualiza el marcador de un evento EN_VIVO sin finalizarlo.
    El WebSocket difunde el nuevo marcador automáticamente vía señal post_save."""

    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
        form = ActualizarMarcadorEventoForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'No se pudo actualizar el marcador. Verifica los goles ingresados.')
            return HttpResponseRedirect(request.POST.get('next') or reverse('deporte:evento_detalle', args=[pk]))

        try:
            evento = actualizar_marcador_en_vivo(
                evento,
                form.cleaned_data['marcador_local'],
                form.cleaned_data['marcador_visitante'],
            )
        except (ResultadoEventoError, ValueError, ValidationError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f'Marcador actualizado: {evento.marcador_local} – {evento.marcador_visitante}',
            )
        return HttpResponseRedirect(
            request.POST.get('next') or reverse('deporte:evento_detalle', args=[pk])
        )


class EventoEstadoActionView(DeporteOperadorRequiredMixin, View):
    accion = None
    success_url = reverse_lazy('deporte:eventos_lista')

    def post(self, request, pk):
        acciones = {
            'en_vivo': (pasar_evento_en_vivo, 'Evento marcado como en vivo.'),
            'reactivar': (reactivar_evento, 'Evento reactivado correctamente.'),
            'suspender': (suspender_evento, 'Evento suspendido correctamente.'),
            'anular': (anular_evento_y_liquidar, 'Evento anulado correctamente.'),
        }
        servicio, mensaje = acciones[self.accion]
        try:
            liquidaciones = []
            if self.accion == 'anular':
                evento, liquidaciones = servicio(pk, liquidado_por=request.user)
            else:
                evento = servicio(pk)
        except (ResultadoEventoError, ValidationError) as exc:
            messages.error(request, self._format_error(exc))
        else:
            if liquidaciones:
                mensaje = f'{mensaje} Apuestas liquidadas: {len(liquidaciones)}.'
            messages.success(request, mensaje)
        return HttpResponseRedirect(request.POST.get('next') or request.META.get('HTTP_REFERER') or self.success_url)

    @staticmethod
    def _format_error(exc):
        if hasattr(exc, 'message_dict'):
            return ' '.join(error for errors in exc.message_dict.values() for error in errors)
        return str(exc)

class EventoConfirmarResultadoView(DeporteOperadorRequiredMixin, FormView):
    form_class = ConfirmarResultadoEventoForm
    template_name = 'deporte/eventos/confirmar_resultado.html'
    success_url = reverse_lazy('deporte:eventos_lista')

    def dispatch(self, request, *args, **kwargs):
        self.evento = EventoDeportivo.objects.get(pk=kwargs['pk'])
        if self.evento.estado_evento in {EstadoEvento.FINALIZADO, EstadoEvento.ANULADO} or self.evento.resultado_confirmado:
            messages.error(request, 'El partido ya fue finalizado o no permite confirmar resultado.')
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[self.evento.pk]))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['evento'] = self.evento
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['evento'] = self.evento
        return context

    def form_valid(self, form):
        try:
            evento, liquidaciones = finalizar_evento_y_liquidar(
                self.evento,
                {
                    'marcador_local': form.cleaned_data['marcador_local'],
                    'marcador_visitante': form.cleaned_data['marcador_visitante'],
                },
                liquidado_por=self.request.user,
            )
        except (ResultadoEventoError, ValidationError) as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)

        mensaje = 'Resultado confirmado correctamente.'
        if liquidaciones:
            mensaje = f'{mensaje} Apuestas liquidadas: {len(liquidaciones)}.'
        messages.success(self.request, mensaje)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('deporte:evento_detalle', args=[self.evento.pk])
