"""Agrupamiento de items por conjunto (`grupo_conjunto`).

Cuando se agregan tres prendas desde el botón "Agregar conjunto", las tres
comparten un número de grupo. Ese número es lo único que después distingue
"un terno de tres piezas" de "tres prendas cargadas sueltas" en la lista, el
detalle y el historial del cliente, donde ya se renderiza el badge «Conjunto N».

La cadena estuvo cortada un tiempo: el campo existía en el modelo, la vista lo
leía del POST y las plantillas lo mostraban, pero ningún formulario mandaba el
input. Los tests de acá cubren el ida y vuelta completo — POST que persiste,
y edición que devuelve el grupo al formulario — porque el eslabón que faltaba
era justamente el que nadie probaba.
"""
import json
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.models import Alquiler, Venta
from .factories import make_prenda, make_prenda_item, make_user


class GrupoConjuntoVentaTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        prenda = make_prenda(nombre='Terno', precio=Decimal('100.00'))
        self.saco = make_prenda_item(prenda, tipo='venta')
        self.pantalon = make_prenda_item(prenda, tipo='venta')
        self.suelta = make_prenda_item(prenda, tipo='venta')

    def _post(self, filas):
        """filas = [(prenda_item, precio, grupo_str)]"""
        data = {
            'fecha_venta': date.today().isoformat(),
            'estado': 'en_proceso',
            'descuento': '0',
            'notas': '',
            'item_prenda_item':      [str(f[0].id) for f in filas],
            'item_precio':           [f[1] for f in filas],
            'item_grupo_conjunto':   [f[2] for f in filas],
            'item_tipo_reparacion':  ['' for _ in filas],
            'item_precio_reparacion': ['' for _ in filas],
            'item_empleado':         ['' for _ in filas],
            'item_monto_comision':   ['' for _ in filas],
        }
        resp = self.client.post(reverse('crear_venta'), data)
        self.assertEqual(resp.status_code, 302)
        return Venta.objects.latest('id')

    def test_el_grupo_llega_del_post_a_la_base(self):
        venta = self._post([
            (self.saco,     '100.00', '1'),
            (self.pantalon, '100.00', '1'),
            (self.suelta,   '100.00', ''),
        ])
        por_item = {i.prenda_item_id: i.grupo_conjunto for i in venta.items.all()}
        self.assertEqual(por_item[self.saco.id], 1)
        self.assertEqual(por_item[self.pantalon.id], 1)
        # Una prenda cargada a mano no pertenece a ningún conjunto.
        self.assertIsNone(por_item[self.suelta.id])

    def test_dos_conjuntos_en_la_misma_venta_no_se_mezclan(self):
        venta = self._post([
            (self.saco,     '100.00', '1'),
            (self.pantalon, '100.00', '2'),
        ])
        por_item = {i.prenda_item_id: i.grupo_conjunto for i in venta.items.all()}
        self.assertEqual(por_item[self.saco.id], 1)
        self.assertEqual(por_item[self.pantalon.id], 2)

    def test_el_formulario_de_edicion_devuelve_el_grupo(self):
        # Sin esto, editar una venta y guardarla borraría el agrupamiento.
        venta = self._post([
            (self.saco,     '100.00', '1'),
            (self.pantalon, '100.00', '1'),
        ])
        html = self.client.get(reverse('editar_venta', kwargs={'id': venta.pk})).content.decode()
        items = json.loads(html.split('const ITEMS_INICIALES = ')[1].split(';\n')[0])
        self.assertEqual(sorted(i['grupo_conjunto'] for i in items), [1, 1])

    def test_la_fila_del_formulario_manda_el_input(self):
        # El eslabón exacto que faltaba. Sin el input, el POST nunca trae la
        # clave y el grupo se guarda como None sin que nada falle a la vista.
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn('name="item_grupo_conjunto"', html)

    def test_el_badge_de_conjunto_aparece_en_la_lista(self):
        self._post([(self.saco, '100.00', '3')])
        html = self.client.get(reverse('lista_ventas')).content.decode()
        self.assertIn('badge-conjunto', html)

    def test_el_formulario_le_pasa_nextGrupo_al_helper_de_conjuntos(self):
        # `addConjuntoToForm` numera la tanda con `ctx.nextGrupo()`, pero si el
        # formulario no se lo pasa cae a `null` sin romper nada: el conjunto se
        # agrega igual, solo que sin número. Fue así como el bug pasó inadvertido.
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn('nextGrupo: nextGrupo', html)
        self.assertIn('function nextGrupo()', html)


class GrupoConjuntoAlquilerTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        prenda = make_prenda(nombre='Terno', precio=Decimal('100.00'))
        self.saco = make_prenda_item(prenda, tipo='alquiler')
        self.pantalon = make_prenda_item(prenda, tipo='alquiler')

    def _post(self, filas):
        data = {
            'fecha_alquiler':   date.today().isoformat(),
            'fecha_devolucion': (date.today() + timedelta(days=3)).isoformat(),
            'estado': 'alquilado',
            'descuento': '0',
            'notas': '',
            'adelanto': '0',
            'forma_pago': 'efectivo',
            'item_prenda_item':      [str(f[0].id) for f in filas],
            'item_precio':           [f[1] for f in filas],
            'item_grupo_conjunto':   [f[2] for f in filas],
            'item_tipo_reparacion':  ['' for _ in filas],
            'item_precio_reparacion': ['' for _ in filas],
            'item_empleado':         ['' for _ in filas],
            'item_monto_comision':   ['' for _ in filas],
        }
        resp = self.client.post(reverse('crear_alquiler'), data)
        self.assertEqual(resp.status_code, 302)
        return Alquiler.objects.latest('id')

    def test_el_grupo_llega_del_post_a_la_base(self):
        alquiler = self._post([
            (self.saco,     '100.00', '1'),
            (self.pantalon, '100.00', '1'),
        ])
        grupos = sorted(i.grupo_conjunto for i in alquiler.items.all())
        self.assertEqual(grupos, [1, 1])

    def test_el_formulario_de_edicion_devuelve_el_grupo(self):
        alquiler = self._post([(self.saco, '100.00', '2')])
        html = self.client.get(reverse('editar_alquiler', kwargs={'id': alquiler.pk})).content.decode()
        items = json.loads(html.split('const ITEMS_INICIALES = ')[1].split(';\n')[0])
        self.assertEqual(items[0]['grupo_conjunto'], 2)

    def test_la_fila_del_formulario_manda_el_input(self):
        html = self.client.get(reverse('crear_alquiler')).content.decode()
        self.assertIn('name="item_grupo_conjunto"', html)

    def test_el_formulario_le_pasa_nextGrupo_al_helper_de_conjuntos(self):
        html = self.client.get(reverse('crear_alquiler')).content.decode()
        self.assertIn('nextGrupo: nextGrupo', html)
        self.assertIn('function nextGrupo()', html)
