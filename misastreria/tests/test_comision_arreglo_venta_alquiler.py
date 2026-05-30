"""
test_comision_arreglo_venta_alquiler.py
=======================================
Cubre la comisión de empleado sobre el ARREGLO (tipo_reparacion + precio_reparacion)
dentro de los ítems de Venta y Alquiler:
  - VentaItem / AlquilerItem.monto_comision (base = precio_reparacion)
  - _calcular_saldo_comision_empleado incluye arreglos de:
      * ventas estado='efectuada'
      * alquileres estado='devuelto'
  - No devenga mientras el documento no esté efectuado/devuelto.
  - No devenga si no hay empleado o porcentaje.
"""
from decimal import Decimal

from django.test import TestCase

from misastreria.models import Venta, VentaItem, Alquiler, AlquilerItem
from misastreria.views import _calcular_saldo_comision_empleado
from .factories import (
    make_empleado, make_tipo_reparacion, make_prenda_item,
    make_venta, make_alquiler,
)


class MontoComisionArregloTests(TestCase):

    def test_venta_item_monto_comision(self):
        emp = make_empleado()
        vi = VentaItem.objects.create(
            venta=make_venta(), prenda_item=make_prenda_item(),
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=emp, porcentaje_comision=Decimal('20'),
        )
        # 20% de 50 = 10 (NO sobre el precio de la prenda)
        self.assertEqual(vi.monto_comision, Decimal('10.0000'))

    def test_alquiler_item_monto_comision(self):
        emp = make_empleado()
        ai = AlquilerItem.objects.create(
            alquiler=make_alquiler(), prenda_item=make_prenda_item(),
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, porcentaje_comision=Decimal('30'),
        )
        self.assertEqual(ai.monto_comision, Decimal('12.0000'))

    def test_sin_porcentaje_monto_cero(self):
        vi = VentaItem.objects.create(
            venta=make_venta(), prenda_item=make_prenda_item(),
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
        )
        self.assertEqual(vi.monto_comision, Decimal('0'))


class SaldoComisionArregloTests(TestCase):

    def test_venta_devenga_solo_cuando_efectuada(self):
        emp = make_empleado()
        tr = make_tipo_reparacion()
        venta = make_venta(estado='en_proceso')
        VentaItem.objects.create(
            venta=venta, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=emp, porcentaje_comision=Decimal('20'),
        )
        # en_proceso → no devenga
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('0'))
        # efectuada → devenga 10
        venta.estado = 'efectuada'
        venta.save(update_fields=['estado'])
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('10'))

    def test_alquiler_devenga_solo_cuando_devuelto(self):
        emp = make_empleado()
        tr = make_tipo_reparacion()
        alquiler = make_alquiler(estado='alquilado')
        AlquilerItem.objects.create(
            alquiler=alquiler, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, porcentaje_comision=Decimal('30'),
        )
        # alquilado → no devenga
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('0'))
        # devuelto → devenga 12
        alquiler.estado = 'devuelto'
        alquiler.save(update_fields=['estado'])
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('12'))

    def test_suma_venta_y_alquiler(self):
        emp = make_empleado()
        tr = make_tipo_reparacion()
        venta = make_venta(estado='efectuada')
        VentaItem.objects.create(
            venta=venta, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=emp, porcentaje_comision=Decimal('20'),
        )
        alquiler = make_alquiler(estado='devuelto')
        AlquilerItem.objects.create(
            alquiler=alquiler, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, porcentaje_comision=Decimal('30'),
        )
        # 10 + 12 = 22
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('22'))

    def test_sin_empleado_no_devenga(self):
        emp = make_empleado()
        tr = make_tipo_reparacion()
        venta = make_venta(estado='efectuada')
        # arreglo SIN empleado asignado → no aporta al saldo de nadie
        VentaItem.objects.create(
            venta=venta, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
        )
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('0'))
