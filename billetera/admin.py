from django.contrib import admin

from billetera.models import Cuenta, LedgerEntry, TransaccionLedger
from core.choices import EstadoTransaccionLedger


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ('id_cuenta', 'codigo', 'nombre', 'tipo_cuenta', 'usuario', 'estado', 'created_at')
    list_filter = ('tipo_cuenta', 'estado', 'created_at')
    search_fields = ('codigo', 'nombre', 'usuario__username', 'usuario__email')
    autocomplete_fields = ('usuario',)
    readonly_fields = ('created_at',)
    ordering = ('id_cuenta',)


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    fields = ('cuenta', 'direction', 'amount', 'created_at')
    readonly_fields = ('cuenta', 'direction', 'amount', 'created_at')
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(TransaccionLedger)
class TransaccionLedgerAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'usuario', 'tipo_transaccion', 'estado', 'idempotency_key', 'created_at')
    list_filter = ('tipo_transaccion', 'estado', 'created_at')
    search_fields = ('transaction_id', 'idempotency_key', 'tipo_referencia', 'id_referencia', 'usuario__username')
    autocomplete_fields = ('usuario',)
    readonly_fields = ('transaction_id', 'created_at')
    inlines = (LedgerEntryInline,)
    ordering = ('-created_at',)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.estado in {EstadoTransaccionLedger.COMPLETED, EstadoTransaccionLedger.REVERSED}:
            return tuple(field.name for field in self.model._meta.fields)
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('id_ledger_entry', 'transaccion', 'cuenta', 'direction', 'amount', 'created_at')
    list_filter = ('direction', 'created_at')
    search_fields = ('transaccion__transaction_id', 'cuenta__codigo', 'cuenta__nombre')
    autocomplete_fields = ('transaccion', 'cuenta')
    readonly_fields = ('id_ledger_entry', 'transaccion', 'cuenta', 'direction', 'amount', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
