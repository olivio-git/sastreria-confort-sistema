"""Cruce venta/alquiler: una prenda entra en el flujo que sea.

El sistema separaba las prendas en dos líneas estancas —«Para Venta» y «Para
Alquiler»— y cada formulario sólo ofrecía las suyas. La sastrería necesitaba
vender trajes de alquiler ya gastados (que es como recuperan la inversión) y
alquilar prendas de la línea de venta.

Se resolvió SIN tocar el modelo: `tipo` sigue diciendo a qué línea pertenece la
prenda, pero dejó de ser un candado. El control es el filtro del selector.
"""
from datetime import date, timedelta
from decimal import Decimal
import json
import re

from django.test import TestCase
from django.urls import reverse

from misastreria.models import Alquiler, PrendaItem, Venta
from .factories import make_prenda, make_prenda_item, make_user


def _embebido(html, nombre):
    """Lee una constante JS embebida en la plantilla."""
    m = re.search(r'const ' + nombre + r' = (.*?);\n', html)
    return json.loads(m.group(1)) if m else None


class GuardarPrendaDeLaOtraLineaTests(TestCase):
    """El caso que motivó todo: la prenda entra aunque sea de la otra línea."""

    def setUp(self):
        self.client.force_login(make_user())
        prenda = make_prenda(nombre='Frac', precio=Decimal('900.00'),
                             precio_alquiler_base=Decimal('250.00'))
        self.de_alquiler = make_prenda_item(prenda, tipo='alquiler')
        self.de_venta = make_prenda_item(prenda, tipo='venta')

    def _fila(self, item, precio):
        return {
            'item_prenda_item':       [str(item.id)],
            'item_precio':            [precio],
            'item_grupo_conjunto':    [''],
            'item_tipo_reparacion':   [''],
            'item_precio_reparacion': [''],
            'item_empleado':          [''],
            'item_monto_comision':    [''],
        }

    def test_se_vende_una_prenda_de_la_linea_de_alquiler(self):
        datos = {'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
                 'cliente': str(_cli_mostrador().id),
                 'empleado': str(_emp_mostrador().id),
                 'descuento': '0', 'notas': ''}
        datos.update(self._fila(self.de_alquiler, '800.00'))
        resp = self.client.post(reverse('crear_venta'), datos)
        self.assertEqual(resp.status_code, 302)

        venta = Venta.objects.latest('id')
        self.assertEqual([i.prenda_item_id for i in venta.items.all()],
                         [self.de_alquiler.id])
        # Vender saca la prenda del inventario, venga de la línea que venga.
        self.de_alquiler.refresh_from_db()
        self.assertEqual(self.de_alquiler.estado, 'baja')
        # El `tipo` NO se toca: sigue diciendo de qué línea venía.
        self.assertEqual(self.de_alquiler.tipo, 'alquiler')

    def test_se_alquila_una_prenda_de_la_linea_de_venta(self):
        datos = {'fecha_alquiler': date.today().isoformat(),
                 'fecha_devolucion': (date.today() + timedelta(days=3)).isoformat(),
                 'estado': 'alquilado', 'descuento': '0', 'notas': '',
                 'adelanto': '0', 'forma_pago': 'efectivo'}
        datos.update(self._fila(self.de_venta, '250.00'))
        resp = self.client.post(reverse('crear_alquiler'), datos)
        self.assertEqual(resp.status_code, 302)

        alquiler = Alquiler.objects.latest('id')
        self.assertEqual([i.prenda_item_id for i in alquiler.items.all()],
                         [self.de_venta.id])
        self.de_venta.refresh_from_db()
        self.assertEqual(self.de_venta.estado, 'alquilado')
        self.assertEqual(self.de_venta.tipo, 'venta')


class FormularioSinVolcadoDeInventarioTests(TestCase):
    """El formulario ya no embebe el inventario entero: pide a demanda."""

    def setUp(self):
        self.client.force_login(make_user())
        prenda = make_prenda(nombre='Terno', precio=Decimal('100.00'))
        self.items = [make_prenda_item(prenda, tipo='venta') for _ in range(12)]

    def test_crear_no_embebe_ninguna_prenda(self):
        for url in ('crear_venta', 'crear_alquiler'):
            html = self.client.get(reverse(url)).content.decode()
            self.assertEqual(_embebido(html, 'PRENDAS'), [], f'{url} embebe inventario')

    def test_crear_incluye_el_selector(self):
        for url in ('crear_venta', 'crear_alquiler'):
            html = self.client.get(reverse(url)).content.decode()
            self.assertIn('sel-items-modal', html)
            self.assertIn('selector_items.js', html)
            # El combobox contra la lista embebida ya no existe.
            self.assertNotIn('makePrendaFlyoutCombobox', html)

    def test_editar_embebe_solo_las_prendas_propias(self):
        datos = {'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
                 'cliente': str(_cli_mostrador().id),
                 'empleado': str(_emp_mostrador().id),
                 'descuento': '0', 'notas': '',
                 'item_prenda_item':       [str(self.items[0].id)],
                 'item_precio':            ['100.00'],
                 'item_grupo_conjunto':    [''],
                 'item_tipo_reparacion':   [''],
                 'item_precio_reparacion': [''],
                 'item_empleado':          [''],
                 'item_monto_comision':    ['']}
        self.client.post(reverse('crear_venta'), datos)
        venta = Venta.objects.latest('id')

        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        prendas = _embebido(html, 'PRENDAS')
        # Una sola: la suya. Las otras once no viajan aunque estén disponibles.
        self.assertEqual([p['prenda_item_id'] for p in prendas], [self.items[0].id])
        # Y viaja aunque la venta la haya dado de baja, o la fila saldría sin nombre.
        self.assertIn(self.items[0].codigo_item, prendas[0]['label'])


class PreloadPorEscaneoTests(TestCase):
    """El `?item=` con el que aterriza un escaneo hecho desde otra pantalla."""

    def setUp(self):
        self.client.force_login(make_user())
        prenda = make_prenda(nombre='Frac', precio=Decimal('900.00'))
        self.de_alquiler = make_prenda_item(prenda, tipo='alquiler')
        self.ocupado = make_prenda_item(prenda, tipo='venta', estado='alquilado')

    def test_precarga_una_prenda_de_la_otra_linea(self):
        html = self.client.get(reverse('crear_venta'),
                               {'item': self.de_alquiler.id}).content.decode()
        iniciales = _embebido(html, 'ITEMS_INICIALES')
        self.assertEqual([i['prenda_item_id'] for i in iniciales], [self.de_alquiler.id])
        # Y su ficha viaja en PRENDAS, o la fila no sabría qué mostrar.
        self.assertEqual([p['prenda_item_id'] for p in _embebido(html, 'PRENDAS')],
                         [self.de_alquiler.id])

    def test_una_prenda_no_disponible_avisa_en_vez_de_fallar_muda(self):
        resp = self.client.get(reverse('crear_venta'),
                               {'item': self.ocupado.id}, follow=True)
        avisos = [m.message for m in resp.context['messages']]
        self.assertTrue(avisos, 'falló en silencio: el empleado no sabe por qué')
        self.assertIn('no se pudo cargar', ' '.join(avisos).lower())


class ConjuntosSiguenNombrandoLaPrendaTests(TestCase):
    """Regresión: al sacar el volcado de inventario, las filas que agrega un
    conjunto se quedaron sin de dónde leer el nombre de la prenda."""

    def setUp(self):
        from misastreria.models import Conjunto, ConjuntoSlot
        self.client.force_login(make_user())
        prenda = make_prenda(nombre='Terno', precio=Decimal('100.00'),
                             precio_alquiler_base=Decimal('80.00'))
        self.saco = make_prenda_item(prenda, tipo='alquiler')
        self.pantalon = make_prenda_item(prenda, tipo='alquiler')
        self.conjunto = Conjunto.objects.create(
            nombre='Terno completo', tipo='alquiler', precio_sugerido=Decimal('150.00'))
        for orden, item in enumerate((self.saco, self.pantalon)):
            ConjuntoSlot.objects.create(conjunto=self.conjunto, prenda_item=item, orden=orden)

    def test_cada_slot_viaja_con_su_label(self):
        html = self.client.get(reverse('crear_alquiler')).content.decode()
        conjuntos = _embebido(html, 'CONJUNTOS')
        self.assertTrue(conjuntos, 'no llegó ningún conjunto al formulario')
        slots = conjuntos[0]['slots']
        self.assertEqual(len(slots), 2)
        for slot in slots:
            self.assertTrue(slot.get('label'), 'slot sin label: la fila saldría en blanco')
            self.assertIn('Terno', slot['label'])
        codigos = {s['prenda_item_codigo'] for s in slots}
        self.assertEqual(codigos, {self.saco.codigo_item, self.pantalon.codigo_item})


class SelectorAgrupadoTests(TestCase):
    """El selector lista MODELOS, no unidades.

    173 unidades disponibles para 23 modelos: listar unidades sueltas es 87% de
    ruido, y con el tope de 40 filas el catálogo no entra ni por la cuarta
    parte. Nadie busca «la camisa blanca número 13».
    """

    def setUp(self):
        self.client.force_login(make_user())
        self.camisa = make_prenda(nombre='Camisa', talla='M', color='Blanco',
                                  precio=Decimal('120.00'))
        for _ in range(5):
            make_prenda_item(self.camisa, tipo='venta')

        self.frac = make_prenda(nombre='Frac', talla='50', color='Negro',
                                precio=Decimal('900.00'),
                                precio_alquiler_base=Decimal('250.00'))
        self.gastado = make_prenda_item(self.frac, tipo='alquiler', veces_alquilado=7)
        self.nuevo = make_prenda_item(self.frac, tipo='alquiler', veces_alquilado=0)
        self.medio = make_prenda_item(self.frac, tipo='alquiler', veces_alquilado=3)
        self.frac_venta = make_prenda_item(self.frac, tipo='venta')

    def _buscar(self, **extra):
        params = {'estado': 'disponible', 'agrupar': '1'}
        params.update(extra)
        return self.client.get(reverse('buscar_items_inventario'), params).json()

    def test_un_renglon_por_modelo_en_vez_de_uno_por_unidad(self):
        sueltas = self.client.get(reverse('buscar_items_inventario'),
                                  {'estado': 'disponible'}).json()['items']
        self.assertEqual(len(sueltas), 9)          # 5 camisas + 4 fracs
        agrupado = self._buscar()['items']
        self.assertEqual(len(agrupado), 3)         # camisa/venta, frac/alquiler, frac/venta

    def test_un_modelo_con_las_dos_lineas_da_dos_renglones(self):
        """PRN de Frac tiene unidades de venta Y de alquiler: fusionarlas
        mezclaría dos cosas que se cargan en flujos distintos."""
        grupos = [g for g in self._buscar()['items'] if g['sku_nombre'] == 'Frac']
        self.assertEqual(len(grupos), 2)
        por_tipo = {g['tipo']: g for g in grupos}
        self.assertEqual(por_tipo['alquiler']['disponibles'], 3)
        self.assertEqual(por_tipo['venta']['disponibles'], 1)

    def test_disponibles_coincide_con_las_unidades_que_viajan(self):
        for grupo in self._buscar()['items']:
            self.assertEqual(grupo['disponibles'], len(grupo['unidades']))

    def test_orden_desgaste_asigna_la_unidad_menos_alquilada(self):
        grupo = [g for g in self._buscar(q='Frac', tipo='alquiler',
                                         orden='desgaste')['items']][0]
        # La primera unidad es la que se lleva quien elige el modelo sin mirar.
        self.assertEqual(grupo['unidades'][0]['prenda_item_id'], self.nuevo.id)
        usos = [u['veces_alquilado'] for u in grupo['unidades']]
        self.assertEqual(usos, sorted(usos), 'las unidades no vienen por desgaste')

    def test_orden_fifo_asigna_la_unidad_mas_vieja(self):
        grupo = [g for g in self._buscar(q='Frac', tipo='alquiler',
                                         orden='fifo')['items']][0]
        self.assertEqual(grupo['unidades'][0]['prenda_item_id'], self.gastado.id)

    def test_el_desgaste_viaja_para_que_el_expansor_sirva(self):
        grupo = [g for g in self._buscar(q='Frac', tipo='alquiler')['items']][0]
        for unidad in grupo['unidades']:
            self.assertIn('veces_alquilado', unidad)
            self.assertIn('condicion_label', unidad)

    def test_el_disenador_sigue_recibiendo_unidades_sueltas(self):
        """Etiquetar es lo contrario: la etiqueta va pegada a UNA prenda."""
        datos = self.client.get(reverse('buscar_items_inventario'),
                                {'q': 'Frac', 'datos': '1'}).json()
        self.assertNotIn('agrupado', datos)
        self.assertEqual(len(datos['items']), 4)
        self.assertIn('codigo_item', datos['items'][0])

    def test_los_formularios_piden_el_modo_agrupado(self):
        casos = (('crear_venta', "orden: 'fifo'"), ('crear_alquiler', "orden: 'desgaste'"))
        for url, orden in casos:
            html = self.client.get(reverse(url)).content.decode()
            self.assertIn('agrupar: true', html, f'{url} no agrupa')
            self.assertIn(orden, html, f'{url} sin regla de asignación')


class SkuDeBajaNoSeOfreceTests(TestCase):
    """Regresión: al generalizar el endpoint se perdió `prenda__estado='ACT'`.

    Importa para el corte de inventario: los SKU archivados se marcan de baja,
    y sin este filtro reaparecen en los formularios de venta y alquiler.
    """

    def setUp(self):
        self.client.force_login(make_user())
        self.viva = make_prenda(nombre='Camisa Viva', precio=Decimal('100.00'))
        self.archivada = make_prenda(nombre='Camisa Archivada', precio=Decimal('100.00'),
                                     estado='BAJ')
        make_prenda_item(self.viva, tipo='venta')
        self.item_archivado = make_prenda_item(self.archivada, tipo='venta')

    def test_el_selector_no_ofrece_unidades_de_un_sku_archivado(self):
        items = self.client.get(reverse('buscar_items_inventario'),
                                {'q': 'Camisa'}).json()['items']
        codigos = [i['codigo_item'] for i in items]
        self.assertNotIn(self.item_archivado.codigo_item, codigos)
        self.assertEqual(len(codigos), 1)

    def test_tampoco_agrupado(self):
        grupos = self.client.get(reverse('buscar_items_inventario'),
                                 {'q': 'Camisa', 'agrupar': '1'}).json()['items']
        self.assertEqual([g['sku_nombre'] for g in grupos], ['Camisa Viva'])

    def test_el_escaneo_ya_lo_rechazaba_y_sigue(self):
        d = self.client.get(reverse('escanear_prenda_item'),
                            {'codigo': self.item_archivado.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'sku_baja')


class TopeDeModelosTests(TestCase):
    """El corte del listado agrupado es de MODELOS, no de unidades.

    Recortar unidades primero puede partir un modelo: el último quedaría con
    menos de las que tiene y `disponibles` mentiría — justo lo que agrupar
    viene a arreglar.
    """

    def setUp(self):
        self.client.force_login(make_user())
        self.prenda = make_prenda(nombre='Pañuelo', precio=Decimal('20.00'))
        for _ in range(30):
            make_prenda_item(self.prenda, tipo='venta')

    def test_el_modelo_llega_entero_con_todas_sus_unidades(self):
        grupo = self.client.get(reverse('buscar_items_inventario'),
                                {'q': 'Pañuelo', 'agrupar': '1',
                                 'estado': 'disponible'}).json()['items'][0]
        self.assertEqual(grupo['disponibles'], 30)
        self.assertEqual(len(grupo['unidades']), 30)


# VentaForm exige cliente y empleado desde que una venta sin cliente deja una
# deuda sin deudor. Estos tests miden otra cosa, así que usan los de mostrador:
# el FK `empleado` del servicio no devenga comisión —eso sale de las tablas de
# asignación—, así que no interfiere con ningún assert.
from .factories import cliente_y_empleado_de_mostrador as _mostrador


def _cli_mostrador():
    return _mostrador()[0]


def _emp_mostrador():
    return _mostrador()[1]
