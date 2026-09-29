from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from misastreria import caja_turno


class Command(BaseCommand):
    """Escape hatch para el caso «un solo Administrador» (WARNING 2 del
    reporte de verificación): la pantalla `/usuarios/` prohíbe que un
    Administrador se resetee el PIN a sí mismo (otro Administrador tiene
    que hacerlo, para no saltarse el bloqueo de 5 intentos fallidos), pero
    si sólo existe un Administrador y su PIN queda bloqueado, no hay OTRO
    Administrador que pueda entrar a resetearlo desde la web. Este comando
    requiere acceso al servidor (shell/SSH), no al sistema — es
    intencionalmente inalcanzable desde una vista."""

    help = (
        'Resetea el PIN de caja de un usuario (borra el hash y el bloqueo). '
        'Sólo desde el servidor — no hay equivalente en la interfaz web para '
        'la propia cuenta de un Administrador (ver resetear_pin_usuario).'
    )

    def add_arguments(self, parser):
        parser.add_argument('username', help='Username del usuario a resetear.')

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"No existe ningún usuario con username «{username}».")
        caja_turno.resetear_pin(user)
        self.stdout.write(self.style.SUCCESS(
            f"PIN de «{user.username}» reseteado. Deberá fijar uno nuevo en su próximo acceso a caja."
        ))
