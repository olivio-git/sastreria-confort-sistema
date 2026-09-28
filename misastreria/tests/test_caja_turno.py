"""
Turno de caja: la sesión abierta pertenece a quien la abrió.

Cubre:
  - misastreria/caja_turno.py (unidad)
  - crear_movimiento_caja / revertir_movimiento_caja / cerrar_sesion_caja (ownership)
  - Force-close de Administrador exige observación
  - No se puede abrir una segunda sesión (unique_caja_abierta)
  - Cobro guard: 0 filas para sin-sesión y sesión-ajena (Admin incluido)
  - crear_venta con pago inline rechaza el envío completo si no hay turno propio
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from misastreria.caja_turno import (
    TurnoCajaError, sesion_abierta, verificar_turno_cobro,
    puede_supervisar, puede_ver_sesion,
)
from misastreria.models import CajaSesion, CajaMovimiento, Venta, Alquiler
from .factories import (
    make_administrador, make_cajero, make_sesion_caja, make_movimiento_caja,
    make_cliente, make_empleado, make_prenda, make_prenda_item,
)


class CajaTurnoUnidadTests(TestCase):
    def test_sesion_abierta_none_sin_sesiones(self):
        self.assertIsNone(sesion_abierta())

    def test_sesion_abierta_devuelve_la_abierta(self):
        s = make_sesion_caja()
        self.assertEqual(sesion_abierta(), s)

    def test_verificar_turno_cobro_sin_sesion_lanza_error(self):
        cajero = make_cajero()
        with self.assertRaises(TurnoCajaError):
            verificar_turno_cobro(cajero)

    def test_verificar_turno_cobro_owner_ok(self):
        cajero = make_cajero()
        make_sesion_caja(usuario=cajero)
        sesion = verificar_turno_cobro(cajero)
        self.assertEqual(sesion.usuario_apertura_id, cajero.id)

    def test_verificar_turno_cobro_no_owner_lanza_error_incluso_admin(self):
        cajero = make_cajero()
        admin = make_administrador()
        make_sesion_caja(usuario=cajero)
        with self.assertRaises(TurnoCajaError):
            verificar_turno_cobro(admin)

    def test_puede_supervisar_administrador_si_cajero_no(self):
        self.assertTrue(puede_supervisar(make_administrador()))
        self.assertFalse(puede_supervisar(make_cajero()))

    def test_puede_ver_sesion_owner_o_supervisor(self):
        cajero = make_cajero()
        otro_cajero = make_cajero(username='otro_cajero')
        admin = make_administrador()
        sesion = make_sesion_caja(usuario=cajero)
        self.assertTrue(puede_ver_sesion(cajero, sesion))
        self.assertTrue(puede_ver_sesion(admin, sesion))
        self.assertFalse(puede_ver_sesion(otro_cajero, sesion))


class CrearMovimientoCajaOwnershipTests(TestCase):
    def test_owner_registra_movimiento(self):
        cajero = make_cajero()
        sesion = make_sesion_caja(usuario=cajero)
        self.client.force_login(cajero)
        resp = self.client.post(reverse('crear_movimiento_caja'), {
            'concepto': 'ingreso_manual', 'monto': '50', 'forma_pago': 'efectivo',
        })
        self.assertEqual(resp.status_code, 302)
        mov = CajaMovimiento.objects.filter(sesion=sesion, concepto='ingreso_manual').first()
        self.assertIsNotNone(mov)

    def test_no_owner_bloqueado(self):
        cajero = make_cajero()
        otro = make_cajero(username='otro_cajero')
        make_sesion_caja(usuario=cajero)
        self.client.force_login(otro)
        resp = self.client.post(reverse('crear_movimiento_caja'), {
            'concepto': 'ingreso_manual', 'monto': '50', 'forma_pago': 'efectivo',
        }, follow=True)
        self.assertEqual(CajaMovimiento.objects.filter(concepto='ingreso_manual').count(), 0)

    def test_sin_sesion_abierta_bloqueado(self):
        cajero = make_cajero()
        self.client.force_login(cajero)
        resp = self.client.post(reverse('crear_movimiento_caja'), {
            'concepto': 'ingreso_manual', 'monto': '50', 'forma_pago': 'efectivo',
        }, follow=True)
        self.assertEqual(CajaMovimiento.objects.filter(concepto='ingreso_manual').count(), 0)


class RevertirMovimientoCajaOwnershipTests(TestCase):
    def test_owner_reversa(self):
        cajero = make_cajero()
        sesion = make_sesion_caja(usuario=cajero)
        mov = make_movimiento_caja(sesion=sesion, origen='manual')
        self.client.force_login(cajero)
        resp = self.client.post(reverse('revertir_movimiento_caja', args=[mov.pk]))
        mov.refresh_from_db()
        self.assertIsNotNone(mov.movimiento_reverso)

    def test_no_owner_no_supervisor_bloqueado(self):
        cajero = make_cajero()
        otro = make_cajero(username='otro_cajero')
        sesion = make_sesion_caja(usuario=cajero)
        mov = make_movimiento_caja(sesion=sesion, origen='manual')
        # `otro` no tiene sesión propia abierta -> bloqueado por verificar_turno_cobro
        self.client.force_login(otro)
        resp = self.client.post(reverse('revertir_movimiento_caja', args=[mov.pk]))
        mov.refresh_from_db()
        self.assertIsNone(mov.movimiento_reverso)

    def test_admin_supervisor_puede_revertir_ajena_con_turno_propio(self):
        cajero = make_cajero()
        admin = make_administrador()
        sesion_cajero = make_sesion_caja(usuario=cajero)
        mov = make_movimiento_caja(sesion=sesion_cajero, origen='manual')
        sesion_cajero.estado = 'cerrada'
        sesion_cajero.save()
        make_sesion_caja(usuario=admin)  # admin abre su propio turno para supervisar
        self.client.force_login(admin)
        resp = self.client.post(reverse('revertir_movimiento_caja', args=[mov.pk]))
        mov.refresh_from_db()
        self.assertIsNotNone(mov.movimiento_reverso)


class CerrarSesionCajaOwnershipTests(TestCase):
    def test_owner_cierra_sin_diferencia_sin_observaciones(self):
        cajero = make_cajero()
        sesion = make_sesion_caja(usuario=cajero, monto_apertura=Decimal('100'))
        self.client.force_login(cajero)
        resp = self.client.post(reverse('cerrar_sesion_caja', args=[sesion.pk]), {
            'monto_cierre_declarado': '100', 'observaciones': '',
        })
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, 'cerrada')

    def test_no_owner_no_supervisor_no_puede_cerrar(self):
        cajero = make_cajero()
        otro = make_cajero(username='otro_cajero')
        sesion = make_sesion_caja(usuario=cajero, monto_apertura=Decimal('100'))
        self.client.force_login(otro)
        resp = self.client.post(reverse('cerrar_sesion_caja', args=[sesion.pk]), {
            'monto_cierre_declarado': '100', 'observaciones': '',
        })
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, 'abierta')

    def test_admin_force_close_requiere_observacion(self):
        cajero = make_cajero()
        admin = make_administrador()
        sesion = make_sesion_caja(usuario=cajero, monto_apertura=Decimal('100'))
        self.client.force_login(admin)
        resp = self.client.post(reverse('cerrar_sesion_caja', args=[sesion.pk]), {
            'monto_cierre_declarado': '100', 'observaciones': '',
        })
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, 'abierta', 'sin observación, el force-close debe rechazarse')

    def test_admin_force_close_con_observacion_exitoso(self):
        cajero = make_cajero()
        admin = make_administrador()
        sesion = make_sesion_caja(usuario=cajero, monto_apertura=Decimal('100'))
        self.client.force_login(admin)
        resp = self.client.post(reverse('cerrar_sesion_caja', args=[sesion.pk]), {
            'monto_cierre_declarado': '100', 'observaciones': 'Cajero se retiró antes de cerrar.',
        })
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, 'cerrada')
        self.assertEqual(sesion.usuario_cierre_id, admin.id)
        self.assertIn('Cajero se retiró', sesion.observaciones)


class SegundaSesionRechazadaTests(TestCase):
    def test_no_se_puede_abrir_segunda_sesion(self):
        make_sesion_caja()
        with self.assertRaises(IntegrityError):
            make_sesion_caja()


class CobroGuardTests(TestCase):
    """Scenario: Cobro guard — 0 filas de CajaMovimiento cuando no hay sesión
    o la sesión abierta es de otro usuario (Administrador incluido)."""

    def setUp(self):
        self.cliente = make_cliente()
        self.empleado = make_empleado()
        self.prenda = make_prenda(precio=Decimal('300.00'))

    def _post_pago_venta(self, user, monto='100'):
        item = make_prenda_item(self.prenda)
        # .update() en vez de save(): crear con total ya puesto dispararía el
        # signal de fallback (venta_to_caja) y cobraría de una — acá se quiere
        # el flujo real (items después, importe se fija después, se cobra por
        # agregar_pago_venta), igual que test_pago_venta_con_saldo.py.
        venta = Venta.objects.create(
            cliente=self.cliente, empleado=self.empleado,
            subtotal=Decimal('0'), total=Decimal('0'), estado='en_proceso',
        )
        Venta.objects.filter(pk=venta.pk).update(total=Decimal('300'), subtotal=Decimal('300'))
        venta.refresh_from_db()
        self.client.force_login(user)
        return venta, self.client.post(
            reverse('agregar_pago_venta', args=[venta.id]),
            {'monto': monto, 'forma_pago': 'efectivo', 'via_caja': 'on'},
        )

    def test_sin_sesion_agregar_pago_venta_no_crea_movimiento(self):
        cajero = make_cajero()
        venta, resp = self._post_pago_venta(cajero)
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_venta=venta).count(), 0
        )

    def test_sesion_de_otro_incluido_admin_no_crea_movimiento(self):
        cajero = make_cajero()
        make_sesion_caja(usuario=cajero)
        admin = make_administrador()
        venta, resp = self._post_pago_venta(admin)
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_venta=venta).count(), 0
        )

    def test_owner_si_puede_cobrar(self):
        cajero = make_cajero()
        make_sesion_caja(usuario=cajero)
        venta, resp = self._post_pago_venta(cajero)
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_venta=venta, concepto='venta_pago').count(), 1
        )


class CrearVentaPagoInlineRechazaTodoTests(TestCase):
    """Scenario: Inline payment during crear_venta with no open session — se
    rechaza TODO el envío (ni venta, ni items, ni pago quedan guardados)."""

    def setUp(self):
        self.cliente = make_cliente()
        self.empleado = make_empleado()
        self.prenda = make_prenda(precio=Decimal('300.00'))
        self.item = make_prenda_item(self.prenda)
        self.cajero = make_cajero()
        self.client.force_login(self.cajero)

    def _datos(self, **extra):
        datos = {
            'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
            'cliente': str(self.cliente.id), 'empleado': str(self.empleado.id),
            'descuento': '0', 'notas': '',
            'item_prenda_item': [str(self.item.id)], 'item_precio': ['300.00'],
            'item_grupo_conjunto': [''], 'item_tipo_reparacion': [''],
            'item_precio_reparacion': [''], 'item_empleado': [''],
            'item_monto_comision': [''],
            'pago[0][monto]': '300.00', 'pago[0][forma_pago]': 'efectivo',
            'via_caja': 'on',
        }
        datos.update(extra)
        return datos

    def test_sin_turno_propio_no_crea_nada(self):
        resp = self.client.post(reverse('crear_venta'), self._datos())
        self.assertEqual(resp.status_code, 200, 're-renderiza el form con error, no redirige')
        self.assertEqual(Venta.objects.count(), 0, 'no debe quedar ninguna venta creada')
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, 'disponible', 'el item no debe salir del inventario')

    def test_con_turno_propio_crea_todo(self):
        make_sesion_caja(usuario=self.cajero)
        resp = self.client.post(reverse('crear_venta'), self._datos())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Venta.objects.count(), 1)
        # El total lo fija recalcular_totales() DESPUÉS de guardar los items
        # (no al crear), así que el cobro viene de _registrar_pagos_venta,
        # no del signal de fallback venta_to_caja (que sólo actúa si el total
        # ya viene puesto al crear) — por eso el concepto es venta_saldo.
        self.assertEqual(
            CajaMovimiento.objects.filter(concepto='venta_saldo').count(), 1
        )

    def test_sin_pago_no_requiere_turno(self):
        """Sin líneas de pago, crear la venta no exige turno abierto."""
        datos = self._datos()
        del datos['pago[0][monto]']
        del datos['pago[0][forma_pago]']
        resp = self.client.post(reverse('crear_venta'), datos)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Venta.objects.count(), 1)


class ReportesCajaPropiosTests(TestCase):
    """Scenario (design): resumen_caja/kardex_financiero/lista_sesiones/
    detalle filtrados a las sesiones propias salvo supervisor."""

    def setUp(self):
        self.cajero_a = make_cajero(username='cajero_a')
        self.cajero_b = make_cajero(username='cajero_b')
        self.sesion_a = make_sesion_caja(usuario=self.cajero_a, monto_apertura=Decimal('100'))

    def _abrir_sesion_b(self):
        # Cierra la de A para poder abrir la de B (unique_caja_abierta).
        self.sesion_a.estado = 'cerrada'
        self.sesion_a.save()
        return make_sesion_caja(usuario=self.cajero_b, monto_apertura=Decimal('50'))

    def test_lista_sesiones_cajero_ve_solo_la_propia(self):
        sesion_b = self._abrir_sesion_b()
        self.client.force_login(self.cajero_a)
        resp = self.client.get(reverse('lista_sesiones_caja'))
        ids = {s.pk for s in resp.context['page_obj']}
        self.assertIn(self.sesion_a.pk, ids)
        self.assertNotIn(sesion_b.pk, ids)

    def test_lista_sesiones_admin_ve_todas(self):
        sesion_b = self._abrir_sesion_b()
        admin = make_administrador()
        self.client.force_login(admin)
        resp = self.client.get(reverse('lista_sesiones_caja'))
        ids = {s.pk for s in resp.context['page_obj']}
        self.assertIn(self.sesion_a.pk, ids)
        self.assertIn(sesion_b.pk, ids)

    def test_detalle_sesion_ajena_redirige(self):
        sesion_b = self._abrir_sesion_b()
        self.client.force_login(self.cajero_a)
        resp = self.client.get(reverse('detalle_sesion_caja', args=[sesion_b.pk]), follow=True)
        self.assertRedirects(resp, reverse('lista_sesiones_caja'))

    def test_detalle_sesion_propia_accesible(self):
        self.client.force_login(self.cajero_a)
        resp = self.client.get(reverse('detalle_sesion_caja', args=[self.sesion_a.pk]))
        self.assertEqual(resp.status_code, 200)
