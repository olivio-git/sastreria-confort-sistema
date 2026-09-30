"""
Brecha encontrada en `sdd-verify` (CRITICAL 2 y 3): `ReparacionForm` y
`ConfeccionForm` exponen el campo `estado` completo, así que alcanzaba con
mandar `estado=entregado` en `crear_reparacion`/`editar_reparacion`/
`crear_confeccion`/`editar_confeccion` para saltarse:
  (a) la regla de la matriz "Reparaciones/Confecciones entregado = Admin/
      Taller only" (acá routeada vía `misastreria.cambiar_estado_taller`,
      igual que `marcar_entregado`/`entregar_confeccion`), y
  (b) el cobro guard (saldo pendiente exige turno propio) — porque el
      `post_save` de `caja_signals` (`reparacion_to_caja`/`confeccion_to_caja`)
      dispara el cobro automático apenas se guarda el modelo, sin pasar por
      ninguna vista dedicada.

Además, sin `transaction.atomic()`, un `CajaSinSesionError`/`TurnoCajaError`
lanzado a mitad de camino dejaba escrituras parciales (reparación ya creada,
alquiler ya marcado devuelto, ítems ya liberados) y una respuesta 500 en vez
de un mensaje de error (CRITICAL 3). Este archivo prueba que ahora el envío
completo se rechaza — nada queda persistido — y no hay 500.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.caja_turno import TurnoCajaError, autorizar_transicion_a_entregado
from misastreria.caja_signals import registrar_pago_venta
from misastreria.models import (
    Alquiler, CajaMovimiento, Confeccion, PagoComisionEmpleado, Reparacion,
    ReparacionEmpleado, Venta,
)
from .factories import (
    make_administrador, make_alquiler, make_alquiler_item, make_cajero,
    make_cliente, make_confeccion, make_empleado, make_prenda,
    make_prenda_item, make_reparacion, make_reparacion_item, make_sesion_caja,
    make_tipo_prenda, make_tipo_reparacion, make_vendedor, make_venta,
)


# ──────────────────────────────────────────────────────────────────────────────
# Unidad: la función compartida en sí misma
# ──────────────────────────────────────────────────────────────────────────────

class AutorizarTransicionAEntregadoUnidadTests(TestCase):
    def test_sin_permiso_rechaza_sin_importar_el_saldo(self):
        vendedor = make_vendedor()
        with self.assertRaises(TurnoCajaError):
            autorizar_transicion_a_entregado(vendedor, Decimal('0'))

    def test_con_permiso_y_saldo_cero_no_exige_turno(self):
        admin = make_administrador()
        autorizar_transicion_a_entregado(admin, Decimal('0'))  # no debe levantar nada

    def test_con_permiso_y_saldo_positivo_exige_turno_propio(self):
        admin = make_administrador()
        with self.assertRaises(TurnoCajaError):
            autorizar_transicion_a_entregado(admin, Decimal('50'))
        make_sesion_caja(usuario=admin)
        autorizar_transicion_a_entregado(admin, Decimal('50'))  # ahora sí


# ──────────────────────────────────────────────────────────────────────────────
# crear_reparacion — estado=entregado en el propio alta
# ──────────────────────────────────────────────────────────────────────────────

class CrearReparacionEstadoEntregadoTests(TestCase):
    def setUp(self):
        self.cliente = make_cliente()
        self.tp = make_tipo_prenda()
        self.tr = make_tipo_reparacion()

    def _datos(self, estado='entregado'):
        return {
            'fecha_entrega': (date.today() + timedelta(days=3)).isoformat(),
            'cliente': str(self.cliente.id),
            'estado': estado,
            'forma_pago': 'efectivo',
            'items_count': '1',
            'items[0][tipo_prenda]': str(self.tp.id),
            'items[0][tipo_reparacion]': str(self.tr.id),
            'items[0][costo]': '100.00',
            'items[0][detalles]': '',
            'asignaciones_count': '0',
        }

    def test_vendedor_no_puede_crear_ya_entregada(self):
        """CRITICAL 2 (P1 del reporte): Vendedor tiene `add_reparacion` pero
        NO `cambiar_estado_taller` — no puede crear una reparación que nazca
        entregada, ni aunque haya una caja abierta de otro usuario."""
        cajero_a = make_cajero(username='cajero_a')
        make_sesion_caja(usuario=cajero_a)
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(reverse('crear_reparacion'), self._datos())

        self.assertEqual(resp.status_code, 200, 're-renderiza el form con error, no redirige')
        self.assertEqual(Reparacion.objects.count(), 0, 'no debe quedar ninguna reparación creada')
        self.assertEqual(
            CajaMovimiento.objects.filter(concepto='reparacion_cobro').count(), 0,
            'no debe haberse escrito ningún cobro en la sesión de cajero_a',
        )

    def test_admin_con_saldo_pendiente_sin_turno_propio_rechaza_todo(self):
        """CRITICAL 3 (P2 del reporte): Administrador SÍ puede entregar, pero
        sin turno propio abierto el cobro no se puede registrar — el envío
        completo se rechaza (nada de Reparacion queda en la base), no HTTP 500."""
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(reverse('crear_reparacion'), self._datos())

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Reparacion.objects.count(), 0, 'ni la reparación ni sus items deben persistir')

    def test_admin_con_turno_propio_crea_y_cobra(self):
        admin = make_administrador()
        make_sesion_caja(usuario=admin)
        self.client.force_login(admin)

        resp = self.client.post(reverse('crear_reparacion'), self._datos())

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Reparacion.objects.count(), 1)
        self.assertEqual(CajaMovimiento.objects.filter(concepto='reparacion_cobro').count(), 1)

    def test_admin_puede_crear_entregada_con_saldo_cero_sin_turno(self):
        admin = make_administrador()
        self.client.force_login(admin)
        datos = self._datos()
        datos['items[0][costo]'] = '0.00'

        resp = self.client.post(reverse('crear_reparacion'), datos)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Reparacion.objects.count(), 1)


# ──────────────────────────────────────────────────────────────────────────────
# editar_reparacion — transición a estado=entregado
# ──────────────────────────────────────────────────────────────────────────────

class EditarReparacionEstadoEntregadoTests(TestCase):
    def setUp(self):
        self.cliente = make_cliente()
        self.tp = make_tipo_prenda()
        self.tr = make_tipo_reparacion()
        self.rep = make_reparacion(cliente=self.cliente, estado='pendiente', total=Decimal('100'))
        make_reparacion_item(self.rep, tipo_prenda=self.tp, tipo_reparacion=self.tr, costo=Decimal('100'))

    def _datos(self, estado='entregado'):
        return {
            'fecha_entrega': (date.today() + timedelta(days=3)).isoformat(),
            'cliente': str(self.cliente.id),
            'estado': estado,
            'forma_pago': 'efectivo',
            'items_count': '1',
            'items[0][tipo_prenda]': str(self.tp.id),
            'items[0][tipo_reparacion]': str(self.tr.id),
            'items[0][costo]': '100.00',
            'items[0][detalles]': '',
            'asignaciones_count': '0',
        }

    def test_vendedor_no_puede_entregar_por_edicion(self):
        """CRITICAL 2 (P3 del reporte): editar_reparacion con estado=entregado
        NO debe poder saltarse la regla Admin/Taller ni el cobro guard, aunque
        Vendedor tenga `change_reparacion`."""
        cajero_a = make_cajero(username='cajero_a')
        make_sesion_caja(usuario=cajero_a)
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': self.rep.id}), self._datos())

        self.rep.refresh_from_db()
        self.assertEqual(self.rep.estado, 'pendiente', 'el estado no debe haber cambiado')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_reparacion=self.rep).count(), 0,
            'no debe haberse escrito ningún movimiento en la sesión de cajero_a',
        )
        self.assertEqual(resp.status_code, 200)

    def test_admin_sin_turno_propio_rechaza_todo(self):
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': self.rep.id}), self._datos())

        self.rep.refresh_from_db()
        self.assertEqual(self.rep.estado, 'pendiente')
        self.assertEqual(CajaMovimiento.objects.filter(referencia_reparacion=self.rep).count(), 0)
        self.assertEqual(resp.status_code, 200)

    def test_admin_con_turno_propio_entrega_y_cobra(self):
        admin = make_administrador()
        make_sesion_caja(usuario=admin)
        self.client.force_login(admin)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': self.rep.id}), self._datos())

        self.rep.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.rep.estado, 'entregado')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_reparacion=self.rep, concepto='reparacion_saldo').count(), 1
        )


# ──────────────────────────────────────────────────────────────────────────────
# crear_confeccion / editar_confeccion — mismo patrón
# ──────────────────────────────────────────────────────────────────────────────

class CrearConfeccionEstadoEntregadoTests(TestCase):
    def setUp(self):
        self.tp = make_tipo_prenda()

    def _datos(self, estado='entregado'):
        return {
            'fecha_inicio': date.today().isoformat(),
            'color': 'Negro', 'modelo': 'Traje', 'precio': '0',
            'estado': estado,
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-tipo_prenda': str(self.tp.id),
            'items-0-costo': '300.00',
            'items-0-talla': '',
        }

    def test_vendedor_no_puede_crear_ya_entregada(self):
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(reverse('crear_confeccion'), self._datos())

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Confeccion.objects.count(), 0)


class EditarConfeccionEstadoEntregadoTests(TestCase):
    def setUp(self):
        self.conf = make_confeccion(estado='pendiente', precio=Decimal('300'), adelanto=Decimal('0'))
        self.tp = make_tipo_prenda()

    def _datos(self, estado='entregado'):
        return {
            'fecha_inicio': date.today().isoformat(),
            'color': self.conf.color, 'modelo': self.conf.modelo, 'precio': '300.00',
            'estado': estado,
            'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        }

    def test_vendedor_no_puede_entregar_por_edicion(self):
        """CRITICAL 2 (P3 del reporte): editar_confeccion tiene la misma forma
        de bypass que editar_reparacion (CAUTO-04 en confeccion_to_caja)."""
        cajero_a = make_cajero(username='cajero_a')
        make_sesion_caja(usuario=cajero_a)
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(
            reverse('editar_confeccion', kwargs={'id': self.conf.id}), self._datos())

        self.conf.refresh_from_db()
        self.assertEqual(self.conf.estado, 'pendiente')
        self.assertEqual(CajaMovimiento.objects.filter(referencia_confeccion=self.conf).count(), 0)
        self.assertEqual(resp.status_code, 200)

    def test_admin_con_turno_propio_entrega_y_cobra(self):
        admin = make_administrador()
        make_sesion_caja(usuario=admin)
        self.client.force_login(admin)

        resp = self.client.post(
            reverse('editar_confeccion', kwargs={'id': self.conf.id}), self._datos())

        self.conf.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.conf.estado, 'entregado')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_confeccion=self.conf, concepto='confeccion_saldo').count(), 1
        )


# ──────────────────────────────────────────────────────────────────────────────
# devolver_alquiler — sin sesión abierta, con garantía monetaria (CRITICAL 3, P4)
# ──────────────────────────────────────────────────────────────────────────────

class DevolverAlquilerSinSesionTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.client.force_login(self.admin)
        self.alquiler = make_alquiler(
            estado='alquilado',
            garantia_tipo='efectivo', garantia_monto=Decimal('100'),
        )
        self.item = make_alquiler_item(self.alquiler)
        self.item.prenda_item.estado = 'alquilado'
        self.item.prenda_item.save(update_fields=['estado'])

    def test_sin_sesion_no_devuelve_nada_ni_revienta(self):
        resp = self.client.post(
            reverse('devolver_alquiler', kwargs={'id': self.alquiler.id}),
            {'garantia_devolver': '100'},
        )

        self.assertNotEqual(resp.status_code, 500, 'no debe reventar con un 500')
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'alquilado', 'no debe quedar marcado como devuelto')
        self.item.prenda_item.refresh_from_db()
        self.assertEqual(
            self.item.prenda_item.estado, 'alquilado',
            'el item no debe volver a disponible si la garantía no se pudo devolver',
        )
        self.assertEqual(CajaMovimiento.objects.filter(referencia_alquiler=self.alquiler).count(), 0)

    def test_con_sesion_propia_devuelve_y_reintegra_garantia(self):
        make_sesion_caja(usuario=self.admin)
        resp = self.client.post(
            reverse('devolver_alquiler', kwargs={'id': self.alquiler.id}),
            {'garantia_devolver': '100'},
        )
        self.assertEqual(resp.status_code, 302)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'devuelto')
        self.assertEqual(
            CajaMovimiento.objects.filter(
                referencia_alquiler=self.alquiler, concepto='garantia_devolucion').count(),
            1,
        )


# ──────────────────────────────────────────────────────────────────────────────
# eliminar_* con movimientos activos y sin sesión abierta (CRITICAL 3, P10)
# ──────────────────────────────────────────────────────────────────────────────

class EliminarConMovimientosActivosSinSesionTests(TestCase):
    """Ninguna de estas vistas debe devolver 500 ni dejar un borrado a medias
    cuando hay CajaMovimiento activos y ninguna caja está abierta."""

    def setUp(self):
        self.admin = make_administrador()
        self.client.force_login(self.admin)

    def _mov(self, **kwargs):
        return CajaMovimiento.objects.create(
            tipo='ingreso', concepto=kwargs.pop('concepto'), monto=Decimal('50'),
            forma_pago='efectivo', origen='automatico', **kwargs,
        )

    def test_eliminar_reparacion(self):
        rep = make_reparacion(total=Decimal('50'))
        self._mov(concepto='reparacion_cobro', referencia_reparacion=rep)

        resp = self.client.post(reverse('eliminar_reparacion', args=[rep.id]))

        self.assertNotEqual(resp.status_code, 500)
        self.assertTrue(Reparacion.objects.filter(id=rep.id).exists())

    def test_eliminar_confeccion(self):
        conf = make_confeccion()
        self._mov(concepto='confeccion_adelanto', referencia_confeccion=conf)

        resp = self.client.post(reverse('eliminar_confeccion', args=[conf.id]))

        self.assertNotEqual(resp.status_code, 500)
        self.assertTrue(Confeccion.objects.filter(id=conf.id).exists())

    def test_eliminar_venta(self):
        cliente = make_cliente()
        empleado = make_empleado()
        prenda = make_prenda()
        item = make_prenda_item(prenda, estado='baja')
        # total se deja en 0 al crear (evita disparar el signal automático
        # `venta_to_caja`, que cobraría de una sin sesión abierta); lo que
        # importa para esta prueba es el movimiento activo creado a mano.
        venta = make_venta(cliente=cliente, empleado=empleado)
        from misastreria.models import VentaItem
        VentaItem.objects.create(venta=venta, prenda_item=item, precio_unitario=Decimal('50'))
        self._mov(concepto='venta_cobro', referencia_venta=venta)

        resp = self.client.post(reverse('eliminar_venta', args=[venta.id]))

        self.assertNotEqual(resp.status_code, 500)
        self.assertTrue(Venta.objects.filter(id=venta.id).exists())
        item.refresh_from_db()
        self.assertEqual(item.estado, 'baja', 'no debe liberarse el item si el borrado se rechaza')

    def test_eliminar_alquiler(self):
        alquiler = make_alquiler(estado='alquilado')
        item = make_alquiler_item(alquiler)
        item.prenda_item.estado = 'alquilado'
        item.prenda_item.save(update_fields=['estado'])
        self._mov(concepto='alquiler_cobro', referencia_alquiler=alquiler)

        resp = self.client.post(reverse('eliminar_alquiler', args=[alquiler.id]))

        self.assertNotEqual(resp.status_code, 500)
        self.assertTrue(Alquiler.objects.filter(id=alquiler.id).exists())
        item.prenda_item.refresh_from_db()
        self.assertEqual(
            item.prenda_item.estado, 'alquilado',
            'no debe liberarse el item si el borrado se rechaza',
        )


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 2 — editar_venta: el reembolso por sobrepago respeta el dueño de la
# sesión (extremo a extremo: vista -> _ajustar_total_en_caja).
# ──────────────────────────────────────────────────────────────────────────────

class EditarVentaReembolsoOwnershipTests(TestCase):
    def setUp(self):
        self.cliente = make_cliente()
        self.empleado = make_empleado()
        self.item = make_prenda_item(make_prenda(precio=Decimal('230.00')))
        self.venta = make_venta(
            cliente=self.cliente, empleado=self.empleado,
            subtotal=Decimal('0'), total=Decimal('0'), estado='en_proceso',
        )
        Venta.objects.filter(pk=self.venta.pk).update(total=Decimal('230'), subtotal=Decimal('230'))
        self.venta.refresh_from_db()
        # Sesión de armado, sólo para poder registrar el pago inicial en el
        # setUp; se cierra enseguida — cada test abre la sesión que le
        # corresponde a su escenario.
        sesion_armado = make_sesion_caja()
        registrar_pago_venta(self.venta, Decimal('100.00'), 'efectivo', None, sesion_armado.usuario_apertura)
        sesion_armado.estado = 'cerrada'
        sesion_armado.save(update_fields=['estado'])

    def _datos(self, precio):
        return {
            'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
            'cliente': str(self.cliente.id), 'empleado': str(self.empleado.id),
            'descuento': '0', 'notas': '',
            'item_prenda_item': [str(self.item.id)], 'item_precio': [precio],
            'item_grupo_conjunto': [''], 'item_tipo_reparacion': [''],
            'item_precio_reparacion': [''], 'item_empleado': [''],
            'item_monto_comision': [''],
        }

    def test_admin_no_puede_generar_el_reembolso_en_sesion_ajena(self):
        cajero_a = make_cajero(username='cajero_a_venta')
        make_sesion_caja(usuario=cajero_a)
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(reverse('editar_venta', args=[self.venta.id]), self._datos('80.00'))

        self.assertEqual(resp.status_code, 200, 're-renderiza con error, no redirige')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_venta=self.venta, concepto='anulacion_cobro').count(), 0
        )

    def test_dueno_de_la_sesion_si_puede(self):
        cajero_a = make_cajero(username='cajero_a_venta2')
        make_sesion_caja(usuario=cajero_a)
        self.client.force_login(cajero_a)

        resp = self.client.post(reverse('editar_venta', args=[self.venta.id]), self._datos('80.00'))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_venta=self.venta, concepto='anulacion_cobro').count(), 1
        )


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 6 — crear_confeccion con adelanto y sin turno propio rechaza todo
# ──────────────────────────────────────────────────────────────────────────────

class CrearConfeccionAdelantoSinTurnoTests(TestCase):
    def setUp(self):
        self.tp = make_tipo_prenda()
        self.admin = make_administrador()
        self.client.force_login(self.admin)

    def _datos(self, **extra):
        data = {
            'fecha_inicio': date.today().isoformat(),
            'color': 'Negro', 'modelo': 'Traje', 'precio': '0',
            'estado': 'pendiente',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-tipo_prenda': str(self.tp.id),
            'items-0-costo': '300.00',
            'items-0-talla': '',
            'via_caja': 'on',
            'pago[0][monto]': '100.00', 'pago[0][forma_pago]': 'efectivo',
        }
        data.update(extra)
        return data

    def test_sin_turno_propio_no_crea_nada(self):
        """Consistente con crear_venta/crear_alquiler: si hay un adelanto y no
        hay turno propio, se rechaza TODO el envío, no sólo el adelanto."""
        resp = self.client.post(reverse('crear_confeccion'), self._datos())
        self.assertEqual(resp.status_code, 200, 're-renderiza el form con error, no redirige')
        self.assertEqual(Confeccion.objects.count(), 0, 'no debe quedar ninguna confección creada')

    def test_con_turno_propio_crea_y_cobra(self):
        make_sesion_caja(usuario=self.admin)
        resp = self.client.post(reverse('crear_confeccion'), self._datos())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Confeccion.objects.count(), 1)
        c = Confeccion.objects.get()
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_confeccion=c, concepto='confeccion_pago').count(), 1
        )

    def test_sin_adelanto_no_requiere_turno(self):
        datos = self._datos()
        del datos['pago[0][monto]']
        del datos['pago[0][forma_pago]']
        resp = self.client.post(reverse('crear_confeccion'), datos)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Confeccion.objects.count(), 1)


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 4 (reporte de verificación) — cobros de confección/reparación sin
# sesión abierta: el mecanismo ya existía (`_registrar_pagos_confeccion` /
# `_puede_cobrar_o_avisar`), sólo faltaba la prueba de "sin sesión -> 0 filas".
# ──────────────────────────────────────────────────────────────────────────────

class AgregarPagoConfeccionSinSesionTests(TestCase):
    def test_sin_sesion_no_crea_movimiento(self):
        conf = make_confeccion(precio=Decimal('500.00'), saldo=Decimal('500.00'))
        cajero = make_cajero()
        self.client.force_login(cajero)
        self.client.post(
            reverse('agregar_pago_confeccion', kwargs={'id': conf.id}),
            {'monto': '200.00', 'forma_pago': 'efectivo', 'via_caja': 'on'},
        )
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_confeccion=conf, concepto='confeccion_pago').count(), 0
        )


class AgregarPagoReparacionSinSesionTests(TestCase):
    def test_sin_sesion_no_crea_movimiento(self):
        rep = make_reparacion(total=Decimal('150.00'))
        cajero = make_cajero()
        self.client.force_login(cajero)
        self.client.post(
            reverse('agregar_pago_reparacion', kwargs={'id': rep.id}),
            {'monto': '100.00', 'forma_pago': 'efectivo', 'via_caja': 'on'},
        )
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_reparacion=rep, concepto='reparacion_pago').count(), 0
        )


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 4 — crear_alquiler: el pago inicial (adelanto/garantía monetaria) sin
# turno propio rechaza TODO el envío, mismo criterio que crear_venta.
# ──────────────────────────────────────────────────────────────────────────────

class CrearAlquilerPagoInlineRechazaTodoTests(TestCase):
    def setUp(self):
        self.cliente = make_cliente()
        prenda = make_prenda(precio_alquiler_base=Decimal('250.00'))
        self.item = make_prenda_item(prenda, tipo='alquiler')
        self.cajero = make_cajero()
        self.client.force_login(self.cajero)

    def _datos(self, **extra):
        datos = {
            'fecha_alquiler': date.today().isoformat(),
            'fecha_devolucion': (date.today() + timedelta(days=3)).isoformat(),
            'cliente': str(self.cliente.id),
            'estado': 'alquilado', 'descuento': '0', 'notas': '',
            'adelanto': '250.00', 'forma_pago': 'efectivo',
            'item_prenda_item': [str(self.item.id)],
            'item_precio': ['250.00'],
            'item_grupo_conjunto': [''], 'item_tipo_reparacion': [''],
            'item_precio_reparacion': [''], 'item_empleado': [''],
            'item_monto_comision': [''],
        }
        datos.update(extra)
        return datos

    def test_sin_turno_propio_no_crea_nada(self):
        resp = self.client.post(reverse('crear_alquiler'), self._datos())
        self.assertEqual(resp.status_code, 200, 're-renderiza el form con error, no redirige')
        self.assertEqual(Alquiler.objects.count(), 0, 'no debe quedar ningún alquiler creado')

    def test_con_turno_propio_crea_y_cobra(self):
        make_sesion_caja(usuario=self.cajero)
        resp = self.client.post(reverse('crear_alquiler'), self._datos())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Alquiler.objects.count(), 1)

    def test_sin_adelanto_ni_garantia_no_requiere_turno(self):
        datos = self._datos(adelanto='0')
        resp = self.client.post(reverse('crear_alquiler'), datos)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Alquiler.objects.count(), 1)


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 4 — editar_venta/editar_alquiler: el reembolso por sobrepago también
# se rechaza (no sólo cuando la sesión es ajena) cuando NO hay ninguna caja
# abierta — complementa `EditarVentaReembolsoOwnershipTests` (ownership) con el
# caso "cero sesiones".
# ──────────────────────────────────────────────────────────────────────────────

class EditarVentaSinSesionAlgunaTests(TestCase):
    def test_sobrepago_sin_ninguna_sesion_abierta_rechaza_todo(self):
        cliente = make_cliente()
        empleado = make_empleado()
        item = make_prenda_item(make_prenda(precio=Decimal('230.00')))
        venta = make_venta(
            cliente=cliente, empleado=empleado,
            subtotal=Decimal('0'), total=Decimal('0'), estado='en_proceso',
        )
        Venta.objects.filter(pk=venta.pk).update(total=Decimal('230'), subtotal=Decimal('230'))
        venta.refresh_from_db()
        sesion_armado = make_sesion_caja()
        registrar_pago_venta(venta, Decimal('100.00'), 'efectivo', None, sesion_armado.usuario_apertura)
        sesion_armado.estado = 'cerrada'
        sesion_armado.save(update_fields=['estado'])

        admin = make_administrador()
        self.client.force_login(admin)
        resp = self.client.post(reverse('editar_venta', args=[venta.id]), {
            'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
            'cliente': str(cliente.id), 'empleado': str(empleado.id),
            'descuento': '0', 'notas': '',
            'item_prenda_item': [str(item.id)], 'item_precio': ['80.00'],
            'item_grupo_conjunto': [''], 'item_tipo_reparacion': [''],
            'item_precio_reparacion': [''], 'item_empleado': [''],
            'item_monto_comision': [''],
        })

        self.assertEqual(resp.status_code, 200, 're-renderiza con error, no redirige')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_venta=venta, concepto='anulacion_cobro').count(), 0
        )


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 4 — marcar_entregado / entregar_confeccion: saldo pendiente sin turno
# propio rechaza la entrega (el mecanismo es de Phase 4; faltaba la prueba
# dedicada del rechazo en sí, más allá del caso de éxito ya cubierto en
# test_views_crud.py).
# ──────────────────────────────────────────────────────────────────────────────

class MarcarEntregadoSinTurnoRechazaTests(TestCase):
    def test_saldo_pendiente_sin_turno_no_entrega(self):
        admin = make_administrador()
        self.client.force_login(admin)
        rep = make_reparacion(total=Decimal('80.00'))

        resp = self.client.post(reverse('marcar_entregado', kwargs={'id': rep.id}))

        rep.refresh_from_db()
        self.assertEqual(resp.status_code, 302, 'redirige con mensaje de error, no un 500')
        self.assertEqual(rep.estado, 'pendiente', 'no debe quedar marcada como entregada')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_reparacion=rep, concepto='reparacion_saldo').count(), 0
        )


class EntregarConfeccionSinTurnoRechazaTests(TestCase):
    def test_saldo_pendiente_sin_turno_no_entrega(self):
        admin = make_administrador()
        self.client.force_login(admin)
        conf = make_confeccion(estado='pendiente', precio=Decimal('300'), adelanto=Decimal('0'))

        resp = self.client.post(reverse('entregar_confeccion', kwargs={'id': conf.id}))

        conf.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(conf.estado, 'pendiente')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_confeccion=conf, concepto='confeccion_saldo').count(), 0
        )


# ──────────────────────────────────────────────────────────────────────────────
# CRITICAL 1 (re-verify) — editar_reparacion: la matriz "en_proceso/entregado
# = Admin/Taller only" aplica a CUALQUIER cambio de estado, no sólo a la
# transición HACIA 'entregado'. Proven exploits del reporte:
#   NEW-1: Vendedor mandaba estado=pendiente sobre una reparación ya
#          entregada -> escribía un egreso `anulacion_cobro` de Bs100 en la
#          caja del cajero A (la reversión automática de caja_signals no
#          chequeaba de quién era la caja).
#   NEW-2: Vendedor también podía pasar pendiente->en_proceso sin permiso.
# ──────────────────────────────────────────────────────────────────────────────

class EditarReparacionRegresionEstadoTests(TestCase):
    def setUp(self):
        self.cliente = make_cliente()
        self.tp = make_tipo_prenda()
        self.tr = make_tipo_reparacion()

    def _rep_entregada_con_cobro(self, sesion_para_el_cobro):
        rep = make_reparacion(cliente=self.cliente, estado='entregado', total=Decimal('100'))
        make_reparacion_item(rep, tipo_prenda=self.tp, tipo_reparacion=self.tr, costo=Decimal('100'))
        CajaMovimiento.objects.create(
            sesion=sesion_para_el_cobro, tipo='ingreso', concepto='reparacion_cobro',
            monto=Decimal('100'), forma_pago='efectivo', origen='automatico',
            referencia_reparacion=rep,
        )
        return rep

    def _datos(self, estado):
        return {
            'fecha_entrega': (date.today() + timedelta(days=3)).isoformat(),
            'cliente': str(self.cliente.id),
            'estado': estado,
            'forma_pago': 'efectivo',
            'items_count': '1',
            'items[0][tipo_prenda]': str(self.tp.id),
            'items[0][tipo_reparacion]': str(self.tr.id),
            'items[0][costo]': '100.00',
            'items[0][detalles]': '',
            'asignaciones_count': '0',
        }

    def test_vendedor_no_puede_regresar_de_entregado_a_pendiente(self):
        cajero_a = make_cajero(username='cajero_a_reg')
        sesion_a = make_sesion_caja(usuario=cajero_a)
        rep = self._rep_entregada_con_cobro(sesion_a)
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': rep.id}), self._datos('pendiente'))

        rep.refresh_from_db()
        self.assertEqual(resp.status_code, 200, 're-renderiza con error, no redirige')
        self.assertEqual(rep.estado, 'entregado', 'el estado no debe haber regresado')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_reparacion=rep, concepto='anulacion_cobro').count(), 0,
            'no debe haberse escrito ningún reverso en la caja de cajero_a',
        )

    def test_vendedor_no_puede_pasar_pendiente_a_en_proceso(self):
        rep = make_reparacion(cliente=self.cliente, estado='pendiente', total=Decimal('100'))
        make_reparacion_item(rep, tipo_prenda=self.tp, tipo_reparacion=self.tr, costo=Decimal('100'))
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': rep.id}), self._datos('en_proceso'))

        rep.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(rep.estado, 'pendiente')

    def test_admin_puede_regresar_y_el_reverso_respeta_la_regla_dueno_o_admin(self):
        """WARNING 1 (regla confirmada por el dueño del producto): un
        Administrador SÍ puede revertir el cobro aunque la caja abierta sea
        de otro cajero — 'revertir: dueño o Administrador'."""
        cajero_a = make_cajero(username='cajero_a_reg2')
        sesion_a = make_sesion_caja(usuario=cajero_a)
        rep = self._rep_entregada_con_cobro(sesion_a)
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': rep.id}), self._datos('pendiente'))

        rep.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(rep.estado, 'pendiente')
        reverso = CajaMovimiento.objects.get(referencia_reparacion=rep, concepto='anulacion_cobro')
        self.assertEqual(reverso.sesion_id, sesion_a.id)
        self.assertEqual(reverso.tipo, 'egreso')

    def test_admin_sin_ninguna_sesion_abierta_no_puede_revertir(self):
        """Sin sesión abierta no hay dónde asentar el reverso — se rechaza
        todo el envío (CRITICAL 3), no un 500 a mitad de camino."""
        sesion = make_sesion_caja()
        rep = self._rep_entregada_con_cobro(sesion)
        sesion.estado = 'cerrada'
        sesion.save(update_fields=['estado'])
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(
            reverse('editar_reparacion', kwargs={'id': rep.id}), self._datos('pendiente'))

        rep.refresh_from_db()
        self.assertNotEqual(resp.status_code, 500)
        self.assertEqual(rep.estado, 'entregado')


# ──────────────────────────────────────────────────────────────────────────────
# CRITICAL 2 (re-verify) — devolver_alquiler: devolver la garantía es un
# egreso NUEVO (no la reversión de un movimiento existente), así que exige
# turno PROPIO igual que cualquier otro cobro — Administrador NO exento (a
# diferencia de la regla de reversión de WARNING 1). Proven exploit del
# reporte (NEW-3): Vendedor (nunca tiene turno propio) escribía un egreso
# `garantia_devolucion` de Bs100 en la caja del cajero A.
# ──────────────────────────────────────────────────────────────────────────────

class DevolverAlquilerGarantiaOwnershipTests(TestCase):
    def setUp(self):
        self.alquiler = make_alquiler(
            estado='alquilado', garantia_tipo='efectivo', garantia_monto=Decimal('100'),
        )
        self.item = make_alquiler_item(self.alquiler)
        self.item.prenda_item.estado = 'alquilado'
        self.item.prenda_item.save(update_fields=['estado'])

    def _devolver(self):
        return self.client.post(
            reverse('devolver_alquiler', kwargs={'id': self.alquiler.id}),
            {'garantia_devolver': '100'},
        )

    def test_vendedor_no_puede_devolver_garantia_en_sesion_ajena(self):
        cajero_a = make_cajero(username='cajero_a_gar')
        make_sesion_caja(usuario=cajero_a)
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self._devolver()

        self.assertNotEqual(resp.status_code, 500)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'alquilado', 'no debe quedar devuelto')
        self.item.prenda_item.refresh_from_db()
        self.assertEqual(self.item.prenda_item.estado, 'alquilado')
        self.assertEqual(
            CajaMovimiento.objects.filter(
                referencia_alquiler=self.alquiler, concepto='garantia_devolucion').count(), 0,
        )

    def test_admin_tampoco_puede_devolver_en_sesion_ajena(self):
        """A diferencia de una reversión, devolver una garantía es un egreso
        NUEVO: Administrador NO está exento — tiene que abrir su propio
        turno, igual que cualquier otro cobro."""
        cajero_a = make_cajero(username='cajero_a_gar2')
        make_sesion_caja(usuario=cajero_a)
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self._devolver()

        self.assertNotEqual(resp.status_code, 500)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'alquilado')
        self.assertEqual(
            CajaMovimiento.objects.filter(
                referencia_alquiler=self.alquiler, concepto='garantia_devolucion').count(), 0,
        )

    def test_dueno_de_la_sesion_si_puede_devolver(self):
        cajero = make_cajero(username='cajero_gar_dueno')
        make_sesion_caja(usuario=cajero)
        self.client.force_login(cajero)

        resp = self._devolver()

        self.assertEqual(resp.status_code, 302)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'devuelto')
        self.assertEqual(
            CajaMovimiento.objects.filter(
                referencia_alquiler=self.alquiler, concepto='garantia_devolucion').count(), 1,
        )


# ──────────────────────────────────────────────────────────────────────────────
# CRITICAL 1 (tercera vuelta de sdd-verify) — pagar_comision_empleado: pagar
# una comisión "por caja" es un egreso NUEVO como cualquier otro — sólo el
# dueño del turno abierto puede generarlo, Administrador NO exento. Proven
# exploit del reporte (P7): un Administrador (no dueño) pagaba Bs80 de
# comisión y el egreso se escribía en la caja de Cajero A; P7b: sin ninguna
# sesión abierta, la vista reventaba con HTTP 500 (CajaSinSesionError no
# contemplada).
# ──────────────────────────────────────────────────────────────────────────────

class PagarComisionEmpleadoOwnershipTests(TestCase):
    def setUp(self):
        self.empleado = make_empleado()
        rep = make_reparacion(total=Decimal('80'))
        self.asignacion = ReparacionEmpleado.objects.create(
            reparacion=rep, empleado=self.empleado, monto_comision_fijo=Decimal('80'),
        )

    def _pagar(self, usuario):
        self.client.force_login(usuario)
        return self.client.post(
            reverse('pagar_comision_empleado', kwargs={'empleado_id': self.empleado.id}),
            {
                'sel': [f'reparacion:{self.asignacion.id}'],
                'forma_pago': 'efectivo',
                'via_caja': 'on',
            },
        )

    def test_admin_no_dueno_no_puede_pagar_comision_en_sesion_ajena(self):
        cajero_a = make_cajero(username='cajero_a_com')
        make_sesion_caja(usuario=cajero_a)
        admin = make_administrador(username='admin_com')

        resp = self._pagar(admin)

        self.assertNotEqual(resp.status_code, 500)
        self.assertFalse(PagoComisionEmpleado.objects.exists(), 'no debe quedar ningún pago registrado')
        self.assertEqual(
            CajaMovimiento.objects.filter(concepto='comision_empleado').count(), 0,
            'no debe haberse escrito ningún egreso en la caja de cajero_a',
        )

    def test_sin_ninguna_sesion_abierta_no_revienta_con_500(self):
        admin = make_administrador(username='admin_com2')

        resp = self._pagar(admin)

        self.assertNotEqual(resp.status_code, 500, 'CajaSinSesionError debe convertirse en mensaje, no en un 500')
        self.assertFalse(PagoComisionEmpleado.objects.exists())
        self.assertEqual(CajaMovimiento.objects.filter(concepto='comision_empleado').count(), 0)

    def test_dueno_de_la_sesion_si_puede_pagar_comision(self):
        # `pagar_comision_empleado` exige `misastreria.change_empleado`, que
        # sólo tiene Administrador — el dueño de la sesión en este escenario
        # es un Administrador que abrió su propio turno.
        admin_dueno = make_administrador(username='admin_com_dueno')
        make_sesion_caja(usuario=admin_dueno)

        resp = self._pagar(admin_dueno)

        self.assertEqual(resp.status_code, 302)
        pago = PagoComisionEmpleado.objects.get(empleado=self.empleado)
        mov = CajaMovimiento.objects.get(concepto='comision_empleado')
        self.assertEqual(mov.monto, Decimal('80'))
        self.assertEqual(mov.referencia_pago_comision_id, pago.id)


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 2 (tercera vuelta de sdd-verify) — crear_reparacion/crear_confeccion:
# la matriz "en_proceso/entregado = Admin/Taller only" también aplica al
# ESTADO INICIAL, no sólo a la transición a 'entregado'. Proven exploit del
# reporte (P8): un Vendedor creaba directamente en 'en_proceso'.
# ──────────────────────────────────────────────────────────────────────────────

class CrearReparacionEstadoEnProcesoTests(TestCase):
    def setUp(self):
        self.cliente = make_cliente()
        self.tp = make_tipo_prenda()
        self.tr = make_tipo_reparacion()

    def _datos(self, estado):
        return {
            'fecha_entrega': (date.today() + timedelta(days=3)).isoformat(),
            'cliente': str(self.cliente.id),
            'estado': estado,
            'forma_pago': 'efectivo',
            'items_count': '1',
            'items[0][tipo_prenda]': str(self.tp.id),
            'items[0][tipo_reparacion]': str(self.tr.id),
            'items[0][costo]': '100.00',
            'items[0][detalles]': '',
            'asignaciones_count': '0',
        }

    def test_vendedor_no_puede_crear_en_proceso(self):
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(reverse('crear_reparacion'), self._datos('en_proceso'))

        self.assertEqual(resp.status_code, 200, 're-renderiza el form con error, no redirige')
        self.assertEqual(Reparacion.objects.count(), 0)

    def test_admin_si_puede_crear_en_proceso(self):
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(reverse('crear_reparacion'), self._datos('en_proceso'))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Reparacion.objects.count(), 1)
        self.assertEqual(Reparacion.objects.first().estado, 'en_proceso')


class CrearConfeccionEstadoEnProcesoTests(TestCase):
    def setUp(self):
        self.tp = make_tipo_prenda()

    def _datos(self, estado):
        return {
            'fecha_inicio': date.today().isoformat(),
            'color': 'Negro', 'modelo': 'Traje', 'precio': '0',
            'estado': estado,
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-tipo_prenda': str(self.tp.id),
            'items-0-costo': '300.00',
            'items-0-talla': '',
        }

    def test_vendedor_no_puede_crear_en_proceso(self):
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(reverse('crear_confeccion'), self._datos('en_proceso'))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Confeccion.objects.count(), 0)

    def test_admin_si_puede_crear_en_proceso(self):
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(reverse('crear_confeccion'), self._datos('en_proceso'))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Confeccion.objects.count(), 1)
        self.assertEqual(Confeccion.objects.first().estado, 'en_proceso')


# ──────────────────────────────────────────────────────────────────────────────
# WARNING 3 (tercera vuelta de sdd-verify) — editar_confeccion: cobertura de
# TODAS las transiciones de estado por roles sin el permiso de taller (P3 del
# reporte: "Vendedor pendiente<->en_proceso, entregado->pendiente,
# entregado->en_proceso -> todos 200, sin cambio"). A diferencia de
# Reparación, `ConfeccionForm.clean_estado` ya bloquea CUALQUIER regresión
# desde 'entregado' a nivel de formulario, para cualquier usuario — por eso
# no hay un escenario de "Administrador SÍ puede revertir" análogo a
# `EditarReparacionRegresionEstadoTests` acá: la confección simplemente no
# se puede regresar por `editar_confeccion` (ver eliminar_confeccion / ajuste
# manual para ese caso, fuera de este guard).
# ──────────────────────────────────────────────────────────────────────────────

class EditarConfeccionTransicionesSinPermisoTallerTests(TestCase):
    def setUp(self):
        self.tp = make_tipo_prenda()

    def _datos(self, conf, estado):
        return {
            'fecha_inicio': date.today().isoformat(),
            'color': conf.color, 'modelo': conf.modelo, 'precio': '300.00',
            'estado': estado,
            'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        }

    def _rechazado_sin_cambio(self, estado_inicial, estado_pedido):
        conf = make_confeccion(precio=Decimal('300'), adelanto=Decimal('0'), estado=estado_inicial)
        vendedor = make_vendedor()
        self.client.force_login(vendedor)

        resp = self.client.post(
            reverse('editar_confeccion', kwargs={'id': conf.id}), self._datos(conf, estado_pedido))

        conf.refresh_from_db()
        self.assertEqual(resp.status_code, 200, 're-renderiza con error, no redirige')
        self.assertEqual(conf.estado, estado_inicial, 'el estado no debe haber cambiado')
        self.assertEqual(CajaMovimiento.objects.filter(referencia_confeccion=conf).count(), 0)

    def test_vendedor_no_puede_pasar_pendiente_a_en_proceso(self):
        self._rechazado_sin_cambio('pendiente', 'en_proceso')

    def test_vendedor_no_puede_pasar_en_proceso_a_pendiente(self):
        self._rechazado_sin_cambio('en_proceso', 'pendiente')

    def test_vendedor_no_puede_regresar_de_entregado_a_pendiente(self):
        self._rechazado_sin_cambio('entregado', 'pendiente')

    def test_vendedor_no_puede_regresar_de_entregado_a_en_proceso(self):
        self._rechazado_sin_cambio('entregado', 'en_proceso')

    def test_admin_tampoco_puede_regresar_de_entregado_por_el_formulario(self):
        """`ConfeccionForm.clean_estado` bloquea la regresión para CUALQUIER
        usuario, Administrador incluido — no es un chequeo de permiso, así
        que no debe confundirse con una brecha de la matriz."""
        conf = make_confeccion(precio=Decimal('300'), adelanto=Decimal('0'), estado='entregado')
        admin = make_administrador()
        self.client.force_login(admin)

        resp = self.client.post(
            reverse('editar_confeccion', kwargs={'id': conf.id}), self._datos(conf, 'pendiente'))

        conf.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(conf.estado, 'entregado')


# ──────────────────────────────────────────────────────────────────────────────
# W4 (cuarta verificación) — tests que SÍ ejercitan `autorizar_cambio_estado`
# en `editar_confeccion`. Las regresiones desde 'entregado' las corta antes
# `ConfeccionForm.clean_estado`, y `count()==0` valía trivialmente sin sesión
# abierta: con saldo 0 (todo pagado) no hay ningún cobro de por medio, así que
# lo único que puede impedir a un Vendedor marcar 'entregado' es el chequeo de
# permiso de la matriz. Si se quita `autorizar_cambio_estado` de la vista,
# estos tests fallan.
# ──────────────────────────────────────────────────────────────────────────────

class EditarConfeccionMatrizDeEstadoAisladaTests(TestCase):
    def setUp(self):
        self.dueno = make_cajero(username='dueno_conf')
        make_sesion_caja(usuario=self.dueno)
        self.conf = make_confeccion(
            precio=Decimal('300'), adelanto=Decimal('0'), estado='en_proceso',
            usuario=self.dueno,
        )
        from misastreria.caja_signals import registrar_pago_confeccion
        registrar_pago_confeccion(self.conf, Decimal('300'), 'efectivo', '', self.dueno)
        self.conf.refresh_from_db()
        self.assertEqual(self.conf.saldo_pendiente, Decimal('0'), 'precondición: sin saldo')

    def _datos(self, estado, color=None):
        return {
            'fecha_inicio': date.today().isoformat(),
            'color': color or self.conf.color, 'modelo': self.conf.modelo,
            'precio': '300.00', 'estado': estado,
            'items-TOTAL_FORMS': '0', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
        }

    def _post(self, user, estado, **kw):
        self.client.force_login(user)
        return self.client.post(
            reverse('editar_confeccion', kwargs={'id': self.conf.id}), self._datos(estado, **kw))

    def test_vendedor_no_marca_entregado_con_saldo_cero_por_falta_de_permiso(self):
        resp = self._post(make_vendedor(), 'entregado')
        self.conf.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.conf.estado, 'en_proceso')
        self.assertIn(
            'No tenés permiso para marcar esto como entregado.',
            list(resp.context['form'].non_field_errors()),
        )

    def test_vendedor_no_cambia_estado_a_pendiente_por_falta_de_permiso(self):
        resp = self._post(make_vendedor(), 'pendiente')
        self.conf.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.conf.estado, 'en_proceso')
        self.assertIn(
            'No tenés permiso para cambiar el estado de esto.',
            list(resp.context['form'].non_field_errors()),
        )

    def test_vendedor_si_edita_otros_campos_sin_tocar_el_estado(self):
        """Triangulación: no es un rechazo generalizado; sin cambio de estado
        el Vendedor edita normalmente."""
        resp = self._post(make_vendedor(), 'en_proceso', color='Azul')
        self.conf.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual((self.conf.estado, self.conf.color), ('en_proceso', 'Azul'))

    def test_admin_pasa_en_proceso_a_pendiente(self):
        resp = self._post(make_administrador(), 'pendiente')
        self.conf.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.conf.estado, 'pendiente')

    def test_admin_marca_entregado_con_saldo_cero_sin_turno_propio(self):
        resp = self._post(make_administrador(), 'entregado')
        self.conf.refresh_from_db()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.conf.estado, 'entregado')
        self.assertEqual(
            CajaMovimiento.objects.filter(referencia_confeccion=self.conf, concepto='confeccion_saldo').count(),
            0, 'saldo 0: no hay saldo final que cobrar',
        )
