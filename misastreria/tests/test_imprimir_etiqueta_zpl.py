"""Imprimir la etiqueta de una prenda por el puente, en ZPL, y no por PDF.

Los botones de la prenda y de cada unidad abrían un PDF que el navegador
mandaba a la térmica por el driver de Windows. La etiqueta salía corrida y
recortada a la izquierda y abajo: el driver no conoce la calibración guardada
en el sistema y agrega sus propios márgenes. El diseñador, que imprime por ZPL,
salía bien. Lo que se cuida acá es que los dos caminos armen el mismo ZPL: la
plantilla activa y la calibración de la impresora.
"""
from django.test import TestCase
from django.urls import reverse

from misastreria import etiquetas
from misastreria.models import ConfiguracionImpresora, PlantillaEtiqueta
from .factories import make_prenda, make_prenda_item, make_user

TEXTO = {'tipo': 'texto', 'x': 20, 'y': 10, 'texto': '{codigo}', 'tamano': 20}


class ZplDeEtiquetaTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        PlantillaEtiqueta.objects.all().delete()
        self.plantilla = PlantillaEtiqueta.objects.create(
            nombre='Activa', elementos=[TEXTO], ancho_puntos=240, alto_puntos=560,
            es_predeterminada=True)
        self.prenda = make_prenda(codigo='PRN-001')
        self.item = make_prenda_item(self.prenda)            # PRN-001-ITM-01

    def _zpl_item(self, item=None):
        return self.client.get(reverse('zpl_etiqueta_item', args=[(item or self.item).id])).json()

    def test_una_unidad_devuelve_su_etiqueta(self):
        datos = self._zpl_item()
        self.assertTrue(datos['ok'])
        self.assertEqual(datos['cantidad'], 1)
        self.assertTrue(datos['zpl'].startswith('^XA'))
        self.assertIn('PRN-001-ITM-01', datos['zpl'])

    def test_aplica_la_calibracion_de_la_impresora(self):
        """El bug: el PDF por el driver ignoraba el encuadre guardado."""
        config = ConfiguracionImpresora.cargar()
        config.desplazamiento_x = 2          # milímetros, como en la pantalla de ajustes
        config.oscuridad = 12
        config.save()
        zpl = self._zpl_item()['zpl']
        esperado = 20 + etiquetas.mm_a_puntos(2)
        self.assertIn('^FO%d,' % esperado, zpl, 'el texto tenía que correrse 2 mm')
        self.assertIn('^MD', zpl, 'tenía que llevar la oscuridad configurada')

    def test_el_sku_devuelve_una_por_unidad_activa(self):
        make_prenda_item(self.prenda)                                   # ITM-02
        make_prenda_item(self.prenda, estado='baja')                    # no va
        datos = self.client.get(reverse('zpl_etiquetas_prenda', args=[self.prenda.id])).json()
        self.assertEqual(datos['cantidad'], 2)
        self.assertEqual(datos['zpl'].count('^XA'), 2)
        self.assertIn('PRN-001-ITM-02', datos['zpl'])

    def test_sku_sin_unidades_activas_avisa(self):
        vacio = make_prenda(codigo='PRN-002')
        resp = self.client.get(reverse('zpl_etiquetas_prenda', args=[vacio.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])

    def test_sin_plantilla_avisa_en_vez_de_romper(self):
        PlantillaEtiqueta.objects.all().delete()
        resp = self.client.get(reverse('zpl_etiqueta_item', args=[self.item.id]))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('plantilla', resp.json()['error'])

    def test_pide_login(self):
        self.client.logout()
        resp = self.client.get(reverse('zpl_etiqueta_item', args=[self.item.id]))
        self.assertEqual(resp.status_code, 302)

    def test_la_prenda_ofrece_imprimir_por_el_puente(self):
        html = self.client.get(reverse('detalle_prenda', args=[self.prenda.id])).content.decode()
        self.assertIn(reverse('zpl_etiqueta_item', args=[self.item.id]), html)
        self.assertIn(reverse('zpl_etiquetas_prenda', args=[self.prenda.id]), html)
        self.assertIn('etiquetas_puente', html)
        self.assertIn('imprimir_etiquetas', html)
