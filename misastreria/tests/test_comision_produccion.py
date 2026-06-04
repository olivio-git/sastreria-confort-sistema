"""
test_comision_produccion.py
===========================
Cubre la comisión de producción (OrdenProduccionEmpleado):
  - Monto fijo en Bs por empleado/fase, devengado al crear la orden.
  - 5ta fuente del saldo de comisión del empleado (junto a reparación/confección/venta/alquiler).
  - Mismo empleado en distintas fases (permitido por el UniqueConstraint del triple).
  - Duplicado exacto (orden, empleado, fase) rechazado a nivel modelo y manejado por el helper.
  - Devenga sin importar el estado de la orden.
"""
from decimal import Decimal

from django.db import IntegrityError
from django.http import QueryDict
from django.test import TestCase

from misastreria.models import OrdenProduccionEmpleado
from misastreria.views import (
    _calcular_saldo_comision_empleado, _guardar_asignaciones_produccion,
)
from .factories import (
    make_empleado, make_orden_produccion, make_orden_produccion_empleado,
)


def _qd(d):
    qd = QueryDict(mutable=True)
    qd.update(d)
    return qd


class ComisionProduccionTests(TestCase):

    def test_monto_comision_property(self):
        orden = make_orden_produccion()
        emp = make_empleado()
        a = make_orden_produccion_empleado(orden, emp, 'corte', Decimal('120'))
        self.assertEqual(a.monto_comision, Decimal('120'))

    def test_produccion_quinta_fuente(self):
        """Una asignación de producción devenga al saldo del empleado."""
        orden = make_orden_produccion()
        emp = make_empleado()
        make_orden_produccion_empleado(orden, emp, 'costura', Decimal('120'))
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('120'))

    def test_mismo_empleado_distintas_fases(self):
        """El mismo empleado puede cobrar en corte y terminado de la misma orden."""
        orden = make_orden_produccion()
        emp = make_empleado()
        make_orden_produccion_empleado(orden, emp, 'corte', Decimal('50'))
        make_orden_produccion_empleado(orden, emp, 'terminado', Decimal('80'))
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('130'))

    def test_dos_empleados_misma_fase(self):
        """Dos empleados distintos pueden compartir la fase costura."""
        orden = make_orden_produccion()
        e1 = make_empleado(ci='P-1')
        e2 = make_empleado(ci='P-2')
        make_orden_produccion_empleado(orden, e1, 'costura', Decimal('40'))
        make_orden_produccion_empleado(orden, e2, 'costura', Decimal('60'))
        self.assertEqual(_calcular_saldo_comision_empleado(e1), Decimal('40'))
        self.assertEqual(_calcular_saldo_comision_empleado(e2), Decimal('60'))

    def test_triple_duplicado_rechazado_modelo(self):
        """El UniqueConstraint bloquea (orden, empleado, fase) idéntico."""
        orden = make_orden_produccion()
        emp = make_empleado()
        make_orden_produccion_empleado(orden, emp, 'corte', Decimal('50'))
        with self.assertRaises(IntegrityError):
            OrdenProduccionEmpleado.objects.create(
                orden=orden, empleado=emp, responsabilidad='corte',
                monto_comision_fijo=Decimal('99'))

    def test_guardar_helper_duplicado_devuelve_error(self):
        """El helper recrea filas y reporta el duplicado sin romper la request."""
        orden = make_orden_produccion()
        emp = make_empleado()
        post = _qd({
            'asignaciones_prod_count': '2',
            'asignacion_prod[0][empleado]': str(emp.id),
            'asignacion_prod[0][responsabilidad]': 'corte',
            'asignacion_prod[0][monto]': '50',
            'asignacion_prod[1][empleado]': str(emp.id),
            'asignacion_prod[1][responsabilidad]': 'corte',
            'asignacion_prod[1][monto]': '70',
        })
        errores = _guardar_asignaciones_produccion(orden, post)
        self.assertEqual(orden.empleados_produccion.count(), 1)  # solo la primera entró
        self.assertTrue(any('ya está asignado' in e for e in errores))

    def test_guardar_helper_crea_filas(self):
        """El helper crea las asignaciones parseadas del POST."""
        orden = make_orden_produccion()
        e1 = make_empleado(ci='P-1')
        e2 = make_empleado(ci='P-2')
        post = _qd({
            'asignaciones_prod_count': '2',
            'asignacion_prod[0][empleado]': str(e1.id),
            'asignacion_prod[0][responsabilidad]': 'corte',
            'asignacion_prod[0][monto]': '100',
            'asignacion_prod[1][empleado]': str(e2.id),
            'asignacion_prod[1][responsabilidad]': 'costura',
            'asignacion_prod[1][monto]': '30',
        })
        errores = _guardar_asignaciones_produccion(orden, post)
        self.assertEqual(errores, [])
        self.assertEqual(orden.empleados_produccion.count(), 2)
        self.assertEqual(_calcular_saldo_comision_empleado(e1), Decimal('100'))
        self.assertEqual(_calcular_saldo_comision_empleado(e2), Decimal('30'))

    def test_saldo_incluye_produccion_sin_gating(self):
        """Producción devenga aunque la orden esté en 'corte' (en proceso)."""
        orden = make_orden_produccion(estado='corte')
        emp = make_empleado()
        make_orden_produccion_empleado(orden, emp, 'corte', Decimal('75'))
        self.assertEqual(_calcular_saldo_comision_empleado(emp), Decimal('75'))
