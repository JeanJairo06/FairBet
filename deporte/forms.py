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
    mercado = forms.ModelChoiceField(queryset=Mercado.objects.select_related('evento').order_by('-created_at'))

    class Meta:
        model = SeleccionMercado
        fields = [
            'mercado',
            'codigo_seleccion',
            'nombre',
            'estado_seleccion',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['mercado'].label_from_instance = self._label_mercado

    @staticmethod
    def _label_mercado(obj):
        evento = obj.evento
        inicia_en = timezone.localtime(evento.inicia_en).strftime('%d/%m/%Y %H:%M')
        return f'{obj.nombre} - {evento} - {inicia_en}'


class MercadoPersonalizadoEventoForm(BaseStyledModelForm):
    class Meta:
        model = Mercado
        fields = [
            'tipo_mercado',
            'nombre',
            'stake_minimo',
            'stake_maximo',
            'permite_in_play',
        ]


class SeleccionInlineForm(BaseStyledModelForm):
    class Meta:
        model = SeleccionMercado
        fields = [
            'codigo_seleccion',
            'nombre',
        ]


class MercadoRapidoForm(forms.Form):
    plantilla = forms.ChoiceField(
        choices=[
            ('resultado_final', 'Resultado final 1X2'),
            ('ambos_anotan', 'Ambos equipos anotan'),
            ('total_goles', 'Total de goles'),
            ('handicap', 'Handicap'),
        ]
    )
    linea = forms.DecimalField(max_digits=8, decimal_places=2, required=False)
    stake_minimo = forms.DecimalField(max_digits=18, decimal_places=4, min_value=0.0001, initial=1)
    stake_maximo = forms.DecimalField(max_digits=18, decimal_places=4, min_value=0.0001, initial=100)

    def clean(self):
        cleaned_data = super().clean()
        plantilla = cleaned_data.get('plantilla')
        linea = cleaned_data.get('linea')
        stake_minimo = cleaned_data.get('stake_minimo')
        stake_maximo = cleaned_data.get('stake_maximo')
        if plantilla in {'total_goles', 'handicap'} and linea is None:
            self.add_error('linea', 'Ingresa la linea del mercado.')
        if stake_minimo is not None and stake_maximo is not None and stake_maximo < stake_minimo:
            self.add_error('stake_maximo', 'La apuesta maxima debe ser mayor o igual a la minima.')
        return cleaned_data


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


class ConfirmarResultadoEventoForm(forms.Form):
    marcador_local = forms.IntegerField(min_value=0)
    marcador_visitante = forms.IntegerField(min_value=0)

    def __init__(self, *args, **kwargs):
        self.evento = kwargs.pop('evento')
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'app-field')
