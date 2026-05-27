from django.apps import AppConfig


class MisastrriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'misastreria'

    def ready(self):
        from . import caja_signals  # noqa: F401
