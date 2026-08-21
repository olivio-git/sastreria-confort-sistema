"""Escaneo de etiquetas con pistola.

El escaneo en sí vive en el navegador (`initScanToAdd` / `initScanVerify`) y
resuelve la mayoría de las lecturas contra el JSON de prendas ya embebido en la
página. Lo que se prueba acá es el endpoint que se consulta cuando ESA búsqueda
falla: su único trabajo es explicar el motivo, y cada motivo es una decisión
distinta para el empleado que tiene la prenda en la mano.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.models import Conjunto, ConjuntoSlot
from .factories import make_prenda, make_prenda_item, make_user


class EscanearPrendaItemTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.url = reverse('escanear_prenda_item')
        self.prenda = make_prenda(nombre='Terno Clásico', precio=Decimal('350.00'))

    def escanear(self, codigo, contexto='alquiler'):
        resp = self.client.get(self.url, {'codigo': codigo, 'contexto': contexto})
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.get(self.url, {'codigo': 'PRN-001-ITM-01'})
        self.assertEqual(resp.status_code, 302)

    def test_item_disponible_devuelve_los_datos_de_la_fila(self):
        item = make_prenda_item(self.prenda, tipo='alquiler')
        data = self.escanear(item.codigo_item)
        self.assertTrue(data['ok'])
        self.assertEqual(data['item']['prenda_item_id'], item.id)
        self.assertEqual(data['item']['codigo_item'], item.codigo_item)
        self.assertEqual(data['item']['precio'], 350.0)
        self.assertIn('Terno Clásico', data['item']['label'])

    def test_codigo_case_insensitive(self):
        # La pistola respeta las mayúsculas, pero el mismo endpoint sirve para
        # tipear el código a mano cuando la etiqueta se despegó.
        item = make_prenda_item(self.prenda)
        data = self.escanear(item.codigo_item.lower())
        self.assertTrue(data['ok'])
        self.assertEqual(data['item']['prenda_item_id'], item.id)

    def test_codigo_vacio(self):
        data = self.escanear('')
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'vacio')

    def test_codigo_inexistente(self):
        data = self.escanear('NO-EXISTE-99')
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'no_existe')
        self.assertIn('NO-EXISTE-99', data['mensaje'])

    def test_item_alquilado_dice_que_esta_ocupado(self):
        item = make_prenda_item(self.prenda, estado='alquilado')
        data = self.escanear(item.codigo_item)
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'ocupado')
        self.assertIn('alquilado', data['mensaje'].lower())

    def test_item_de_baja(self):
        item = make_prenda_item(self.prenda, estado='baja')
        data = self.escanear(item.codigo_item)
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'baja')

    def test_item_de_otro_tipo_no_sirve_para_este_formulario(self):
        item = make_prenda_item(self.prenda, tipo='venta')
        data = self.escanear(item.codigo_item, contexto='alquiler')
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'tipo')

    def test_sin_contexto_no_filtra_por_tipo(self):
        item = make_prenda_item(self.prenda, tipo='venta')
        data = self.escanear(item.codigo_item, contexto='')
        self.assertTrue(data['ok'])

    def test_item_de_conjunto_manda_al_boton_de_conjuntos(self):
        item = make_prenda_item(self.prenda)
        conjunto = Conjunto.objects.create(nombre='Terno completo', tipo='alquiler')
        ConjuntoSlot.objects.create(conjunto=conjunto, prenda_item=item, orden=0)
        data = self.escanear(item.codigo_item)
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'conjunto')
        self.assertIn('Terno completo', data['mensaje'])

    def test_escanear_la_etiqueta_del_sku_avisa_que_es_del_modelo(self):
        # Es el error fácil: la etiqueta de SKU también se imprime desde el
        # sistema y es fácil pegarla a una prenda. Identifica el modelo, no la
        # unidad, así que no alcanza para cargar una venta.
        make_prenda_item(self.prenda)
        make_prenda_item(self.prenda)
        data = self.escanear(self.prenda.codigo)
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'sku')
        self.assertIn('2 disponibles', data['mensaje'])

    def test_sku_dado_de_baja(self):
        item = make_prenda_item(self.prenda)
        self.prenda.estado = 'BAJ'
        self.prenda.save(update_fields=['estado'])
        data = self.escanear(item.codigo_item)
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'sku_baja')


class BarraDeEscaneoEnPantallasTests(TestCase):
    """La barra de escaneo tiene que llegar renderizada a las cuatro pantallas.

    Es un include con IDs fijos que el JS busca por `getElementById`. Si el
    include se cae de una plantilla, no hay error en ningún lado: la pantalla
    abre normal y el escaneo simplemente no hace nada, que es la peor forma de
    romperse.
    """

    def setUp(self):
        self.client.force_login(make_user())

    def _html(self, nombre, **kwargs):
        resp = self.client.get(reverse(nombre, kwargs=kwargs or None))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def _assert_barra(self, html):
        self.assertIn('id="scanInput"', html)
        self.assertIn('id="scanMsg"', html)
        # Ningún comentario de plantilla puede filtrarse al HTML. `{# … #}` en
        # Django es de UNA sola línea: escrito en varias no se parsea como
        # comentario y sale impreso como texto visible en la pantalla.
        self.assertNotIn('{#', html)
        self.assertNotIn('{% comment %}', html)

    def test_formulario_de_venta(self):
        html = self._html('crear_venta')
        self._assert_barra(html)
        self.assertIn('initScanToAdd', html)
        # La carga manual sigue en pie: las dos formas conviven.
        self.assertIn('btnAgregarItem', html)
        # Sin contador acá: la tabla de abajo ya muestra cuántas prendas hay.
        self.assertNotIn('id="scanContador"', html)

    def test_formulario_de_alquiler(self):
        html = self._html('crear_alquiler')
        self._assert_barra(html)
        self.assertIn('initScanToAdd', html)
        self.assertIn('btnAgregarItem', html)
        self.assertNotIn('id="scanContador"', html)

    def test_salida_de_alquiler_lleva_el_codigo_en_cada_fila(self):
        from .factories import make_alquiler, make_alquiler_item
        alquiler = make_alquiler(estado='reservado')
        item = make_alquiler_item(alquiler, make_prenda_item(estado='reservado'))
        html = self._html('confirmar_reserva', id=alquiler.pk)
        self._assert_barra(html)
        self.assertIn('initScanVerify', html)
        # Acá el contador sí dice algo que no está a la vista: cuántas faltan.
        self.assertIn('id="scanContador"', html)
        self.assertIn(f'data-codigo="{item.prenda_item.codigo_item}"', html)

    def test_devolucion_de_alquiler_lleva_el_codigo_en_cada_fila(self):
        from .factories import make_alquiler, make_alquiler_item
        alquiler = make_alquiler(estado='alquilado')
        item = make_alquiler_item(alquiler, make_prenda_item(estado='alquilado'))
        html = self._html('devolver_alquiler', id=alquiler.pk)
        self._assert_barra(html)
        self.assertIn('initScanVerify', html)
        # Acá el contador sí dice algo que no está a la vista: cuántas faltan.
        self.assertIn('id="scanContador"', html)
        self.assertIn(f'data-codigo="{item.prenda_item.codigo_item}"', html)
