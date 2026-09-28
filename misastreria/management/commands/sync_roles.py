from django.core.management.base import BaseCommand

from misastreria.roles import ROLES, aplicar_roles


class Command(BaseCommand):
    help = (
        'Reaplica misastreria/roles.py::ROLES sobre los grupos Administrador, '
        'Cajero, Vendedor y Taller (idempotente). Correr después de editar el '
        'diccionario ROLES si no se va a hacer un `migrate` completo.'
    )

    def handle(self, *args, **options):
        aplicar_roles()
        for nombre in ROLES:
            self.stdout.write(self.style.SUCCESS(f'  Sincronizado: {nombre}'))
        self.stdout.write(self.style.SUCCESS('\nRoles sincronizados desde roles.py.'))
