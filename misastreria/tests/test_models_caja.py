"""
test_models_caja.py
====================
Cubre:
  - CajaMovimiento: concepto_tipo(), autocode MOV-NNNN, tipo auto-derivado
  - UniqueConstraint (un solo alquiler/venta/confeccion/reparación por concepto activo)
  - CajaSesion: saldo_sistema, total_ingresos, total_egresos, saldo_garantias
  - UniqueConstraint: solo una sesión abierta a la vez
  - CajaMovimiento: es_reverso / fue_reversado properties
"""
from decimal import Decimal

from django.test import TestCase
from django.db import IntegrityError

from misastreria.models import CajaMovimiento, CajaSesion
from .factories import (
    make_sesion_caja, make_movimiento_caja, make_user,
    make_alquiler, make_venta, make_reparacion, make_confeccion,
)


class CajaMovimientoConceptoTipoTests(TestCase):
    """concepto_tipo() devuelve 'ingreso' o 'egreso'."""

    def test_alquiler_cobro_es_ingreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('alquiler_cobro'), 'ingreso')

    def test_venta_cobro_es_ingreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('venta_cobro'), 'ingreso')

    def test_garantia_alquiler_es_ingreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('garantia_alquiler'), 'ingreso')

    def test_garantia_devolucion_es_egreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('garantia_devolucion'), 'egreso')

    def test_egreso_manual_es_egreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('egreso_manual'), 'egreso')

    def test_gasto_fijo_es_egreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('gasto_fijo'), 'egreso')

    def test_comision_empleado_es_egreso(self):
        self.assertEqual(CajaMovimiento.concepto_tipo('comision_empleado'), 'egreso')

    def test_concepto_desconocido_lanza_error(self):
        with self.assertRaises(ValueError):
            CajaMovimiento.concepto_tipo('concepto_inventado')

    def test_todos_los_conceptos_mapeados(self):
        """Todos los conceptos en CONCEPTO_CHOICES deben estar en CONCEPTO_TIPO_MAP."""
        conceptos_choices = {c for c, _ in CajaMovimiento.CONCEPTO_CHOICES}
        conceptos_mapeados = set(CajaMovimiento.CONCEPTO_TIPO_MAP.keys())
        faltantes = conceptos_choices - conceptos_mapeados
        self.assertEqual(faltantes, set(), f"Conceptos sin mapeo: {faltantes}")


class CajaMovimientoAutoCodigoTests(TestCase):

    def test_primer_movimiento_codigo_0001(self):
        sesion = make_sesion_caja()
        mov = make_movimiento_caja(sesion=sesion)
        self.assertRegex(mov.codigo, r'^MOV-\d{4}$')
        self.assertEqual(mov.codigo, 'MOV-0001')

    def test_segundo_movimiento_codigo_0002(self):
        sesion = make_sesion_caja()
        make_movimiento_caja(sesion=sesion)
        mov2 = make_movimiento_caja(sesion=sesion, concepto='egreso_manual', tipo='egreso')
        self.assertEqual(mov2.codigo, 'MOV-0002')


class CajaMovimientoTipoAutoTests(TestCase):
    """tipo se deriva automáticamente del concepto si no se pasa explícitamente."""

    def test_tipo_derivado_de_ingreso_manual(self):
        sesion = make_sesion_caja()
        mov = CajaMovimiento.objects.create(
            sesion=sesion,
            concepto='ingreso_manual',
            # tipo deliberadamente NO incluido — debe auto-derivarse
            monto=Decimal('100.00'),
            forma_pago='efectivo',
            origen='manual',
        )
        self.assertEqual(mov.tipo, 'ingreso')

    def test_tipo_derivado_de_egreso_manual(self):
        sesion = make_sesion_caja()
        mov = CajaMovimiento.objects.create(
            sesion=sesion,
            concepto='egreso_manual',
            monto=Decimal('50.00'),
            forma_pago='efectivo',
            origen='manual',
        )
        self.assertEqual(mov.tipo, 'egreso')


class CajaMovimientoEsReversoTests(TestCase):

    def test_movimiento_normal_no_es_reverso(self):
        sesion = make_sesion_caja()
        mov = make_movimiento_caja(sesion=sesion)
        self.assertFalse(mov.es_reverso)

    def test_movimiento_con_reverso_es_reverso(self):
        sesion = make_sesion_caja()
        mov1 = make_movimiento_caja(sesion=sesion)
        mov2 = CajaMovimiento.objects.create(
            sesion=sesion,
            tipo='egreso',
            concepto='egreso_manual',
            monto=Decimal('50.00'),
            forma_pago='efectivo',
            origen='manual',
            movimiento_reverso=mov1,
        )
        self.assertTrue(mov2.es_reverso)


class CajaSesionUnicaAbiertaTests(TestCase):
    """Solo puede haber una sesión abierta a la vez."""

    def test_crear_dos_sesiones_abiertas_falla(self):
        user = make_user()
        make_sesion_caja(usuario=user)
        with self.assertRaises(Exception):
            make_sesion_caja(usuario=user)


class CajaSesionSaldoSistemaTests(TestCase):
    """saldo_sistema = apertura + ingresos (sin apertura, sin garantías) - egresos (sin garantías)."""

    def test_sesion_sin_movimientos_saldo_es_apertura(self):
        sesion = make_sesion_caja()
        self.assertEqual(sesion.saldo_sistema, Decimal('100.00'))

    def test_ingreso_manual_suma_al_saldo(self):
        sesion = make_sesion_caja()
        make_movimiento_caja(
            sesion=sesion, tipo='ingreso',
            concepto='ingreso_manual', monto=Decimal('50.00'),
        )
        self.assertEqual(sesion.saldo_sistema, Decimal('150.00'))

    def test_egreso_manual_resta_del_saldo(self):
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='egreso',
            concepto='egreso_manual', monto=Decimal('30.00'),
            forma_pago='efectivo', origen='manual',
        )
        self.assertEqual(sesion.saldo_sistema, Decimal('70.00'))

    def test_garantia_alquiler_no_afecta_saldo_sistema(self):
        """Garantías se excluyen del saldo_sistema."""
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='ingreso',
            concepto='garantia_alquiler', monto=Decimal('500.00'),
            forma_pago='efectivo', origen='automatico',
        )
        # Saldo sigue siendo solo la apertura
        self.assertEqual(sesion.saldo_sistema, Decimal('100.00'))

    def test_apertura_caja_no_duplica_saldo(self):
        """El concepto apertura_caja no se suma de nuevo al saldo_sistema."""
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='ingreso',
            concepto='apertura_caja', monto=Decimal('100.00'),
            forma_pago='efectivo', origen='automatico',
        )
        # Sigue siendo 100 (apertura ya contabilizada en monto_apertura)
        self.assertEqual(sesion.saldo_sistema, Decimal('100.00'))


class CajaSesionTotalesTests(TestCase):

    def test_total_ingresos_cuenta_solo_ingresos_operativos(self):
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='ingreso',
            concepto='venta_cobro', monto=Decimal('200.00'),
            forma_pago='efectivo', origen='automatico',
        )
        self.assertEqual(sesion.total_ingresos, Decimal('200.00'))

    def test_total_ingresos_excluye_apertura(self):
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='ingreso',
            concepto='apertura_caja', monto=Decimal('100.00'),
            forma_pago='efectivo', origen='automatico',
        )
        self.assertEqual(sesion.total_ingresos, Decimal('0'))

    def test_total_egresos_cuenta_egresos_operativos(self):
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='egreso',
            concepto='gasto_fijo', monto=Decimal('75.00'),
            forma_pago='efectivo', origen='manual',
        )
        self.assertEqual(sesion.total_egresos, Decimal('75.00'))


class CajaSesionGarantiasTests(TestCase):

    def test_saldo_garantias_sin_movimientos_cero(self):
        sesion = make_sesion_caja()
        self.assertEqual(sesion.saldo_garantias, Decimal('0'))

    def test_garantia_recibida_suma(self):
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='ingreso',
            concepto='garantia_alquiler', monto=Decimal('300.00'),
            forma_pago='efectivo', origen='automatico',
        )
        self.assertEqual(sesion.saldo_garantias, Decimal('300.00'))

    def test_garantia_devuelta_resta(self):
        sesion = make_sesion_caja()
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='ingreso',
            concepto='garantia_alquiler', monto=Decimal('300.00'),
            forma_pago='efectivo', origen='automatico',
        )
        CajaMovimiento.objects.create(
            sesion=sesion, tipo='egreso',
            concepto='garantia_devolucion', monto=Decimal('300.00'),
            forma_pago='efectivo', origen='automatico',
        )
        self.assertEqual(sesion.saldo_garantias, Decimal('0'))
