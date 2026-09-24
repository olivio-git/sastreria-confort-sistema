"""Pasa las operaciones de cada prenda apartada (TMP-) a la prenda nueva que la reemplaza.

Los dueños cargan el catálogo desde cero, en orden, desde PRN-001 —incluidas las
prendas que ya tienen un cliente—. Las prendas viejas quedaron apartadas con
`apartar_prendas` (PRN-004 → TMP-004) y nadie las toca. Cuando terminan de
etiquetar, cada prenda física existe dos veces: la vieja (TMP-, con su reserva,
sus cobros y su garantía) y la nueva (PRN-, recién etiquetada). Este comando
une cada par: la reserva, el alquiler o la venta pasan a la nueva, y la vieja
se borra.

  manage.py conciliar_apartadas
      Lista las prendas apartadas que faltan conciliar, con su cliente. Es la
      hoja que se imprime para anotar, al etiquetar, el código nuevo de cada una.

  manage.py conciliar_apartadas TMP-004-ITM-01=PRN-015-ITM-02 TMP-005-ITM-01=PRN-021-ITM-01
      Simulacro de esos pares: valida todo y muestra qué haría.

  manage.py conciliar_apartadas ... --confirmar
      Aplica.

Por qué no se borran y se vuelven a cargar las operaciones: una tiene la prenda
en la calle con Bs 950 de garantía, otras ya cobraron. Borrarlas le haría perder
al sistema a quién hay que devolverle qué, y borrar un cobro deja un
contra-asiento en caja por plata que nunca salió.

Qué pasa de la vieja a la nueva: las líneas de alquiler y de venta, el estado
(reservado, alquilado…), las veces alquilada y el historial de kardex salvo el
ingreso —la nueva ya tiene el suyo, el del día en que se etiquetó—. Los precios
viven en cada operación, así que ningún importe cambia.

Todo o nada: si un solo par es inválido, no se aplica ninguno.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from misastreria.models import (
    AlquilerItem, KardexEvento, PrendaInventario, PrendaItem, VentaItem,
)


def _operaciones(item):
    """Las operaciones de una unidad, en texto, para reconocerla."""
    partes = []
    for ai in (AlquilerItem.objects.filter(prenda_item=item)
               .select_related('alquiler', 'alquiler__cliente')):
        a = ai.alquiler
        evento = (' · evento %s' % a.fecha_evento.strftime('%d/%m')) if a.fecha_evento else ''
        partes.append('%s %s · %s%s' % (
            a.codigo, a.estado, a.cliente if a.cliente_id else 'sin cliente', evento))
    for vi in VentaItem.objects.filter(prenda_item=item).select_related('venta', 'venta__cliente'):
        v = vi.venta
        partes.append('%s %s · %s' % (
            v.codigo, v.estado, v.cliente if v.cliente_id else 'sin cliente'))
    return '; '.join(partes) or 'sin operaciones'


def _tiene_operaciones(item):
    return (AlquilerItem.objects.filter(prenda_item=item).exists()
            or VentaItem.objects.filter(prenda_item=item).exists())


class Command(BaseCommand):
    help = 'Pasa las operaciones de cada prenda apartada (TMP-) a la prenda nueva que la reemplaza.'

    def add_arguments(self, parser):
        parser.add_argument('pares', nargs='*', metavar='VIEJA=NUEVA',
                            help='Pares de códigos de unidad, ej. TMP-004-ITM-01=PRN-015-ITM-02')
        parser.add_argument('--confirmar', action='store_true',
                            help='Aplica los cambios. Sin esto es un simulacro.')

    def handle(self, *args, **opciones):
        T = PrendaInventario.PREFIJO_APARTADO
        P = PrendaInventario.PREFIJO

        if not opciones['pares']:
            self._listar(T)
            return

        # ── Leer y validar TODOS los pares antes de tocar nada ──────────────
        problemas, pares = [], []
        vistos_viejo, vistos_nuevo = set(), set()
        for texto in opciones['pares']:
            if texto.count('=') != 1:
                problemas.append('«%s»: el formato es VIEJA=NUEVA' % texto)
                continue
            cod_viejo, cod_nuevo = (c.strip().upper() for c in texto.split('='))
            if cod_viejo in vistos_viejo:
                problemas.append('%s aparece dos veces' % cod_viejo)
            if cod_nuevo in vistos_nuevo:
                problemas.append('%s aparece dos veces: una prenda nueva reemplaza a una sola vieja' % cod_nuevo)
            vistos_viejo.add(cod_viejo)
            vistos_nuevo.add(cod_nuevo)

            viejo = PrendaItem.objects.filter(codigo_item__iexact=cod_viejo).select_related('prenda').first()
            nuevo = PrendaItem.objects.filter(codigo_item__iexact=cod_nuevo).select_related('prenda').first()
            if not viejo:
                problemas.append('%s no existe' % cod_viejo)
            elif not viejo.codigo_item.startswith(T + '-'):
                problemas.append('%s no es una prenda apartada (%s-)' % (cod_viejo, T))
            if not nuevo:
                problemas.append('%s no existe' % cod_nuevo)
            elif not nuevo.codigo_item.startswith(P + '-'):
                problemas.append('%s no es del catálogo nuevo (%s-)' % (cod_nuevo, P))
            elif _tiene_operaciones(nuevo):
                problemas.append('%s ya tiene operaciones propias (%s): no es una prenda recién '
                                 'cargada' % (cod_nuevo, _operaciones(nuevo)))
            elif nuevo.estado != 'disponible':
                problemas.append('%s está %s: la prenda nueva tiene que estar disponible'
                                 % (cod_nuevo, nuevo.get_estado_display().lower()))
            if viejo and nuevo:
                pares.append((viejo, nuevo))

        if problemas:
            raise CommandError('No se aplicó ningún par:\n  ' + '\n  '.join(problemas))

        self.stdout.write(self.style.MIGRATE_HEADING('CONCILIAR  ·  %d par(es)' % len(pares)))
        for viejo, nuevo in pares:
            self.stdout.write('  %-18s → %-18s %s' % (viejo.codigo_item, nuevo.codigo_item, nuevo.prenda))
            self.stdout.write('      %s · estado %s' % (_operaciones(viejo), viejo.get_estado_display().lower()))

        if not opciones['confirmar']:
            self.stdout.write(self.style.NOTICE(
                '\n  SIMULACRO — no se tocó nada. Agregá --confirmar para aplicar.'))
            return

        skus_viejos = set()
        with transaction.atomic():
            for viejo, nuevo in pares:
                AlquilerItem.objects.filter(prenda_item=viejo).update(prenda_item=nuevo)
                VentaItem.objects.filter(prenda_item=viejo).update(prenda_item=nuevo)
                (KardexEvento.objects.filter(prenda_item=viejo)
                 .exclude(tipo='ingreso').update(prenda_item=nuevo))
                nuevo.estado = viejo.estado
                nuevo.veces_alquilado = viejo.veces_alquilado
                nuevo.save(update_fields=['estado', 'veces_alquilado', 'actualizado'])
                skus_viejos.add(viejo.prenda_id)
                viejo.delete()

            vacios = (PrendaInventario.objects
                      .filter(id__in=skus_viejos, codigo__startswith=T + '-', items__isnull=True))
            borrados = list(vacios.values_list('codigo', flat=True))
            vacios.delete()

        self.stdout.write(self.style.SUCCESS('\n  Listo: %d prenda(s) conciliadas.' % len(pares)))
        if borrados:
            self.stdout.write('  SKU apartados que quedaron vacíos y se borraron: %s' % ', '.join(borrados))
        pendientes = PrendaItem.objects.filter(codigo_item__startswith=T + '-').count()
        self.stdout.write('  Prendas apartadas que faltan: %d' % pendientes)

    def _listar(self, T):
        items = (PrendaItem.objects.filter(codigo_item__startswith=T + '-')
                 .select_related('prenda').order_by('codigo_item'))
        if not items.exists():
            self.stdout.write(self.style.SUCCESS('No quedan prendas apartadas: todo conciliado.'))
            return
        self.stdout.write(self.style.MIGRATE_HEADING(
            'PRENDAS APARTADAS  ·  %d  ·  anotá el código nuevo de cada una al etiquetarla'
            % items.count()))
        for it in items:
            p = it.prenda
            self.stdout.write('\n  %-16s %s · talla %s · %s' % (
                it.codigo_item, p.nombre, p.talla or '—', p.color or '—'))
            self.stdout.write('      %s' % _operaciones(it))
            self.stdout.write('      código nuevo: ____________________')
