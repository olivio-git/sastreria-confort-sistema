"""
test_models_confecciones.py
============================
Cubre:
  - Auto-generación de código CONF-NNN
  - saldo = precio - adelanto (calculado en save)
  - garantia_estado property
  - total_pagado / saldo_pendiente
  - __str__
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from misastreria.models import Confeccion
from .factories import make_confeccion, make_cliente


class ConfeccionAutoCodigoTests(TestCase):

    def test_primera_confeccion_codigo_001(self):
        c = make_confeccion()
        self.assertRegex(c.codigo, r'^CONF-\d{3}$')
        self.assertEqual(c.codigo, 'CONF-001')

    def test_segunda_confeccion_codigo_002(self):
        make_confeccion()
        c2 = make_confeccion()
        self.assertEqual(c2.codigo, 'CONF-002')

    def test_codigo_no_cambia_al_editar(self):
        c = make_confeccion()
        original = c.codigo
        c.estado = 'en_proceso'
        c.save()
        self.assertEqual(c.codigo, original)


class ConfeccionSaldoTests(TestCase):
    """saldo = precio - adelanto, calculado en save."""

    def test_saldo_inicial_sin_adelanto(self):
        c = make_confeccion(precio=Decimal('500.00'), adelanto=Decimal('0'))
        self.assertEqual(c.saldo, Decimal('500.00'))

    def test_saldo_con_adelanto_parcial(self):
        c = make_confeccion(precio=Decimal('500.00'), adelanto=Decimal('200.00'))
        self.assertEqual(c.saldo, Decimal('300.00'))

    def test_saldo_pago_completo(self):
        c = make_confeccion(precio=Decimal('500.00'), adelanto=Decimal('500.00'))
        self.assertEqual(c.saldo, Decimal('0.00'))

    def test_saldo_se_actualiza_al_editar(self):
        c = make_confeccion(precio=Decimal('500.00'), adelanto=Decimal('0'))
        c.adelanto = Decimal('300.00')
        c.save()
        c.refresh_from_db()
        self.assertEqual(c.saldo, Decimal('200.00'))

    def test_saldo_puede_ser_negativo_si_adelanto_mayor(self):
        """El sistema no bloquea adelanto > precio (saldo negativo posible)."""
        c = make_confeccion(precio=Decimal('100.00'), adelanto=Decimal('150.00'))
        self.assertEqual(c.saldo, Decimal('-50.00'))


class ConfeccionGarantiaEstadoTests(TestCase):
    """garantia_estado devuelve 'vigente', 'vencida' o None."""

    def test_sin_garantia_estado_none(self):
        c = make_confeccion(garantia_hasta=None)
        self.assertIsNone(c.garantia_estado)

    def test_garantia_vigente(self):
        c = make_confeccion(garantia_hasta=date.today() + timedelta(days=30))
        self.assertEqual(c.garantia_estado, 'vigente')

    def test_garantia_hoy_vigente(self):
        c = make_confeccion(garantia_hasta=date.today())
        self.assertEqual(c.garantia_estado, 'vigente')

    def test_garantia_vencida(self):
        c = make_confeccion(garantia_hasta=date.today() - timedelta(days=1))
        self.assertEqual(c.garantia_estado, 'vencida')

    def test_garantia_vencida_hace_meses(self):
        c = make_confeccion(garantia_hasta=date(2020, 1, 1))
        self.assertEqual(c.garantia_estado, 'vencida')


class ConfeccionSaldoPendienteTests(TestCase):
    """saldo_pendiente = max(0, precio - total_pagado)."""

    def test_sin_pagos_saldo_igual_a_precio(self):
        c = make_confeccion(precio=Decimal('500.00'))
        self.assertEqual(c.saldo_pendiente, Decimal('500.00'))

    def test_total_pagado_sin_movimientos_es_cero(self):
        c = make_confeccion(precio=Decimal('300.00'))
        self.assertEqual(c.total_pagado, Decimal('0'))

    def test_saldo_pendiente_nunca_negativo(self):
        c = make_confeccion(precio=Decimal('0'))
        self.assertEqual(c.saldo_pendiente, Decimal('0'))


class ConfeccionEstadoTests(TestCase):

    def test_estado_default_pendiente(self):
        c = make_confeccion()
        self.assertEqual(c.estado, 'pendiente')

    def test_cambio_estado_en_proceso(self):
        c = make_confeccion()
        c.estado = 'en_proceso'
        c.save()
        self.assertEqual(c.estado, 'en_proceso')

    def test_cambio_estado_entregado(self):
        c = make_confeccion()
        c.estado = 'entregado'
        c.save()
        self.assertEqual(c.estado, 'entregado')


class ConfeccionStrTests(TestCase):

    def test_str_con_cliente(self):
        cli = make_cliente()
        c = make_confeccion(cliente=cli)
        self.assertIn('CONF-001', str(c))

    def test_str_sin_cliente(self):
        c = make_confeccion()
        self.assertIn('CONF-001', str(c))
        self.assertIn('Sin cliente', str(c))
