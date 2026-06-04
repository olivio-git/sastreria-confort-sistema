"""
test_comision_arreglo_venta_alquiler.py
=======================================
Cubre la comisión de empleado sobre el ARREGLO (tipo_reparacion + precio_reparacion)
dentro de los ítems de Venta y Alquiler:
  - VentaItem / AlquilerItem.monto_comision (monto fijo en Bs)
  - _calcular_saldo_comision_empleado incluye arreglos de todos los estados.
  - Devenga en el momento de creación, sin esperar efectuada/devuelto.
  - No devenga si monto_comision_fijo es NULL.
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
            empleado=emp, monto_comision_fijo=Decimal('10'),
        )
        # monto fijo directo: 10
        self.assertEqual(vi.monto_comision, Decimal('10'))

    def test_alquiler_item_monto_comision(self):
        emp = make_empleado()
        ai = AlquilerItem.objects.create(
            alquiler=make_alquiler(), prenda_item=make_prenda_item(),
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, monto_comision_fijo=Decimal('12'),
        )
        self.assertEqual(ai.monto_comision, Decimal('12'))

    def test_sin_monto_comision_cero(self):
        vi = VentaItem.objects.create(
            venta=make_venta(), prenda_item=make_prenda_item(),
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
        )
        self.assertEqual(vi.monto_comision, Decimal('0'))


class SaldoComisionArregloTests(TestCase):

    def test_venta_devenga_en_creacion(self):
        """VentaItem devenga commission immediately regardless of venta estado."""
        emp = make_empleado()
        tr = make_tipo_reparacion()
        venta = make_venta(estado='en_proceso')
        VentaItem.objects.create(
            venta=venta, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=emp, monto_comision_fijo=Decimal('10'),
        )
        # en_proceso → ya devenga con monto fijo
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('10'))

    def test_alquiler_devenga_en_creacion(self):
        """AlquilerItem devenga commission immediately regardless of alquiler estado."""
        emp = make_empleado()
        tr = make_tipo_reparacion()
        alquiler = make_alquiler(estado='alquilado')
        AlquilerItem.objects.create(
            alquiler=alquiler, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, monto_comision_fijo=Decimal('12'),
        )
        # alquilado → ya devenga con monto fijo
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('12'))

    def test_suma_venta_y_alquiler(self):
        emp = make_empleado()
        tr = make_tipo_reparacion()
        venta = make_venta(estado='efectuada')
        VentaItem.objects.create(
            venta=venta, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=emp, monto_comision_fijo=Decimal('10'),
        )
        alquiler = make_alquiler(estado='devuelto')
        AlquilerItem.objects.create(
            alquiler=alquiler, prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, monto_comision_fijo=Decimal('12'),
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

    def test_venta_arreglo_monto_fijo(self):
        """VentaItem(monto_comision_fijo=45) → devengado from ventas = 45."""
        emp = make_empleado()
        tr = make_tipo_reparacion()
        VentaItem.objects.create(
            venta=make_venta(), prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=emp, monto_comision_fijo=Decimal('45'),
        )
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('45'))

    def test_alquiler_arreglo_monto_fijo(self):
        """AlquilerItem(monto_comision_fijo=20) → devengado from alquileres = 20."""
        emp = make_empleado()
        tr = make_tipo_reparacion()
        AlquilerItem.objects.create(
            alquiler=make_alquiler(), prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=emp, monto_comision_fijo=Decimal('20'),
        )
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('20'))
