"""Corte de inventario: archivar lo actual para recargar desde PRN-001.

Borrar no es opción — 62% de las unidades están bajo `on_delete=PROTECT` por
ventas y alquileres, y con ellas caerían los eventos de kardex por CASCADE—.
Se archiva con prefijo, el modelo pasa a BAJ y la numeración vuelve a empezar.
"""
from datetime import date, timedelta
from decimal import Decimal
import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from misastreria.models import (
    Alquiler, AlquilerItem, KardexEvento, PrendaInventario, PrendaItem,
)
from .factories import make_cliente, make_prenda, make_prenda_item, make_user


def cortar(**kw):
    salida = io.StringIO()
    call_command('cortar_inventario', stdout=salida, **kw)
    return salida.getvalue()


class CorteDeInventarioTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        self.prenda = make_prenda(nombre='Frac', precio=Decimal('900.00'))
        self.libre = make_prenda_item(self.prenda, tipo='alquiler')
        self.salida = make_prenda_item(self.prenda, tipo='alquiler', estado='alquilado')
        self.alquiler = Alquiler.objects.create(
            cliente=make_cliente(), fecha_alquiler=date.today(),
            fecha_devolucion=date.today() + timedelta(days=3), estado='alquilado')
        AlquilerItem.objects.create(alquiler=self.alquiler, prenda_item=self.salida,
                                    precio_unitario=Decimal('250.00'))

    def test_el_simulacro_no_toca_nada(self):
        salida = cortar()
        self.assertIn('SIMULACRO', salida)
        self.prenda.refresh_from_db()
        self.assertEqual(self.prenda.codigo, 'PRN-001')
        self.assertEqual(self.prenda.estado, 'ACT')

    def test_archiva_con_prefijo_y_da_de_baja_el_modelo(self):
        cortar(confirmar=True)
        self.prenda.refresh_from_db(); self.libre.refresh_from_db()
        self.assertEqual(self.prenda.codigo, 'H-PRN-001')
        self.assertEqual(self.prenda.estado, 'BAJ')
        self.assertEqual(self.libre.codigo_item, 'H-PRN-001-ITM-01')

    def test_no_borra_ni_una_fila(self):
        antes = (PrendaInventario.objects.count(), PrendaItem.objects.count(),
                 AlquilerItem.objects.count(), KardexEvento.objects.count())
        cortar(confirmar=True)
        despues = (PrendaInventario.objects.count(), PrendaItem.objects.count(),
                   AlquilerItem.objects.count(), KardexEvento.objects.count())
        self.assertEqual(antes, despues)

    def test_la_prenda_en_la_calle_conserva_su_estado(self):
        """Se archiva, pero sigue alquilada: su devolución tiene que funcionar."""
        cortar(confirmar=True)
        self.salida.refresh_from_db()
        self.assertEqual(self.salida.estado, 'alquilado')
        self.assertEqual(self.alquiler.items.first().prenda_item_id, self.salida.id)
        resp = self.client.get(reverse('devolver_alquiler', args=[self.alquiler.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('H-PRN-001-ITM-02', resp.content.decode())

    def test_la_numeracion_vuelve_a_empezar_en_uno(self):
        cortar(confirmar=True)
        nueva = make_prenda(nombre='Frac nuevo', precio=Decimal('900.00'))
        self.assertEqual(nueva.codigo, 'PRN-001')
        self.assertEqual(make_prenda_item(nueva).codigo_item, 'PRN-001-ITM-01')

    def test_lo_archivado_no_se_ofrece_en_los_formularios(self):
        cortar(confirmar=True)
        nueva = make_prenda(nombre='Frac nuevo', precio=Decimal('900.00'))
        item_nuevo = make_prenda_item(nueva, tipo='alquiler')
        items = self.client.get(reverse('buscar_items_inventario'),
                                {'estado': 'disponible'}).json()['items']
        self.assertEqual([i['codigo_item'] for i in items], [item_nuevo.codigo_item])

    def test_correrlo_dos_veces_no_anida_prefijos(self):
        cortar(confirmar=True)
        salida = cortar(confirmar=True)
        self.assertIn('No hay nada que archivar', salida)
        self.prenda.refresh_from_db()
        self.assertEqual(self.prenda.codigo, 'H-PRN-001')

    def test_se_puede_revertir_antes_de_cargar_nada(self):
        cortar(confirmar=True)
        cortar(confirmar=True, revertir=True)
        self.prenda.refresh_from_db(); self.libre.refresh_from_db()
        self.assertEqual(self.prenda.codigo, 'PRN-001')
        self.assertEqual(self.prenda.estado, 'ACT')
        self.assertEqual(self.libre.codigo_item, 'PRN-001-ITM-01')

    def test_no_se_puede_revertir_si_ya_hay_inventario_nuevo(self):
        """El código liberado ya está ocupado: se avisa en vez de reventar."""
        cortar(confirmar=True)
        make_prenda(nombre='Frac nuevo', precio=Decimal('900.00'))   # toma PRN-001
        with self.assertRaises(CommandError) as ctx:
            cortar(confirmar=True, revertir=True)
        mensaje = str(ctx.exception)
        self.assertIn('No se puede revertir', mensaje)
        self.assertIn('H-PRN-001', mensaje)
        self.assertIn('respaldo', mensaje)
        # y no dejó nada a medias
        self.prenda.refresh_from_db()
        self.assertEqual(self.prenda.codigo, 'H-PRN-001')


class DependenciasTrasElCorteTests(TestCase):
    """Lo que apunta al inventario tiene que seguir andando tras archivarlo."""

    def setUp(self):
        self.client.force_login(make_user())
        self.prenda = make_prenda(nombre='Terno', precio=Decimal('500.00'))
        self.item = make_prenda_item(self.prenda, tipo='venta')

    def test_produccion_no_ofrece_modelos_archivados(self):
        from misastreria.forms import OrdenProduccionForm
        self.assertIn(self.prenda, OrdenProduccionForm().fields['prenda_inventario'].queryset)
        cortar(confirmar=True)
        self.assertNotIn(self.prenda,
                         OrdenProduccionForm().fields['prenda_inventario'].queryset)

    def test_una_orden_existente_conserva_su_modelo_al_editarse(self):
        """El FK es PROTECT: la orden vieja no puede quedarse sin su modelo."""
        from misastreria.forms import OrdenProduccionForm
        from misastreria.models import OrdenProduccion
        orden = OrdenProduccion.objects.create(
            tipo='stock', prenda_inventario=self.prenda, cantidad=3,
            fecha_inicio=date.today())
        cortar(confirmar=True)
        form = OrdenProduccionForm(instance=orden)
        self.assertIn(self.prenda, form.fields['prenda_inventario'].queryset)

    def test_los_conjuntos_no_ofrecen_unidades_archivadas(self):
        from misastreria.forms import ConjuntoSlotFormSet
        cortar(confirmar=True)
        # empty_form y no forms[0]: el formset viene sin extras.
        campo = ConjuntoSlotFormSet().empty_form.fields['prenda_item']
        self.assertNotIn(self.item, campo.queryset)
