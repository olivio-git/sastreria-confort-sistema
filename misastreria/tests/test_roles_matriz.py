"""
Muestras de la matriz rol -> permiso (spec: Role-Module Permission Matrix).

No es exhaustivo (serían ~150 vistas x 4 roles); son casos representativos
por módulo elegidos a mano, más el caso de permiso compartido "OR" para
catálogos dinámicos. Complementa (no reemplaza) a `test_url_coverage.py`,
que garantiza que TODA vista tenga algún decorador.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .factories import (
    make_administrador, make_cajero, make_vendedor, make_taller,
    make_cliente, make_reparacion, make_confeccion,
    make_prenda, make_prenda_item,
)


class DashboardAccesoTests(TestCase):
    """Dashboard: Full para los 4 roles."""

    def test_los_4_roles_acceden_al_dashboard(self):
        for maker in (make_administrador, make_cajero, make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'u_{maker.__name__}'))
                resp = self.client.get(reverse('dashboard'))
                self.assertEqual(resp.status_code, 200)


class EmpleadosMatrizTests(TestCase):
    """Empleados: sólo Administrador."""

    def test_admin_accede_a_lista_empleados(self):
        self.client.force_login(make_administrador())
        resp = self.client.get(reverse('lista_empleados'))
        self.assertEqual(resp.status_code, 200)

    def test_cajero_vendedor_taller_403_en_lista_empleados(self):
        for maker in (make_cajero, make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'e_{maker.__name__}'))
                resp = self.client.get(reverse('lista_empleados'))
                self.assertEqual(resp.status_code, 403)

    def test_admin_accede_a_crear_empleado(self):
        self.client.force_login(make_administrador())
        resp = self.client.get(reverse('crear_empleado'))
        self.assertEqual(resp.status_code, 200)


class ClientesMatrizTests(TestCase):
    def test_admin_cajero_vendedor_ven_clientes(self):
        for maker in (make_administrador, make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'c_{maker.__name__}'))
                resp = self.client.get(reverse('lista_clientes'))
                self.assertEqual(resp.status_code, 200)

    def test_taller_403_en_clientes(self):
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('lista_clientes'))
        self.assertEqual(resp.status_code, 403)

    def test_taller_403_al_eliminar_cliente(self):
        cliente = make_cliente()
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('eliminar_cliente', args=[cliente.id]))
        self.assertEqual(resp.status_code, 403)


class ReparacionesMatrizTests(TestCase):
    def test_admin_cajero_vendedor_acceden_a_crear_reparacion(self):
        for maker in (make_administrador, make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'r_{maker.__name__}'))
                resp = self.client.get(reverse('crear_reparacion'))
                self.assertEqual(resp.status_code, 200)

    def test_taller_403_en_crear_reparacion(self):
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('crear_reparacion'))
        self.assertEqual(resp.status_code, 403)

    def test_solo_admin_y_taller_marcan_en_proceso(self):
        reparacion = make_reparacion()
        for maker, esperado in (
            (make_administrador, 302), (make_taller, 302),
            (make_cajero, 403), (make_vendedor, 403),
        ):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'ep_{maker.__name__}'))
                resp = self.client.post(reverse('reparacion_en_proceso', args=[reparacion.id]))
                self.assertEqual(resp.status_code, esperado)

    def test_solo_admin_elimina_reparacion(self):
        reparacion = make_reparacion()
        self.client.force_login(make_cajero())
        resp = self.client.get(reverse('eliminar_reparacion', args=[reparacion.id]))
        self.assertEqual(resp.status_code, 403)


class VentasMatrizTests(TestCase):
    def test_admin_cajero_vendedor_acceden_a_crear_venta(self):
        for maker in (make_administrador, make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'v_{maker.__name__}'))
                resp = self.client.get(reverse('crear_venta'))
                self.assertEqual(resp.status_code, 200)

    def test_taller_403_en_ventas(self):
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('lista_ventas'))
        self.assertEqual(resp.status_code, 403)


class ConfeccionesMatrizTests(TestCase):
    """Intake (crear/editar): Admin y Vendedor sí, Cajero no (default D)."""

    def test_admin_y_vendedor_acceden_a_crear_confeccion(self):
        for maker in (make_administrador, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'cf_{maker.__name__}'))
                resp = self.client.get(reverse('crear_confeccion'))
                self.assertEqual(resp.status_code, 200)

    def test_cajero_403_en_crear_confeccion(self):
        self.client.force_login(make_cajero())
        resp = self.client.get(reverse('crear_confeccion'))
        self.assertEqual(resp.status_code, 403)

    def test_taller_403_en_crear_confeccion(self):
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('crear_confeccion'))
        self.assertEqual(resp.status_code, 403)

    def test_solo_admin_y_taller_entregan_confeccion(self):
        confeccion = make_confeccion()
        for maker, esperado in (
            (make_administrador, 302), (make_taller, 302),
            (make_cajero, 403), (make_vendedor, 403),
        ):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'ent_{maker.__name__}'))
                resp = self.client.post(reverse('entregar_confeccion', args=[confeccion.id]))
                self.assertEqual(resp.status_code, esperado)


class AlquileresMatrizTests(TestCase):
    def test_admin_cajero_vendedor_acceden_a_crear_alquiler(self):
        for maker in (make_administrador, make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'al_{maker.__name__}'))
                resp = self.client.get(reverse('crear_alquiler'))
                self.assertEqual(resp.status_code, 200)

    def test_taller_403_en_crear_alquiler(self):
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('crear_alquiler'))
        self.assertEqual(resp.status_code, 403)


class InventarioMatrizTests(TestCase):
    """Inventario/Prendas CRUD: Admin y Taller sí, Cajero/Vendedor no."""

    def test_admin_y_taller_acceden_a_crear_prenda(self):
        for maker in (make_administrador, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'pr_{maker.__name__}'))
                resp = self.client.get(reverse('crear_prenda'))
                self.assertEqual(resp.status_code, 200)

    def test_cajero_y_vendedor_403_en_crear_prenda(self):
        for maker in (make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'pr2_{maker.__name__}'))
                resp = self.client.get(reverse('crear_prenda'))
                self.assertEqual(resp.status_code, 403)

    def test_los_4_roles_acceden_al_escaneo_ajax(self):
        """Inventario buscar/escanear (AJAX): Yes para los 4 roles."""
        for maker in (make_administrador, make_cajero, make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'esc_{maker.__name__}'))
                resp = self.client.get(reverse('buscar_prenda_items'), {'q': ''})
                self.assertEqual(resp.status_code, 200)


class CortesMatrizTests(TestCase):
    def test_admin_y_taller_acceden_a_buscar_cortes(self):
        for maker in (make_administrador, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'co_{maker.__name__}'))
                resp = self.client.get(reverse('buscar_cortes'), {'q': ''})
                self.assertEqual(resp.status_code, 200)

    def test_cajero_y_vendedor_403_en_buscar_cortes(self):
        for maker in (make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'co2_{maker.__name__}'))
                resp = self.client.get(reverse('buscar_cortes'), {'q': ''})
                self.assertEqual(resp.status_code, 403)


class InsumosYProduccionMatrizTests(TestCase):
    def test_admin_y_taller_ven_insumos(self):
        for maker in (make_administrador, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'in_{maker.__name__}'))
                resp = self.client.get(reverse('lista_insumos'))
                self.assertEqual(resp.status_code, 200)

    def test_cajero_y_vendedor_403_en_insumos(self):
        for maker in (make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'in2_{maker.__name__}'))
                resp = self.client.get(reverse('lista_insumos'))
                self.assertEqual(resp.status_code, 403)

    def test_admin_y_taller_ven_produccion(self):
        for maker in (make_administrador, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'op_{maker.__name__}'))
                resp = self.client.get(reverse('lista_ordenes'))
                self.assertEqual(resp.status_code, 200)


class TransaccionesMatrizTests(TestCase):
    """Gastos crear: Admin/Cajero. Editar/eliminar: sólo Admin."""

    def test_admin_y_cajero_acceden_a_crear_transaccion(self):
        for maker in (make_administrador, make_cajero):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'tx_{maker.__name__}'))
                resp = self.client.get(reverse('crear_transaccion'))
                self.assertEqual(resp.status_code, 200)

    def test_vendedor_y_taller_403_en_crear_transaccion(self):
        for maker in (make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'tx2_{maker.__name__}'))
                resp = self.client.get(reverse('crear_transaccion'))
                self.assertEqual(resp.status_code, 403)

    def test_cajero_403_al_editar_transaccion(self):
        from misastreria.models import Transaccion
        tx = Transaccion.objects.create(
            codigo='TXN-999', tipo_transaccion='gasto', tipo_servicio='otros',
            descripcion='x', fecha=date.today(), cantidad=1, monto=Decimal('10'),
        )
        self.client.force_login(make_cajero())
        resp = self.client.get(reverse('editar_transaccion', args=[tx.id]))
        self.assertEqual(resp.status_code, 403)


class ConjuntosMatrizTests(TestCase):
    """Conjuntos CRUD: Admin only (default D)."""

    def test_solo_admin_ve_conjuntos(self):
        self.client.force_login(make_administrador())
        resp = self.client.get(reverse('lista_conjuntos'))
        self.assertEqual(resp.status_code, 200)

    def test_cajero_vendedor_taller_403_en_conjuntos(self):
        for maker in (make_cajero, make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'cj_{maker.__name__}'))
                resp = self.client.get(reverse('lista_conjuntos'))
                self.assertEqual(resp.status_code, 403)


class ReportesYAnaliticaMatrizTests(TestCase):
    """Reportes generales y Analítica: Admin only (default D)."""

    def test_solo_admin_ve_reporte_empleados(self):
        self.client.force_login(make_administrador())
        resp = self.client.get(reverse('reporte_empleados'))
        self.assertEqual(resp.status_code, 200)

    def test_cajero_403_en_reporte_empleados(self):
        self.client.force_login(make_cajero())
        resp = self.client.get(reverse('reporte_empleados'))
        self.assertEqual(resp.status_code, 403)

    def test_solo_admin_ve_analitica(self):
        self.client.force_login(make_administrador())
        resp = self.client.get(reverse('analitica_items'))
        self.assertEqual(resp.status_code, 200)

    def test_cajero_vendedor_taller_403_en_analitica(self):
        for maker in (make_cajero, make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'an_{maker.__name__}'))
                resp = self.client.get(reverse('analitica_items'))
                self.assertEqual(resp.status_code, 403)


class CajaMatrizTests(TestCase):
    """Abrir sesión: Admin/Cajero. Reportes de caja: Admin/Cajero."""

    def test_admin_y_cajero_acceden_a_abrir_sesion(self):
        for maker in (make_administrador, make_cajero):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'ab_{maker.__name__}'))
                resp = self.client.get(reverse('abrir_sesion_caja'))
                self.assertEqual(resp.status_code, 200)

    def test_vendedor_y_taller_403_en_abrir_sesion(self):
        for maker in (make_vendedor, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'ab2_{maker.__name__}'))
                resp = self.client.get(reverse('abrir_sesion_caja'))
                self.assertEqual(resp.status_code, 403)

    def test_admin_y_cajero_ven_lista_de_sesiones(self):
        for maker in (make_administrador, make_cajero):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'ls_{maker.__name__}'))
                resp = self.client.get(reverse('lista_sesiones_caja'))
                self.assertEqual(resp.status_code, 200)


class TipoGastoMatrizTests(TestCase):
    """Conceptos de gasto: Admin only."""

    def test_solo_admin_ve_conceptos_de_gasto(self):
        self.client.force_login(make_administrador())
        resp = self.client.get(reverse('lista_tipo_gasto'))
        self.assertEqual(resp.status_code, 200)

    def test_cajero_403_en_conceptos_de_gasto(self):
        self.client.force_login(make_cajero())
        resp = self.client.get(reverse('lista_tipo_gasto'))
        self.assertEqual(resp.status_code, 403)


class EtiquetasMatrizTests(TestCase):
    """Diseñador/calibración: Admin only. Impresión: Admin + Taller."""

    def test_solo_admin_accede_al_disenador(self):
        self.client.force_login(make_administrador())
        # Sin plantilla predeterminada aún, pero `?nueva=1` evita el redirect
        # a `editar_plantilla` que hace la vista cuando sí existe una.
        resp = self.client.get(reverse('disenador_etiqueta'), {'nueva': '1'})
        self.assertEqual(resp.status_code, 200)

    def test_taller_403_en_disenador(self):
        self.client.force_login(make_taller())
        resp = self.client.get(reverse('disenador_etiqueta'))
        self.assertEqual(resp.status_code, 403)

    def test_admin_y_taller_imprimen_etiqueta_de_item(self):
        item = make_prenda_item(make_prenda())
        for maker in (make_administrador, make_taller):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'im_{maker.__name__}'))
                resp = self.client.get(reverse('exportar_etiqueta_item_pdf', args=[item.id]))
                self.assertEqual(resp.status_code, 200)

    def test_cajero_y_vendedor_403_al_imprimir_etiqueta(self):
        item = make_prenda_item(make_prenda())
        for maker in (make_cajero, make_vendedor):
            with self.subTest(rol=maker.__name__):
                self.client.force_login(maker(username=f'im2_{maker.__name__}'))
                resp = self.client.get(reverse('exportar_etiqueta_item_pdf', args=[item.id]))
                self.assertEqual(resp.status_code, 403)


class CatalogoCompartidoORTests(TestCase):
    """Scenario: Shared catalog AJAX resolves via OR-permission.

    Cajero no tiene `add_confeccion`, pero `crear_tipo_prenda` acepta
    cualquiera de add_reparacion/add_venta/add_confeccion/add_alquiler —
    Cajero pasa porque tiene las otras tres.
    """

    def test_cajero_sin_add_confeccion_igual_accede_a_crear_tipo_prenda(self):
        cajero = make_cajero()
        self.assertFalse(cajero.has_perm('misastreria.add_confeccion'))
        self.client.force_login(cajero)
        resp = self.client.post(reverse('crear_tipo_prenda'), {'nombre': 'Saco'})
        self.assertNotEqual(resp.status_code, 403)

    def test_taller_403_en_crear_tipo_prenda(self):
        """Taller no tiene ninguno de los 4 permisos padre -> 403."""
        self.client.force_login(make_taller())
        resp = self.client.post(reverse('crear_tipo_prenda'), {'nombre': 'Saco'})
        self.assertEqual(resp.status_code, 403)
