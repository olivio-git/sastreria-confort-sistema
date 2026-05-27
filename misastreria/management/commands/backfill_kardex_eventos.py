from django.core.management.base import BaseCommand
from django.db import transaction
from misastreria.models import PrendaItem
from misastreria import kardex_events


class Command(BaseCommand):
    help = 'Backfill KardexEvento records for existing PrendaItems (idempotent)'

    def handle(self, *args, **options):
        items = PrendaItem.objects.prefetch_related(
            'alquiler_items__alquiler__cliente',
            'venta_items__venta__cliente',
        ).all()

        total_items = items.count()
        total_eventos = 0

        self.stdout.write(f'Procesando {total_items} items...')

        with transaction.atomic():
            for item in items:
                n = kardex_events.backfill_item(item)
                total_eventos += n
                if n > 0:
                    self.stdout.write(f'  {item.codigo_item}: {n} evento(s) creado(s)')

        self.stdout.write(self.style.SUCCESS(
            f'Backfill completo: {total_eventos} evento(s) creado(s) en {total_items} item(s).'
        ))
