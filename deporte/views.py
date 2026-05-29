from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView, ListView, UpdateView

from deporte.forms import ActualizarOddsForm, EventoDeportivoForm, MercadoForm, SeleccionMercadoForm
from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado
from deporte.services import actualizar_odds


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
    success_url = reverse_lazy('deporte:eventos_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Evento deportivo creado correctamente.')
        return super().form_valid(form)


class EventoUpdateView(DeporteLoginRequiredMixin, UpdateView):
    model = EventoDeportivo
    form_class = EventoDeportivoForm
    template_name = 'deporte/eventos/formulario.html'
    success_url = reverse_lazy('deporte:eventos_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Evento deportivo actualizado correctamente.')
        return super().form_valid(form)


class MercadoListView(DeporteLoginRequiredMixin, ListView):
    model = Mercado
    template_name = 'deporte/mercados/lista.html'
    context_object_name = 'mercados'
    paginate_by = 10

    def get_queryset(self):
        queryset = Mercado.objects.select_related('evento').prefetch_related('selecciones').order_by('-created_at')
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
