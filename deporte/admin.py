from django.contrib import admin

from deporte.models import EventoDeportivo, HistorialOdds, Mercado, SeleccionMercado


class MercadoInline(admin.TabularInline):
    model = Mercado
    extra = 0
    show_change_link = True


@admin.register(EventoDeportivo)
class EventoDeportivoAdmin(admin.ModelAdmin):
    list_display = ('id_evento', 'deporte', 'competicion', 'equipo_local', 'equipo_visitante', 'inicia_en', 'estado_evento', 'resultado_confirmado')
    list_filter = ('deporte', 'competicion', 'estado_evento', 'resultado_confirmado', 'inicia_en')
    search_fields = ('equipo_local', 'equipo_visitante', 'competicion', 'deporte')
    readonly_fields = ('created_at', 'updated_at')
    inlines = (MercadoInline,)
    ordering = ('-inicia_en',)


class SeleccionMercadoInline(admin.TabularInline):
    model = SeleccionMercado
    extra = 0
    show_change_link = True


@admin.register(Mercado)
class MercadoAdmin(admin.ModelAdmin):
    list_display = ('id_mercado', 'evento', 'tipo_mercado', 'nombre', 'estado_mercado', 'stake_minimo', 'stake_maximo', 'permite_in_play')
    list_filter = ('tipo_mercado', 'estado_mercado', 'permite_in_play', 'created_at')
    search_fields = ('nombre', 'evento__equipo_local', 'evento__equipo_visitante')
    autocomplete_fields = ('evento',)
    readonly_fields = ('created_at',)
    inlines = (SeleccionMercadoInline,)
    ordering = ('id_mercado',)


class HistorialOddsInline(admin.TabularInline):
    model = HistorialOdds
    extra = 0
    fields = ('odds', 'numero_version', 'activa', 'valido_desde', 'valido_hasta', 'cambiado_por')
    show_change_link = True


@admin.register(SeleccionMercado)
class SeleccionMercadoAdmin(admin.ModelAdmin):
    list_display = ('id_seleccion', 'mercado', 'codigo_seleccion', 'nombre', 'estado_seleccion', 'created_at')
    list_filter = ('estado_seleccion', 'created_at')
    search_fields = ('codigo_seleccion', 'nombre', 'mercado__nombre', 'mercado__evento__equipo_local', 'mercado__evento__equipo_visitante')
    autocomplete_fields = ('mercado',)
    readonly_fields = ('created_at',)
    inlines = (HistorialOddsInline,)
    ordering = ('id_seleccion',)


@admin.register(HistorialOdds)
class HistorialOddsAdmin(admin.ModelAdmin):
    list_display = ('id_historial_odds', 'seleccion', 'odds', 'numero_version', 'activa', 'valido_desde', 'valido_hasta', 'cambiado_por')
    list_filter = ('activa', 'valido_desde', 'valido_hasta', 'created_at')
    search_fields = ('seleccion__nombre', 'seleccion__codigo_seleccion', 'seleccion__mercado__evento__equipo_local', 'seleccion__mercado__evento__equipo_visitante')
    autocomplete_fields = ('seleccion', 'cambiado_por')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
