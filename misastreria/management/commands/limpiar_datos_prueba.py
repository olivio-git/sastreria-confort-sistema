"""Borra el inventario cargado DESPUÉS del corte y las operaciones que lo usaron.

Tras `cortar_inventario` la sastrería probó el circuito completo —cargar una
prenda, etiquetarla, venderla, cobrarla— sobre datos inventados. Esas pruebas
dejaron `PRN-001` ocupado por un saco que no existe, unos cortes con siglas de
relleno y varias ventas con saldos que nadie debe. Si se empieza a cargar en
serio encima, el primer modelo real queda numerado PRN-002 y los reportes de
«por cobrar» mezclan deuda real con deuda de prueba.

El alcance no se define por fecha sino por los datos, que es lo que se puede
verificar: todo modelo SIN el prefijo `H-` nació después del corte, y por lo
tanto es de prueba. De ahí salen sus unidades, sus cortes y las operaciones que
las consumieron.

  manage.py limpiar_datos_prueba              # simulacro, no toca nada
  manage.py limpiar_datos_prueba --confirmar  # aplica

Una operación que mezcle una unidad nueva con una archivada (`H-`) NO se borra:
sería historia real. El comando la reporta y se detiene sin aplicar nada, en
vez de decidir por su cuenta.

Borrar una venta dispara `servicio_pre_delete_reversar_caja`, que genera los
contra-asientos: la caja queda consistente y auditable, no se borra historia
contable. Conviene correrlo con la caja abierta.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from misastreria.models import (
    Alquiler, AlquilerItem, Corte, OrdenProduccion, PrendaInventario,
    PrendaItem, Venta, VentaItem,
)

ARCHIVADO = 'H-'


class Command(BaseCommand):
    help = 'Borra el inventario de prueba cargado después del corte y sus operaciones.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true',
                            help='Aplica los cambios. Sin esto es un simulacro.')

    def handle(self, *args, **opciones):
        aplicar = opciones['confirmar']

        # Seguro contra el peor escenario posible. El alcance se define por
        # negación —«lo que NO está archivado»— y esa definición sólo es válida
        # DESPUÉS del corte. En una base sin corte, «lo que no empieza con H-»
        # es el inventario entero: correr esto ahí lo borraría todo, con sus
        # ventas y sus alquileres. No hay deshacer, así que se verifica antes.
        if not PrendaInventario.objects.filter(
                codigo__startswith=ARCHIVADO).exists():
            raise CommandError(
                'No hay ningún modelo archivado (H-), así que en esta base '
                'nunca se corrió `cortar_inventario`.\n\nEste comando asume '
                'ese corte: sin él, "todo lo que no empieza con H-" es el '
                'inventario COMPLETO y esto lo borraría entero. Abortado.')

        prendas = PrendaInventario.objects.exclude(codigo__startswith=ARCHIVADO)
        if not prendas.exists():
            self.stdout.write(self.style.WARNING(
                'No hay inventario posterior al corte: nada que limpiar.'))
            return

        items = PrendaItem.objects.filter(prenda__in=prendas)
        ventas = Venta.objects.filter(items__prenda_item__in=items).distinct()
        alquileres = Alquiler.objects.filter(items__prenda_item__in=items).distinct()

        # Una operación que además toca inventario archivado es historia real.
        # Se detecta ANTES de borrar nada: a mitad de camino la transacción
        # revierte igual, pero el mensaje sería un error de FK ilegible.
        mezcladas = []
        for venta in ventas:
            if VentaItem.objects.filter(
                    venta=venta,
                    prenda_item__prenda__codigo__startswith=ARCHIVADO).exists():
                mezcladas.append(venta.codigo)
        for alquiler in alquileres:
            if AlquilerItem.objects.filter(
                    alquiler=alquiler,
                    prenda_item__prenda__codigo__startswith=ARCHIVADO).exists():
                mezcladas.append(alquiler.codigo)

        ordenes = OrdenProduccion.objects.filter(prenda_inventario__in=prendas)
        cortes = Corte.objects.all()

        self.stdout.write(self.style.MIGRATE_HEADING(
            'LIMPIAR DATOS DE PRUEBA  ·  %d modelo(s)  ·  %d unidad(es)'
            % (prendas.count(), items.count())))

        for prenda in prendas:
            self.stdout.write('    %-10s %s' % (prenda.codigo, prenda.nombre))
        self.stdout.write('')
        self.stdout.write('    ventas a borrar     : %d  %s' % (
            ventas.count(), ', '.join(v.codigo for v in ventas[:8])))
        self.stdout.write('    alquileres a borrar : %d  %s' % (
            alquileres.count(), ', '.join(a.codigo for a in alquileres[:8])))
        self.stdout.write('    cortes a borrar     : %d  %s' % (
            cortes.count(), ', '.join(c.numero for c in cortes[:8])))

        if mezcladas:
            raise CommandError(
                'Estas operaciones mezclan inventario nuevo con inventario '
                'archivado, así que son historia real y no se borran:\n  '
                + '\n  '.join(mezcladas)
                + '\n\nQuitales la prenda nueva a mano y volvé a correr el comando.')

        if ordenes.exists():
            raise CommandError(
                'Hay órdenes de producción apuntando a estos modelos '
                '(%s). Resolvelas antes: el borrado las dejaría rotas.'
                % ', '.join(o.codigo for o in ordenes[:5]))

        if not aplicar:
            self.stdout.write(self.style.NOTICE(
                '\n  SIMULACRO — no se tocó nada. Agregá --confirmar para aplicar.'))
            return

        with transaction.atomic():
            # El orden lo imponen los PROTECT: las operaciones sueltan las
            # unidades, las unidades sueltan los cortes, y recién ahí caen los
            # modelos. Borrar una venta reversa sus movimientos de caja.
            n_ventas = ventas.count()
            for venta in list(ventas):
                venta.delete()

            n_alquileres = alquileres.count()
            for alquiler in list(alquileres):
                alquiler.delete()

            n_items = items.count()
            items.delete()

            n_prendas = prendas.count()
            prendas.delete()

            n_cortes = cortes.count()
            cortes.delete()

        self.stdout.write(self.style.SUCCESS(
            '\n  Listo: %d venta(s), %d alquiler(es), %d unidad(es), '
            '%d modelo(s) y %d corte(s) eliminados.'
            % (n_ventas, n_alquileres, n_items, n_prendas, n_cortes)))
        self.stdout.write('  El próximo alta será %s.'
                          % PrendaInventario.siguiente_codigo())
