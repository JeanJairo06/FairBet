from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from cuentas.models import PerfilJugador, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('id_usuario', 'username', 'email', 'rol', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('rol', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email')
    ordering = ('id_usuario',)
    fieldsets = UserAdmin.fieldsets + (
        ('FairBet', {'fields': ('rol',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('FairBet', {'fields': ('email', 'rol')}),
    )


@admin.register(PerfilJugador)
class PerfilJugadorAdmin(admin.ModelAdmin):
    list_display = ('id_perfil', 'usuario', 'dni', 'nombre_completo', 'estado_cuenta', 'kyc_verificado_en')
    list_filter = ('estado_cuenta', 'created_at', 'kyc_verificado_en')
    search_fields = ('usuario__username', 'usuario__email', 'dni', 'nombres', 'apellidos')
    autocomplete_fields = ('usuario',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('id_perfil',)
