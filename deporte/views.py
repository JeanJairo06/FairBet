from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from apuesta.servicios import liquidar_apuestas_de_evento
from deporte.forms import (
    ActualizarOddsForm,
    ConfirmarResultadoEventoForm,
    EventoDeportivoForm,
    MercadoPersonalizadoEventoForm,
    MercadoRapidoForm,
    MercadoForm,
    SeleccionInlineForm,
    SeleccionMercadoForm,
)
from deporte.exceptions import ResultadoEventoError
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado
from deporte.services import (
    actualizar_odds,
    anular_evento,
    confirmar_resultado_evento,
    crear_mercado_rapido,
    crear_seleccion,
    marcar_seleccion_ganadora,
    pasar_evento_en_vivo,
    reactivar_evento,
    suspender_evento,
)


class DeporteLoginRequiredMixin(LoginRequiredMixin):
    login_url = 'login'


class EventoListView(DeporteLoginRequiredMixin, ListView):
    model = EventoDeportivo
    template_name = 'deporte/eventos/lista.html'
    context_object_name = 'eventos'
    paginate_by = 10

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
        ).order_by('-inicia_en')
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(competicion__icontains=q)
                | Q(equipo_local__icontains=q)
                | Q(equipo_visitante__icontains=q)
            )
        return queryset


class EventoCreateView(DeporteLoginRequiredMixin, CreateView):
    model = EventoDeportivo
    form_class = EventoDeportivoForm
    template_name = 'deporte/eventos/formulario.html'

    def form_valid(self, form):
        messages.success(self.request, 'Partido creado correctamente. Ahora configura sus mercados y odds.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('deporte:evento_detalle', args=[self.object.pk])


class EventoUpdateView(DeporteLoginRequiredMixin, UpdateView):
    model = EventoDeportivo
    form_class = EventoDeportivoForm
    template_name = 'deporte/eventos/formulario.html'
    success_url = reverse_lazy('deporte:eventos_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Evento deportivo actualizado correctamente.')
        return super().form_valid(form)


class EventoDetailView(DeporteLoginRequiredMixin, DetailView):
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
        selecciones_total = 0
        odds_vigentes_total = 0

        for mercado in mercados:
            mercado.selecciones_workspace = list(mercado.selecciones.all())
            for seleccion in mercado.selecciones_workspace:
                historial = list(seleccion.historial_odds.all())
                seleccion.odds_vigente = next((odds for odds in historial if odds.activa), None)
                seleccion.historial_reciente = historial[:4]
                selecciones_total += 1
                if seleccion.odds_vigente:
                    odds_vigentes_total += 1

        tiene_mercados = bool(mercados)
        tiene_selecciones = selecciones_total > 0
        tiene_odds = tiene_selecciones and odds_vigentes_total >= selecciones_total
        listo = tiene_mercados and tiene_selecciones and tiene_odds

        context.update(
            {
                'mercados': mercados,
                'historial_odds_reciente': HistorialOdds.objects.select_related('seleccion__mercado').filter(
                    seleccion__mercado__evento=evento
                ).order_by('-created_at')[:12],
                'mercado_rapido_form': MercadoRapidoForm(),
                'mercado_personalizado_form': MercadoPersonalizadoEventoForm(
                    initial={'stake_minimo': '1.0000', 'stake_maximo': '100.0000'}
                ),
                'seleccion_inline_form': SeleccionInlineForm(),
                'resultado_form': ConfirmarResultadoEventoForm(evento=evento),
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


class MercadoListView(DeporteLoginRequiredMixin, ListView):
    model = Mercado
    template_name = 'deporte/mercados/lista.html'
    context_object_name = 'mercados'
    paginate_by = 10

    def get_queryset(self):
        queryset = Mercado.objects.select_related('evento').prefetch_related('selecciones').order_by('-created_at')
        evento_id = self.request.GET.get('evento')
        if evento_id:
            queryset = queryset.filter(evento_id=evento_id)
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(nombre__icontains=q)
                | Q(evento__equipo_local__icontains=q)
                | Q(evento__equipo_visitante__icontains=q)
                | Q(evento__competicion__icontains=q)
            )
        return queryset


class MercadoCreateView(DeporteLoginRequiredMixin, CreateView):
    model = Mercado
    form_class = MercadoForm
    template_name = 'deporte/mercados/formulario.html'
    success_url = reverse_lazy('deporte:mercados_lista')

    def get_initial(self):
        initial = super().get_initial()
        evento_id = self.request.GET.get('evento')
        if evento_id:
            initial['evento'] = evento_id
        return initial

    def form_valid(self, form):
        messages.success(self.request, 'Mercado creado correctamente.')
        return super().form_valid(form)


class MercadoUpdateView(DeporteLoginRequiredMixin, UpdateView):
    model = Mercado
    form_class = MercadoForm
    template_name = 'deporte/mercados/formulario.html'
    success_url = reverse_lazy('deporte:mercados_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Mercado actualizado correctamente.')
        return super().form_valid(form)


class SeleccionListView(DeporteLoginRequiredMixin, ListView):
    model = SeleccionMercado
    template_name = 'deporte/selecciones/lista.html'
    context_object_name = 'selecciones'
    paginate_by = 10

    def get_queryset(self):
        queryset = SeleccionMercado.objects.select_related('mercado__evento').order_by('-created_at')
        mercado_id = self.request.GET.get('mercado')
        if mercado_id:
            queryset = queryset.filter(mercado_id=mercado_id)
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(codigo_seleccion__icontains=q)
                | Q(nombre__icontains=q)
                | Q(mercado__nombre__icontains=q)
                | Q(mercado__evento__equipo_local__icontains=q)
                | Q(mercado__evento__equipo_visitante__icontains=q)
            )
        return queryset


class SeleccionCreateView(DeporteLoginRequiredMixin, CreateView):
    model = SeleccionMercado
    form_class = SeleccionMercadoForm
    template_name = 'deporte/selecciones/formulario.html'
    success_url = reverse_lazy('deporte:selecciones_lista')

    def get_initial(self):
        initial = super().get_initial()
        mercado_id = self.request.GET.get('mercado')
        if mercado_id:
            initial['mercado'] = mercado_id
        return initial

    def form_valid(self, form):
        messages.success(self.request, 'Seleccion creada correctamente.')
        return super().form_valid(form)


class SeleccionUpdateView(DeporteLoginRequiredMixin, UpdateView):
    model = SeleccionMercado
    form_class = SeleccionMercadoForm
    template_name = 'deporte/selecciones/formulario.html'
    success_url = reverse_lazy('deporte:selecciones_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Seleccion actualizada correctamente.')
        return super().form_valid(form)


class OddsListView(DeporteLoginRequiredMixin, ListView):
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


class OddsUpdateView(DeporteLoginRequiredMixin, FormView):
    form_class = ActualizarOddsForm
    template_name = 'deporte/odds/formulario.html'
    success_url = reverse_lazy('deporte:odds_lista')

    def get_initial(self):
        initial = super().get_initial()
        seleccion_id = self.request.GET.get('seleccion')
        if seleccion_id:
            initial['seleccion'] = seleccion_id
        return initial

    def form_valid(self, form):
        try:
            actualizar_odds(
                seleccion=form.cleaned_data['seleccion'],
                odds=form.cleaned_data['odds'],
                cambiado_por=self.request.user if self.request.user.is_authenticated else None,
            )
        except ValidationError as exc:
            if hasattr(exc, 'message_dict'):
                for field_name, errors in exc.message_dict.items():
                    target_field = field_name if field_name in form.fields else None
                    for error in errors:
                        form.add_error(target_field, error)
            else:
                form.add_error(None, exc)
            return self.form_invalid(form)

        messages.success(self.request, 'Odds actualizada y version anterior cerrada correctamente.')
        return super().form_valid(form)


class EventoMercadoRapidoView(DeporteLoginRequiredMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
        form = MercadoRapidoForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'No se pudo crear el mercado. Verifica los datos ingresados.')
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))

        try:
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
        return str(exc)


class EventoMercadoPersonalizadoView(DeporteLoginRequiredMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
        form = MercadoPersonalizadoEventoForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'No se pudo crear el mercado personalizado. Revisa los campos.')
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[evento.pk]))

        try:
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


class MercadoSeleccionCrearView(DeporteLoginRequiredMixin, View):
    def post(self, request, pk):
        mercado = get_object_or_404(Mercado.objects.select_related('evento'), pk=pk)
        form = SeleccionInlineForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'No se pudo agregar la seleccion. Revisa codigo y nombre.')
            return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[mercado.evento_id]))

        try:
            crear_seleccion(mercado, form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, EventoEstadoActionView._format_error(exc))
        else:
            messages.success(request, 'Seleccion agregada correctamente.')
        return HttpResponseRedirect(reverse('deporte:evento_detalle', args=[mercado.evento_id]))


class EventoOddsActualizarView(DeporteLoginRequiredMixin, View):
    def post(self, request, pk):
        evento = get_object_or_404(EventoDeportivo, pk=pk)
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


class EventoEstadoActionView(DeporteLoginRequiredMixin, View):
    accion = None
    success_url = reverse_lazy('deporte:eventos_lista')

    def post(self, request, pk):
        acciones = {
            'en_vivo': (pasar_evento_en_vivo, 'Evento marcado como en vivo.'),
            'reactivar': (reactivar_evento, 'Evento reactivado correctamente.'),
            'suspender': (suspender_evento, 'Evento suspendido correctamente.'),
            'anular': (anular_evento, 'Evento anulado correctamente.'),
        }
        servicio, mensaje = acciones[self.accion]
        try:
            evento = servicio(pk)
            liquidaciones = []
            if self.accion == 'anular':
                liquidaciones = liquidar_apuestas_de_evento(
                    evento,
                    liquidado_por=request.user,
                    observacion='Liquidacion automatica por anulacion de evento.',
                )
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

class EventoConfirmarResultadoView(DeporteLoginRequiredMixin, FormView):
    form_class = ConfirmarResultadoEventoForm
    template_name = 'deporte/eventos/confirmar_resultado.html'
    success_url = reverse_lazy('deporte:eventos_lista')

    def dispatch(self, request, *args, **kwargs):
        self.evento = EventoDeportivo.objects.get(pk=kwargs['pk'])
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
            confirmar_resultado_evento(
                self.evento,
                {
                    'marcador_local': form.cleaned_data['marcador_local'],
                    'marcador_visitante': form.cleaned_data['marcador_visitante'],
                },
            )
            liquidaciones = []
            if form.cleaned_data['seleccion_ganadora']:
                marcar_seleccion_ganadora(form.cleaned_data['seleccion_ganadora'])
                liquidaciones = liquidar_apuestas_de_evento(
                    self.evento,
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
        return self.request.META.get('HTTP_REFERER') or reverse('deporte:evento_detalle', args=[self.evento.pk])
