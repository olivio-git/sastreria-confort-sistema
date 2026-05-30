"""
test_asignaciones_empleado.py
=============================
Cubre el feature de múltiples empleados asignados por trabajo
(reparación / confección), cada uno con su porcentaje de comisión:
  - ReparacionEmpleado / ConfeccionEmpleado.monto_comision
  - _calcular_saldo_comision_empleado (devengado vía asignaciones)
  - _parse_asignaciones (parseo del POST: huecos, duplicados)
  - _guardar_asignaciones (recrea filas + setea lead)
  - empleados_extra (indicador '+N')
"""
import datetime
from decimal import Decimal

from django.http import QueryDict
from django.test import TestCase

from misastreria.models import (
    Reparacion, ReparacionEmpleado, Confeccion, ConfeccionEmpleado,
)
from misastreria.views import (
    _calcular_saldo_comision_empleado, _guardar_asignaciones, _parse_asignaciones,
)
from .factories import make_empleado, make_reparacion, make_confeccion


def _qd(d):
    qd = QueryDict(mutable=True)
    qd.update(d)
    return qd


class MontoComisionTests(TestCase):

    def test_monto_reparacion(self):
        rep = make_reparacion(total=Decimal('1000'))
        emp = make_empleado()
        a = ReparacionEmpleado.objects.create(reparacion=rep, empleado=emp, porcentaje_comision=Decimal('15'))
        self.assertEqual(a.monto_comision, Decimal('150.00'))

    def test_monto_confeccion(self):
        conf = make_confeccion(precio=Decimal('800'))
        emp = make_empleado()
        a = ConfeccionEmpleado.objects.create(confeccion=conf, empleado=emp, porcentaje_comision=Decimal('25'))
        self.assertEqual(a.monto_comision, Decimal('200.00'))


class SaldoComisionMultiEmpleadoTests(TestCase):

    def test_varios_empleados_un_trabajo_cada_uno_su_comision(self):
        rep = make_reparacion(total=Decimal('1000'), estado='entregado')
        e1 = make_empleado(ci='C-1')
        e2 = make_empleado(ci='C-2')
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e1, porcentaje_comision=Decimal('50'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e2, porcentaje_comision=Decimal('30'))
        self.assertEqual(_calcular_saldo_comision_empleado(e1), Decimal('500'))
        self.assertEqual(_calcular_saldo_comision_empleado(e2), Decimal('300'))

    def test_solo_cuenta_trabajos_entregados(self):
        e = make_empleado()
        entregada = make_reparacion(total=Decimal('400'), estado='entregado')
        pendiente = make_reparacion(total=Decimal('400'), estado='pendiente')
        ReparacionEmpleado.objects.create(reparacion=entregada, empleado=e, porcentaje_comision=Decimal('10'))
        ReparacionEmpleado.objects.create(reparacion=pendiente, empleado=e, porcentaje_comision=Decimal('10'))
        # solo la entregada devenga: 400 * 10% = 40
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('40'))

    def test_devengado_suma_reparacion_y_confeccion(self):
        e = make_empleado()
        rep = make_reparacion(total=Decimal('1000'), estado='entregado')
        conf = make_confeccion(precio=Decimal('500'), estado='entregado')
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e, porcentaje_comision=Decimal('10'))
        ConfeccionEmpleado.objects.create(confeccion=conf, empleado=e, porcentaje_comision=Decimal('20'))
        # 100 + 100 = 200
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('200'))


class ParseAsignacionesTests(TestCase):

    def test_parsea_filas_validas(self):
        qd = _qd({'asignaciones_count': '2',
                  'asignacion[0][empleado]': '5', 'asignacion[0][pct]': '50',
                  'asignacion[1][empleado]': '7', 'asignacion[1][pct]': '30'})
        self.assertEqual(_parse_asignaciones(qd), [('5', Decimal('50')), ('7', Decimal('30'))])

    def test_salta_filas_vacias_y_huecos(self):
        # fila 1 vacía (eliminada en UI); count es high-water = 3
        qd = _qd({'asignaciones_count': '3',
                  'asignacion[0][empleado]': '5', 'asignacion[0][pct]': '50',
                  'asignacion[2][empleado]': '7', 'asignacion[2][pct]': '30'})
        self.assertEqual(_parse_asignaciones(qd), [('5', Decimal('50')), ('7', Decimal('30'))])

    def test_evita_empleado_duplicado(self):
        qd = _qd({'asignaciones_count': '2',
                  'asignacion[0][empleado]': '5', 'asignacion[0][pct]': '50',
                  'asignacion[1][empleado]': '5', 'asignacion[1][pct]': '30'})
        self.assertEqual(_parse_asignaciones(qd), [('5', Decimal('50'))])


class GuardarAsignacionesTests(TestCase):

    def test_crea_filas_y_setea_lead(self):
        rep = make_reparacion(total=Decimal('1000'))
        e1 = make_empleado(ci='L-1'); e2 = make_empleado(ci='L-2')
        qd = _qd({'asignaciones_count': '2',
                  'asignacion[0][empleado]': str(e1.id), 'asignacion[0][pct]': '40',
                  'asignacion[1][empleado]': str(e2.id), 'asignacion[1][pct]': '20'})
        errores = _guardar_asignaciones(rep, qd, ReparacionEmpleado, 'reparacion')
        self.assertEqual(errores, [])
        rep.refresh_from_db()
        self.assertEqual(rep.empleado_id, e1.id)            # lead = primera fila
        self.assertEqual(rep.porcentaje_comision, Decimal('40'))
        self.assertEqual(rep.asignaciones.count(), 2)

    def test_reasignar_reemplaza_filas_anteriores(self):
        rep = make_reparacion(total=Decimal('1000'))
        e1 = make_empleado(ci='R-1'); e2 = make_empleado(ci='R-2')
        _guardar_asignaciones(rep, _qd({'asignaciones_count': '1',
            'asignacion[0][empleado]': str(e1.id), 'asignacion[0][pct]': '50'}),
            ReparacionEmpleado, 'reparacion')
        # re-guardar solo con e2
        _guardar_asignaciones(rep, _qd({'asignaciones_count': '1',
            'asignacion[0][empleado]': str(e2.id), 'asignacion[0][pct]': '10'}),
            ReparacionEmpleado, 'reparacion')
        rep.refresh_from_db()
        self.assertEqual(rep.asignaciones.count(), 1)
        self.assertEqual(rep.empleado_id, e2.id)

    def test_sin_asignaciones_deja_lead_nulo(self):
        rep = make_reparacion(total=Decimal('1000'))
        _guardar_asignaciones(rep, _qd({'asignaciones_count': '0'}), ReparacionEmpleado, 'reparacion')
        rep.refresh_from_db()
        self.assertIsNone(rep.empleado_id)
        self.assertEqual(rep.asignaciones.count(), 0)


class EmpleadosExtraTests(TestCase):

    def test_extra_cero_con_un_empleado(self):
        rep = make_reparacion(total=Decimal('100'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='X-1'), porcentaje_comision=Decimal('5'))
        self.assertEqual(rep.empleados_extra, 0)

    def test_extra_cuenta_adicionales(self):
        rep = make_reparacion(total=Decimal('100'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='Y-1'), porcentaje_comision=Decimal('5'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='Y-2'), porcentaje_comision=Decimal('5'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='Y-3'), porcentaje_comision=Decimal('5'))
        self.assertEqual(rep.empleados_extra, 2)
