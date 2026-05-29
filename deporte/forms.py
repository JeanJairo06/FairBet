from django import forms
from django.utils import timezone

from core.choices import EstadoEvento, EstadoMercado, EstadoSeleccion
from deporte.models import EventoDeportivo, Mercado, SeleccionMercado


class EventoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        inicia_en = timezone.localtime(obj.inicia_en).strftime('%d/%m/%Y %H:%M')
        return f'{obj.equipo_local} vs {obj.equipo_visitante} - {obj.competicion} - {inicia_en}'


class SeleccionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        evento = obj.mercado.evento
        inicia_en = timezone.localtime(evento.inicia_en).strftime('%d/%m/%Y %H:%M')
        return f'{obj.nombre} ({obj.codigo_seleccion}) - {obj.mercado.nombre} - {evento} - {inicia_en}'


class BaseStyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'app-field')


class EventoDeportivoForm(BaseStyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.deporte = 'Futbol'
        self.fields['inicia_en'].input_formats = ['%Y-%m-%dT%H:%M']

    class Meta:
        model = EventoDeportivo
        fields = [
            'competicion',
            'equipo_local',
            'equipo_visitante',
            'inicia_en',
            'estado_evento',
            'marcador_local',
            'marcador_visitante',
            'resultado_confirmado',
        ]
        widgets = {
            'inicia_en': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
        }

    def save(self, commit=True):
        evento = super().save(commit=False)
        evento.deporte = 'Futbol'
        if commit:
            evento.save()
            self.save_m2m()
        return evento


class MercadoForm(BaseStyledModelForm):
    evento = EventoChoiceField(
        queryset=EventoDeportivo.objects.all().order_by('-inicia_en'),
    )

    class Meta:
        model = Mercado
        fields = [
            'evento',
            'tipo_mercado',
            'nombre',
            'estado_mercado',
            'margen_operador',
            'stake_minimo',
            'stake_maximo',
            'permite_in_play',
            'suspendido_hasta',
        ]
        widgets = {
            'suspendido_hasta': forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['suspendido_hasta'].input_formats = ['%Y-%m-%dT%H:%M']


class SeleccionMercadoForm(BaseStyledModelForm):
    class Meta:
        model = SeleccionMercado
        fields = [
            'mercado',
            'codigo_seleccion',
            'nombre',
            'estado_seleccion',
        ]


class ActualizarOddsForm(forms.Form):
    seleccion = SeleccionChoiceField(queryset=SeleccionMercado.objects.none())
    odds = forms.DecimalField(max_digits=18, decimal_places=4, min_value=1.0001)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['seleccion'].queryset = SeleccionMercado.objects.select_related('mercado__evento').filter(
            estado_seleccion=EstadoSeleccion.ACTIVA,
            mercado__estado_mercado=EstadoMercado.ABIERTO,
            mercado__evento__estado_evento__in=[EstadoEvento.PROGRAMADO, EstadoEvento.EN_VIVO],
            mercado__evento__resultado_confirmado=False,
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'app-field')
