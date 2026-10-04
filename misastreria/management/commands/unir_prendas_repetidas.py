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

`--renumerar` cierra los huecos que dejan los SKU borrados: todos los PRN-
pasan a PRN-001, PRN-002… en el mismo orden que tenían, y sus unidades con
ellos (PRN-024-ITM-03 → PRN-003-ITM-03). Además vacía los códigos de referencia
que son en realidad un código de unidad tipeado a mano (PRN-012-ITM-001):
después de renumerar apuntarían a otra prenda. Hacerlo sólo antes de etiquetar.

Todo corre en una sola transacción, con los SKU bloqueados. El simulacro aplica
todo y lo deshace al final, así que muestra exactamente lo que va a pasar. Antes
de borrar un SKU se verifica que quedó vacío: si alguien le cargó una unidad
mientras tanto, se aborta todo en vez de borrarla en cascada.

  manage.py unir_prendas_repetidas                           # simulacro
  manage.py unir_prendas_repetidas --renumerar               # simulacro
  manage.py unir_prendas_repetidas --renumerar --confirmar   # aplica
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

# Un código de unidad tipeado en «Código de referencia» (PRN-12-ITM-001).
_RE_REFERENCIA_FALSA = re.compile(r'^\s*PRN-\d+-ITM-\d+\s*$', re.IGNORECASE)


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
        parser.add_argument('--renumerar', action='store_true',
                            help='Después de unir, numera los PRN- seguidos desde '
                                 'PRN-001 y vacía las referencias que son códigos de unidad.')
        parser.add_argument('--confirmar', action='store_true',
                            help='Aplica los cambios. Sin esto es un simulacro.')

    def handle(self, *args, **opciones):
        aplicar = opciones['confirmar']
        if not aplicar:
            self.stdout.write(self.style.WARNING(
                'SIMULACRO: se aplica todo y se deshace al final. '
                'Para aplicar: --confirmar\n'))
        with transaction.atomic():
            resumen = self._unir()
            if opciones['renumerar']:
                resumen += self._renumerar()
            if not aplicar:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(resumen) if aplicar else resumen)

    def _unir(self):
        unibles, conflictos = grupos_repetidos()

        movidas = borrados = 0
        for destino, origenes in unibles:
            movidas += self._unir_grupo(destino, origenes)
            borrados += len(origenes)

        for clave, skus, campos in conflictos:
            self.stdout.write(self.style.WARNING(
                'NO SE UNE %s: %s difieren en %s. Corríjanlo a mano y vuelvan a correr.' % (
                    ' / '.join(clave), ', '.join(s.codigo for s in skus),
                    ', '.join(campos))))

        if not unibles and not conflictos:
            return '\nNo hay SKU repetidos.'
        resumen = '\n%d grupos unidos · %d unidades movidas · %d SKU borrados' % (
            len(unibles), movidas, borrados)
        if conflictos:
            resumen += ' · %d grupos sin unir' % len(conflictos)
        return resumen

    def _unir_grupo(self, destino, origenes):
        """Mueve las unidades de `origenes` a `destino` y borra los vacíos.
        Devuelve cuántas unidades movió."""
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
            if (ref and ref != destino.codigo_referencia.strip()
                    and not _RE_REFERENCIA_FALSA.match(ref)):
                self.stdout.write('    se descarta la referencia «%s» de %s' % (
                    ref, origen.codigo))
        destino.notas = '\n'.join(notas)
        destino.save(update_fields=['notas', 'stock_minimo'])

        movidas = 0
        for origen in origenes:
            for item in origen.items.order_by('codigo_item'):
                viejo = item.codigo_item
                item.prenda = destino
                item.codigo_item = PrendaItem.siguiente_codigo(destino)
                while PrendaItem.objects.filter(codigo_item=item.codigo_item).exists():
                    # Un código suelto de otro SKU ya lo usa: se salta.
                    numero = int(item.codigo_item.rsplit('-', 1)[1]) + 1
                    item.codigo_item = '%s-ITM-%02d' % (destino.codigo, numero)
                item.save(update_fields=['prenda', 'codigo_item', 'actualizado'])
                self.stdout.write('    %s → %s  (%s)' % (
                    viejo, item.codigo_item, item.get_estado_display()))
                movidas += 1

            ordenes = origen.ordenes_produccion.update(prenda_inventario=destino)
            if ordenes:
                self.stdout.write('    %d orden(es) de producción de %s pasan a %s' % (
                    ordenes, origen.codigo, destino.codigo))
            if origen.items.exists():
                raise CommandError(
                    '%s todavía tiene unidades: alguien cargó una mientras '
                    'corría el comando. No se cambió nada; vuelvan a correrlo.'
                    % origen.codigo)
            origen.delete()
        return movidas

    def _renumerar(self):
        """PRN-001, PRN-002… seguidos, en el orden que ya tenían, con sus
        unidades. Ir de menor a mayor garantiza que el número que toma cada SKU
        ya está libre: es el suyo o el de uno que ya se corrió más abajo."""
        P = PrendaInventario.PREFIJO
        self.stdout.write(self.style.MIGRATE_HEADING('\nRenumeración'))
        skus = sorted(PrendaInventario.objects.select_for_update()
                      .filter(codigo__startswith=P + '-'), key=_numero)

        corridos = referencias = 0
        for n, sku in enumerate(skus, start=1):
            if _RE_REFERENCIA_FALSA.match(sku.codigo_referencia):
                sku.codigo_referencia = ''
                sku.save(update_fields=['codigo_referencia'])
                referencias += 1

            nuevo = '%s-%03d' % (P, n)
            if sku.codigo == nuevo:
                continue
            viejo = sku.codigo
            sku.codigo = nuevo
            sku.save(update_fields=['codigo'])
            for item in sku.items.all():
                sufijo = item.codigo_item.rsplit('-ITM-', 1)
                if len(sufijo) != 2 or sufijo[0] != viejo:
                    raise CommandError(
                        'La unidad %s no sigue el formato de %s. No se cambió nada.'
                        % (item.codigo_item, viejo))
                item.codigo_item = '%s-ITM-%s' % (nuevo, sufijo[1])
                item.save(update_fields=['codigo_item', 'actualizado'])
            self.stdout.write('    %s → %s  %s' % (viejo, nuevo, sku))
            corridos += 1

        return ('\n%d SKU renumerados (PRN-001 a %s-%03d) · %d referencias vaciadas'
                ' · el próximo alta será %s' % (
                    corridos, P, len(skus), referencias,
                    PrendaInventario.siguiente_codigo()))
