"""
test_models_ventas.py
======================
Cubre:
  - Auto-generación de código VEN-NNN
  - VentaItem.subtotal = precio_unitario + precio_reparacion
  - Venta.recalcular_totales() — incluye descuento
  - __str__
"""
from decimal import Decimal

from django.test import TestCase

from misastreria.models import Venta, VentaItem
from .factories import (
    make_venta, make_prenda_item, make_tipo_reparacion,
)


class VentaAutoCodigoTests(TestCase):

    def test_primera_venta_codigo_001(self):
        v = make_venta()
        self.assertEqual(v.codigo, 'VEN-001')

    def test_segunda_venta_codigo_002(self):
        make_venta()
        v2 = make_venta()
        self.assertEqual(v2.codigo, 'VEN-002')

    def test_codigo_formato(self):
        v = make_venta()
        self.assertRegex(v.codigo, r'^VEN-\d{3}$')

    def test_tipo_auto_ventas(self):
        v = make_venta()
        self.assertEqual(v.tipo, 'ventas')


class VentaItemSubtotalTests(TestCase):
    """VentaItem.subtotal = precio_unitario + precio_reparacion."""

    def test_subtotal_sin_reparacion(self):
        v = make_venta()
        pi = make_prenda_item()
        item = VentaItem.objects.create(
            venta=v,
            prenda_item=pi,
            precio_unitario=Decimal('100.00'),
            precio_reparacion=Decimal('0'),
        )
        self.assertEqual(item.subtotal, Decimal('100.00'))

    def test_subtotal_con_reparacion(self):
        v = make_venta()
        pi = make_prenda_item()
        item = VentaItem.objects.create(
            venta=v,
            prenda_item=pi,
            precio_unitario=Decimal('100.00'),
            precio_reparacion=Decimal('25.00'),
        )
        self.assertEqual(item.subtotal, Decimal('125.00'))

    def test_subtotal_se_recalcula_al_editar(self):
        v = make_venta()
        pi = make_prenda_item()
        item = VentaItem.objects.create(
            venta=v,
            prenda_item=pi,
            precio_unitario=Decimal('80.00'),
            precio_reparacion=Decimal('0'),
        )
        item.precio_reparacion = Decimal('10.00')
        item.save()
        self.assertEqual(item.subtotal, Decimal('90.00'))


class VentaRecalcularTotalesTests(TestCase):
    """recalcular_totales() calcula subtotal y aplica descuento."""

    def _add_item(self, venta, precio, reparacion=Decimal('0')):
        pi = make_prenda_item()
        return VentaItem.objects.create(
            venta=venta,
            prenda_item=pi,
            precio_unitario=precio,
            precio_reparacion=reparacion,
        )

    def test_sin_descuento_total_igual_subtotal(self):
        v = make_venta(descuento=Decimal('0'))
        self._add_item(v, Decimal('100.00'))
        self._add_item(v, Decimal('50.00'))
        v.recalcular_totales()
        self.assertEqual(v.subtotal, Decimal('150.00'))
        self.assertEqual(v.total, Decimal('150.00'))

    def test_con_descuento_10pct(self):
        v = make_venta(descuento=Decimal('10'))
        self._add_item(v, Decimal('200.00'))
        v.recalcular_totales()
        self.assertEqual(v.subtotal, Decimal('200.00'))
        self.assertEqual(v.total, Decimal('180.00'))

    def test_con_descuento_50pct(self):
        v = make_venta(descuento=Decimal('50'))
        self._add_item(v, Decimal('300.00'))
        v.recalcular_totales()
        self.assertEqual(v.total, Decimal('150.00'))

    def test_descuento_100pct_total_cero(self):
        v = make_venta(descuento=Decimal('100'))
        self._add_item(v, Decimal('500.00'))
        v.recalcular_totales()
        self.assertEqual(v.total, Decimal('0'))

    def test_sin_items_totales_cero(self):
        v = make_venta(descuento=Decimal('0'))
        v.recalcular_totales()
        self.assertEqual(v.subtotal, Decimal('0'))
        self.assertEqual(v.total, Decimal('0'))

    def test_items_con_reparacion_incluidos_en_subtotal(self):
        v = make_venta(descuento=Decimal('0'))
        self._add_item(v, Decimal('100.00'), reparacion=Decimal('20.00'))
        v.recalcular_totales()
        self.assertEqual(v.subtotal, Decimal('120.00'))


class VentaStrTests(TestCase):

    def test_str_venta(self):
        v = make_venta()
        self.assertIn('VEN-001', str(v))
