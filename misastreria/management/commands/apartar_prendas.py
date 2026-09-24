"""Aparta los SKU actuales de la numeración para reordenar el catálogo desde PRN-001.

La secretaria cargó cada prenda a medida que salía para un cliente. Los dueños
quieren numerar en orden —todos los sacos negros primero, después lo que
siga— y todavía no se etiquetó nada, así que es el momento de hacerlo.

No se puede borrar ni reiniciar: casi todas esas prendas ya están en
reservas, alquileres o ventas de clientes reales. Lo que hace este comando es
correrlas de la numeración: PRN-004 pasa a TMP-004, y sus unidades de
PRN-004-ITM-01 a TMP-004-ITM-01. Las operaciones apuntan a la unidad por id,
así que ninguna reserva se entera. Como `siguiente_codigo()` sólo mira los
PRN-, el próximo SKU que se cree vuelve a ser PRN-001.

Después, al etiquetar, cada prenda apartada NO se carga de nuevo: se abre y se
usa «Mover a otro SKU» para pasarla al SKU ordenado. El SKU TMP- se borra solo
cuando se queda sin unidades.

  manage.py apartar_prendas                      # simulacro, no toca nada
  manage.py apartar_prendas --confirmar          # aplica
  manage.py apartar_prendas --confirmar --limpiar-cortes

`--limpiar-cortes` desasigna el corte de las unidades apartadas y borra los
cortes que queden vacíos. Úsenlo si los cortes que cargaron están mal: los
correctos se asignan al mover cada prenda, con el selector de corte.

La lista que imprime es la que hay que tener a mano al etiquetar: cada prenda
con su reserva, cliente y fecha de evento, para reconocerla en la percha.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from misastreria.models import (
    AlquilerItem, Corte, PrendaInventario, PrendaItem, VentaItem,
)


def _operacion_viva(item):
    """Reserva, alquiler o venta en curso de la unidad, para reconocerla."""
    ai = (AlquilerItem.objects
          .filter(prenda_item=item, alquiler__estado__in=('reservado', 'alquilado'))
          .select_related('alquiler', 'alquiler__cliente').first())
    if ai:
        a = ai.alquiler
        evento = a.fecha_evento.strftime('%d/%m') if a.fecha_evento else '—'
        return '%s %s · %s · evento %s' % (
            a.codigo, a.estado, a.cliente if a.cliente_id else 'sin cliente', evento)
    vi = (VentaItem.objects
          .filter(prenda_item=item, venta__estado='en_proceso')
          .select_related('venta', 'venta__cliente').first())
    if vi:
        v = vi.venta
        return '%s en proceso · %s' % (v.codigo, v.cliente if v.cliente_id else 'sin cliente')
    return 'libre'


class Command(BaseCommand):
    help = 'Aparta los SKU PRN- a TMP- para reordenar el catálogo desde PRN-001.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true',
                            help='Aplica los cambios. Sin esto es un simulacro.')
        parser.add_argument('--limpiar-cortes', action='store_true',
                            help='Quita el corte a las unidades apartadas y borra '
                                 'los cortes que queden vacíos.')

    def handle(self, *args, **opciones):
        aplicar = opciones['confirmar']
        limpiar_cortes = opciones['limpiar_cortes']
        P = PrendaInventario.PREFIJO
        T = PrendaInventario.PREFIJO_APARTADO

        skus = list(PrendaInventario.objects
                    .filter(codigo__startswith=P + '-').order_by('codigo'))
        if not skus:
            self.stdout.write(self.style.WARNING(
                'No hay SKU %s- que apartar: el próximo alta ya será %s.'
                % (P, PrendaInventario.siguiente_codigo())))
            return

        nuevo = {s.id: T + s.codigo[len(P):] for s in skus}
        ocupados = sorted(PrendaInventario.objects
                          .filter(codigo__in=nuevo.values())
                          .values_list('codigo', flat=True))
        if ocupados:
            raise CommandError(
                'Ya existen SKU con estos códigos, así que apartar chocaría:\n  '
                + '\n  '.join(ocupados)
                + '\n\nTerminen de mover las prendas apartadas antes de apartar otra vez.')

        items = PrendaItem.objects.filter(prenda__in=skus)
        cortes = (Corte.objects.filter(items__in=items).distinct()
                  if limpiar_cortes else Corte.objects.none())

        self.stdout.write(self.style.MIGRATE_HEADING(
            'APARTAR  ·  %d SKU  ·  %d unidad(es)' % (len(skus), items.count())))
        for sku in skus:
            self.stdout.write('  %-10s → %-10s %s' % (sku.codigo, nuevo[sku.id], sku))
            for it in sku.items.all().order_by('codigo_item'):
                self.stdout.write('      %-18s %-11s %s' % (
                    T + it.codigo_item[len(P):], it.estado, _operacion_viva(it)))
        if limpiar_cortes:
            self.stdout.write('\n  cortes a desasignar: %s' % (
                ', '.join(str(c) for c in cortes) or 'ninguno'))

        if not aplicar:
            self.stdout.write(self.style.NOTICE(
                '\n  SIMULACRO — no se tocó nada. Agregá --confirmar para aplicar.'))
            return

        with transaction.atomic():
            ids_cortes = list(cortes.values_list('id', flat=True))
            for sku in skus:
                for it in sku.items.all():
                    it.codigo_item = T + it.codigo_item[len(P):]
                    campos = ['codigo_item']
                    if limpiar_cortes:
                        it.corte = None
                        campos.append('corte')
                    it.save(update_fields=campos)
                sku.codigo = nuevo[sku.id]
                sku.save(update_fields=['codigo'])
            borrados = 0
            if ids_cortes:
                vacios = (Corte.objects.filter(id__in=ids_cortes)
                          .annotate(n=Count('items')).filter(n=0))
                borrados = vacios.count()
                vacios.delete()

        self.stdout.write(self.style.SUCCESS(
            '\n  Listo: %d SKU apartados a %s-.' % (len(skus), T)))
        if limpiar_cortes:
            self.stdout.write('  Cortes vacíos borrados: %d.' % borrados)
        self.stdout.write('  El próximo alta será %s.' % PrendaInventario.siguiente_codigo())
