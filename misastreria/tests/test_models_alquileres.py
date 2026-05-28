"""
test_models_alquileres.py
==========================
Cubre:
  - Auto-generación de código ALQ-NNN
  - recalcular_totales() con descuento
  - con_recargo property (fecha vencida)
  - estado_color (busca EstadoAlquiler o devuelve 'secondary')
  - AlquilerItem.subtotal
  - total_pagado / saldo_pendiente
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from misastreria.models import Alquiler, AlquilerItem
from .factories import (
    make_alquiler, make_alquiler_item, make_prenda_item,
    make_estado_alquiler,
)


class AlquilerAutoCodigoTests(TestCase):

    def test_primer_alquiler_codigo_001(self):
        a = make_alquiler()
        self.assertRegex(a.codigo, r'^ALQ-\d{3}$')
        self.assertEqual(a.codigo, 'ALQ-001')

    def test_segundo_alquiler_codigo_002(self):
        make_alquiler()
        a2 = make_alquiler()
        self.assertEqual(a2.codigo, 'ALQ-002')

    def test_tipo_auto_alquiler(self):
        a = make_alquiler()
        self.assertEqual(a.tipo, 'alquiler')


class AlquilerRecalcularTotalesTests(TestCase):

    def _add_item(self, alquiler, precio):
        pi = make_prenda_item()
        return AlquilerItem.objects.create(
            alquiler=alquiler,
            prenda_item=pi,
            precio_unitario=precio,
            precio_reparacion=Decimal('0'),
        )

    def test_sin_descuento_total_igual_subtotal(self):
        a = make_alquiler(descuento=Decimal('0'), subtotal=Decimal('0'), total=Decimal('0'))
        self._add_item(a, Decimal('100.00'))
        self._add_item(a, Decimal('80.00'))
        a.recalcular_totales()
        self.assertEqual(a.subtotal, Decimal('180.00'))
        self.assertEqual(a.total, Decimal('180.00'))

    def test_con_descuento_20pct(self):
        a = make_alquiler(descuento=Decimal('20'), subtotal=Decimal('0'), total=Decimal('0'))
        self._add_item(a, Decimal('200.00'))
        a.recalcular_totales()
        self.assertEqual(a.total, Decimal('160.00'))

    def test_sin_items_totales_cero(self):
        a = make_alquiler(descuento=Decimal('0'), subtotal=Decimal('0'), total=Decimal('0'))
        a.recalcular_totales()
        self.assertEqual(a.subtotal, Decimal('0'))
        self.assertEqual(a.total, Decimal('0'))


class AlquilerConRecargoTests(TestCase):
    """con_recargo=True cuando fecha_devolucion está vencida."""

    def test_fecha_futura_sin_recargo(self):
        a = make_alquiler(fecha_devolucion=date.today() + timedelta(days=5))
        self.assertFalse(a.con_recargo)

    def test_fecha_pasada_con_recargo(self):
        a = make_alquiler(fecha_devolucion=date.today() - timedelta(days=1))
        self.assertTrue(a.con_recargo)

    def test_fecha_muy_pasada_con_recargo(self):
        a = make_alquiler(fecha_devolucion=date(2020, 1, 1))
        self.assertTrue(a.con_recargo)


class AlquilerEstadoColorTests(TestCase):
    """estado_color busca en EstadoAlquiler o devuelve 'secondary'."""

    def test_estado_existente_devuelve_color(self):
        make_estado_alquiler(nombre='alquilado', color='alquilado')
        a = make_alquiler(estado='alquilado')
        self.assertEqual(a.estado_color, 'alquilado')

    def test_estado_inexistente_devuelve_secondary(self):
        a = make_alquiler(estado='estado_raro_inexistente')
        self.assertEqual(a.estado_color, 'secondary')

    def test_estado_display_capitaliza_underscores(self):
        a = make_alquiler(estado='en_proceso')
        self.assertNotIn('_', a.estado_display)


class AlquilerItemSubtotalTests(TestCase):
    """AlquilerItem.subtotal = precio_unitario + precio_reparacion."""

    def test_subtotal_sin_reparacion(self):
        a = make_alquiler()
        pi = make_prenda_item()
        item = AlquilerItem.objects.create(
            alquiler=a, prenda_item=pi,
            precio_unitario=Decimal('150.00'),
            precio_reparacion=Decimal('0'),
        )
        self.assertEqual(item.subtotal, Decimal('150.00'))

    def test_subtotal_con_reparacion(self):
        a = make_alquiler()
        pi = make_prenda_item()
        item = AlquilerItem.objects.create(
            alquiler=a, prenda_item=pi,
            precio_unitario=Decimal('150.00'),
            precio_reparacion=Decimal('30.00'),
        )
        self.assertEqual(item.subtotal, Decimal('180.00'))


class AlquilerSaldoTests(TestCase):
    """saldo_pendiente = max(0, total - total_pagado)."""

    def test_sin_pagos_saldo_igual_total(self):
        a = make_alquiler(total=Decimal('300.00'))
        self.assertEqual(a.saldo_pendiente, Decimal('300.00'))

    def test_total_pagado_sin_movimientos_cero(self):
        a = make_alquiler(total=Decimal('100.00'))
        self.assertEqual(a.total_pagado, Decimal('0'))

    def test_saldo_pendiente_nunca_negativo(self):
        a = make_alquiler(total=Decimal('0'))
        self.assertEqual(a.saldo_pendiente, Decimal('0'))


class AlquilerStrTests(TestCase):

    def test_str_alquiler(self):
        a = make_alquiler()
        self.assertIn('ALQ-001', str(a))
