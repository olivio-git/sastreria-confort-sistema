"""Payload numérico del código de barras y normalización de lo escaneado.

Dos problemas distintos se resuelven con la misma pieza, y por eso se prueban
juntos:

  - La pistola es un teclado HID: manda scancodes. La tecla del `-` en el mapa
    US llega como `'` en el mapa latinoamericano de la PC del taller, así que
    una etiqueta impresa `PRN-015-ITM-01` entraba al sistema como
    `PRN'015'ITM'01` y no matcheaba con nada.
  - Ese código ocupaba casi el ancho entero de la etiqueta en barras.

El payload comprimido mata los dos: es puro dígito (idéntico en los dos mapas
de teclado) y activa el subset C de Code 128 (dos dígitos por símbolo).
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria import etiquetas
from .factories import make_prenda, make_prenda_item, make_user


class PayloadCodigoTests(TestCase):
    """`payload_de_codigo` ⇄ `codigo_de_payload` tienen que ser inversas."""

    def test_item_comprime_a_seis_digitos(self):
        self.assertEqual(etiquetas.payload_de_codigo('PRN-015-ITM-01'), '001501')

    def test_sku_comprime_a_cuatro_digitos(self):
        self.assertEqual(etiquetas.payload_de_codigo('PRN-015'), '0015')

    def test_largo_par_para_no_romper_el_subset_c(self):
        # Un dígito impar corta el subset C en el último símbolo y se pierde el
        # ahorro: 7 dígitos ocupan MÁS que 8. Los dos largos tienen que ser par.
        self.assertEqual(len(etiquetas.payload_de_codigo('PRN-015-ITM-01')) % 2, 0)
        self.assertEqual(len(etiquetas.payload_de_codigo('PRN-015')) % 2, 0)

    def test_ida_y_vuelta(self):
        for codigo in ('PRN-001-ITM-01', 'PRN-015-ITM-07', 'PRN-999-ITM-99',
                       'PRN-9999-ITM-99', 'PRN-001', 'PRN-9999'):
            payload = etiquetas.payload_de_codigo(codigo)
            self.assertEqual(etiquetas.codigo_de_payload(payload), codigo, codigo)

    def test_codigo_que_no_es_de_inventario_pasa_sin_tocar(self):
        # Reparaciones y confecciones también imprimen etiqueta, y sus códigos
        # no siguen el patrón PRN. Tienen que poder imprimirse igual.
        self.assertEqual(etiquetas.payload_de_codigo('REP-001'), 'REP-001')
        self.assertEqual(etiquetas.payload_de_codigo(''), '')

    def test_fuera_de_rango_no_se_comprime(self):
        # Más allá de PRN-9999 el payload sería ambiguo: mejor largo que mal.
        largo = 'PRN-10000-ITM-01'
        self.assertEqual(etiquetas.payload_de_codigo(largo), largo)


class NormalizarEscaneoTests(TestCase):
    def test_repara_el_apostrofo_del_layout_de_teclado(self):
        self.assertEqual(
            etiquetas.normalizar_escaneo("PRN'015'ITM'01"), 'PRN-015-ITM-01'
        )

    def test_expande_el_payload_comprimido(self):
        self.assertEqual(etiquetas.normalizar_escaneo('001501'), 'PRN-015-ITM-01')
        self.assertEqual(etiquetas.normalizar_escaneo('0015'), 'PRN-015')

    def test_etiqueta_vieja_sigue_funcionando(self):
        # Todo lo ya impreso lleva el código largo en las barras. No se
        # reimprime nada para migrar: las dos formas entran por la misma puerta.
        self.assertEqual(
            etiquetas.normalizar_escaneo('PRN-015-ITM-01'), 'PRN-015-ITM-01'
        )

    def test_minusculas_y_espacios(self):
        self.assertEqual(
            etiquetas.normalizar_escaneo("  prn'015'itm'01  "), 'PRN-015-ITM-01'
        )

    def test_texto_ajeno_vuelve_igual(self):
        self.assertEqual(etiquetas.normalizar_escaneo('REP-001'), 'REP-001')
        self.assertEqual(etiquetas.normalizar_escaneo(''), '')


class AnchoCode128Tests(TestCase):
    """El ancho tiene que contar SÍMBOLOS, no caracteres."""

    def test_el_payload_entra_en_un_tercio_del_ancho(self):
        largo = etiquetas.modulos_code128('PRN-015-ITM-01')
        corto = etiquetas.modulos_code128('001501')
        self.assertEqual(largo, 189)
        self.assertEqual(corto, 68)      # subset C: dos dígitos por símbolo
        # Poco más de un tercio del original, o sea menos de la mitad.
        self.assertLess(corto * 2, largo)

    def test_coincide_con_lo_que_dibuja_reportlab(self):
        # Los dos renderers y la validación tienen que medir lo mismo, o el
        # código centrado cae en un lugar distinto en el PDF y en la impresora.
        from reportlab.graphics.barcode import code128
        for dato in ('PRN-015-ITM-01', '001501', '0015', '14-17058', 'A1234B'):
            self.assertEqual(
                etiquetas.modulos_code128(dato),
                code128.Code128(dato, barWidth=1, quiet=0).width,
                dato,
            )

    def test_dato_vacio(self):
        self.assertEqual(etiquetas.modulos_code128(''), 0)


class DatosDeEtiquetaTests(TestCase):
    def setUp(self):
        self.prenda = make_prenda(nombre='Terno Clásico', precio=Decimal('350.00'))

    def test_item_expone_los_dos_codigos(self):
        item = make_prenda_item(self.prenda)
        datos = etiquetas.datos_de_item(item)
        # El legible es el que lee la persona; el comprimido va a las barras.
        self.assertEqual(datos['codigo'], item.codigo_item)
        self.assertEqual(datos['codigo_barra'],
                         etiquetas.payload_de_codigo(item.codigo_item))

    def test_sku_expone_los_dos_codigos(self):
        datos = etiquetas.datos_de_prenda(self.prenda)
        self.assertEqual(datos['codigo'], self.prenda.codigo)
        self.assertEqual(datos['codigo_barra'],
                         etiquetas.payload_de_codigo(self.prenda.codigo))

    def test_plantillas_por_defecto_separan_barras_de_texto(self):
        for elementos in (etiquetas.elementos_por_defecto(),
                          etiquetas.elementos_textil_vertical()):
            barras = [e for e in elementos if e['tipo'] == 'barcode']
            textos = [e for e in elementos if e['tipo'] == 'texto']
            self.assertTrue(barras)
            for el in barras:
                self.assertEqual(el['texto'], '{codigo_barra}')
            # Y el código largo sigue impreso como texto para la persona.
            self.assertTrue(any('{codigo}' in e['texto'] for e in textos))

    def test_el_campo_esta_en_el_menu_del_disenador(self):
        self.assertIn('codigo_barra', etiquetas.CAMPOS)


class EscaneoEndpointTests(TestCase):
    """El endpoint acepta las dos formas y responde con el código canónico."""

    def setUp(self):
        self.client.force_login(make_user())
        self.url = reverse('escanear_prenda_item')
        self.prenda = make_prenda(nombre='Terno Clásico', precio=Decimal('350.00'))
        self.item = make_prenda_item(self.prenda, tipo='alquiler')

    def escanear(self, codigo):
        resp = self.client.get(self.url, {'codigo': codigo, 'contexto': 'alquiler'})
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_payload_comprimido_resuelve_al_item(self):
        payload = etiquetas.payload_de_codigo(self.item.codigo_item)
        data = self.escanear(payload)
        self.assertTrue(data['ok'], data)
        self.assertEqual(data['item']['prenda_item_id'], self.item.id)

    def test_codigo_deformado_por_el_teclado_resuelve_al_item(self):
        data = self.escanear(self.item.codigo_item.replace('-', "'"))
        self.assertTrue(data['ok'], data)
        self.assertEqual(data['item']['prenda_item_id'], self.item.id)

    def test_el_mensaje_de_error_muestra_el_codigo_legible(self):
        # Si falla, el empleado tiene que poder comparar el mensaje con lo que
        # dice la etiqueta. Mostrarle el payload crudo no le sirve de nada.
        data = self.escanear('009901')
        self.assertFalse(data['ok'])
        self.assertIn('PRN-099-ITM-01', data['mensaje'])

    def test_payload_de_sku_avisa_que_es_el_modelo(self):
        payload = etiquetas.payload_de_codigo(self.prenda.codigo)
        data = self.escanear(payload)
        self.assertFalse(data['ok'])
        self.assertEqual(data['motivo'], 'sku')
