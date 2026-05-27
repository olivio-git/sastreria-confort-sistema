from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from misastreria.models import CajaMovimiento, Alquiler


ESTADOS_CERRADOS = ['devuelto', 'extraviado']


class Command(BaseCommand):
    help = (
        'Backfill CajaMovimiento de cobro para alquileres cerrados (devuelto/extraviado) '
        'creados antes del módulo de caja. Idempotente.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        ya_tienen = CajaMovimiento.objects.filter(
            referencia_alquiler__isnull=False,
            movimiento_reverso__isnull=True,
        ).values_list('referencia_alquiler_id', flat=True)

        pendientes = (
            Alquiler.objects
            .filter(estado__in=ESTADOS_CERRADOS, total__gt=0)
            .exclude(pk__in=ya_tienen)
            .select_related('cliente')
        )

        total = pendientes.count()
        self.stdout.write(f'Alquileres a backfill ({", ".join(ESTADOS_CERRADOS)}): {total}')

        if dry_run:
            for a in pendientes:
                self.stdout.write(f'  [DRY] {a.codigo} [{a.estado}] — Bs {a.total} — forma_pago: {a.forma_pago or "efectivo"}')
            self.stdout.write(self.style.WARNING('Dry-run: no se creó ningún registro.'))
            return

        creados = 0
        with transaction.atomic():
            for a in pendientes:
                CajaMovimiento.objects.create(
                    sesion=None,
                    tipo='ingreso',
                    concepto='alquiler_cobro',
                    origen='automatico',
                    forma_pago=a.forma_pago or 'efectivo',
                    monto=Decimal(str(a.total)),
                    fecha=timezone.now(),
                    descripcion=f'Backfill cobro alquiler {a.codigo}',
                    referencia_alquiler=a,
                    cliente=a.cliente,
                )
                creados += 1
                self.stdout.write(f'  {a.codigo} [{a.estado}] — Bs {a.total}')

        self.stdout.write(self.style.SUCCESS(f'Backfill completo: {creados} movimiento(s) creado(s).'))
