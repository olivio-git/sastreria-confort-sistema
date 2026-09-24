"""Unir cada prenda apartada (TMP-) con la prenda nueva que la reemplaza.

Los dueños cargan todo desde cero, incluidas las prendas que ya tienen un
cliente. Al terminar, cada una de esas existe dos veces. Lo que se cuida acá:
que la reserva, los cobros y el historial pasen enteros a la nueva, y que un
par mal escrito no deje nada a medias.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from misastreria import kardex_events
from misastreria.models import (
    AlquilerItem, KardexEvento, PrendaInventario, PrendaItem, VentaItem,
)
from .factories import (
    make_alquiler, make_alquiler_item, make_prenda, make_prenda_item, make_venta,
)


def _correr(*args):
    salida = StringIO()
    call_command('conciliar_apartadas', *args, stdout=salida, stderr=salida)
    return salida.getvalue()


class ConciliarApartadasTests(TestCase):
    def setUp(self):
        # La vieja: apartada, reservada para un cliente, con su historial.
        self.sku_viejo = make_prenda(codigo='TMP-004', nombre='SACO/JUS', talla='52')
        self.vieja = make_prenda_item(self.sku_viejo, codigo_item='TMP-004-ITM-01',
                                      estado='reservado', veces_alquilado=3)
        kardex_events.emit_ingreso(self.vieja)
        self.alquiler = make_alquiler(estado='reservado')
        self.linea = make_alquiler_item(alquiler=self.alquiler, prenda_item=self.vieja,
                                        precio_unitario=Decimal('185'))
        kardex_events.emit_alquiler(self.vieja, self.alquiler, Decimal('185'))

        # La nueva: recién cargada en el catálogo ordenado.
        self.sku_nuevo = make_prenda(codigo='PRN-015', nombre='Saco azul marino', talla='52')
        self.nueva = make_prenda_item(self.sku_nuevo, codigo_item='PRN-015-ITM-01')
        kardex_events.emit_ingreso(self.nueva)
        self.par = 'TMP-004-ITM-01=PRN-015-ITM-01'

    def test_sin_argumentos_lista_lo_pendiente_para_imprimir(self):
        salida = _correr()
        self.assertIn('TMP-004-ITM-01', salida)
        self.assertIn(self.alquiler.codigo, salida)
        self.assertIn('código nuevo', salida)

    def test_el_simulacro_no_toca_nada(self):
        salida = _correr(self.par)
        self.assertIn('SIMULACRO', salida)
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.prenda_item_id, self.vieja.id)
        self.assertTrue(PrendaItem.objects.filter(pk=self.vieja.pk).exists())

    def test_la_reserva_pasa_a_la_nueva_con_su_precio(self):
        _correr(self.par, '--confirmar')
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.prenda_item_id, self.nueva.id)
        self.assertEqual(self.linea.precio_unitario, Decimal('185'))

    def test_la_nueva_hereda_estado_y_usos(self):
        _correr(self.par, '--confirmar')
        self.nueva.refresh_from_db()
        self.assertEqual(self.nueva.estado, 'reservado')
        self.assertEqual(self.nueva.veces_alquilado, 3)

    def test_el_historial_pasa_sin_duplicar_el_ingreso(self):
        _correr(self.par, '--confirmar')
        tipos = sorted(KardexEvento.objects.filter(prenda_item=self.nueva)
                       .values_list('tipo', flat=True))
        self.assertEqual(tipos, ['alquiler', 'ingreso'])

    def test_la_vieja_y_su_sku_vacio_se_borran(self):
        _correr(self.par, '--confirmar')
        self.assertFalse(PrendaItem.objects.filter(pk=self.vieja.pk).exists())
        self.assertFalse(PrendaInventario.objects.filter(codigo='TMP-004').exists())

    def test_tambien_pasa_una_venta(self):
        venta = make_venta(estado='en_proceso')
        VentaItem.objects.create(venta=venta, prenda_item=self.vieja,
                                 precio_unitario=Decimal('255'))
        _correr(self.par, '--confirmar')
        self.assertEqual(VentaItem.objects.get(venta=venta).prenda_item_id, self.nueva.id)

    def test_un_par_invalido_frena_todos(self):
        otra_vieja = make_prenda_item(self.sku_viejo, codigo_item='TMP-004-ITM-02')
        with self.assertRaises(CommandError):
            _correr(self.par, 'TMP-004-ITM-02=PRN-999-ITM-01', '--confirmar')
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.prenda_item_id, self.vieja.id,
                         'con un par malo no tenía que aplicar ninguno')
        self.assertTrue(PrendaItem.objects.filter(pk=otra_vieja.pk).exists())

    def test_rechaza_una_nueva_que_ya_tiene_operaciones(self):
        make_alquiler_item(prenda_item=self.nueva)
        with self.assertRaises(CommandError) as ctx:
            _correr(self.par, '--confirmar')
        self.assertIn('ya tiene operaciones', str(ctx.exception))

    def test_rechaza_una_nueva_que_no_esta_disponible(self):
        self.nueva.estado = 'baja'
        self.nueva.save(update_fields=['estado'])
        with self.assertRaises(CommandError):
            _correr(self.par, '--confirmar')

    def test_rechaza_una_vieja_que_no_esta_apartada(self):
        catalogo = make_prenda_item(self.sku_nuevo, codigo_item='PRN-015-ITM-02')
        with self.assertRaises(CommandError) as ctx:
            _correr('PRN-015-ITM-02=PRN-015-ITM-01', '--confirmar')
        self.assertIn('no es una prenda apartada', str(ctx.exception))
        self.assertTrue(PrendaItem.objects.filter(pk=catalogo.pk).exists())

    def test_rechaza_la_misma_nueva_para_dos_viejas(self):
        make_prenda_item(self.sku_viejo, codigo_item='TMP-004-ITM-02')
        with self.assertRaises(CommandError) as ctx:
            _correr(self.par, 'TMP-004-ITM-02=PRN-015-ITM-01', '--confirmar')
        self.assertIn('dos veces', str(ctx.exception))

    def test_un_sku_apartado_con_otras_unidades_se_queda(self):
        make_prenda_item(self.sku_viejo, codigo_item='TMP-004-ITM-02')
        _correr(self.par, '--confirmar')
        self.assertTrue(PrendaInventario.objects.filter(codigo='TMP-004').exists())

    def test_acepta_minusculas(self):
        _correr(self.par.lower(), '--confirmar')
        self.linea.refresh_from_db()
        self.assertEqual(self.linea.prenda_item_id, self.nueva.id)


class CircuitoCompletoTests(TestCase):
    """Apartar → cargar desde cero → conciliar, como lo van a hacer los dueños."""

    def test_de_punta_a_punta(self):
        from misastreria.models import Alquiler
        # Lo que cargó la secretaria: una prenda reservada para un cliente.
        sku = make_prenda(codigo='PRN-001', nombre='SACO/JUS', talla='52', color='azul')
        unidad = make_prenda_item(sku)                                  # PRN-001-ITM-01
        unidad.estado = 'reservado'
        unidad.save(update_fields=['estado'])
        reserva = make_alquiler_item(alquiler=make_alquiler(estado='reservado'),
                                     prenda_item=unidad, precio_unitario=Decimal('185'))

        # 1. Apartar.
        call_command('apartar_prendas', '--confirmar', stdout=StringIO())
        unidad.refresh_from_db()
        self.assertEqual(unidad.codigo_item, 'TMP-001-ITM-01')

        # 2. Los dueños cargan desde cero, en su orden: primero dos sacos negros,
        #    después el azul, que es el reservado.
        negros = PrendaInventario.objects.create(nombre='Saco', talla='50', color='negro',
                                                 precio=Decimal('600'))
        azul = PrendaInventario.objects.create(nombre='Saco', talla='52', color='azul',
                                               precio=Decimal('600'))
        self.assertEqual((negros.codigo, azul.codigo), ('PRN-001', 'PRN-002'))
        nueva = PrendaItem.objects.create(prenda=azul, tipo='alquiler', condicion='nueva')
        self.assertEqual(nueva.codigo_item, 'PRN-002-ITM-01')

        # 3. Conciliar con el código que anotaron.
        call_command('conciliar_apartadas', 'TMP-001-ITM-01=PRN-002-ITM-01',
                     '--confirmar', stdout=StringIO())

        reserva.refresh_from_db()
        nueva.refresh_from_db()
        self.assertEqual(reserva.prenda_item_id, nueva.id)
        self.assertEqual(nueva.estado, 'reservado')
        self.assertFalse(PrendaInventario.objects.filter(codigo__startswith='TMP-').exists())
        self.assertEqual(Alquiler.objects.get(pk=reserva.alquiler_id).items.get().prenda_item.codigo_item,
                         'PRN-002-ITM-01')
