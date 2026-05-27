from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from misastreria.models import CajaMovimiento, Confeccion


class Command(BaseCommand):
    help = (
        'Backfill CajaMovimiento de adelanto para confecciones creadas antes de pagos-confeccion. '
        'Idempotente: salta confecciones que ya tienen movimiento confeccion_adelanto.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra qué haría sin crear registros.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Confecciones con adelanto > 0 que NO tienen ningún CajaMovimiento de tipo confeccion_adelanto
        ya_tienen = CajaMovimiento.objects.filter(
            concepto='confeccion_adelanto',
            movimiento_reverso__isnull=True,
        ).values_list('referencia_confeccion_id', flat=True)

        pendientes = (
            Confeccion.objects
            .filter(adelanto__gt=0)
            .exclude(pk__in=ya_tienen)
            .select_related('cliente')
        )

        total = pendientes.count()
        self.stdout.write(f'Confecciones a backfill: {total}')

        if dry_run:
            for c in pendientes:
                self.stdout.write(f'  [DRY] {c.codigo} — adelanto Bs {c.adelanto} — forma_pago: {c.forma_pago or "efectivo"}')
            self.stdout.write(self.style.WARNING('Dry-run: no se creó ningún registro.'))
            return

        creados = 0
        with transaction.atomic():
            for c in pendientes:
                CajaMovimiento.objects.create(
                    sesion=None,
                    tipo='ingreso',
                    concepto='confeccion_adelanto',
                    origen='automatico',
                    forma_pago=c.forma_pago or 'efectivo',
                    monto=Decimal(str(c.adelanto)),
                    fecha=timezone.now(),
                    descripcion=f'Backfill adelanto confección {c.codigo}',
                    referencia_confeccion=c,
                    cliente=c.cliente,
                )
                creados += 1
                self.stdout.write(f'  {c.codigo} — Bs {c.adelanto}')

        self.stdout.write(self.style.SUCCESS(f'Backfill completo: {creados} movimiento(s) creado(s).'))
