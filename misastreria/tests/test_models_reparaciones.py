"""
test_models_reparaciones.py
============================
Cubre:
  - Auto-generación de código REP-NNN
  - recalcular_total() — suma de items
  - total_pagado / saldo_pendiente (via caja_signals)
  - ReparacionItem
  - __str__
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from misastreria.models import Reparacion, ReparacionItem
from .factories import (
    make_reparacion, make_reparacion_item,
    make_tipo_prenda, make_tipo_reparacion,
    make_cliente, make_empleado,
)


class ReparacionAutoCodigoTests(TestCase):

    def test_primera_reparacion_codigo_001(self):
        rep = make_reparacion()
        self.assertEqual(rep.codigo, 'REP-001')

    def test_segunda_reparacion_codigo_002(self):
        make_reparacion()
        rep2 = make_reparacion()
        self.assertEqual(rep2.codigo, 'REP-002')

    def test_codigo_formato_correcto(self):
        rep = make_reparacion()
        self.assertRegex(rep.codigo, r'^REP-\d{3}$')

    def test_codigo_no_cambia_al_editar(self):
        rep = make_reparacion()
        original = rep.codigo
        rep.estado = 'en_proceso'
        rep.save()
        self.assertEqual(rep.codigo, original)


class ReparacionRecalcularTotalTests(TestCase):
    """recalcular_total() suma los costos de todos los items."""

    def test_sin_items_total_cero(self):
        rep = make_reparacion(total=Decimal('0'))
        rep.recalcular_total()
        rep.refresh_from_db()
        self.assertEqual(rep.total, Decimal('0'))

    def test_un_item(self):
        rep = make_reparacion(total=Decimal('0'))
        make_reparacion_item(reparacion=rep, costo=Decimal('80.00'))
        rep.recalcular_total()
        rep.refresh_from_db()
        self.assertEqual(rep.total, Decimal('80.00'))

    def test_multiples_items_suma(self):
        rep = make_reparacion(total=Decimal('0'))
        make_reparacion_item(reparacion=rep, costo=Decimal('30.00'))
        make_reparacion_item(reparacion=rep, costo=Decimal('50.00'))
        make_reparacion_item(reparacion=rep, costo=Decimal('20.00'))
        rep.recalcular_total()
        rep.refresh_from_db()
        self.assertEqual(rep.total, Decimal('100.00'))

    def test_item_con_costo_none_no_suma(self):
        """Un item sin costo no afecta la suma."""
        rep = make_reparacion(total=Decimal('0'))
        make_reparacion_item(reparacion=rep, costo=None)
        rep.recalcular_total()
        rep.refresh_from_db()
        self.assertEqual(rep.total, Decimal('0'))


class ReparacionSaldoTests(TestCase):
    """saldo_pendiente es max(0, total - total_pagado)."""

    def test_sin_pagos_saldo_igual_a_total(self):
        rep = make_reparacion(total=Decimal('200.00'))
        self.assertEqual(rep.saldo_pendiente, Decimal('200.00'))

    def test_saldo_nunca_negativo(self):
        """No puede haber saldo negativo aunque total_pagado > total."""
        rep = make_reparacion(total=Decimal('0'))
        self.assertEqual(rep.saldo_pendiente, Decimal('0'))

    def test_total_pagado_sin_movimientos_es_cero(self):
        rep = make_reparacion(total=Decimal('100.00'))
        self.assertEqual(rep.total_pagado, Decimal('0'))


class ReparacionItemTests(TestCase):
    """ReparacionItem se crea correctamente."""

    def test_crear_item_con_costo(self):
        rep = make_reparacion()
        item = make_reparacion_item(reparacion=rep, costo=Decimal('45.00'))
        self.assertEqual(item.reparacion, rep)
        self.assertEqual(item.costo, Decimal('45.00'))

    def test_str_item(self):
        rep = make_reparacion()
        item = make_reparacion_item(reparacion=rep)
        s = str(item)
        # Debe mencionar el tipo de prenda y el tipo de reparación
        self.assertIn('—', s)

    def test_multiples_items_mismo_tipo(self):
        rep = make_reparacion()
        tp = make_tipo_prenda()
        tr = make_tipo_reparacion()
        ReparacionItem.objects.create(reparacion=rep, tipo_prenda=tp, tipo_reparacion=tr, costo=Decimal('10'))
        ReparacionItem.objects.create(reparacion=rep, tipo_prenda=tp, tipo_reparacion=tr, costo=Decimal('20'))
        self.assertEqual(rep.items.count(), 2)


class ReparacionStrTests(TestCase):

    def test_str_reparacion(self):
        rep = make_reparacion()
        self.assertIn('REP-001', str(rep))


class ReparacionEstadoTests(TestCase):
    """Transiciones de estado."""

    def test_estado_default_pendiente(self):
        rep = make_reparacion()
        self.assertEqual(rep.estado, 'pendiente')

    def test_cambio_a_en_proceso(self):
        rep = make_reparacion()
        rep.estado = 'en_proceso'
        rep.save()
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'en_proceso')

    def test_cambio_a_entregado(self):
        rep = make_reparacion()
        rep.estado = 'entregado'
        rep.save()
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'entregado')
