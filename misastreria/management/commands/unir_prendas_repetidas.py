"""Une los SKU repetidos del catálogo en uno solo por modelo.

Al cargar el catálogo nuevo (desde PRN-001) se creó un SKU por cada prenda
física: cinco sacos iguales quedaron como cinco SKU con una unidad cada uno,
en vez de un SKU con cinco unidades. Este comando los junta antes de etiquetar.

Dos SKU son el mismo modelo si coinciden nombre, modelo, talla y color, sin
distinguir mayúsculas, espacios de más ni guion contra espacio («NEGRO-MARENGO»
es «NEGRO MARENGO»). En cada grupo se queda el SKU de número más bajo; las
unidades de los demás se mueven a él, en el orden de su código, y los SKU que
quedan vacíos se borran.

Mover una unidad le cambia el código (PRN-022-ITM-01 pasa a PRN-021-ITM-02),
igual que «Mover a otro SKU». Las reservas, alquileres y ventas apuntan a la
unidad por id y guardan su propio precio, así que no se enteran. Las órdenes de
producción que apuntaban a un SKU borrado pasan al que se queda.

Un grupo cuyos SKU difieren en precio, precio de alquiler, mínimo o máximo de
usos NO se une: no hay forma segura de elegir cuál vale. Se informa para que lo
corrijan a mano. El tipo de prenda sí puede diferir (hay «Saco» y «SACO»
repetidos en TipoPrenda): queda el del SKU que se conserva.

Del resto de los datos del SKU no se pierde nada en silencio: las notas de los
borrados se agregan a las del que queda, el stock mínimo se toma si el que
queda no tiene, y el código de referencia que se descarta se informa.

Todo corre en una sola transacción, con los SKU bloqueados, y antes de borrar
un SKU se verifica que quedó vacío: si alguien le cargó una unidad mientras
tanto, se aborta todo en vez de borrarla en cascada.

  manage.py unir_prendas_repetidas               # simulacro, no toca nada
  manage.py unir_prendas_repetidas --confirmar   # aplica

La lista que imprime (código viejo → código nuevo) es la que hay que usar al
etiquetar.
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from misastreria.models import PrendaInventario, PrendaItem

# Lo que tiene que coincidir para que juntar dos SKU no cambie ningún precio.
CAMPOS_QUE_DEBEN_COINCIDIR = (
    'precio', 'precio_alquiler_base', 'precio_alquiler_minimo_pct',
    'max_usos_default',
)


def _normalizar(texto):
    texto = (texto or '').upper().replace('-', ' ')
    return re.sub(r'\s+', ' ', texto).strip()


def clave_modelo(prenda):
    return tuple(_normalizar(getattr(prenda, campo))
                 for campo in ('nombre', 'modelo', 'talla', 'color'))


def _numero(prenda):
    sufijo = prenda.codigo.split('-', 1)[1]
    return int(sufijo) if sufijo.isdigit() else float('inf')


def grupos_repetidos():
    """[(destino, [origenes])] de los SKU activos del catálogo con el mismo
    modelo, más [(clave, [skus], campos)] de los que no se pueden unir."""
    grupos = {}
    for prenda in (PrendaInventario.objects
                   .select_for_update()
                   .filter(estado='ACT',
                           codigo__startswith=PrendaInventario.PREFIJO + '-')
                   .select_related('tipo_prenda')):
        grupos.setdefault(clave_modelo(prenda), []).append(prenda)

    unibles, conflictos = [], []
    for clave, skus in sorted(grupos.items()):
        if len(skus) < 2:
            continue
        skus.sort(key=_numero)
        distintos = [c for c in CAMPOS_QUE_DEBEN_COINCIDIR
                     if len({getattr(s, c) for s in skus}) > 1]
        if distintos:
            conflictos.append((clave, skus, distintos))
        else:
            unibles.append((skus[0], skus[1:]))
    return unibles, conflictos


class Command(BaseCommand):
    help = 'Une los SKU PRN- repetidos (mismo nombre, modelo, talla y color) en uno solo.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true',
                            help='Aplica los cambios. Sin esto es un simulacro.')

    def handle(self, *args, **opciones):
        aplicar = opciones['confirmar']
        with transaction.atomic():
            self._unir(aplicar)

    def _unir(self, aplicar):
        unibles, conflictos = grupos_repetidos()

        if not unibles and not conflictos:
            self.stdout.write(self.style.SUCCESS('No hay SKU repetidos.'))
            return

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                'SIMULACRO: no se cambia nada. Para aplicar: --confirmar\n'))

        movidas = borrados = 0
        for destino, origenes in unibles:
            movidas += self._unir_grupo(destino, origenes, aplicar)
            borrados += len(origenes)

        for clave, skus, campos in conflictos:
            self.stdout.write(self.style.WARNING(
                'NO SE UNE %s: %s difieren en %s. Corríjanlo a mano y vuelvan a correr.' % (
                    ' / '.join(clave), ', '.join(s.codigo for s in skus),
                    ', '.join(campos))))

        resumen = '\n%d grupos · %d unidades movidas · %d SKU %s' % (
            len(unibles), movidas, borrados,
            'borrados' if aplicar else 'a borrar')
        if conflictos:
            resumen += ' · %d grupos sin unir' % len(conflictos)
        self.stdout.write(self.style.SUCCESS(resumen) if aplicar else resumen)

    def _unir_grupo(self, destino, origenes, aplicar):
        """Mueve las unidades de `origenes` a `destino` y borra los vacíos.
        Devuelve cuántas unidades movió (o movería, en el simulacro)."""
        self.stdout.write(self.style.MIGRATE_HEADING(
            '%s  %s  ←  %s' % (destino.codigo, destino,
                               ', '.join(o.codigo for o in origenes))))
        tipos = {o.tipo_prenda for o in origenes} - {destino.tipo_prenda}
        if tipos:
            self.stdout.write('    tipo de prenda: queda «%s» (también tenía %s)' % (
                destino.tipo_prenda, ', '.join('«%s»' % t for t in tipos)))

        # Lo que vive en el SKU y no debe perderse al borrar los repetidos.
        notas = [destino.notas.strip()] if destino.notas.strip() else []
        for origen in origenes:
            if origen.notas.strip() and origen.notas.strip() not in notas:
                notas.append(origen.notas.strip())
            if destino.stock_minimo is None and origen.stock_minimo is not None:
                destino.stock_minimo = origen.stock_minimo
            ref = origen.codigo_referencia.strip()
            if ref and ref != destino.codigo_referencia.strip():
                self.stdout.write('    se descarta la referencia «%s» de %s' % (
                    ref, origen.codigo))
        destino.notas = '\n'.join(notas)

        # El próximo número se lleva a mano: en el simulacro nada se guarda y
        # siguiente_codigo() devolvería siempre el mismo. Se saltan los códigos
        # que ya use otra unidad, para que el simulacro muestre lo que pasará.
        siguiente = int(PrendaItem.siguiente_codigo(destino).rsplit('-', 1)[1])
        movidas = 0
        for origen in origenes:
            for item in origen.items.order_by('codigo_item'):
                nuevo = '%s-ITM-%02d' % (destino.codigo, siguiente)
                while PrendaItem.objects.filter(codigo_item=nuevo).exists():
                    siguiente += 1
                    nuevo = '%s-ITM-%02d' % (destino.codigo, siguiente)
                siguiente += 1
                self.stdout.write('    %s → %s  (%s)' % (
                    item.codigo_item, nuevo, item.get_estado_display()))
                if aplicar:
                    item.prenda = destino
                    item.codigo_item = nuevo
                    item.save(update_fields=['prenda', 'codigo_item', 'actualizado'])
                movidas += 1

            ordenes = origen.ordenes_produccion.count()
            if ordenes:
                self.stdout.write('    %d orden(es) de producción de %s pasan a %s' % (
                    ordenes, origen.codigo, destino.codigo))
            if aplicar:
                origen.ordenes_produccion.update(prenda_inventario=destino)
                if origen.items.exists():
                    raise CommandError(
                        '%s todavía tiene unidades: alguien cargó una mientras '
                        'corría el comando. No se cambió nada; vuelvan a correrlo.'
                        % origen.codigo)
                origen.delete()

        if aplicar:
            destino.save(update_fields=['notas', 'stock_minimo'])
        return movidas
