from django.contrib import admin

from apuesta.models import Apuesta, DetalleApuesta, LiquidacionApuesta


class DetalleApuestaInline(admin.TabularInline):
    model = DetalleApuesta
    extra = 0
    fields = ('seleccion', 'odds_snapshot', 'version_odds', 'estado_detalle', 'resultada_en')
    readonly_fields = ('seleccion', 'odds_snapshot', 'version_odds', 'estado_detalle', 'resultada_en')
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Apuesta)
class ApuestaAdmin(admin.ModelAdmin):
    list_display = ('id_apuesta', 'usuario', 'tipo_apuesta', 'stake', 'odds_total', 'payout_potencial', 'estado_apuesta', 'aceptada_en', 'liquidada_en')
    list_filter = ('tipo_apuesta', 'estado_apuesta', 'aceptada_en', 'liquidada_en', 'created_at')
    search_fields = ('id_apuesta', 'usuario__username', 'usuario__email', 'idempotency_key', 'transaction_bloqueo__transaction_id')
    autocomplete_fields = ('usuario', 'transaction_bloqueo')
    readonly_fields = ('created_at',)
    inlines = (DetalleApuestaInline,)
    ordering = ('-created_at',)


@admin.register(DetalleApuesta)
class DetalleApuestaAdmin(admin.ModelAdmin):
    list_display = ('id_detalle_apuesta', 'apuesta', 'seleccion', 'odds_snapshot', 'version_odds', 'estado_detalle', 'resultada_en')
    list_filter = ('estado_detalle', 'resultada_en')
    search_fields = ('apuesta__id_apuesta', 'seleccion__nombre', 'seleccion__codigo_seleccion')
    autocomplete_fields = ('apuesta', 'seleccion')
    ordering = ('id_detalle_apuesta',)


@admin.register(LiquidacionApuesta)
class LiquidacionApuestaAdmin(admin.ModelAdmin):
    list_display = ('id_liquidacion', 'apuesta', 'resultado_liquidacion', 'payout', 'transaction_liquidacion', 'liquidado_por', 'liquidado_en')
    list_filter = ('resultado_liquidacion', 'liquidado_en')
    search_fields = ('apuesta__id_apuesta', 'transaction_liquidacion__transaction_id', 'liquidado_por__username', 'observacion')
    autocomplete_fields = ('apuesta', 'transaction_liquidacion', 'liquidado_por')
    ordering = ('-liquidado_en',)
