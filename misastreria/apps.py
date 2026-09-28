from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sincronizar_roles(sender, **kwargs):
    """Reaplica `roles.py::ROLES` después de cada `migrate`.

    Corre siempre (no sólo la primera vez): así, cambiar la matriz de un rol
    en `roles.py` y desplegar (que hace `migrate`) alcanza para que el cambio
    tome efecto, sin tocar ninguna vista ni correr un comando aparte.
    """
    from .roles import aplicar_roles
    aplicar_roles()


class MisastrriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'misastreria'

    def ready(self):
        from . import caja_signals  # noqa: F401
        post_migrate.connect(_sincronizar_roles, sender=self)
