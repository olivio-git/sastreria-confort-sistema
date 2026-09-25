"""Cinta extra del lado del título, para cortar y coser sin tocarlo.

Se imprime de a una etiqueta y se corta con tijera en la boca de la impresora.
El título sale último, así que al terminar queda pegado a la boca: el corte
pasaba casi encima de él. Agrandar la plantilla desde el diseñador no servía:
el espacio quedaba del lado del código de barras. Este ajuste corre el diseño
hacia abajo y alarga la etiqueta la misma cantidad.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria import etiquetas, etiquetas_zpl
from misastreria.models import ConfiguracionImpresora
from .factories import make_user

TITULO = {'tipo': 'texto', 'x': 20, 'y': 40, 'texto': 'Fortium Tailor', 'tamano': 20}
CODIGO = {'tipo': 'barcode', 'x': 10, 'y': 500, 'texto': '000101', 'alto_barra': 80}


def _zpl(config):
    return etiquetas_zpl.render([TITULO, CODIGO], ancho=240, alto=659, datos={}, config=config)


class MargenArribaZplTests(TestCase):
    def test_sin_margen_no_cambia_nada(self):
        zpl = _zpl(ConfiguracionImpresora.cargar())
        self.assertIn('^LL659', zpl)
        self.assertIn('^FO20,40', zpl)

    def test_alarga_la_etiqueta_y_baja_el_diseno_lo_mismo(self):
        config = ConfiguracionImpresora.cargar()
        config.margen_arriba = Decimal('10')
        extra = etiquetas.mm_a_puntos(10)
        zpl = _zpl(config)
        self.assertIn('^LL%d' % (659 + extra), zpl)
        self.assertIn('^FO20,%d' % (40 + extra), zpl, 'el título tenía que bajar')
        self.assertIn(',%d^BY' % (500 + extra), zpl.replace('^FO10,', ','),
                      'el código de barras tenía que bajar lo mismo: si no, se corta abajo')

    def test_se_suma_al_corrimiento_vertical(self):
        config = ConfiguracionImpresora.cargar()
        config.margen_arriba = Decimal('10')
        config.desplazamiento_y = Decimal('2')
        zpl = _zpl(config)
        self.assertIn('^FO20,%d' % (40 + etiquetas.mm_a_puntos(10) + etiquetas.mm_a_puntos(2)), zpl)

    def test_cada_etiqueta_del_lote_lleva_el_margen(self):
        config = ConfiguracionImpresora.cargar()
        config.margen_arriba = Decimal('5')
        zpl = etiquetas_zpl.render_lote([TITULO], ancho=240, alto=659,
                                        lote=[{}, {}], config=config)
        self.assertEqual(zpl.count('^LL%d' % (659 + etiquetas.mm_a_puntos(5))), 2)


class GuardarMargenTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())

    def _post(self, **extra):
        datos = {'oscuridad': '1', 'velocidad': '4', 'desplazamiento_x': '0',
                 'desplazamiento_y': '0', 'tipo_papel': 'continuo', 'usa_ribbon': 'on'}
        datos.update(extra)
        return self.client.post(reverse('etiquetas_set_impresora'), datos,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_guarda_el_margen(self):
        self.assertTrue(self._post(margen_arriba='12').json()['ok'])
        self.assertEqual(ConfiguracionImpresora.cargar().margen_arriba, Decimal('12'))

    def test_si_no_viene_el_campo_no_lo_borra(self):
        """Una pestaña abierta desde antes del despliegue no lo manda."""
        self._post(margen_arriba='12')
        self._post()
        self.assertEqual(ConfiguracionImpresora.cargar().margen_arriba, Decimal('12'))

    def test_rechaza_fuera_de_rango(self):
        resp = self._post(margen_arriba='80')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(ConfiguracionImpresora.cargar().margen_arriba, Decimal('0'))

    def test_la_pantalla_de_ajustes_muestra_el_campo(self):
        html = self.client.get(reverse('etiquetas_calibrar')).content.decode()
        self.assertIn('name="margen_arriba"', html)
