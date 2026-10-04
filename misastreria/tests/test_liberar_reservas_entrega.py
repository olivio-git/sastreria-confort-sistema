"""
Reservas (`via_caja=False`) y entrega de la prenda.

Decisión del dueño (architecture/caja-pagos-reserva): un pago reservado es
efectivo guardado aparte hasta que la prenda se ENTREGA. Al entregar, la
reserva se libera (`via_caja=True`) y se asienta en la sesión abierta de
quien entrega — sólo el dueño del turno, atómico.

Cubre además el hallazgo S1 de la 4ª verificación: `marcar_entregado` y
`entregar_confeccion` no deben dejar un 'entregado' comprometido sin su
cobro si el turno se cierra entre el chequeo y el guardado.
"""
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from misastreria.caja_signals import (
    registrar_pago_confeccion, registrar_pago_reparacion, registrar_pago_venta,
)
from misastreria.caja_turno import TurnoCajaError
from misastreria.models import CajaMovimiento, Reparacion, Venta
from .factories import (
    make_administrador, make_cajero, make_taller, make_sesion_caja,
    make_reparacion, make_confeccion, make_venta,
)


def _cerrar(sesion):
    sesion.estado = 'cerrada'
    sesion.fecha_cierre = timezone.now()
    sesion.save()


def _reserva_de_turno_anterior(registrar, servicio, monto, cajero):
    """Reserva `monto` en un turno de `cajero` que después se cierra: queda
    una fila via_caja=False asentada en una sesión ya cerrada."""
    turno_viejo = make_sesion_caja(usuario=cajero)
    registrar(servicio, Decimal(monto), 'efectivo', '', cajero, via_caja=False)
    _cerrar(turno_viejo)
    return turno_viejo


class LiberarReservaAlEntregarReparacionTests(TestCase):
    def setUp(self):
        self.cajero = make_cajero()
        self.admin = make_administrador()
        self.rep = make_reparacion(estado='en_proceso', total=Decimal('100.00'))

    def test_owner_entrega_y_la_reserva_pasa_a_su_sesion(self):
        _reserva_de_turno_anterior(registrar_pago_reparacion, self.rep, '30', self.cajero)
        turno = make_sesion_caja(usuario=self.admin)
        self.client.force_login(self.admin)

        resp = self.client.post(reverse('marcar_entregado', args=[self.rep.id]))

        self.assertEqual(resp.status_code, 302)
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.estado, 'entregado')
        reserva = CajaMovimiento.objects.get(
            referencia_reparacion=self.rep, concepto='reparacion_pago')
        self.assertTrue(reserva.via_caja, 'la reserva se libera al entregar')
        self.assertEqual(reserva.sesion_id, turno.id)
        # El saldo (70) se cobra normal, en la misma sesión.
        saldo = CajaMovimiento.objects.get(
            referencia_reparacion=self.rep, concepto='reparacion_saldo')
        self.assertEqual((saldo.monto, saldo.via_caja, saldo.sesion_id),
                         (Decimal('70.00'), True, turno.id))

    def test_entrega_con_todo_reservado_libera_aunque_saldo_sea_cero(self):
        _reserva_de_turno_anterior(registrar_pago_reparacion, self.rep, '100', self.cajero)
        turno = make_sesion_caja(usuario=self.admin)
        self.client.force_login(self.admin)

        self.client.post(reverse('marcar_entregado', args=[self.rep.id]))

        self.rep.refresh_from_db()
        self.assertEqual(self.rep.estado, 'entregado')
        reserva = CajaMovimiento.objects.get(referencia_reparacion=self.rep)
        self.assertTrue(reserva.via_caja)
        self.assertEqual(reserva.sesion_id, turno.id)

    def test_taller_sin_turno_no_entrega_si_hay_reservas(self):
        """Con saldo 0 Taller entregaba sin turno; con reservas pendientes
        de liberar necesita el turno del dueño, así que se rechaza entero."""
        taller = make_taller()
        _reserva_de_turno_anterior(registrar_pago_reparacion, self.rep, '100', self.cajero)
        make_sesion_caja(usuario=self.admin)
        self.client.force_login(taller)

        resp = self.client.post(reverse('marcar_entregado', args=[self.rep.id]))

        self.assertEqual(resp.status_code, 302)
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.estado, 'en_proceso')
        reserva = CajaMovimiento.objects.get(referencia_reparacion=self.rep)
        self.assertFalse(reserva.via_caja)

    def test_taller_entrega_sin_turno_cuando_no_hay_reservas_ni_saldo(self):
        """Triangulación: sin reservas y con saldo 0, Taller sigue entregando."""
        taller = make_taller()
        make_sesion_caja(usuario=self.admin)
        registrar_pago_reparacion(self.rep, Decimal('100'), 'efectivo', '', self.admin)
        self.client.force_login(taller)

        self.client.post(reverse('marcar_entregado', args=[self.rep.id]))

        self.rep.refresh_from_db()
        self.assertEqual(self.rep.estado, 'entregado')

    def test_senal_directa_con_actor_ajeno_falla_y_no_libera(self):
        _reserva_de_turno_anterior(registrar_pago_reparacion, self.rep, '100', self.cajero)
        make_sesion_caja(usuario=self.admin)
        rep = Reparacion.objects.get(pk=self.rep.pk)
        rep.estado = 'entregado'
        rep._actor_caja = make_taller()
        with self.assertRaises(TurnoCajaError):
            rep.save()
        self.assertFalse(CajaMovimiento.objects.get(referencia_reparacion=rep).via_caja)

    def test_senal_directa_sin_actor_falla_cerrada(self):
        _reserva_de_turno_anterior(registrar_pago_reparacion, self.rep, '100', self.cajero)
        make_sesion_caja(usuario=self.admin)
        rep = Reparacion.objects.get(pk=self.rep.pk)
        rep.estado = 'entregado'
        with self.assertRaises(TurnoCajaError):
            rep.save()
        self.assertFalse(CajaMovimiento.objects.get(referencia_reparacion=rep).via_caja)


class LiberarReservaAlEntregarConfeccionTests(TestCase):
    def setUp(self):
        self.cajero = make_cajero()
        self.admin = make_administrador()
        self.conf = make_confeccion(
            estado='en_proceso', precio=Decimal('300'), adelanto=Decimal('0'))

    def test_owner_entrega_y_la_reserva_pasa_a_su_sesion(self):
        _reserva_de_turno_anterior(registrar_pago_confeccion, self.conf, '50', self.cajero)
        turno = make_sesion_caja(usuario=self.admin)
        self.client.force_login(self.admin)

        resp = self.client.post(reverse('entregar_confeccion', args=[self.conf.id]))

        self.assertEqual(resp.status_code, 302)
        self.conf.refresh_from_db()
        self.assertEqual(self.conf.estado, 'entregado')
        reserva = CajaMovimiento.objects.get(
            referencia_confeccion=self.conf, concepto='confeccion_pago')
        self.assertTrue(reserva.via_caja)
        self.assertEqual(reserva.sesion_id, turno.id)

    def test_taller_sin_turno_no_entrega_si_hay_reservas(self):
        taller = make_taller()
        _reserva_de_turno_anterior(registrar_pago_confeccion, self.conf, '300', self.cajero)
        make_sesion_caja(usuario=self.admin)
        self.client.force_login(taller)

        self.client.post(reverse('entregar_confeccion', args=[self.conf.id]))

        self.conf.refresh_from_db()
        self.assertEqual(self.conf.estado, 'en_proceso')
        self.assertFalse(CajaMovimiento.objects.get(referencia_confeccion=self.conf).via_caja)


class LiberarReservaAlEfectuarseVentaTests(TestCase):
    """Venta: `efectuada` es el equivalente de la entrega. Un pago reservado
    que la completa se libera a la sesión de quien lo registra."""

    def _venta_con_total(self, total):
        venta = make_venta(estado='en_proceso')
        Venta.objects.filter(pk=venta.pk).update(total=Decimal(total), subtotal=Decimal(total))
        venta.refresh_from_db()
        return venta

    def test_pago_reservado_que_completa_la_venta_se_libera(self):
        cajero = make_cajero()
        turno = make_sesion_caja(usuario=cajero)
        venta = self._venta_con_total('200')

        registrar_pago_venta(venta, Decimal('200'), 'efectivo', '', cajero, via_caja=False)

        venta.refresh_from_db()
        self.assertEqual(venta.estado, 'efectuada')
        reserva = CajaMovimiento.objects.get(referencia_venta=venta)
        self.assertTrue(reserva.via_caja)
        self.assertEqual(reserva.sesion_id, turno.id)

    def test_pago_reservado_parcial_sigue_reservado(self):
        """Triangulación: si la venta NO se completa, no hay entrega y la
        reserva se mantiene apartada."""
        cajero = make_cajero()
        make_sesion_caja(usuario=cajero)
        venta = self._venta_con_total('200')

        registrar_pago_venta(venta, Decimal('80'), 'efectivo', '', cajero, via_caja=False)

        venta.refresh_from_db()
        self.assertEqual(venta.estado, 'en_proceso')
        self.assertFalse(CajaMovimiento.objects.get(referencia_venta=venta).via_caja)


class EntregaAtomicaSiSeCierraElTurnoTests(TestCase):
    """S1: el turno se cierra entre el chequeo de la vista y el guardado. El
    post_save levanta; la vista debe capturarlo, no dejar 'entregado' sin su
    cobro ni devolver un 500."""

    def test_marcar_entregado_captura_el_error_de_turno_y_no_entrega(self):
        admin = make_administrador()
        rep = make_reparacion(estado='en_proceso', total=Decimal('80.00'))
        self.client.force_login(admin)
        with mock.patch(
            'misastreria.views.caja_turno.autorizar_transicion_a_entregado',
            return_value=None,
        ):
            resp = self.client.post(reverse('marcar_entregado', args=[rep.id]))
        self.assertEqual(resp.status_code, 302)
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'en_proceso')
        self.assertEqual(CajaMovimiento.objects.filter(referencia_reparacion=rep).count(), 0)

    def test_entregar_confeccion_captura_el_error_de_turno_y_no_entrega(self):
        admin = make_administrador()
        conf = make_confeccion(estado='en_proceso', precio=Decimal('300'), adelanto=Decimal('0'))
        self.client.force_login(admin)
        with mock.patch(
            'misastreria.views.caja_turno.autorizar_transicion_a_entregado',
            return_value=None,
        ):
            resp = self.client.post(reverse('entregar_confeccion', args=[conf.id]))
        self.assertEqual(resp.status_code, 302)
        conf.refresh_from_db()
        self.assertEqual(conf.estado, 'en_proceso')
        self.assertEqual(CajaMovimiento.objects.filter(referencia_confeccion=conf).count(), 0)

    def test_marcar_entregado_es_atomico_estado_y_cobro_van_juntos(self):
        """Si el cobro falla a mitad de camino, el estado no queda guardado
        (se prueba en una transacción real, no sólo con el mensaje)."""
        admin = make_administrador()
        make_sesion_caja(usuario=admin)
        rep = make_reparacion(estado='en_proceso', total=Decimal('80.00'))
        self.client.force_login(admin)
        with mock.patch(
            'misastreria.caja_signals._crear_mov_auto',
            side_effect=TurnoCajaError('simulado'),
        ):
            resp = self.client.post(reverse('marcar_entregado', args=[rep.id]))
        self.assertEqual(resp.status_code, 302)
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'en_proceso')
