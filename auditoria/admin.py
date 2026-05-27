from django.contrib import admin

from auditoria.models import AuditoriaInmutable


@admin.register(AuditoriaInmutable)
class AuditoriaInmutableAdmin(admin.ModelAdmin):
    list_display = ('id_auditoria', 'numero_secuencia', 'accion', 'tipo_entidad', 'id_entidad', 'usuario_actor', 'created_at')
    list_filter = ('accion', 'tipo_entidad', 'created_at')
    search_fields = ('numero_secuencia', 'accion', 'tipo_entidad', 'id_entidad', 'hash_actual', 'usuario_actor__username')
    autocomplete_fields = ('usuario_actor',)
    readonly_fields = (
        'numero_secuencia',
        'hash_anterior',
        'payload_json',
        'hash_actual',
        'usuario_actor',
        'accion',
        'tipo_entidad',
        'id_entidad',
        'created_at',
    )
    ordering = ('-numero_secuencia',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
