"""
test_caja_signals.py
=====================
Cubre el módulo de caja_signals — el corazón del flujo de pagos.
Prueba escenarios reales, edge cases y comportamientos a romper.

Módulos probados:
  - registrar_alquiler_en_caja (adelanto)
  - registrar_garantia_alquiler_en_caja
  - registrar_pago_alquiler (pagos parciales)
  - registrar_venta_en_caja
  - registrar_reparacion_en_caja
  - registrar_pago_reparacion / registrar_pago_confeccion
  - _calcular_pagado_alquiler / reparacion / confeccion
  - _reversar_movimientos_activos (al eliminar)
  - UniqueConstraints: segundo cobro mismo servicio
"""
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from django.db import IntegrityError

from misastreria.caja_signals import (
    registrar_alquiler_en_caja,
    registrar_garantia_alquiler_en_caja,
    registrar_pago_alquiler,
    registrar_reparacion_en_caja,
    registrar_pago_reparacion,
    registrar_pago_confeccion,
    registrar_venta_en_caja,
    registrar_pago_venta,
    _calcular_pagado_alquiler,
    _calcular_pagado_reparacion,
    _calcular_pagado_confeccion,
    _calcular_pagado_venta,
    _ajustar_total_en_caja,
    _reversar_movimientos_activos,
)
from misastreria.models import CajaMovimiento, Alquiler, Reparacion, Confeccion, Venta
from .factories import (
    make_user, make_alquiler, make_alquiler_item, make_prenda_item,
    make_reparacion, make_reparacion_item,
    make_confeccion, make_venta, make_prenda,
    make_sesion_caja, make_cliente, make_empleado,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de test
# ─────────────────────────────────────────────────────────────────────────────

def _movs_activos(alquiler=None, reparacion=None, confeccion=None, venta=None, concepto=None):
    """Devuelve movimientos activos (no reversados) para una referencia dada."""
    qs = CajaMovimiento.objects.filter(movimiento_reverso__isnull=True)
    if alquiler:
        qs = qs.filter(referencia_alquiler=alquiler)
    if reparacion:
        qs = qs.filter(referencia_reparacion=reparacion)
    if confeccion:
        qs = qs.filter(referencia_confeccion=confeccion)
    if venta:
        qs = qs.filter(referencia_venta=venta)
    if concepto:
        qs = qs.filter(concepto=concepto)
    return qs


# ─────────────────────────────────────────────────────────────────────────────
# Alquiler — cobro inicial
# ─────────────────────────────────────────────────────────────────────────────

class RegistrarAlquilerEnCajaTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()
        self.alquiler = make_alquiler(total=Decimal('300.00'))

    def test_adelanto_cero_no_crea_movimiento(self):
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('0'))
        self.assertEqual(
            _movs_activos(alquiler=self.alquiler, concepto='alquiler_cobro').count(), 0
        )

    def test_adelanto_positivo_crea_movimiento(self):
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('150.00'))
        movs = _movs_activos(alquiler=self.alquiler, concepto='alquiler_cobro')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('150.00'))
        self.assertEqual(movs.first().tipo, 'ingreso')

    def test_idempotente_no_crea_duplicado(self):
        """Llamar dos veces con mismo alquiler no duplica el movimiento."""
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('100.00'))
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('100.00'))
        self.assertEqual(
            _movs_activos(alquiler=self.alquiler, concepto='alquiler_cobro').count(), 1
        )

    def test_adelanto_negativo_no_crea_movimiento(self):
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('-50.00'))
        self.assertEqual(
            _movs_activos(alquiler=self.alquiler, concepto='alquiler_cobro').count(), 0
        )

    def test_sin_sesion_abierta_crea_movimiento_sin_sesion(self):
        """Sin sesión activa, el movimiento se crea con sesion=None."""
        self.sesion.estado = 'cerrada'
        self.sesion.save()
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('50.00'))
        mov = _movs_activos(alquiler=self.alquiler, concepto='alquiler_cobro').first()
        self.assertIsNotNone(mov)
        self.assertIsNone(mov.sesion)


# ─────────────────────────────────────────────────────────────────────────────
# Alquiler — garantías
# ─────────────────────────────────────────────────────────────────────────────

class RegistrarGarantiaAlquilerTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()

    def test_garantia_efectivo_crea_movimiento(self):
        alquiler = make_alquiler(
            garantia_tipo='efectivo',
            garantia_monto=Decimal('500.00'),
        )
        registrar_garantia_alquiler_en_caja(alquiler)
        movs = _movs_activos(alquiler=alquiler, concepto='garantia_alquiler')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('500.00'))
        self.assertEqual(movs.first().tipo, 'ingreso')

    def test_garantia_descripcion_no_crea_movimiento(self):
        """Garantía tipo 'descripcion' no es monetaria — no crea movimiento."""
        alquiler = make_alquiler(
            garantia_tipo='descripcion',
            garantia_monto=Decimal('500.00'),
            garantia='Presenta DNI',
        )
        registrar_garantia_alquiler_en_caja(alquiler)
        self.assertEqual(
            _movs_activos(alquiler=alquiler, concepto='garantia_alquiler').count(), 0
        )

    def test_garantia_tipo_vacio_no_crea_movimiento(self):
        alquiler = make_alquiler(garantia_tipo='', garantia_monto=None)
        registrar_garantia_alquiler_en_caja(alquiler)
        self.assertEqual(
            _movs_activos(alquiler=alquiler, concepto='garantia_alquiler').count(), 0
        )

    def test_garantia_monto_cero_no_crea_movimiento(self):
        alquiler = make_alquiler(
            garantia_tipo='efectivo',
            garantia_monto=Decimal('0'),
        )
        registrar_garantia_alquiler_en_caja(alquiler)
        self.assertEqual(
            _movs_activos(alquiler=alquiler, concepto='garantia_alquiler').count(), 0
        )

    def test_idempotente_garantia(self):
        alquiler = make_alquiler(
            garantia_tipo='qr',
            garantia_monto=Decimal('200.00'),
        )
        registrar_garantia_alquiler_en_caja(alquiler)
        registrar_garantia_alquiler_en_caja(alquiler)  # segunda llamada
        self.assertEqual(
            _movs_activos(alquiler=alquiler, concepto='garantia_alquiler').count(), 1
        )


# ─────────────────────────────────────────────────────────────────────────────
# Alquiler — pagos parciales
# ─────────────────────────────────────────────────────────────────────────────

class PagosAlquilerTests(TestCase):

    def setUp(self):
        # Create user first, then pass to make_sesion_caja to avoid duplicate username
        self.user = make_user(username='cajero_alq')
        self.sesion = make_sesion_caja(usuario=self.user)
        self.alquiler = make_alquiler(total=Decimal('400.00'))

    def test_pago_parcial_crea_movimiento(self):
        registrar_pago_alquiler(
            self.alquiler, Decimal('100.00'), 'efectivo', 'Primer pago', self.user
        )
        movs = _movs_activos(alquiler=self.alquiler, concepto='alquiler_pago')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('100.00'))

    def test_multiples_pagos_parciales_se_acumulan(self):
        """Pueden haber múltiples pagos del mismo alquiler."""
        registrar_pago_alquiler(self.alquiler, Decimal('100'), 'efectivo', 'P1', self.user)
        registrar_pago_alquiler(self.alquiler, Decimal('150'), 'qr', 'P2', self.user)
        registrar_pago_alquiler(self.alquiler, Decimal('150'), 'transferencia', 'P3', self.user)
        movs = _movs_activos(alquiler=self.alquiler, concepto='alquiler_pago')
        self.assertEqual(movs.count(), 3)

    def test_calcular_pagado_alquiler_suma_correcta(self):
        registrar_alquiler_en_caja(self.alquiler, adelanto=Decimal('200.00'))
        registrar_pago_alquiler(self.alquiler, Decimal('100'), 'efectivo', 'P2', self.user)
        total_pagado = _calcular_pagado_alquiler(self.alquiler)
        self.assertEqual(total_pagado, Decimal('300.00'))

    def test_calcular_pagado_excluye_garantias(self):
        """Las garantías no cuentan como pago del servicio."""
        registrar_garantia_alquiler_en_caja(
            make_alquiler(
                garantia_tipo='efectivo',
                garantia_monto=Decimal('500.00'),
            )
        )
        # El alquiler de test no tiene garantía
        registrar_pago_alquiler(self.alquiler, Decimal('200'), 'efectivo', 'Pago', self.user)
        total_pagado = _calcular_pagado_alquiler(self.alquiler)
        self.assertEqual(total_pagado, Decimal('200.00'))  # Solo el pago, no la garantía ajena

    def test_pago_monto_cero_no_crea_movimiento(self):
        registrar_pago_alquiler(self.alquiler, Decimal('0'), 'efectivo', 'Zero', self.user)
        self.assertEqual(
            _movs_activos(alquiler=self.alquiler, concepto='alquiler_pago').count(), 0
        )

    def test_pago_sobrepasa_total_no_falla(self):
        """El sistema permite pagar más del total — no es un error técnico."""
        registrar_pago_alquiler(self.alquiler, Decimal('999.00'), 'efectivo', 'Overpago', self.user)
        total_pagado = _calcular_pagado_alquiler(self.alquiler)
        self.assertEqual(total_pagado, Decimal('999.00'))


# ─────────────────────────────────────────────────────────────────────────────
# Reparacion — flujo completo
# ─────────────────────────────────────────────────────────────────────────────

class PagosReparacionTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()
        self.user = make_user(username='cajero_rep')
        self.rep = make_reparacion(total=Decimal('150.00'))

    def test_reparacion_no_entregada_no_registra(self):
        self.rep.estado = 'pendiente'
        self.rep.save()
        registrar_reparacion_en_caja(self.rep)
        self.assertEqual(
            _movs_activos(reparacion=self.rep, concepto='reparacion_cobro').count(), 0
        )

    def test_reparacion_entregada_registra_cobro(self):
        self.rep.estado = 'entregado'
        self.rep.save()
        registrar_reparacion_en_caja(self.rep)
        movs = _movs_activos(reparacion=self.rep, concepto='reparacion_cobro')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('150.00'))

    def test_reparacion_entregada_total_cero_no_registra(self):
        rep = make_reparacion(total=Decimal('0'), estado='entregado')
        rep.save()
        registrar_reparacion_en_caja(rep)
        self.assertEqual(
            _movs_activos(reparacion=rep, concepto='reparacion_cobro').count(), 0
        )

    def test_idempotente_reparacion_cobro(self):
        self.rep.estado = 'entregado'
        self.rep.save()
        registrar_reparacion_en_caja(self.rep)
        registrar_reparacion_en_caja(self.rep)
        self.assertEqual(
            _movs_activos(reparacion=self.rep, concepto='reparacion_cobro').count(), 1
        )

    def test_pago_parcial_reparacion(self):
        registrar_pago_reparacion(
            self.rep, Decimal('50.00'), 'efectivo', 'Primer pago rep', self.user
        )
        movs = _movs_activos(reparacion=self.rep, concepto='reparacion_pago')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('50.00'))

    def test_multiples_pagos_reparacion(self):
        """reparacion_pago permite múltiples movimientos (no tiene UniqueConstraint)."""
        registrar_pago_reparacion(self.rep, Decimal('50'), 'efectivo', 'P1', self.user)
        registrar_pago_reparacion(self.rep, Decimal('50'), 'qr', 'P2', self.user)
        registrar_pago_reparacion(self.rep, Decimal('50'), 'efectivo', 'P3', self.user)
        movs = _movs_activos(reparacion=self.rep, concepto='reparacion_pago')
        self.assertEqual(movs.count(), 3)

    def test_calcular_pagado_reparacion_suma_cobro_y_pagos(self):
        # Use update() to bypass reparacion_to_caja signal (which would create reparacion_saldo),
        # so only registrar_reparacion_en_caja runs — avoiding double-counting.
        from misastreria.models import Reparacion as _Rep
        _Rep.objects.filter(pk=self.rep.pk).update(estado='entregado')
        self.rep.refresh_from_db()
        registrar_reparacion_en_caja(self.rep)   # creates reparacion_cobro=150
        registrar_pago_reparacion(self.rep, Decimal('50'), 'efectivo', 'P2', self.user)
        # cobro=150 + pago=50 = 200
        total = _calcular_pagado_reparacion(self.rep)
        self.assertEqual(total, Decimal('200.00'))

    def test_saldo_pendiente_reparacion_con_cobro(self):
        self.rep.estado = 'entregado'
        self.rep.save()
        registrar_reparacion_en_caja(self.rep)
        # total=150, pagado=150 → saldo=0
        self.assertEqual(self.rep.saldo_pendiente, Decimal('0'))

    def test_saldo_pendiente_reparacion_sin_cobro(self):
        # total=150, pagado=0 → saldo=150
        self.assertEqual(self.rep.saldo_pendiente, Decimal('150.00'))


# ─────────────────────────────────────────────────────────────────────────────
# Confeccion — flujo
# ─────────────────────────────────────────────────────────────────────────────

class PagosConfeccionTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()
        self.user = make_user(username='cajero_conf')
        self.conf = make_confeccion(precio=Decimal('600.00'), adelanto=Decimal('0'))

    def test_pago_confeccion_crea_movimiento(self):
        registrar_pago_confeccion(
            self.conf, Decimal('200.00'), 'efectivo', 'Adelanto', self.user
        )
        movs = _movs_activos(confeccion=self.conf, concepto='confeccion_pago')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('200.00'))

    def test_multiples_pagos_confeccion(self):
        registrar_pago_confeccion(self.conf, Decimal('200'), 'efectivo', 'P1', self.user)
        registrar_pago_confeccion(self.conf, Decimal('200'), 'qr', 'P2', self.user)
        registrar_pago_confeccion(self.conf, Decimal('200'), 'efectivo', 'P3', self.user)
        movs = _movs_activos(confeccion=self.conf, concepto='confeccion_pago')
        self.assertEqual(movs.count(), 3)

    def test_calcular_pagado_confeccion(self):
        registrar_pago_confeccion(self.conf, Decimal('300'), 'efectivo', 'P1', self.user)
        registrar_pago_confeccion(self.conf, Decimal('100'), 'qr', 'P2', self.user)
        self.assertEqual(_calcular_pagado_confeccion(self.conf), Decimal('400.00'))

    def test_saldo_pendiente_con_pagos(self):
        registrar_pago_confeccion(self.conf, Decimal('600'), 'efectivo', 'Pago total', self.user)
        self.assertEqual(self.conf.saldo_pendiente, Decimal('0'))

    def test_saldo_pendiente_sin_pagos(self):
        self.assertEqual(self.conf.saldo_pendiente, Decimal('600.00'))


# ─────────────────────────────────────────────────────────────────────────────
# Venta
# ─────────────────────────────────────────────────────────────────────────────

class RegistrarVentaEnCajaTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()
        self.venta = make_venta()
        # Agregar item para que tenga total > 0
        from misastreria.models import VentaItem
        pi = make_prenda_item()
        VentaItem.objects.create(
            venta=self.venta,
            prenda_item=pi,
            precio_unitario=Decimal('200.00'),
            precio_reparacion=Decimal('0'),
        )
        self.venta.recalcular_totales()

    def test_venta_sin_sesion_crea_mov_con_sesion_none(self):
        """Sin sesión abierta, registrar_venta_en_caja crea movimiento con sesion=None.
        El sistema no bloquea cobros fuera de sesión — permite registrarlos y asignarlos
        manualmente a una sesión posterior.
        """
        self.sesion.estado = 'cerrada'
        self.sesion.save()
        registrar_venta_en_caja(self.venta)
        mov = _movs_activos(venta=self.venta, concepto='venta_cobro').first()
        self.assertIsNotNone(mov)
        self.assertIsNone(mov.sesion)

    def test_venta_con_sesion_crea_mov(self):
        registrar_venta_en_caja(self.venta)
        movs = _movs_activos(venta=self.venta, concepto='venta_cobro')
        self.assertEqual(movs.count(), 1)
        self.assertEqual(movs.first().monto, Decimal('200.00'))

    def test_idempotente_venta(self):
        registrar_venta_en_caja(self.venta)
        registrar_venta_en_caja(self.venta)
        self.assertEqual(
            _movs_activos(venta=self.venta, concepto='venta_cobro').count(), 1
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reversar movimientos
# ─────────────────────────────────────────────────────────────────────────────

class ReversarMovimientosTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()
        self.user = make_user(username='supervisor')

    def test_reversar_alquiler_crea_movimiento_reverso(self):
        alquiler = make_alquiler(total=Decimal('200.00'))
        registrar_alquiler_en_caja(alquiler, adelanto=Decimal('200.00'))
        mov = _movs_activos(alquiler=alquiler, concepto='alquiler_cobro').first()
        self.assertIsNotNone(mov)

        _reversar_movimientos_activos(
            referencia_field='referencia_alquiler',
            instance=alquiler,
            usuario=self.user,
        )
        mov.refresh_from_db()
        # El movimiento original ahora debe tener un reverso
        self.assertIsNotNone(mov.movimiento_reverso)

    def test_reversar_alquiler_crea_egreso(self):
        alquiler = make_alquiler(total=Decimal('300.00'))
        registrar_alquiler_en_caja(alquiler, adelanto=Decimal('300.00'))
        _reversar_movimientos_activos(
            referencia_field='referencia_alquiler',
            instance=alquiler,
            usuario=self.user,
        )
        # Debe existir un movimiento de tipo egreso (anulacion_cobro)
        reversados = CajaMovimiento.objects.filter(
            referencia_alquiler=alquiler,
            concepto='anulacion_cobro',
        )
        self.assertEqual(reversados.count(), 1)
        self.assertEqual(reversados.first().tipo, 'egreso')

    def test_reversar_dos_veces_no_duplica(self):
        alquiler = make_alquiler(total=Decimal('200.00'))
        registrar_alquiler_en_caja(alquiler, adelanto=Decimal('200.00'))
        _reversar_movimientos_activos(
            referencia_field='referencia_alquiler', instance=alquiler
        )
        _reversar_movimientos_activos(
            referencia_field='referencia_alquiler', instance=alquiler
        )
        reversados = CajaMovimiento.objects.filter(
            referencia_alquiler=alquiler, concepto='anulacion_cobro'
        )
        self.assertEqual(reversados.count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# UniqueConstraints — intentar romper con datos duplicados
# ─────────────────────────────────────────────────────────────────────────────

class UniqueConstraintsCajaTests(TestCase):

    def setUp(self):
        self.sesion = make_sesion_caja()

    def test_no_puede_haber_dos_venta_cobro_activos(self):
        """Un venta_cobro activo por venta — el segundo debe fallar con UniqueConstraint."""
        venta = make_venta()
        # First venta_cobro — must succeed
        CajaMovimiento.objects.create(
            sesion=self.sesion,
            tipo='ingreso',
            concepto='venta_cobro',
            monto=Decimal('100.00'),
            forma_pago='efectivo',
            origen='automatico',
            referencia_venta=venta,
        )
        # Second venta_cobro for same venta — must fail (DB UniqueConstraint)
        with self.assertRaises(Exception):
            CajaMovimiento.objects.create(
                sesion=self.sesion,
                tipo='ingreso',
                concepto='venta_cobro',
                monto=Decimal('100.00'),
                forma_pago='efectivo',
                origen='automatico',
                referencia_venta=venta,
            )

    def test_garantia_alquiler_duplicada_falla(self):
        """No puede haber dos garantia_alquiler activos para el mismo alquiler."""
        alquiler = make_alquiler(
            garantia_tipo='efectivo', garantia_monto=Decimal('300.00')
        )
        registrar_garantia_alquiler_en_caja(alquiler)
        with self.assertRaises(Exception):
            CajaMovimiento.objects.create(
                sesion=self.sesion,
                tipo='ingreso',
                concepto='garantia_alquiler',
                monto=Decimal('300.00'),
                forma_pago='efectivo',
                origen='automatico',
                referencia_alquiler=alquiler,
            )


# ─────────────────────────────────────────────────────────────────────────────
# _ajustar_total_en_caja — reconcilia caja al editar el total de un servicio
# ─────────────────────────────────────────────────────────────────────────────

class AjustarTotalEnCajaTests(TestCase):
    """Editar el total NO mueve dinero; sólo devuelve el exceso si el nuevo
    total queda por debajo de lo realmente pagado."""

    def setUp(self):
        self.sesion = make_sesion_caja()

    def _venta_en_proceso(self, total):
        """Venta sin cobro automático: se crea con total 0 (el signal no cobra)
        y luego se le fija el total, replicando una venta en proceso sin pagos."""
        venta = make_venta(total=Decimal('0'))
        venta.total = Decimal(str(total))
        venta.save(update_fields=['total'])
        return venta

    def _ajustar(self, venta, nuevo_total):
        _ajustar_total_en_caja(
            referencia_field='referencia_venta',
            instance=venta,
            concepto_cobro='venta_ajuste',
            nuevo_total=Decimal(str(nuevo_total)),
            old_total=venta.total,
            forma_pago='efectivo',
            cliente=getattr(venta, 'cliente', None),
        )

    def test_bajar_total_sin_pagos_no_crea_egreso(self):
        """Bug reportado: venta en proceso sin pagos, bajar el precio NO debe
        generar un egreso de anulación fantasma."""
        venta = self._venta_en_proceso('230.00')
        self._ajustar(venta, Decimal('220.00'))
        self.assertEqual(_movs_activos(venta=venta).count(), 0)
        self.assertEqual(_calcular_pagado_venta(venta), Decimal('0'))

    def test_subir_total_sin_pagos_no_crea_ingreso(self):
        """Subir el total tampoco inventa un ingreso: el cliente no pagó nada."""
        venta = self._venta_en_proceso('200.00')
        self._ajustar(venta, Decimal('300.00'))
        self.assertEqual(_movs_activos(venta=venta).count(), 0)

    def test_bajar_total_con_pago_parcial_sobre_saldo_no_devuelve(self):
        """Pago parcial 100, total 230→180: sigue habiendo saldo (80), no se
        devuelve nada."""
        venta = self._venta_en_proceso('230.00')
        registrar_pago_venta(venta, Decimal('100.00'), 'efectivo', None, None)
        self._ajustar(venta, Decimal('180.00'))
        self.assertEqual(
            _movs_activos(venta=venta, concepto='anulacion_cobro').count(), 0
        )
        self.assertEqual(_calcular_pagado_venta(venta), Decimal('100.00'))

    def test_bajar_total_por_debajo_de_lo_pagado_devuelve_exceso(self):
        """Pago parcial 100, total 230→80: el cliente sobrepagó 20, se devuelve."""
        venta = self._venta_en_proceso('230.00')
        registrar_pago_venta(venta, Decimal('100.00'), 'efectivo', None, None)
        self._ajustar(venta, Decimal('80.00'))
        anul = _movs_activos(venta=venta, concepto='anulacion_cobro')
        self.assertEqual(anul.count(), 1)
        self.assertEqual(anul.first().monto, Decimal('20.00'))
        self.assertEqual(anul.first().tipo, 'egreso')
        self.assertEqual(_calcular_pagado_venta(venta), Decimal('80.00'))

    def test_ajustar_dos_veces_es_idempotente(self):
        """Reejecutar el ajuste con el mismo total no acumula devoluciones."""
        venta = self._venta_en_proceso('230.00')
        registrar_pago_venta(venta, Decimal('100.00'), 'efectivo', None, None)
        self._ajustar(venta, Decimal('80.00'))
        self._ajustar(venta, Decimal('80.00'))
        self.assertEqual(
            _movs_activos(venta=venta, concepto='anulacion_cobro').count(), 1
        )

    def test_reparacion_bajar_total_sin_pagos_no_crea_egreso(self):
        """La misma protección aplica a Reparación (comparte _ajustar_total_en_caja)."""
        rep = make_reparacion(total=Decimal('230.00'))
        _ajustar_total_en_caja(
            referencia_field='referencia_reparacion', instance=rep,
            concepto_cobro='reparacion_ajuste', nuevo_total=Decimal('220.00'),
            old_total=Decimal('230.00'), forma_pago='efectivo',
        )
        self.assertEqual(_movs_activos(reparacion=rep).count(), 0)

    def test_alquiler_bajar_total_sin_pagos_no_crea_egreso(self):
        """La misma protección aplica a Alquiler (comparte _ajustar_total_en_caja)."""
        alq = make_alquiler(total=Decimal('200.00'))
        _ajustar_total_en_caja(
            referencia_field='referencia_alquiler', instance=alq,
            concepto_cobro='alquiler_ajuste', nuevo_total=Decimal('150.00'),
            old_total=Decimal('200.00'), forma_pago='efectivo',
        )
        self.assertEqual(_movs_activos(alquiler=alq).count(), 0)

    def test_alquiler_garantia_no_cuenta_como_pago_al_ajustar(self):
        """La garantía NO debe contarse como pago: bajar el total de un alquiler
        con garantía registrada (pero sin cobro del alquiler) no debe devolver
        nada."""
        alq = make_alquiler(
            total=Decimal('200.00'),
            garantia_tipo='efectivo', garantia_monto=Decimal('300.00'),
        )
        registrar_garantia_alquiler_en_caja(alq)  # ingreso garantia 300
        _ajustar_total_en_caja(
            referencia_field='referencia_alquiler', instance=alq,
            concepto_cobro='alquiler_ajuste', nuevo_total=Decimal('150.00'),
            old_total=Decimal('200.00'), forma_pago='efectivo',
        )
        # No se devuelve nada: el alquiler no se pagó; la garantía es aparte.
        self.assertEqual(
            _movs_activos(alquiler=alq, concepto='anulacion_cobro').count(), 0
        )
        # La garantía sigue intacta.
        self.assertEqual(
            _movs_activos(alquiler=alq, concepto='garantia_alquiler').count(), 1
        )


# ─────────────────────────────────────────────────────────────────────────────
# pre_delete: borrar un servicio por cualquier vía reversa su caja (red de seguridad)
# ─────────────────────────────────────────────────────────────────────────────

class ServicioPreDeleteReversaTests(TestCase):
    """El signal pre_delete reversa los movimientos activos al borrar un servicio
    directamente (admin/shell/.delete()), sin pasar por la vista eliminar_*."""

    def setUp(self):
        self.sesion = make_sesion_caja()

    def test_delete_directo_venta_reversa_cobro(self):
        venta = make_venta(total=Decimal('300.00'))  # signal crea venta_cobro 300
        self.assertEqual(
            CajaMovimiento.objects.filter(
                concepto='venta_cobro', movimiento_reverso__isnull=True).count(), 1)
        venta.delete()  # pre_delete debe reversar
        # el cobro ya no está activo
        self.assertEqual(
            CajaMovimiento.objects.filter(
                concepto='venta_cobro', movimiento_reverso__isnull=True).count(), 0)
        # existe el reverso anulacion_cobro (egreso) activo
        self.assertEqual(
            CajaMovimiento.objects.filter(
                concepto='anulacion_cobro', tipo='egreso',
                movimiento_reverso__isnull=True).count(), 1)

    def test_delete_directo_alquiler_reversa_pago(self):
        alq = make_alquiler(total=Decimal('200.00'))
        registrar_pago_alquiler(alq, Decimal('100.00'), 'efectivo', 'cuota', None)
        self.assertEqual(
            CajaMovimiento.objects.filter(
                concepto='alquiler_pago', movimiento_reverso__isnull=True).count(), 1)
        alq.delete()
        self.assertEqual(
            CajaMovimiento.objects.filter(
                concepto='alquiler_pago', movimiento_reverso__isnull=True).count(), 0)
        self.assertEqual(
            CajaMovimiento.objects.filter(
                concepto='anulacion_cobro', tipo='egreso',
                movimiento_reverso__isnull=True).count(), 1)
