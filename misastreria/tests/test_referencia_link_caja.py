"""
test_referencia_link_caja.py
============================
Cubre la property CajaMovimiento.referencia_link, que expone el documento de
origen del movimiento (venta, alquiler, confección, reparación o pago de
comisión) como {tipo, codigo, url} para enlazar desde las vistas de caja al
detalle del servicio. Devuelve None para movimientos manuales/sin referencia.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.models import PagoComisionEmpleado
from .factories import (
    make_movimiento_caja, make_venta, make_alquiler,
    make_reparacion, make_confeccion, make_empleado,
)


class ReferenciaLinkTests(TestCase):

    def test_venta_link(self):
        venta = make_venta()
        mov = make_movimiento_caja(concepto='venta_cobro', referencia_venta=venta)
        ref = mov.referencia_link
        self.assertEqual(ref['tipo'], 'Venta')
        self.assertEqual(ref['codigo'], venta.codigo)
        self.assertEqual(ref['url'], reverse('detalle_venta', args=[venta.id]))

    def test_alquiler_link(self):
        alquiler = make_alquiler()
        mov = make_movimiento_caja(concepto='alquiler_cobro', referencia_alquiler=alquiler)
        ref = mov.referencia_link
        self.assertEqual(ref['tipo'], 'Alquiler')
        self.assertEqual(ref['codigo'], alquiler.codigo)
        self.assertEqual(ref['url'], reverse('detalle_alquiler', args=[alquiler.id]))

    def test_confeccion_link(self):
        confeccion = make_confeccion()
        mov = make_movimiento_caja(concepto='confeccion_adelanto', referencia_confeccion=confeccion)
        ref = mov.referencia_link
        self.assertEqual(ref['tipo'], 'Confección')
        self.assertEqual(ref['codigo'], confeccion.codigo)
        self.assertEqual(ref['url'], reverse('detalle_confeccion', args=[confeccion.id]))

    def test_reparacion_link(self):
        reparacion = make_reparacion()
        mov = make_movimiento_caja(concepto='reparacion_cobro', referencia_reparacion=reparacion)
        ref = mov.referencia_link
        self.assertEqual(ref['tipo'], 'Reparación')
        self.assertEqual(ref['codigo'], reparacion.codigo)
        self.assertEqual(ref['url'], reverse('detalle_reparacion', args=[reparacion.id]))

    def test_pago_comision_link_apunta_al_empleado(self):
        empleado = make_empleado()
        pago = PagoComisionEmpleado.objects.create(empleado=empleado, monto=Decimal('100.00'))
        mov = make_movimiento_caja(
            tipo='egreso', concepto='comision_empleado',
            referencia_pago_comision=pago,
        )
        ref = mov.referencia_link
        self.assertEqual(ref['tipo'], 'Comisión')
        self.assertEqual(ref['codigo'], pago.codigo)
        self.assertEqual(ref['url'], reverse('detalle_empleado', args=[empleado.id]))

    def test_movimiento_manual_sin_referencia_devuelve_none(self):
        mov = make_movimiento_caja(concepto='ingreso_manual')
        self.assertIsNone(mov.referencia_link)
