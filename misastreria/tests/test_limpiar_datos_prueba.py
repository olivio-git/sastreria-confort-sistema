"""El comando que borra los datos de prueba posteriores al corte.

Lo que se cuida acá es el alcance. El comando define qué borrar por NEGACIÓN
—«todo modelo que no empieza con H-»— y esa definición sólo vale después de
`cortar_inventario`. En una base sin corte significa «el inventario entero»,
así que el test más importante de este archivo es el que verifica que en ese
caso se niegue a correr.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from misastreria.models import (
    Corte, OrdenProduccion, OrdenProduccionEmpleado, PrendaInventario,
    PrendaItem, Venta, VentaItem,
)
from .factories import (
    cliente_y_empleado_de_mostrador, make_corte, make_empleado,
    make_orden_produccion, make_prenda, make_prenda_item, make_venta,
)


class LimpiarDatosPruebaTests(TestCase):
    def setUp(self):
        # Una prenda archivada: representa el inventario histórico, y es lo que
        # le dice al comando que el corte ya se aplicó.
        self.vieja = make_prenda(codigo='H-PRN-500', nombre='Saco histórico',
                                 estado='BAJ')
        self.item_viejo = make_prenda_item(self.vieja, codigo_item='H-PRN-500-ITM-01')

        # Y una nueva, de las que se cargaron probando.
        self.corte = make_corte()
        self.nueva = make_prenda(codigo='PRN-001', nombre='Saco de prueba')
        self.item_nuevo = make_prenda_item(self.nueva, codigo_item='PRN-001-ITM-01',
                                           tipo='venta', corte=self.corte)

    def _correr(self, *args):
        salida = StringIO()
        call_command('limpiar_datos_prueba', *args, stdout=salida, stderr=salida)
        return salida.getvalue()

    def _venta_de_prueba(self):
        cli, emp = cliente_y_empleado_de_mostrador()
        venta = make_venta(cliente=cli, empleado=emp)
        VentaItem.objects.create(venta=venta, prenda_item=self.item_nuevo,
                                 precio_unitario=Decimal('100'))
        return venta

    def test_sin_corte_previo_se_niega(self):
        """El caso que evita un desastre: sin corte, el alcance sería todo."""
        self.vieja.delete()
        with self.assertRaises(CommandError) as ctx:
            self._correr()
        self.assertIn('nunca se corrió', str(ctx.exception))
        self.assertTrue(PrendaInventario.objects.filter(codigo='PRN-001').exists(),
                        'no tenía que borrar nada')

    def test_el_simulacro_no_borra(self):
        salida = self._correr()
        self.assertIn('SIMULACRO', salida)
        self.assertTrue(PrendaInventario.objects.filter(codigo='PRN-001').exists())
        self.assertTrue(Corte.objects.exists())

    def test_confirmar_borra_lo_nuevo_y_respeta_lo_archivado(self):
        self._venta_de_prueba()
        self._correr('--confirmar')

        self.assertFalse(PrendaInventario.objects.filter(codigo='PRN-001').exists())
        self.assertFalse(PrendaItem.objects.filter(codigo_item='PRN-001-ITM-01').exists())
        self.assertFalse(Venta.objects.exists(), 'la venta de prueba tenía que irse')
        self.assertFalse(Corte.objects.exists())

        # Lo archivado no se toca: es la historia comercial de la sastrería.
        self.assertTrue(PrendaInventario.objects.filter(codigo='H-PRN-500').exists())
        self.assertTrue(PrendaItem.objects.filter(codigo_item='H-PRN-500-ITM-01').exists())

    def test_una_operacion_mezclada_frena_todo(self):
        """Una venta que toca inventario nuevo Y archivado es historia real."""
        venta = self._venta_de_prueba()
        VentaItem.objects.create(venta=venta, prenda_item=self.item_viejo,
                                 precio_unitario=Decimal('50'))

        with self.assertRaises(CommandError) as ctx:
            self._correr('--confirmar')
        self.assertIn('mezclan', str(ctx.exception))
        self.assertTrue(PrendaInventario.objects.filter(codigo='PRN-001').exists(),
                        'al frenar no tenía que haber borrado nada')

    def test_el_proximo_codigo_vuelve_a_prn_001(self):
        self._correr('--confirmar')
        self.assertEqual(PrendaInventario.siguiente_codigo(), 'PRN-001')

    def test_borra_las_ordenes_de_produccion_de_prueba(self):
        orden = make_orden_produccion(prenda_inventario=self.nueva,
                                      tipo='stock', cantidad=1)
        self._correr('--confirmar')
        self.assertFalse(OrdenProduccion.objects.filter(pk=orden.pk).exists())

    def test_una_orden_con_comision_frena_todo(self):
        """Una orden con empleados asignados devengó plata de alguien."""
        orden = make_orden_produccion(prenda_inventario=self.nueva,
                                      tipo='stock', cantidad=1)
        OrdenProduccionEmpleado.objects.create(
            orden=orden, empleado=make_empleado(nombres='Devenga'),
            responsabilidad='corte', monto_comision_fijo=Decimal('50'))

        with self.assertRaises(CommandError) as ctx:
            self._correr('--confirmar')
        self.assertIn('comisión', str(ctx.exception))
        self.assertTrue(PrendaInventario.objects.filter(codigo='PRN-001').exists(),
                        'al frenar no tenía que borrar nada')

    def test_no_toca_una_orden_sobre_inventario_archivado(self):
        orden = make_orden_produccion(prenda_inventario=self.vieja,
                                      tipo='stock', cantidad=1)
        self._correr('--confirmar')
        self.assertTrue(OrdenProduccion.objects.filter(pk=orden.pk).exists(),
                        'la orden sobre inventario histórico es real')
