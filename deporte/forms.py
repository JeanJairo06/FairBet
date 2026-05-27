from django import forms

from deporte.models import EventoDeportivo, Mercado, SeleccionMercado


class BaseStyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'app-field')


class EventoDeportivoForm(BaseStyledModelForm):
    class Meta:
        model = EventoDeportivo
        fields = [
            'deporte',
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
            'inicia_en': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class MercadoForm(BaseStyledModelForm):
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
            'suspendido_hasta': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


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
    seleccion = forms.ModelChoiceField(queryset=SeleccionMercado.objects.select_related('mercado__evento'))
    odds = forms.DecimalField(max_digits=18, decimal_places=4, min_value=1.0001)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'app-field')
