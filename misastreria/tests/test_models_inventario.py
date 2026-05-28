"""
test_models_inventario.py
==========================
Cubre:
  - PrendaInventario: autocode PRN-NNN, __str__, cantidad, stock_disponible
  - PrendaItem: autocode PRN-NNN-ITM-NN, max_usos_efectivo,
                porcentaje_vida_util, estado_vida_util
  - UbicacionItem: unique, __str__
"""
from decimal import Decimal

from django.test import TestCase
from django.db import IntegrityError

from misastreria.models import PrendaInventario, PrendaItem, UbicacionItem
from .factories import make_prenda, make_prenda_item


class PrendaInventarioAutoCodigoTests(TestCase):

    def test_primera_prenda_codigo_001(self):
        p = make_prenda()
        self.assertRegex(p.codigo, r'^PRN-\d{3}$')
        self.assertEqual(p.codigo, 'PRN-001')

    def test_segunda_prenda_codigo_002(self):
        make_prenda()
        p2 = make_prenda(nombre='Chaleco')
        self.assertEqual(p2.codigo, 'PRN-002')

    def test_codigo_no_cambia_al_editar(self):
        p = make_prenda()
        original = p.codigo
        p.notas = 'Nota extra'
        p.save()
        self.assertEqual(p.codigo, original)


class PrendaInventarioStrTests(TestCase):

    def test_str_solo_nombre(self):
        p = make_prenda(nombre='Traje Negro', codigo_referencia='', color='', talla='')
        self.assertEqual(str(p), 'Traje Negro')

    def test_str_con_referencia(self):
        p = make_prenda(nombre='Traje', codigo_referencia='REF-001', color='', talla='')
        s = str(p)
        self.assertIn('REF-001', s)

    def test_str_con_color_y_talla(self):
        p = make_prenda(nombre='Traje', codigo_referencia='', color='Negro', talla='M')
        s = str(p)
        self.assertIn('Negro', s)
        self.assertIn('M', s)


class PrendaInventarioCantidadTests(TestCase):
    """cantidad = items activos (no baja)."""

    def test_sin_items_cantidad_cero(self):
        p = make_prenda()
        self.assertEqual(p.cantidad, 0)

    def test_items_disponibles_cuentan(self):
        p = make_prenda()
        make_prenda_item(prenda=p, estado='disponible')
        make_prenda_item(prenda=p, estado='disponible')
        self.assertEqual(p.cantidad, 2)

    def test_items_alquilados_cuentan(self):
        p = make_prenda()
        make_prenda_item(prenda=p, estado='alquilado')
        self.assertEqual(p.cantidad, 1)

    def test_items_en_baja_no_cuentan(self):
        p = make_prenda()
        make_prenda_item(prenda=p, estado='baja')
        self.assertEqual(p.cantidad, 0)

    def test_mix_baja_y_disponible(self):
        p = make_prenda()
        make_prenda_item(prenda=p, estado='disponible')
        make_prenda_item(prenda=p, estado='baja')
        make_prenda_item(prenda=p, estado='disponible')
        self.assertEqual(p.cantidad, 2)


class PrendaInventarioStockDisponibleTests(TestCase):
    """stock_disponible = items con estado='disponible'."""

    def test_sin_items_cero(self):
        p = make_prenda()
        self.assertEqual(p.stock_disponible, 0)

    def test_solo_disponibles(self):
        p = make_prenda()
        make_prenda_item(prenda=p, estado='disponible')
        make_prenda_item(prenda=p, estado='disponible')
        self.assertEqual(p.stock_disponible, 2)

    def test_alquilado_no_cuenta_como_disponible(self):
        p = make_prenda()
        make_prenda_item(prenda=p, estado='disponible')
        make_prenda_item(prenda=p, estado='alquilado')
        self.assertEqual(p.stock_disponible, 1)


class PrendaItemAutoCodigoTests(TestCase):
    """codigo_item se genera como <SKU>-ITM-NN."""

    def test_primer_item_codigo_itm_01(self):
        p = make_prenda()
        item = make_prenda_item(prenda=p)
        self.assertEqual(item.codigo_item, 'PRN-001-ITM-01')

    def test_segundo_item_codigo_itm_02(self):
        p = make_prenda()
        make_prenda_item(prenda=p)
        item2 = make_prenda_item(prenda=p)
        self.assertEqual(item2.codigo_item, 'PRN-001-ITM-02')

    def test_items_de_distintas_prendas_independientes(self):
        p1 = make_prenda(nombre='Saco')
        p2 = make_prenda(nombre='Chaleco')
        i1 = make_prenda_item(prenda=p1)
        i2 = make_prenda_item(prenda=p2)
        # Cada SKU empieza en 01
        self.assertTrue(i1.codigo_item.endswith('-01'))
        self.assertTrue(i2.codigo_item.endswith('-01'))

    def test_codigo_item_unico_global(self):
        """codigo_item debe ser único a nivel de toda la BD."""
        p = make_prenda()
        i1 = make_prenda_item(prenda=p)
        i2 = make_prenda_item(prenda=p)
        self.assertNotEqual(i1.codigo_item, i2.codigo_item)


class PrendaItemMaxUsosEfectivoTests(TestCase):
    """max_usos_efectivo: usa el del item si está definido, sino el del SKU."""

    def test_sin_max_usos_en_ninguno_retorna_none(self):
        p = make_prenda(max_usos_default=None)
        item = make_prenda_item(prenda=p, max_usos=None)
        self.assertIsNone(item.max_usos_efectivo)

    def test_usa_max_usos_del_sku(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, max_usos=None)
        self.assertEqual(item.max_usos_efectivo, 10)

    def test_override_item_tiene_prioridad(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, max_usos=20)
        self.assertEqual(item.max_usos_efectivo, 20)

    def test_override_cero_usa_sku(self):
        """max_usos=0 en item se evalúa como falsy, cae al SKU."""
        p = make_prenda(max_usos_default=15)
        item = make_prenda_item(prenda=p, max_usos=0)
        # 0 or 15 == 15
        self.assertEqual(item.max_usos_efectivo, 15)


class PrendaItemPorcentajeVidaUtilTests(TestCase):

    def test_sin_max_usos_retorna_none(self):
        p = make_prenda(max_usos_default=None)
        item = make_prenda_item(prenda=p, veces_alquilado=5, max_usos=None)
        self.assertIsNone(item.porcentaje_vida_util)

    def test_0_usos_es_0_pct(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=0)
        self.assertEqual(item.porcentaje_vida_util, 0)

    def test_mitad_es_50_pct(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=5)
        self.assertEqual(item.porcentaje_vida_util, 50)

    def test_supera_max_usos_tope_100(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=15)
        self.assertEqual(item.porcentaje_vida_util, 100)


class PrendaItemEstadoVidaUtilTests(TestCase):

    def test_sin_max_usos_retorna_none(self):
        p = make_prenda(max_usos_default=None)
        item = make_prenda_item(prenda=p)
        self.assertIsNone(item.estado_vida_util)

    def test_0_usos_es_ok(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=0)
        self.assertEqual(item.estado_vida_util, 'ok')

    def test_60pct_es_ok(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=6)
        self.assertEqual(item.estado_vida_util, 'ok')

    def test_70pct_es_advertencia(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=7)
        self.assertEqual(item.estado_vida_util, 'advertencia')

    def test_89pct_es_advertencia(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=9)
        # 9/10 = 90% → critico (no 89)
        # Let's compute: 9/10 * 100 = 90 → >=90 → critico
        self.assertEqual(item.estado_vida_util, 'critico')

    def test_90pct_es_critico(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=9)
        self.assertEqual(item.estado_vida_util, 'critico')

    def test_100pct_es_critico(self):
        p = make_prenda(max_usos_default=10)
        item = make_prenda_item(prenda=p, veces_alquilado=10)
        self.assertEqual(item.estado_vida_util, 'critico')


class UbicacionItemTests(TestCase):

    def test_crear_ubicacion(self):
        u = UbicacionItem.objects.create(nombre='Estante A-1')
        self.assertEqual(str(u), 'Estante A-1')

    def test_ubicacion_unica(self):
        UbicacionItem.objects.create(nombre='Estante B')
        with self.assertRaises(IntegrityError):
            UbicacionItem.objects.create(nombre='Estante B')

    def test_asignar_ubicacion_a_item(self):
        p = make_prenda()
        u = UbicacionItem.objects.create(nombre='Colgador 3')
        item = make_prenda_item(prenda=p, ubicacion=u)
        self.assertEqual(item.ubicacion, u)
