from django.core.management.base import BaseCommand

from misastreria.models import TipoGasto


TIPOS_GASTO = [
    {'nombre': 'Servicios Básicos', 'descripcion': 'Agua, luz, internet y otros servicios básicos'},
    {'nombre': 'Alquiler Local', 'descripcion': 'Alquiler del local o espacio de trabajo'},
    {'nombre': 'Sueldos', 'descripcion': 'Pagos de sueldos y salarios al personal'},
    {'nombre': 'Mantenimiento', 'descripcion': 'Mantenimiento y reparación de equipos e instalaciones'},
    {'nombre': 'Materiales', 'descripcion': 'Compra de materiales e insumos para producción'},
    {'nombre': 'Otros', 'descripcion': 'Gastos varios no clasificados en otras categorías'},
]


class Command(BaseCommand):
    help = 'Crea los tipos de gasto predeterminados (idempotente)'

    def handle(self, *args, **options):
        created_count = 0
        for data in TIPOS_GASTO:
            obj, created = TipoGasto.objects.get_or_create(
                nombre=data['nombre'],
                defaults={'descripcion': data['descripcion'], 'activo': True},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Creado: {obj.nombre}'))
            else:
                self.stdout.write(f'  Ya existe: {obj.nombre}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSeed completado: {created_count} nuevos, {len(TIPOS_GASTO) - created_count} ya existían.'
            )
        )
