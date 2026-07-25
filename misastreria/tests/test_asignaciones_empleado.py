"""
test_asignaciones_empleado.py
=============================
Cubre el feature de múltiples empleados asignados por trabajo
(reparación / confección), cada uno con su comisión:
  - ReparacionEmpleado.monto_comision (monto fijo en Bs)
  - ConfeccionEmpleado.monto_comision (monto fijo en Bs)
  - _calcular_saldo_comision_empleado (devengado vía asignaciones, sin filtro de estado)
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
        a = ReparacionEmpleado.objects.create(reparacion=rep, empleado=emp, monto_comision_fijo=Decimal('150'))
        self.assertEqual(a.monto_comision, Decimal('150.00'))

    def test_monto_confeccion(self):
        conf = make_confeccion(precio=Decimal('800'))
        emp = make_empleado()
        a = ConfeccionEmpleado.objects.create(confeccion=conf, empleado=emp, monto_comision_fijo=Decimal('200'))
        self.assertEqual(a.monto_comision, Decimal('200'))


class SaldoComisionMultiEmpleadoTests(TestCase):

    def test_varios_empleados_un_trabajo_cada_uno_su_comision(self):
        rep = make_reparacion(total=Decimal('1000'))
        e1 = make_empleado(ci='C-1')
        e2 = make_empleado(ci='C-2')
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e1, monto_comision_fijo=Decimal('500'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e2, monto_comision_fijo=Decimal('300'))
        self.assertEqual(_calcular_saldo_comision_empleado(e1), Decimal('500'))
        self.assertEqual(_calcular_saldo_comision_empleado(e2), Decimal('300'))

    def test_devenga_en_creacion(self):
        """Reparacion accrues commission immediately, regardless of estado."""
        e = make_empleado()
        pendiente = make_reparacion(total=Decimal('400'), estado='pendiente')
        en_proceso = make_reparacion(total=Decimal('400'), estado='en_proceso')
        ReparacionEmpleado.objects.create(reparacion=pendiente, empleado=e, monto_comision_fijo=Decimal('40'))
        ReparacionEmpleado.objects.create(reparacion=en_proceso, empleado=e, monto_comision_fijo=Decimal('40'))
        # ambas deviengan monto fijo: 40 + 40 = 80
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('80'))

    def test_devengado_suma_reparacion_y_confeccion(self):
        e = make_empleado()
        rep = make_reparacion(total=Decimal('1000'))
        conf = make_confeccion(precio=Decimal('500'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e, monto_comision_fijo=Decimal('100'))
        ConfeccionEmpleado.objects.create(confeccion=conf, empleado=e, monto_comision_fijo=Decimal('100'))
        # 100 (rep fijo) + 100 (conf fijo) = 200
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('200'))


class ParseAsignacionesTests(TestCase):

    def test_parsea_filas_validas(self):
        qd = _qd({'asignaciones_count': '2',
                  'asignacion[0][empleado]': '5', 'asignacion[0][pct]': '50',
                  'asignacion[1][empleado]': '7', 'asignacion[1][pct]': '30'})
        self.assertEqual(_parse_asignaciones(qd), [('5', Decimal('50')), ('7', Decimal('30'))])

    def test_parsea_filas_monto_key(self):
        """_parse_asignaciones with monto_key='monto' reads [monto] POST key."""
        qd = _qd({'asignaciones_count': '1',
                  'asignacion[0][empleado]': '5', 'asignacion[0][monto]': '80'})
        self.assertEqual(_parse_asignaciones(qd, monto_key='monto'), [('5', Decimal('80'))])

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
                  'asignacion[0][empleado]': str(e1.id), 'asignacion[0][monto]': '400',
                  'asignacion[1][empleado]': str(e2.id), 'asignacion[1][monto]': '200'})
        errores = _guardar_asignaciones(rep, qd, ReparacionEmpleado, 'reparacion',
                                        commission_field='monto_comision_fijo',
                                        monto_key='monto', sync_lead=False)
        self.assertEqual(errores, [])
        rep.refresh_from_db()
        self.assertEqual(rep.empleado_id, e1.id)            # lead = primera fila
        self.assertEqual(rep.asignaciones.get(empleado=e1).monto_comision_fijo, Decimal('400'))
        self.assertEqual(rep.asignaciones.count(), 2)

    def test_crea_filas_confeccion_monto_fijo(self):
        """Confeccion asignaciones use monto_comision_fijo field; lead sync is skipped."""
        conf = make_confeccion()
        e1 = make_empleado(ci='CF-1')
        qd = _qd({'asignaciones_count': '1',
                  'asignacion[0][empleado]': str(e1.id), 'asignacion[0][monto]': '80'})
        errores = _guardar_asignaciones(conf, qd, ConfeccionEmpleado, 'confeccion',
                                        commission_field='monto_comision_fijo',
                                        monto_key='monto', sync_lead=False)
        self.assertEqual(errores, [])
        ce = ConfeccionEmpleado.objects.get(confeccion=conf, empleado=e1)
        self.assertEqual(ce.monto_comision_fijo, Decimal('80'))

    def test_reasignar_reemplaza_filas_anteriores(self):
        rep = make_reparacion(total=Decimal('1000'))
        e1 = make_empleado(ci='R-1'); e2 = make_empleado(ci='R-2')
        _guardar_asignaciones(rep, _qd({'asignaciones_count': '1',
            'asignacion[0][empleado]': str(e1.id), 'asignacion[0][monto]': '500'}),
            ReparacionEmpleado, 'reparacion',
            commission_field='monto_comision_fijo', monto_key='monto', sync_lead=False)
        # re-guardar solo con e2
        _guardar_asignaciones(rep, _qd({'asignaciones_count': '1',
            'asignacion[0][empleado]': str(e2.id), 'asignacion[0][monto]': '100'}),
            ReparacionEmpleado, 'reparacion',
            commission_field='monto_comision_fijo', monto_key='monto', sync_lead=False)
        rep.refresh_from_db()
        self.assertEqual(rep.asignaciones.count(), 1)
        self.assertEqual(rep.empleado_id, e2.id)

    def test_sin_asignaciones_deja_lead_nulo(self):
        rep = make_reparacion(total=Decimal('1000'))
        _guardar_asignaciones(rep, _qd({'asignaciones_count': '0'}), ReparacionEmpleado, 'reparacion',
                              commission_field='monto_comision_fijo', monto_key='monto', sync_lead=False)
        rep.refresh_from_db()
        self.assertIsNone(rep.empleado_id)
        self.assertEqual(rep.asignaciones.count(), 0)


class EmpleadosExtraTests(TestCase):

    def test_extra_cero_con_un_empleado(self):
        rep = make_reparacion(total=Decimal('100'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='X-1'), monto_comision_fijo=Decimal('5'))
        self.assertEqual(rep.empleados_extra, 0)

    def test_extra_cuenta_adicionales(self):
        rep = make_reparacion(total=Decimal('100'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='Y-1'), monto_comision_fijo=Decimal('5'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='Y-2'), monto_comision_fijo=Decimal('5'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=make_empleado(ci='Y-3'), monto_comision_fijo=Decimal('5'))
        self.assertEqual(rep.empleados_extra, 2)


class NuevosTestsComisionFija(TestCase):

    def test_confeccion_devenga_monto_fijo(self):
        """ConfeccionEmpleado con monto_comision_fijo=80 contribuye 80 al saldo sin importar estado/precio."""
        e = make_empleado()
        conf = make_confeccion(precio=Decimal('500'))
        ConfeccionEmpleado.objects.create(confeccion=conf, empleado=e, monto_comision_fijo=Decimal('80'))
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('80'))

    def test_saldo_incluye_trabajo_en_proceso(self):
        """Reparacion en estado en_proceso contribuye al saldo devengado."""
        e = make_empleado()
        rep = make_reparacion(total=Decimal('1500'), estado='en_proceso')
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e, monto_comision_fijo=Decimal('150'))
        # monto fijo = 150
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('150'))

    def test_saldo_suma_cuatro_fuentes(self):
        """saldo = reparacion + confeccion + venta + alquiler - pagos."""
        from misastreria.models import VentaItem, AlquilerItem, PagoComisionEmpleado
        from .factories import make_tipo_reparacion, make_prenda_item, make_venta, make_alquiler

        e = make_empleado()

        # reparacion = 100
        rep = make_reparacion(total=Decimal('1000'))
        ReparacionEmpleado.objects.create(reparacion=rep, empleado=e, monto_comision_fijo=Decimal('100'))

        # confeccion = 80
        conf = make_confeccion()
        ConfeccionEmpleado.objects.create(confeccion=conf, empleado=e, monto_comision_fijo=Decimal('80'))

        # venta = 30
        tr = make_tipo_reparacion()
        VentaItem.objects.create(
            venta=make_venta(), prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('50'),
            empleado=e, monto_comision_fijo=Decimal('30'),
        )

        # alquiler = 20
        AlquilerItem.objects.create(
            alquiler=make_alquiler(), prenda_item=make_prenda_item(), tipo_reparacion=tr,
            precio_unitario=Decimal('200'), precio_reparacion=Decimal('40'),
            empleado=e, monto_comision_fijo=Decimal('20'),
        )

        # pago = 50
        PagoComisionEmpleado.objects.create(empleado=e, monto=Decimal('50'), forma_pago='efectivo')

        # saldo = 230 - 50 = 180
        self.assertEqual(_calcular_saldo_comision_empleado(e), Decimal('180'))
