"""Archiva el inventario actual para poder cargarlo de cero desde PRN-001.

La sastrería empieza a etiquetar y quiere numerar desde 1 con la prenda física
en la mano. Borrar no es una opción: 261 de las 419 unidades están referenciadas
por ventas o alquileres con `on_delete=PROTECT`, y borrarlas exigiría borrar
antes toda la historia comercial —y con ella 927 eventos de kardex por CASCADE—.

Así que no se borra: se archiva. Cada código recibe el prefijo `H-`, el modelo
pasa a estado BAJ, y el inventario nuevo vuelve a empezar en PRN-001 sin
colisionar. La historia queda intacta y legible; simplemente deja de ofrecerse.

  manage.py cortar_inventario                 # simulacro, no toca nada
  manage.py cortar_inventario --confirmar     # aplica
  manage.py cortar_inventario --revertir --confirmar

La reversa sirve SÓLO hasta que se cargue la primera prenda nueva. Después el
código liberado ya está ocupado y volver atrás chocaría contra el `unique`: a
partir de ahí el corte es una puerta de una sola dirección y la red pasa a ser
el respaldo de la base. El comando lo detecta y se niega, en vez de reventar a
mitad de camino.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from misastreria.models import Alquiler, PrendaInventario, PrendaItem

PREFIJO = 'H-'


class Command(BaseCommand):
    help = 'Archiva el inventario actual para recargarlo desde PRN-001.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true',
                            help='Aplica los cambios. Sin esto es un simulacro.')
        parser.add_argument('--revertir', action='store_true',
                            help='Deshace el corte: quita el prefijo y reactiva.')

    def handle(self, *args, **opciones):
        revertir = opciones['revertir']
        aplicar = opciones['confirmar']

        skus = PrendaInventario.objects.filter(
            codigo__startswith=PREFIJO if revertir else PrendaInventario.PREFIJO + '-'
        ).order_by('codigo')
        if not revertir:
            # Un SKU ya archivado no se vuelve a archivar: el comando es
            # reintentable y correrlo dos veces no debe anidar prefijos.
            skus = skus.exclude(codigo__startswith=PREFIJO)

        if not skus.exists():
            self.stdout.write(self.style.WARNING(
                'No hay nada que ' + ('revertir' if revertir else 'archivar') + '.'))
            return

        items = PrendaItem.objects.filter(prenda__in=skus)
        vivos = items.filter(estado__in=('alquilado', 'reservado'))

        self.stdout.write(self.style.MIGRATE_HEADING(
            ('REVERTIR' if revertir else 'ARCHIVAR') +
            f'  ·  {skus.count()} modelos  ·  {items.count()} unidades'))
        for sku in skus[:5]:
            nuevo = (sku.codigo[len(PREFIJO):] if revertir
                     else PREFIJO + sku.codigo)
            self.stdout.write(f'    {sku.codigo:16s} → {nuevo}')
        if skus.count() > 5:
            self.stdout.write(f'    … y {skus.count() - 5} más')

        if vivos.exists() and not revertir:
            # No se les toca el estado: siguen alquiladas y su devolución tiene
            # que funcionar igual. Quedan archivadas, que es lo correcto — esa
            # prenda salió con ese registro— y al volver se cargan en el
            # inventario nuevo.
            self.stdout.write(self.style.WARNING(
                f'\n    {vivos.count()} unidades están en la calle '
                f'({Alquiler.objects.filter(estado__in=["reservado", "alquilado"]).count()} '
                f'alquileres vivos). Se archivan sin tocarles el estado: '
                f'la devolución sigue funcionando y se reetiquetan al volver.'))

        if revertir:
            # Si alguien ya cargó inventario nuevo, los códigos liberados están
            # ocupados. Se detecta ANTES de tocar nada: a mitad de camino la
            # transacción revierte igual, pero el mensaje sería un IntegrityError
            # ilegible en vez de decir qué pasó.
            ocupados = []
            existentes = set(
                PrendaInventario.objects.values_list('codigo', flat=True))
            for sku in skus:
                destino = sku.codigo[len(PREFIJO):]
                if destino in existentes:
                    ocupados.append(f'{sku.codigo} → {destino}')
            if ocupados:
                raise CommandError(
                    'No se puede revertir: ya hay inventario nuevo usando los '
                    'códigos liberados.\n  ' + '\n  '.join(ocupados[:5])
                    + (f'\n  … y {len(ocupados) - 5} más' if len(ocupados) > 5 else '')
                    + '\n\nLa reversa sólo sirve antes de cargar la primera '
                      'prenda nueva. Para volver atrás ahora hace falta el '
                      'respaldo de la base.')

        if not aplicar:
            self.stdout.write(self.style.NOTICE(
                '\n  SIMULACRO — no se tocó nada. Agregá --confirmar para aplicar.'))
            return

        with transaction.atomic():
            n_sku = n_item = 0
            for sku in list(skus):
                viejo = sku.codigo
                sku.codigo = (viejo[len(PREFIJO):] if revertir else PREFIJO + viejo)
                sku.estado = 'ACT' if revertir else 'BAJ'
                sku.save(update_fields=['codigo', 'estado'])
                n_sku += 1
                for item in sku.items.all():
                    item.codigo_item = (item.codigo_item[len(PREFIJO):] if revertir
                                        else PREFIJO + item.codigo_item)
                    item.save(update_fields=['codigo_item'])
                    n_item += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n  Listo: {n_sku} modelos y {n_item} unidades '
            + ('reactivadas.' if revertir else 'archivadas.')))
        if not revertir:
            self.stdout.write(
                f'  El próximo alta será {PrendaInventario.siguiente_codigo()}.')
