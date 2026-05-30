from django.apps import AppConfig


class ApuestaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apuesta'

    def ready(self):
        import apuesta.signals  # noqa: F401
