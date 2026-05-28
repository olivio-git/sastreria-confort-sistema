"""
test_models_insumos.py
=======================
Cubre:
  - Insumo: autocode INS-NNN, __str__ con distintas combinaciones
  - Transaccion: autocode TXN-NNN, clean() validations
  - OrdenProduccion: autocode PROD-NNN, avanzar estado
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.core.exceptions import ValidationError

from misastreria.models import Insumo, Transaccion, OrdenProduccion
from .factories import make_empleado, make_confeccion


class InsumoAutoCodigoTests(TestCase):

    def test_primer_insumo_codigo_001(self):
        ins = Insumo.objects.create(articulo='Tela Azul')
        self.assertRegex(ins.codigo, r'^INS-\d{3}$')
        self.assertEqual(ins.codigo, 'INS-001')

    def test_segundo_insumo_codigo_002(self):
        Insumo.objects.create(articulo='Tela Negra')
        ins2 = Insumo.objects.create(articulo='Botones')
        self.assertEqual(ins2.codigo, 'INS-002')

    def test_codigo_no_cambia_al_editar(self):
        ins = Insumo.objects.create(articulo='Hilo')
        original = ins.codigo
        ins.notas = 'stock bajo'
        ins.save()
        self.assertEqual(ins.codigo, original)


class InsumoStrTests(TestCase):
    """__str__ usa distintos campos según los que estén definidos."""

    def test_str_con_coleccion_y_color(self):
        ins = Insumo.objects.create(
            articulo='Tela', coleccion='Verano 2025', color='Azul'
        )
        s = str(ins)
        self.assertIn('Verano 2025', s)
        self.assertIn('Azul', s)

    def test_str_con_codigo_referencia(self):
        ins = Insumo.objects.create(articulo='Botón', codigo_referencia='BTN-99')
        s = str(ins)
        self.assertIn('BTN-99', s)

    def test_str_fallback_articulo(self):
        ins = Insumo.objects.create(articulo='Hilo')
        self.assertEqual(str(ins), 'Hilo')

    def test_str_con_tipo_tela_y_color(self):
        ins = Insumo.objects.create(articulo='Tela', tipo_tela='Seda', color='Rojo')
        s = str(ins)
        self.assertIn('Seda', s)
        self.assertIn('Rojo', s)


class TransaccionValidacionTests(TestCase):
    """Transaccion.clean() rechaza descripción vacía, cantidad y monto <=0."""

    def _make_txn(**kwargs):
        return Transaccion(**{
            'tipo_transaccion': 'ingreso',
            'descripcion': 'Test',
            'tipo_servicio': 'otros',
            'fecha': date.today(),
            'cantidad': 1,
            'monto': Decimal('10.00'),
            **kwargs
        })

    def test_transaccion_valida_se_guarda(self):
        txn = Transaccion.objects.create(
            tipo_transaccion='ingreso',
            descripcion='Venta de tela',
            tipo_servicio='otros',
            cantidad=1,
            monto=Decimal('50.00'),
        )
        self.assertRegex(txn.codigo, r'^TXN-\d{3}$')

    def test_descripcion_vacia_lanza_error(self):
        with self.assertRaises(ValidationError):
            txn = Transaccion(
                tipo_transaccion='ingreso',
                descripcion='',
                tipo_servicio='otros',
                cantidad=1,
                monto=Decimal('50.00'),
            )
            txn.full_clean()

    def test_cantidad_cero_lanza_error(self):
        with self.assertRaises(ValidationError):
            txn = Transaccion(
                tipo_transaccion='ingreso',
                descripcion='Test',
                tipo_servicio='otros',
                cantidad=0,
                monto=Decimal('10.00'),
            )
            txn.full_clean()

    def test_monto_cero_lanza_error(self):
        with self.assertRaises(ValidationError):
            Transaccion.objects.create(
                tipo_transaccion='ingreso',
                descripcion='Test',
                tipo_servicio='otros',
                cantidad=1,
                monto=Decimal('0'),
            )

    def test_autocode_txn_001(self):
        txn = Transaccion.objects.create(
            tipo_transaccion='gasto',
            descripcion='Gastos varios',
            tipo_servicio='caja_chica',
            cantidad=2,
            monto=Decimal('30.00'),
        )
        self.assertEqual(txn.codigo, 'TXN-001')


class OrdenProduccionAutoCodigoTests(TestCase):

    def test_primera_orden_codigo_001(self):
        emp = make_empleado()
        op = OrdenProduccion.objects.create(
            descripcion='Cortar tela azul',
            tipo='stock',
        )
        self.assertRegex(op.codigo, r'^PROD-\d{3}$')

    def test_estado_default_corte(self):
        op = OrdenProduccion.objects.create(descripcion='Test', tipo='stock')
        self.assertEqual(op.estado, 'corte')

    def test_avanzar_de_corte_a_costura(self):
        op = OrdenProduccion.objects.create(descripcion='Test', tipo='stock')
        siguiente = OrdenProduccion.ESTADO_SIGUIENTE.get(op.estado)
        op.estado = siguiente
        op.save()
        self.assertEqual(op.estado, 'costura')

    def test_avanzar_de_costura_a_terminado(self):
        op = OrdenProduccion.objects.create(descripcion='Test', tipo='stock', estado='costura')
        siguiente = OrdenProduccion.ESTADO_SIGUIENTE.get(op.estado)
        op.estado = siguiente
        op.save()
        self.assertEqual(op.estado, 'terminado')

    def test_terminado_no_tiene_estado_siguiente(self):
        op = OrdenProduccion.objects.create(descripcion='Test', tipo='stock', estado='terminado')
        self.assertIsNone(OrdenProduccion.ESTADO_SIGUIENTE.get(op.estado))
