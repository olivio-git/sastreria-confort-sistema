"""Reordenar el catálogo desde PRN-001 sin perder ninguna reserva.

La secretaria cargó cada prenda a medida que salía para un cliente. Los dueños
quieren numerar en orden antes de etiquetar. Las prendas ya cargadas no se
pueden borrar —están en reservas reales—, así que se apartan a TMP- y después
se MUEVEN una por una al SKU ordenado.

Lo que se cuida acá es que ninguna reserva, alquiler o venta se entere:
apuntan a la unidad por id, y eso tiene que seguir siendo cierto después de
apartar y después de mover.
"""
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from misastreria.models import AlquilerItem, Corte, PrendaInventario, PrendaItem
from .factories import (
    make_alquiler, make_alquiler_item, make_corte, make_prenda, make_prenda_item,
    make_user,
)


def _correr(*args):
    salida = StringIO()
    call_command('apartar_prendas', *args, stdout=salida, stderr=salida)
    return salida.getvalue()


class ApartarPrendasTests(TestCase):
    def setUp(self):
        self.saco = make_prenda(codigo='PRN-001', nombre='SACO/JUS')
        self.item = make_prenda_item(self.saco)                      # PRN-001-ITM-01
        self.reserva = make_alquiler_item(
            alquiler=make_alquiler(estado='reservado'), prenda_item=self.item,
            precio_unitario=Decimal('185'))

    def test_el_simulacro_no_toca_nada(self):
        salida = _correr()
        self.assertIn('SIMULACRO', salida)
        self.saco.refresh_from_db()
        self.assertEqual(self.saco.codigo, 'PRN-001')

    def test_aparta_sku_y_unidades_y_libera_prn_001(self):
        _correr('--confirmar')
        self.saco.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.saco.codigo, 'TMP-001')
        self.assertEqual(self.item.codigo_item, 'TMP-001-ITM-01')
        self.assertEqual(PrendaInventario.siguiente_codigo(), 'PRN-001')

    def test_la_reserva_sigue_apuntando_a_la_misma_unidad(self):
        _correr('--confirmar')
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.prenda_item_id, self.item.id)
        self.assertEqual(self.reserva.precio_unitario, Decimal('185'))

    def test_el_listado_muestra_la_reserva_para_reconocer_la_prenda(self):
        salida = _correr()
        self.assertIn(self.reserva.alquiler.codigo, salida)
        self.assertIn('reservado', salida)

    def test_no_aparta_los_archivados(self):
        viejo = make_prenda(codigo='H-PRN-500', estado='BAJ')
        _correr('--confirmar')
        viejo.refresh_from_db()
        self.assertEqual(viejo.codigo, 'H-PRN-500')

    def test_si_ya_hay_apartados_con_ese_numero_se_niega(self):
        make_prenda(codigo='TMP-001')
        with self.assertRaises(CommandError):
            _correr('--confirmar')
        self.saco.refresh_from_db()
        self.assertEqual(self.saco.codigo, 'PRN-001', 'no tenía que tocar nada')

    def test_limpiar_cortes_desasigna_y_borra_solo_los_vacios(self):
        de_prueba = make_corte(sigla='MAL')
        compartido = make_corte(sigla='HISTORICO')
        self.item.corte = de_prueba
        self.item.save(update_fields=['corte'])
        otro = make_prenda_item(self.saco, corte=compartido)
        make_prenda_item(make_prenda(codigo='H-PRN-600', estado='BAJ'), corte=compartido)

        _correr('--confirmar', '--limpiar-cortes')

        self.item.refresh_from_db()
        otro.refresh_from_db()
        self.assertIsNone(self.item.corte_id)
        self.assertIsNone(otro.corte_id)
        self.assertFalse(Corte.objects.filter(pk=de_prueba.pk).exists())
        self.assertTrue(Corte.objects.filter(pk=compartido.pk).exists(),
                        'un corte que sigue usando una unidad archivada no se borra')

    def test_sin_limpiar_cortes_los_respeta(self):
        corte = make_corte()
        self.item.corte = corte
        self.item.save(update_fields=['corte'])
        _correr('--confirmar')
        self.item.refresh_from_db()
        self.assertEqual(self.item.corte_id, corte.id)


class MoverPrendaItemTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        self.apartado = make_prenda(codigo='TMP-004', nombre='SACO/JUS')
        self.item = make_prenda_item(self.apartado, codigo_item='TMP-004-ITM-01')
        self.reserva = make_alquiler_item(
            alquiler=make_alquiler(estado='reservado'), prenda_item=self.item,
            precio_unitario=Decimal('185'))
        self.destino = make_prenda(codigo='PRN-003', nombre='Saco negro', talla='50')
        make_prenda_item(self.destino)                     # PRN-003-ITM-01 ya existe

    def _mover(self, item=None, destino=None):
        item = item or self.item
        return self.client.post(
            reverse('mover_prenda_item', args=[item.id]),
            {'destino': str((destino or self.destino).id)}, follow=True)

    def test_mueve_y_toma_el_siguiente_codigo_del_destino(self):
        self._mover()
        self.item.refresh_from_db()
        self.assertEqual(self.item.prenda_id, self.destino.id)
        self.assertEqual(self.item.codigo_item, 'PRN-003-ITM-02')

    def test_la_reserva_la_sigue_con_su_precio(self):
        self._mover()
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.prenda_item_id, self.item.id)
        self.assertEqual(self.reserva.precio_unitario, Decimal('185'))

    def test_el_apartado_vacio_se_borra_solo(self):
        self._mover()
        self.assertFalse(PrendaInventario.objects.filter(codigo='TMP-004').exists())

    def test_un_apartado_con_mas_unidades_se_queda(self):
        make_prenda_item(self.apartado, codigo_item='TMP-004-ITM-02')
        self._mover()
        self.assertTrue(PrendaInventario.objects.filter(codigo='TMP-004').exists())

    def test_un_sku_del_catalogo_vacio_no_se_borra(self):
        origen = make_prenda(codigo='PRN-009')
        item = make_prenda_item(origen)
        self._mover(item=item)
        self.assertTrue(PrendaInventario.objects.filter(codigo='PRN-009').exists(),
                        'un SKU del catálogo sin unidades es válido: se repone')

    def test_rechaza_destinos_fuera_del_catalogo(self):
        for codigo, estado in (('TMP-020', 'ACT'), ('H-PRN-700', 'BAJ'), ('PRN-030', 'BAJ')):
            with self.subTest(codigo=codigo):
                destino = make_prenda(codigo=codigo, estado=estado)
                resp = self._mover(destino=destino)
                self.assertContains(resp, 'Sólo se puede mover')
                self.item.refresh_from_db()
                self.assertEqual(self.item.prenda_id, self.apartado.id)

    def test_no_mueve_unidades_archivadas(self):
        archivada = make_prenda_item(make_prenda(codigo='H-PRN-800', estado='BAJ'))
        resp = self._mover(item=archivada)
        self.assertContains(resp, 'son historia')
        archivada.refresh_from_db()
        self.assertNotEqual(archivada.prenda_id, self.destino.id)

    def test_pide_login(self):
        self.client.logout()
        self.client.post(reverse('mover_prenda_item', args=[self.item.id]),
                         {'destino': str(self.destino.id)})
        self.item.refresh_from_db()
        self.assertEqual(self.item.prenda_id, self.apartado.id)


class BuscadorSoloCatalogoTests(TestCase):
    def test_excluye_apartados_y_archivados(self):
        make_prenda(codigo='PRN-001', nombre='Saco negro')
        make_prenda(codigo='TMP-004', nombre='Saco negro viejo')
        make_prenda(codigo='H-PRN-100', nombre='Saco negro archivado', estado='BAJ')
        url = reverse('buscar_prenda_inventario')
        codigos = {r['ci'] for r in self.client.get(url, {'solo_catalogo': 1, 'q': 'saco'}).json()}
        self.assertEqual(codigos, {'PRN-001'})
        sin_filtro = {r['ci'] for r in self.client.get(url, {'q': 'saco'}).json()}
        self.assertIn('TMP-004', sin_filtro, 'sin el parámetro, el buscador no cambia')
