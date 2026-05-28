from django.apps import AppConfig


class JuegoResponsableConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'juego_responsable'
    verbose_name = 'Juego Responsable'

    def ready(self):
        import juego_responsable.signals