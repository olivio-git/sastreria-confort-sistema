"""
test_models_alquileres.py
==========================
Cubre:
  - Auto-generación de código ALQ-NNN
  - recalcular_totales() con descuento
  - con_recargo / dias_retraso (contra la devolución REAL, no contra hoy)
  - estado_color (busca EstadoAlquiler o devuelve 'secondary')
  - AlquilerItem.subtotal
  - total_pagado / saldo_pendiente
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

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


def _momento(dia, hora=12, minuto=0):
    """Datetime aware en la zona local, para simular una devolución real."""
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto)))


class AlquilerConRecargoActivoTests(TestCase):
    """Alquiler todavía afuera: el atraso se mide contra ahora."""

    def test_fecha_futura_sin_recargo(self):
        a = make_alquiler(fecha_devolucion=date.today() + timedelta(days=5))
        self.assertFalse(a.con_recargo)

    def test_fecha_pasada_con_recargo(self):
        a = make_alquiler(fecha_devolucion=date.today() - timedelta(days=1))
        self.assertTrue(a.con_recargo)

    def test_fecha_muy_pasada_con_recargo(self):
        a = make_alquiler(fecha_devolucion=date(2020, 1, 1))
        self.assertTrue(a.con_recargo)


class AlquilerConRecargoDevueltoTests(TestCase):
    """Ya devuelto: el veredicto se congela contra el momento REAL de entrega.

    Este es el bug que hacía que TODO alquiler pasado saliera con recargo: se
    comparaba la fecha pactada contra hoy, así que bastaba con que el calendario
    avanzara para acusar de mora a un cliente que devolvió antes de tiempo.
    """

    def test_devuelto_a_tiempo_hace_anios_no_tiene_recargo(self):
        a = make_alquiler(
            fecha_alquiler=date(2020, 1, 5),
            fecha_devolucion=date(2020, 1, 10),
            fecha_devolucion_real=_momento(date(2020, 1, 10)),
            estado='devuelto',
        )
        self.assertFalse(a.con_recargo)
        self.assertEqual(a.dias_retraso, 0)

    def test_devuelto_antes_de_tiempo_no_tiene_recargo(self):
        a = make_alquiler(
            fecha_devolucion=date.today() - timedelta(days=10),
            fecha_devolucion_real=_momento(date.today() - timedelta(days=13)),
            estado='devuelto',
        )
        self.assertFalse(a.con_recargo)
        self.assertEqual(a.dias_retraso, 0)

    def test_devuelto_tarde_tiene_recargo(self):
        a = make_alquiler(
            fecha_devolucion=date.today() - timedelta(days=10),
            fecha_devolucion_real=_momento(date.today() - timedelta(days=7)),
            estado='devuelto',
        )
        self.assertTrue(a.con_recargo)
        self.assertEqual(a.dias_retraso, 3)

    def test_mismo_dia_antes_de_la_hora_no_tiene_recargo(self):
        dia = date.today() - timedelta(days=4)
        a = make_alquiler(
            fecha_devolucion=dia,
            hora_devolucion=time(18, 0),
            fecha_devolucion_real=_momento(dia, 17, 30),
            estado='devuelto',
        )
        self.assertFalse(a.con_recargo)

    def test_mismo_dia_pasada_la_hora_tiene_recargo_de_un_dia(self):
        dia = date.today() - timedelta(days=4)
        a = make_alquiler(
            fecha_devolucion=dia,
            hora_devolucion=time(18, 0),
            fecha_devolucion_real=_momento(dia, 19, 30),
            estado='devuelto',
        )
        self.assertTrue(a.con_recargo)
        self.assertEqual(a.dias_retraso, 1)

    def test_mismo_dia_sin_hora_pactada_no_tiene_recargo(self):
        """Sin hora acordada, todo el día pactado cuenta como a tiempo."""
        dia = date.today() - timedelta(days=4)
        a = make_alquiler(
            fecha_devolucion=dia,
            hora_devolucion=None,
            fecha_devolucion_real=_momento(dia, 23, 0),
            estado='devuelto',
        )
        self.assertFalse(a.con_recargo)

    def test_devuelto_sin_fecha_real_no_inventa_mora(self):
        """Registro viejo sin rastro en el kardex: sin evidencia no se acusa."""
        a = make_alquiler(
            fecha_devolucion=date(2020, 1, 10),
            fecha_devolucion_real=None,
            estado='devuelto',
        )
        self.assertFalse(a.con_recargo)
        self.assertEqual(a.dias_retraso, 0)


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
