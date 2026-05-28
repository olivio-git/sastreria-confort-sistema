"""
test_views_smoke.py
====================
Smoke test: golpea CADA URL del sistema con un usuario autenticado
y verifica que ninguna devuelva 500 (error interno).

Detecta crashes silenciosos antes de que el usuario los vea.
Incluye URLs con parámetros GET que activen todas las ramas de código
(filtros, exportaciones, analítica, kardex, etc).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from .factories import (
    make_user, make_empleado, make_cliente,
    make_reparacion, make_reparacion_item,
    make_venta, make_confeccion, make_alquiler, make_alquiler_item,
    make_prenda, make_prenda_item,
    make_sesion_caja, make_movimiento_caja,
    make_tipo_prenda, make_tipo_reparacion, make_tipo_gasto,
    make_estado_alquiler,
)
from misastreria.models import (
    Insumo, OrdenProduccion, Transaccion, Conjunto, ConjuntoSlot,
    KardexEvento, PrendaItem,
)


class SmokeTestBase(TestCase):
    """Crea datos mínimos que todas las vistas de detalle necesitan."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user()
        cls.empleado = make_empleado()
        cls.cliente = make_cliente()
        cls.prenda = make_prenda(
            nombre='Traje Test',
            precio_alquiler_base=Decimal('200'),
            max_usos_default=10,
        )
        cls.item = make_prenda_item(prenda=cls.prenda)
        cls.reparacion = make_reparacion(cliente=cls.cliente)
        make_reparacion_item(reparacion=cls.reparacion)
        cls.venta = make_venta(cliente=cls.cliente)
        cls.confeccion = make_confeccion(
            cliente=cls.cliente,
            empleado=cls.empleado,
        )
        cls.alquiler = make_alquiler(
            cliente=cls.cliente,
            estado='alquilado',
        )
        make_alquiler_item(alquiler=cls.alquiler, prenda_item=cls.item)
        cls.sesion = make_sesion_caja(usuario=cls.user)
        cls.mov = make_movimiento_caja(sesion=cls.sesion)
        cls.tipo_gasto = make_tipo_gasto()
        cls.insumo = Insumo.objects.create(articulo='Tela de prueba')
        cls.orden = OrdenProduccion.objects.create(
            descripcion='Orden test', tipo='stock'
        )
        cls.txn = Transaccion.objects.create(
            tipo_transaccion='ingreso',
            descripcion='Transaccion test',
            tipo_servicio='otros',
            cantidad=1,
            monto=Decimal('50.00'),
        )
        cls.conjunto = Conjunto.objects.create(
            nombre='Conjunto Test', tipo='alquiler', precio_sugerido=0
        )
        make_estado_alquiler(nombre='alquilado', color='alquilado')
        make_estado_alquiler(nombre='devuelto', color='devuelto')

        # Kardex events
        KardexEvento.objects.create(tipo='ingreso', prenda_item=cls.item)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get(self, url_name, kwargs=None, params=''):
        url = reverse(url_name, kwargs=kwargs or {})
        if params:
            url = f"{url}?{params}"
        resp = self.client.get(url)
        self.assertNotEqual(
            resp.status_code, 500,
            f"500 ERROR en {url_name} ({url})"
        )
        return resp


class ListasSmoke(SmokeTestBase):
    """Todas las vistas de lista — sin filtros y con filtros."""

    def test_lista_empleados(self):
        self._get('lista_empleados')

    def test_lista_empleados_con_filtro(self):
        self._get('lista_empleados', params='q=Juan&estado=activo')

    def test_lista_clientes(self):
        self._get('lista_clientes')

    def test_lista_clientes_con_filtro(self):
        self._get('lista_clientes', params='q=Maria')

    def test_lista_reparaciones(self):
        self._get('lista_reparaciones')

    def test_lista_reparaciones_filtros(self):
        self._get('lista_reparaciones', params='q=REP&estado=pendiente&periodo=mes')

    def test_lista_ventas(self):
        self._get('lista_ventas')

    def test_lista_ventas_filtros(self):
        self._get('lista_ventas', params='q=VEN&periodo=semana')

    def test_lista_confecciones(self):
        self._get('lista_confecciones')

    def test_lista_confecciones_filtros(self):
        self._get('lista_confecciones', params='estado=pendiente&periodo=3meses')

    def test_lista_alquileres(self):
        self._get('lista_alquileres')

    def test_lista_alquileres_filtros(self):
        self._get('lista_alquileres', params='estado=alquilado&periodo=mes')

    def test_lista_prendas(self):
        self._get('lista_prendas')

    def test_lista_prendas_filtros(self):
        self._get('lista_prendas', params='q=Traje&estado=ACT')

    def test_lista_insumos(self):
        self._get('lista_insumos')

    def test_lista_ordenes(self):
        self._get('lista_ordenes')

    def test_lista_transacciones(self):
        self._get('lista_transacciones')

    def test_lista_movimientos_caja(self):
        self._get('lista_movimientos_caja')

    def test_lista_movimientos_filtros(self):
        self._get('lista_movimientos_caja', params='tipo=ingreso&concepto=ingreso_manual')

    def test_lista_sesiones_caja(self):
        self._get('lista_sesiones_caja')

    def test_lista_tipo_gasto(self):
        self._get('lista_tipo_gasto')

    def test_lista_conjuntos(self):
        self._get('lista_conjuntos')

    def test_items_proximos_baja(self):
        self._get('items_proximos_baja')


class DetallesSmoke(SmokeTestBase):
    """Vistas de detalle por ID."""

    def test_detalle_empleado(self):
        self._get('detalle_empleado', {'id': self.empleado.pk})

    def test_detalle_cliente_historial(self):
        self._get('historial_cliente', {'id': self.cliente.pk})

    def test_detalle_reparacion(self):
        self._get('detalle_reparacion', {'id': self.reparacion.pk})

    def test_detalle_confeccion(self):
        self._get('detalle_confeccion', {'id': self.confeccion.pk})

    def test_detalle_alquiler(self):
        self._get('detalle_alquiler', {'id': self.alquiler.pk})

    def test_detalle_prenda(self):
        self._get('detalle_prenda', {'id': self.prenda.pk})

    def test_detalle_movimiento_caja(self):
        self._get('detalle_movimiento_caja', {'pk': self.mov.pk})

    def test_detalle_sesion_caja(self):
        self._get('detalle_sesion_caja', {'pk': self.sesion.pk})


class FormulariosSmoke(SmokeTestBase):
    """Formularios de crear/editar — solo GET."""

    def test_crear_empleado(self):
        self._get('crear_empleado')

    def test_editar_empleado(self):
        self._get('editar_empleado', {'id': self.empleado.pk})

    def test_crear_cliente(self):
        self._get('crear_cliente')

    def test_editar_cliente(self):
        self._get('editar_cliente', {'id': self.cliente.pk})

    def test_crear_reparacion(self):
        self._get('crear_reparacion')

    def test_editar_reparacion(self):
        self._get('editar_reparacion', {'id': self.reparacion.pk})

    def test_crear_venta(self):
        self._get('crear_venta')

    def test_editar_venta(self):
        self._get('editar_venta', {'id': self.venta.pk})

    def test_crear_confeccion(self):
        self._get('crear_confeccion')

    def test_editar_confeccion(self):
        self._get('editar_confeccion', {'id': self.confeccion.pk})

    def test_crear_alquiler(self):
        self._get('crear_alquiler')

    def test_editar_alquiler(self):
        self._get('editar_alquiler', {'id': self.alquiler.pk})

    def test_crear_prenda(self):
        self._get('crear_prenda')

    def test_editar_prenda(self):
        self._get('editar_prenda', {'id': self.prenda.pk})

    def test_crear_insumo(self):
        self._get('crear_insumo')

    def test_editar_insumo(self):
        self._get('editar_insumo', {'id': self.insumo.pk})

    def test_crear_orden(self):
        self._get('crear_orden')

    def test_editar_orden(self):
        self._get('editar_orden', {'id': self.orden.pk})

    def test_crear_movimiento_caja(self):
        self._get('crear_movimiento_caja')

    def test_abrir_sesion_caja(self):
        self._get('abrir_sesion_caja')

    def test_crear_tipo_gasto(self):
        self._get('crear_tipo_gasto')

    def test_editar_tipo_gasto(self):
        self._get('editar_tipo_gasto', {'pk': self.tipo_gasto.pk})

    def test_crear_conjunto(self):
        self._get('crear_conjunto')

    def test_editar_conjunto(self):
        self._get('editar_conjunto', {'pk': self.conjunto.pk})

    def test_pagar_comision_empleado(self):
        self._get('pagar_comision_empleado', {'empleado_id': self.empleado.pk})

    def test_agregar_pago_reparacion(self):
        self._get('agregar_pago_reparacion', {'id': self.reparacion.pk})

    def test_agregar_pago_confeccion(self):
        self._get('agregar_pago_confeccion', {'id': self.confeccion.pk})

    def test_agregar_pago_alquiler(self):
        self._get('agregar_pago_alquiler', {'id': self.alquiler.pk})


class ReportesSmoke(SmokeTestBase):
    """Todos los reportes — sin datos y con datos."""

    def test_dashboard(self):
        self._get('dashboard')

    def test_reporte_empleados(self):
        self._get('reporte_empleados')

    def test_reporte_clientes(self):
        self._get('reporte_clientes')

    def test_reporte_reparaciones(self):
        self._get('reporte_reparaciones')

    def test_reporte_ventas(self):
        self._get('reporte_ventas')

    def test_reporte_confecciones(self):
        self._get('reporte_confecciones')

    def test_reporte_alquileres(self):
        self._get('reporte_alquileres')

    def test_reporte_transacciones(self):
        self._get('reporte_transacciones')

    def test_reporte_inventario(self):
        self._get('reporte_inventario')

    def test_reporte_articulos(self):
        self._get('reporte_articulos')

    def test_reporte_stock(self):
        self._get('reporte_stock')

    def test_reporte_dias_trabajados(self):
        self._get('reporte_dias_trabajados')

    def test_resumen_caja(self):
        self._get('resumen_caja')

    def test_resumen_caja_con_filtros(self):
        self._get('resumen_caja', params='periodo=semana')

    def test_kardex_item(self):
        self._get('kardex_item', {'codigo_item': self.item.codigo_item})

    def test_kardex_inventario(self):
        self._get('kardex_inventario', {'prenda_id': self.prenda.pk})

    def test_kardex_financiero(self):
        self._get('kardex_financiero')

    def test_kardex_financiero_con_filtros(self):
        self._get('kardex_financiero', params='periodo=mes')


class AnaliticaSmoke(SmokeTestBase):
    """Vistas de analítica fase 2."""

    def test_analitica_items(self):
        self._get('analitica_items')

    def test_analitica_items_con_filtros(self):
        hoy = date.today().isoformat()
        self._get('analitica_items', params=f'fecha_inicio={hoy}&servicio=alquiler')

    def test_analitica_empleados(self):
        self._get('analitica_empleados')

    def test_analitica_clientes_ltv(self):
        self._get('analitica_clientes_ltv')

    def test_analitica_clientes_ltv_con_limit(self):
        self._get('analitica_clientes_ltv', params='limit=10')

    def test_analitica_operativas(self):
        self._get('analitica_operativas')

    def test_analitica_comparativas(self):
        self._get('analitica_comparativas')

    def test_analitica_comparativas_periodos(self):
        for periodo in ('this_month', 'last_month', 'this_quarter', 'this_year'):
            resp = self._get('analitica_comparativas', params=f'periodo={periodo}')
            self.assertNotEqual(resp.status_code, 500, f"500 en periodo={periodo}")

    def test_analitica_estacionalidad(self):
        self._get('analitica_estacionalidad')

    def test_analitica_prendas_temporada(self):
        self._get('analitica_prendas_temporada')


class AJAXEndpointsSmoke(SmokeTestBase):
    """Endpoints AJAX — deben devolver JSON, no 500."""

    def _assert_json(self, url_name, params=''):
        resp = self._get(url_name, params=params)
        self.assertIn('application/json', resp.get('Content-Type', ''))
        return resp

    def test_buscar_clientes_vacio(self):
        self._assert_json('buscar_clientes', 'q=')

    def test_buscar_clientes_con_q(self):
        self._assert_json('buscar_clientes', 'q=Maria')

    def test_buscar_empleados_vacio(self):
        self._assert_json('buscar_empleados', 'q=')

    def test_buscar_empleados_con_q(self):
        self._assert_json('buscar_empleados', 'q=Juan')

    def test_buscar_tipo_prenda(self):
        self._assert_json('buscar_tipo_prenda', 'q=Pan')

    def test_buscar_tipo_reparacion(self):
        self._assert_json('buscar_tipo_reparacion', 'q=')

    def test_buscar_estado_alquiler(self):
        self._assert_json('buscar_estado_alquiler', 'q=')

    def test_buscar_unidad_medida(self):
        self._assert_json('buscar_unidad_medida', 'q=')

    def test_buscar_tipo_contrato(self):
        self._assert_json('buscar_tipo_contrato', 'q=')

    def test_buscar_tipo_material(self):
        self._assert_json('buscar_tipo_material', 'q=')

    def test_buscar_ubicacion_item(self):
        self._assert_json('buscar_ubicacion_item', 'q=')

    def test_buscar_prenda_inventario(self):
        self._assert_json('buscar_prenda_inventario', 'q=Traje')

    def test_buscar_prenda_items(self):
        self._assert_json('buscar_prenda_items', 'q=')

    def test_buscar_confeccion(self):
        self._assert_json('buscar_confeccion', 'q=')

    def test_buscar_modelo_confeccion(self):
        self._assert_json('buscar_modelo_confeccion', 'q=')

    def test_get_precio_articulo(self):
        resp = self.client.get(
            reverse('get_precio_articulo') + f'?prenda_item_id={self.item.pk}'
        )
        self.assertNotEqual(resp.status_code, 500)


class IDInexistentesSmoke(SmokeTestBase):
    """Acceder a IDs que no existen → debe devolver 404, no 500."""

    def _assert_404(self, url_name, kwargs):
        url = reverse(url_name, kwargs=kwargs)
        resp = self.client.get(url)
        self.assertEqual(
            resp.status_code, 404,
            f"{url_name} con ID inexistente devolvió {resp.status_code}, esperaba 404"
        )

    def test_detalle_empleado_404(self):
        self._assert_404('detalle_empleado', {'id': 999999})

    def test_detalle_reparacion_404(self):
        self._assert_404('detalle_reparacion', {'id': 999999})

    def test_detalle_confeccion_404(self):
        self._assert_404('detalle_confeccion', {'id': 999999})

    def test_detalle_alquiler_404(self):
        self._assert_404('detalle_alquiler', {'id': 999999})

    def test_detalle_prenda_404(self):
        self._assert_404('detalle_prenda', {'id': 999999})

    def test_editar_empleado_404(self):
        self._assert_404('editar_empleado', {'id': 999999})

    def test_editar_reparacion_404(self):
        self._assert_404('editar_reparacion', {'id': 999999})

    def test_editar_alquiler_404(self):
        self._assert_404('editar_alquiler', {'id': 999999})

    def test_kardex_item_404(self):
        url = reverse('kardex_item', kwargs={'codigo_item': 'FAKE-999'})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
