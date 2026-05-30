from django.apps import AppConfig


class DeporteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'deporte'

    def ready(self):
        import deporte.signals  # noqa: F401
