from django.contrib import admin

from juego_responsable.models import Autoexclusion, LimiteJuegoResponsable


@admin.register(LimiteJuegoResponsable)
class LimiteJuegoResponsableAdmin(admin.ModelAdmin):
    list_display = ('id_limite', 'usuario', 'periodo', 'limite_actual', 'limite_pendiente', 'pendiente_aplicar_en')
    list_filter = ('periodo', 'created_at', 'updated_at')
    search_fields = ('usuario__username', 'usuario__email')
    autocomplete_fields = ('usuario',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('usuario', 'periodo')


@admin.register(Autoexclusion)
class AutoexclusionAdmin(admin.ModelAdmin):
    list_display = ('id_autoexclusion', 'usuario', 'tipo_autoexclusion', 'inicia_en', 'finaliza_en', 'activa')
    list_filter = ('tipo_autoexclusion', 'activa', 'inicia_en', 'finaliza_en')
    search_fields = ('usuario__username', 'usuario__email', 'motivo')
    autocomplete_fields = ('usuario',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
