from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from misastreria.models import CajaMovimiento, Reparacion


class Command(BaseCommand):
    help = (
        'Backfill CajaMovimiento de cobro para reparaciones entregadas '
        'creadas antes del módulo de caja. Idempotente.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        ya_tienen = CajaMovimiento.objects.filter(
            referencia_reparacion__isnull=False,
            movimiento_reverso__isnull=True,
        ).values_list('referencia_reparacion_id', flat=True)

        pendientes = (
            Reparacion.objects
            .filter(estado='entregado', total__gt=0)
            .exclude(pk__in=ya_tienen)
            .select_related('cliente')
        )

        total = pendientes.count()
        self.stdout.write(f'Reparaciones entregadas a backfill: {total}')

        if dry_run:
            for r in pendientes:
                self.stdout.write(f'  [DRY] {r.codigo} — Bs {r.total} — forma_pago: {r.forma_pago or "efectivo"}')
            self.stdout.write(self.style.WARNING('Dry-run: no se creó ningún registro.'))
            return

        creados = 0
        with transaction.atomic():
            for r in pendientes:
                CajaMovimiento.objects.create(
                    sesion=None,
                    tipo='ingreso',
                    concepto='reparacion_cobro',
                    origen='automatico',
                    forma_pago=r.forma_pago or 'efectivo',
                    monto=Decimal(str(r.total)),
                    fecha=timezone.now(),
                    descripcion=f'Backfill cobro reparación {r.codigo}',
                    referencia_reparacion=r,
                    cliente=r.cliente,
                )
                creados += 1
                self.stdout.write(f'  {r.codigo} — Bs {r.total}')

        self.stdout.write(self.style.SUCCESS(f'Backfill completo: {creados} movimiento(s) creado(s).'))
