"""
WARNING 1 (reporte de verificación, ampliado por decisión del dueño del
producto DESPUÉS del primer batch de fixes): los pagos "reservados"
(`via_caja=False`) son plata real que alguien guarda aparte hasta la entrega
— no una anotación contable sin efecto. Por eso:

  1. Registrar un pago con `via_caja=False` exige el MISMO turno propio
     abierto que un cobro normal (antes lo saltaba por completo: cualquiera
     sin caja abierta, o con la caja de otro, podía crear una fila con
     `sesion=None`).
  2. Al liberarlos (`_liberar_pagos_reservados`, via_caja False→True), el
     movimiento se asigna a la sesión de quien los libera — y quien libera
     también necesita turno propio; si no lo tiene, no se libera nada.
  3. Filas reservadas viejas (de antes de este fix, con `sesion=None`)
     quedan intactas hasta que alguien con turno propio las libere; no hace
     falta una migración de datos.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.caja_signals import (
    _liberar_pagos_reservados, registrar_pago_venta,
)
from misastreria.caja_turno import TurnoCajaError
from misastreria.models import CajaMovimiento, Venta
from .factories import (
    make_administrador, make_cajero, make_cliente, make_empleado,
    make_prenda, make_prenda_item, make_sesion_caja, make_venta,
)


def _venta_en_proceso(cliente, empleado, total):
    venta = Venta.objects.create(
        cliente=cliente, empleado=empleado,
        subtotal=Decimal('0'), total=Decimal('0'), estado='en_proceso',
    )
    Venta.objects.filter(pk=venta.pk).update(total=Decimal(str(total)), subtotal=Decimal(str(total)))
    venta.refresh_from_db()
    return venta


class RegistrarPagoViaCajaFalseExigeTurnoTests(TestCase):
    """Registrar un pago reservado exige turno propio, igual que uno normal."""

    def setUp(self):
        self.cliente = make_cliente()
        self.empleado = make_empleado()

    def _post_reserva(self, user, monto='300'):
        venta = _venta_en_proceso(self.cliente, self.empleado, '300')
        self.client.force_login(user)
        # via_caja NO viene en el POST -> PagoVentaForm.via_caja=False (reserva).
        resp = self.client.post(
            reverse('agregar_pago_venta', args=[venta.id]),
            {'monto': monto, 'forma_pago': 'efectivo'},
        )
        return venta, resp

    def test_sin_sesion_abierta_rechaza_todo(self):
        cajero = make_cajero()
        venta, resp = self._post_reserva(cajero)
        self.assertEqual(CajaMovimiento.objects.filter(referencia_venta=venta).count(), 0)

    def test_sesion_de_otro_incluido_admin_rechaza(self):
        cajero_a = make_cajero()
        make_sesion_caja(usuario=cajero_a)
        admin = make_administrador()
        venta, resp = self._post_reserva(admin)
        self.assertEqual(CajaMovimiento.objects.filter(referencia_venta=venta).count(), 0)

    def test_dueno_de_la_sesion_si_puede_reservar(self):
        cajero = make_cajero()
        sesion = make_sesion_caja(usuario=cajero)
        venta, resp = self._post_reserva(cajero)
        mov = CajaMovimiento.objects.get(referencia_venta=venta, concepto='venta_saldo')
        self.assertFalse(mov.via_caja)
        self.assertEqual(mov.sesion_id, sesion.id)


class LiberarPagosReservadosTests(TestCase):
    """`_liberar_pagos_reservados`: reasigna la sesión de quien libera y
    exige que esa persona tenga turno propio abierto."""

    def setUp(self):
        self.cliente = make_cliente()
        self.empleado = make_empleado()

    def test_unidad_sin_turno_propio_no_libera_nada(self):
        venta = _venta_en_proceso(self.cliente, self.empleado, '300')
        cajero_a = make_cajero(username='reserva_a')
        sesion_a = make_sesion_caja(usuario=cajero_a)
        mov = CajaMovimiento.objects.create(
            referencia_venta=venta, tipo='ingreso', concepto='venta_pago',
            monto=Decimal('100'), forma_pago='efectivo', origen='automatico',
            via_caja=False, sesion=sesion_a,
        )
        sesion_a.estado = 'cerrada'
        sesion_a.save(update_fields=['estado'])
        otro = make_cajero(username='sin_turno')

        with self.assertRaises(TurnoCajaError):
            _liberar_pagos_reservados('referencia_venta', venta, otro)

        mov.refresh_from_db()
        self.assertFalse(mov.via_caja)
        self.assertEqual(mov.sesion_id, sesion_a.id)

    def test_unidad_reasigna_a_la_sesion_de_quien_libera(self):
        venta = _venta_en_proceso(self.cliente, self.empleado, '300')
        cajero_a = make_cajero(username='reserva_b')
        sesion_a = make_sesion_caja(usuario=cajero_a)
        mov = CajaMovimiento.objects.create(
            referencia_venta=venta, tipo='ingreso', concepto='venta_pago',
            monto=Decimal('100'), forma_pago='efectivo', origen='automatico',
            via_caja=False, sesion=sesion_a,
        )
        sesion_a.estado = 'cerrada'
        sesion_a.save(update_fields=['estado'])
        cajero_b = make_cajero(username='libera_b')
        sesion_b = make_sesion_caja(usuario=cajero_b)

        _liberar_pagos_reservados('referencia_venta', venta, cajero_b)

        mov.refresh_from_db()
        self.assertTrue(mov.via_caja)
        self.assertEqual(
            mov.sesion_id, sesion_b.id,
            'el movimiento liberado debe quedar en la sesión de quien lo liberó, no en la original',
        )

    def test_fila_legada_con_sesion_none_se_asigna_al_liberar(self):
        """Filas reservadas de ANTES de este fix (sesion=None) no se migran;
        quedan así hasta que alguien con turno propio las libere."""
        venta = _venta_en_proceso(self.cliente, self.empleado, '300')
        mov_legado = CajaMovimiento.objects.create(
            referencia_venta=venta, tipo='ingreso', concepto='venta_pago',
            monto=Decimal('100'), forma_pago='efectivo', origen='automatico',
            via_caja=False, sesion=None,
        )
        cajero = make_cajero(username='libera_legado')
        sesion = make_sesion_caja(usuario=cajero)

        _liberar_pagos_reservados('referencia_venta', venta, cajero)

        mov_legado.refresh_from_db()
        self.assertTrue(mov_legado.via_caja)
        self.assertEqual(mov_legado.sesion_id, sesion.id)


class FlujoCompletoReservaYLiberacionTests(TestCase):
    """Extremo a extremo vía la vista: reservar con A, cerrar su turno, y
    liberar con B al completar el pago — B pasa a ser dueño del movimiento
    reservado en su propia sesión."""

    def test_reserva_con_a_liberacion_con_b_reasigna_sesion(self):
        cliente = make_cliente()
        empleado = make_empleado()
        venta = _venta_en_proceso(cliente, empleado, '300')

        cajero_a = make_cajero(username='flujo_a')
        sesion_a = make_sesion_caja(usuario=cajero_a)
        self.client.force_login(cajero_a)
        resp = self.client.post(
            reverse('agregar_pago_venta', args=[venta.id]),
            {'monto': '100', 'forma_pago': 'efectivo'},  # sin via_caja -> reserva
        )
        mov_reservado = CajaMovimiento.objects.get(referencia_venta=venta, concepto='venta_pago')
        self.assertFalse(mov_reservado.via_caja)
        self.assertEqual(mov_reservado.sesion_id, sesion_a.id)

        sesion_a.estado = 'cerrada'
        sesion_a.save(update_fields=['estado'])
        self.client.logout()

        cajero_b = make_cajero(username='flujo_b')
        sesion_b = make_sesion_caja(usuario=cajero_b)
        self.client.force_login(cajero_b)
        resp = self.client.post(
            reverse('agregar_pago_venta', args=[venta.id]),
            {'monto': '200', 'forma_pago': 'efectivo', 'via_caja': 'on'},
        )

        mov_reservado.refresh_from_db()
        self.assertTrue(mov_reservado.via_caja, 'la reserva de A debe liberarse cuando B completa el pago')
        self.assertEqual(
            mov_reservado.sesion_id, sesion_b.id,
            'liberada, la reserva pasa a la sesión de quien completó el cobro (B), no la original de A',
        )
        venta.refresh_from_db()
        self.assertEqual(venta.estado, 'efectuada')
