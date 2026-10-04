"""Unir los SKU repetidos del catálogo en uno solo por modelo.

Al cargar el catálogo nuevo se creó un SKU por cada prenda física. Lo que se
cuida acá: que se junten sólo los que son el mismo modelo, que ninguna reserva
se entere, y que no se una nada cuyo precio no coincida.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from misastreria.models import PrendaInventario, PrendaItem
from .factories import (
    make_alquiler, make_alquiler_item, make_orden_produccion, make_prenda,
    make_prenda_item, make_tipo_prenda,
)


def _correr(*args):
    salida = StringIO()
    call_command('unir_prendas_repetidas', *args, stdout=salida, stderr=salida)
    return salida.getvalue()


def _saco(codigo, **kwargs):
    datos = dict(codigo=codigo, nombre='SACO', modelo='SLIM-TW', talla='48',
                 color='NEGRO', precio=Decimal('900'),
                 precio_alquiler_base=Decimal('120'))
    datos.update(kwargs)
    prenda = make_prenda(**datos)
    make_prenda_item(prenda)                                     # <codigo>-ITM-01
    return prenda


class UnirPrendasRepetidasTests(TestCase):
    def setUp(self):
        self.a = _saco('PRN-021')
        self.b = _saco('PRN-022')
        self.c = _saco('PRN-023')

    def _codigos(self, prenda):
        return list(prenda.items.order_by('codigo_item')
                    .values_list('codigo_item', flat=True))

    def test_el_simulacro_no_toca_nada(self):
        salida = _correr()
        self.assertIn('SIMULACRO', salida)
        self.assertIn('PRN-022-ITM-01 → PRN-021-ITM-02', salida)
        self.assertIn('PRN-023-ITM-01 → PRN-021-ITM-03', salida)
        self.assertEqual(PrendaInventario.objects.count(), 3)
        self.assertEqual(self._codigos(self.a), ['PRN-021-ITM-01'])

    def test_junta_las_unidades_en_el_sku_mas_bajo_y_borra_los_vacios(self):
        _correr('--confirmar')
        self.assertEqual(list(PrendaInventario.objects.values_list('codigo', flat=True)),
                         ['PRN-021'])
        self.assertEqual(self._codigos(self.a),
                         ['PRN-021-ITM-01', 'PRN-021-ITM-02', 'PRN-021-ITM-03'])

    def test_la_reserva_sigue_apuntando_a_la_misma_unidad(self):
        item = self.b.items.get()
        reserva = make_alquiler_item(
            alquiler=make_alquiler(estado='reservado'), prenda_item=item,
            precio_unitario=Decimal('185'))
        _correr('--confirmar')
        reserva.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(reserva.prenda_item_id, item.id)
        self.assertEqual(reserva.precio_unitario, Decimal('185'))
        self.assertEqual(item.codigo_item, 'PRN-021-ITM-02')

    def test_ignora_mayusculas_espacios_y_guion_contra_espacio(self):
        d = _saco('PRN-024', nombre=' saco ', color='negro-marengo')
        e = _saco('PRN-025', color='NEGRO  MARENGO')
        _correr('--confirmar')
        self.assertTrue(PrendaInventario.objects.filter(id=d.id).exists())
        self.assertFalse(PrendaInventario.objects.filter(id=e.id).exists())
        self.assertEqual(self._codigos(d), ['PRN-024-ITM-01', 'PRN-024-ITM-02'])

    def test_no_junta_tallas_distintas(self):
        otra = _saco('PRN-030', talla='50')
        _correr('--confirmar')
        self.assertEqual(self._codigos(otra), ['PRN-030-ITM-01'])

    def test_no_une_si_el_precio_difiere(self):
        self.c.precio = Decimal('950')
        self.c.save()
        salida = _correr('--confirmar')
        self.assertIn('NO SE UNE', salida)
        self.assertIn('precio', salida)
        self.assertEqual(PrendaInventario.objects.count(), 3)

    def test_el_tipo_de_prenda_puede_diferir_y_queda_el_del_destino(self):
        saco = make_tipo_prenda('Saco')
        self.a.tipo_prenda = saco
        self.a.save()
        self.b.tipo_prenda = make_tipo_prenda('SACO')
        self.b.save()
        _correr('--confirmar')
        self.a.refresh_from_db()
        self.assertEqual(self.a.tipo_prenda, saco)
        self.assertEqual(self.a.items.count(), 3)

    def test_no_toca_historicos_apartados_ni_dados_de_baja(self):
        hist = _saco('H-PRN-900')
        apartado = _saco('TMP-001')
        baja = _saco('PRN-040', estado='BAJ')
        _correr('--confirmar')
        for prenda in (hist, apartado, baja):
            self.assertTrue(PrendaInventario.objects.filter(id=prenda.id).exists())
            self.assertEqual(prenda.items.count(), 1)

    def test_la_orden_de_produccion_pasa_al_sku_que_queda(self):
        orden = make_orden_produccion(tipo='stock', prenda_inventario=self.c)
        _correr('--confirmar')
        orden.refresh_from_db()
        self.assertEqual(orden.prenda_inventario_id, self.a.id)

    def test_numera_despues_de_las_unidades_que_ya_tiene_el_destino(self):
        make_prenda_item(self.a)                                 # PRN-021-ITM-02
        _correr('--confirmar')
        self.assertEqual(self._codigos(self.a), [
            'PRN-021-ITM-01', 'PRN-021-ITM-02', 'PRN-021-ITM-03', 'PRN-021-ITM-04'])

    def test_no_une_si_difiere_el_maximo_de_usos(self):
        self.b.max_usos_default = 30
        self.b.save()
        salida = _correr('--confirmar')
        self.assertIn('max_usos_default', salida)
        self.assertEqual(PrendaInventario.objects.count(), 3)

    def test_no_pierde_notas_ni_stock_minimo_de_los_borrados(self):
        self.a.notas = 'Lote de septiembre'
        self.a.save()
        self.b.notas = 'Botón flojo'
        self.b.stock_minimo = 2
        self.b.save()
        _correr('--confirmar')
        self.a.refresh_from_db()
        self.assertEqual(self.a.notas, 'Lote de septiembre\nBotón flojo')
        self.assertEqual(self.a.stock_minimo, 2)

    def test_informa_la_referencia_que_se_descarta(self):
        self.b.codigo_referencia = 'REF-8841'
        self.b.save()
        salida = _correr()
        self.assertIn('se descarta la referencia «REF-8841» de PRN-022', salida)

    def test_salta_un_codigo_que_ya_usa_otra_unidad(self):
        # Una unidad suelta que ya tiene el código que tocaría (quedó así por
        # una edición a mano): el simulacro y la aplicación lo saltan igual.
        otra = make_prenda(codigo='PRN-099', nombre='CAMISA')
        make_prenda_item(otra, codigo_item='PRN-021-ITM-02')
        salida = _correr()
        self.assertIn('PRN-022-ITM-01 → PRN-021-ITM-03', salida)
        _correr('--confirmar')
        self.assertEqual(self._codigos(self.a),
                         ['PRN-021-ITM-01', 'PRN-021-ITM-03', 'PRN-021-ITM-04'])

    def test_el_simulacro_muestra_lo_mismo_que_se_aplica(self):
        simulacro = _correr()
        aplicado = _correr('--confirmar')
        lineas = lambda s: [l for l in s.splitlines() if '→' in l]
        self.assertEqual(lineas(simulacro), lineas(aplicado))

    def test_correrlo_dos_veces_no_cambia_nada(self):
        _correr('--confirmar')
        salida = _correr('--confirmar')
        self.assertIn('No hay SKU repetidos', salida)
        self.assertEqual(PrendaItem.objects.filter(prenda=self.a).count(), 3)
