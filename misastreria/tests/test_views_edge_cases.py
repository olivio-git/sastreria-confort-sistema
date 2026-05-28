"""
test_views_edge_cases.py
=========================
Tests agresivos de edge cases en vistas:
  - POSTs con datos inválidos/incompletos
  - Parámetros GET malformados (fechas, IDs, strings raros)
  - Filtros que no deberían romper la app
  - Comportamientos post-estado (eliminar algo ya entregado, etc.)
  - Exportaciones PDF/Excel con y sin datos
  - Endpoints que reciben parámetros numéricos inválidos
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from .factories import (
    make_user, make_empleado, make_cliente, make_reparacion,
    make_reparacion_item, make_venta, make_confeccion, make_alquiler,
    make_prenda, make_prenda_item, make_sesion_caja, make_movimiento_caja,
    make_tipo_gasto, make_tipo_prenda, make_tipo_reparacion,
)
from misastreria.models import (
    Reparacion, Confeccion, Alquiler, CajaMovimiento,
    PrendaItem, Insumo, Transaccion,
)


class EdgeCaseBase(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)

    def _get(self, url_name, kwargs=None, params=''):
        url = reverse(url_name, kwargs=kwargs or {})
        if params:
            url = f"{url}?{params}"
        return self.client.get(url)

    def _post(self, url_name, data, kwargs=None):
        url = reverse(url_name, kwargs=kwargs or {})
        return self.client.post(url, data, follow=True)


# ─────────────────────────────────────────────────────────────────────────────
# Filtros con parámetros malformados
# ─────────────────────────────────────────────────────────────────────────────

class FiltrosMalformadosTests(EdgeCaseBase):
    """Los filtros con parámetros inválidos no deben crashear el servidor."""

    def _assert_no_500(self, url_name, params):
        resp = self._get(url_name, params=params)
        self.assertNotEqual(resp.status_code, 500, f"{url_name}?{params} devolvió 500")

    def test_lista_reparaciones_fecha_invalida(self):
        self._assert_no_500('lista_reparaciones', 'desde=not-a-date&hasta=also-invalid')

    def test_lista_ventas_fecha_invalida(self):
        self._assert_no_500('lista_ventas', 'desde=2024-13-99&hasta=0000-00-00')

    def test_lista_confecciones_fecha_invalida(self):
        self._assert_no_500('lista_confecciones', 'desde=abc&hasta=xyz')

    def test_lista_alquileres_fecha_invalida(self):
        self._assert_no_500('lista_alquileres', 'desde=&hasta=')

    def test_lista_prendas_estado_invalido(self):
        self._assert_no_500('lista_prendas', 'estado=INVALIDO')

    def test_lista_movimientos_concepto_invalido(self):
        self._assert_no_500('lista_movimientos_caja', 'concepto=inexistente')

    def test_lista_transacciones_tipo_invalido(self):
        self._assert_no_500('lista_transacciones', 'tipo=XYZ')

    def test_reporte_reparaciones_fechas_invalidas(self):
        self._assert_no_500('reporte_reparaciones', 'fecha_inicio=abc&fecha_fin=xyz')

    def test_reporte_ventas_fechas_invalidas(self):
        self._assert_no_500('reporte_ventas', 'fecha_inicio=2024-99-99')

    def test_reporte_alquileres_fechas_invalidas(self):
        self._assert_no_500('reporte_alquileres', 'fecha_inicio=&fecha_fin=')

    def test_analitica_items_fecha_invalida(self):
        self._assert_no_500('analitica_items', 'fecha_inicio=not-a-date')

    def test_analitica_comparativas_periodo_invalido(self):
        self._assert_no_500('analitica_comparativas', 'periodo=raro_inexistente')

    def test_analitica_clientes_limit_invalido(self):
        self._assert_no_500('analitica_clientes_ltv', 'limit=abc')

    def test_analitica_clientes_limit_negativo(self):
        self._assert_no_500('analitica_clientes_ltv', 'limit=-999')

    def test_analitica_clientes_limit_enorme(self):
        self._assert_no_500('analitica_clientes_ltv', 'limit=999999')

    def test_lista_prendas_pagina_invalida(self):
        self._assert_no_500('lista_prendas', 'page=abc')

    def test_lista_prendas_pagina_negativa(self):
        self._assert_no_500('lista_prendas', 'page=-1')

    def test_lista_prendas_pagina_enorme(self):
        self._assert_no_500('lista_prendas', 'page=99999')

    def test_resumen_caja_fecha_invalida(self):
        self._assert_no_500('resumen_caja', 'desde=not-a-date&hasta=invalid')


# ─────────────────────────────────────────────────────────────────────────────
# POSTs con datos inválidos / incompletos
# ─────────────────────────────────────────────────────────────────────────────

class PostsInvalidosTests(EdgeCaseBase):
    """POSTs con datos incompletos no deben crashear — deben mostrar form con errores."""

    def test_crear_empleado_sin_datos_no_500(self):
        resp = self._post('crear_empleado', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_cliente_sin_datos_no_500(self):
        resp = self._post('crear_cliente', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_reparacion_sin_datos_no_500(self):
        resp = self._post('crear_reparacion', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_confeccion_sin_datos_no_500(self):
        resp = self._post('crear_confeccion', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_alquiler_sin_datos_no_500(self):
        resp = self._post('crear_alquiler', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_prenda_sin_datos_no_500(self):
        resp = self._post('crear_prenda', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_insumo_sin_datos_no_500(self):
        resp = self._post('crear_insumo', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_movimiento_caja_sin_datos_no_500(self):
        resp = self._post('crear_movimiento_caja', {})
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_empleado_celular_invalido_no_500(self):
        resp = self._post('crear_empleado', {
            'nombres': 'Luis',
            'apellido_paterno': 'Test',
            'celular': 'no-es-numero',
            'fecha_ingreso': date.today().isoformat(),
        })
        self.assertNotEqual(resp.status_code, 500)

    def test_crear_transaccion_monto_negativo_no_500(self):
        resp = self._post('crear_transaccion', {
            'tipo_transaccion': 'ingreso',
            'descripcion': 'Test',
            'tipo_servicio': 'otros',
            'cantidad': '1',
            'monto': '-50.00',
        })
        self.assertNotEqual(resp.status_code, 500)

    def test_abrir_sesion_monto_negativo_no_500(self):
        resp = self._post('abrir_sesion_caja', {'monto_apertura': '-100'})
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Acciones de estado (marcar en_proceso, entregar, devolver)
# ─────────────────────────────────────────────────────────────────────────────

class AccionesEstadoTests(EdgeCaseBase):

    def test_marcar_reparacion_en_proceso_dos_veces(self):
        rep = make_reparacion()
        self._post('reparacion_en_proceso', {}, kwargs={'id': rep.pk})
        resp = self._post('reparacion_en_proceso', {}, kwargs={'id': rep.pk})
        # No debe crashear — puede dar 302 o 200
        self.assertNotEqual(resp.status_code, 500)

    def test_marcar_reparacion_entregada_dos_veces(self):
        rep = make_reparacion()
        self._post('marcar_entregado', {}, kwargs={'id': rep.pk})
        resp = self._post('marcar_entregado', {}, kwargs={'id': rep.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_marcar_confeccion_en_proceso(self):
        conf = make_confeccion()
        resp = self._post('confeccion_en_proceso', {}, kwargs={'id': conf.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_entregar_confeccion(self):
        conf = make_confeccion()
        resp = self._post('entregar_confeccion', {}, kwargs={'id': conf.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_devolver_alquiler(self):
        sesion = make_sesion_caja()
        alquiler = make_alquiler(estado='alquilado')
        pi = make_prenda_item(estado='alquilado')
        from misastreria.models import AlquilerItem
        AlquilerItem.objects.create(
            alquiler=alquiler, prenda_item=pi,
            precio_unitario=Decimal('100'), precio_reparacion=Decimal('0'),
        )
        resp = self._post('devolver_alquiler', {}, kwargs={'id': alquiler.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_avanzar_orden_estado_terminado_no_avanza(self):
        orden = Insumo.objects.create(articulo='Test')
        from misastreria.models import OrdenProduccion
        op = OrdenProduccion.objects.create(
            descripcion='Op terminada', tipo='stock', estado='terminado'
        )
        resp = self._post('avanzar_estado_orden', {}, kwargs={'id': op.pk})
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Eliminación de objetos
# ─────────────────────────────────────────────────────────────────────────────

class EliminacionTests(EdgeCaseBase):

    def test_eliminar_reparacion_no_500(self):
        rep = make_reparacion()
        resp = self._post('eliminar_reparacion', {}, kwargs={'id': rep.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_eliminar_reparacion_elimina_objeto(self):
        rep = make_reparacion()
        pk = rep.pk
        self._post('eliminar_reparacion', {}, kwargs={'id': pk})
        self.assertFalse(Reparacion.objects.filter(pk=pk).exists())

    def test_eliminar_confeccion(self):
        conf = make_confeccion()
        pk = conf.pk
        resp = self._post('eliminar_confeccion', {}, kwargs={'id': pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_eliminar_alquiler(self):
        sesion = make_sesion_caja()
        alquiler = make_alquiler()
        pk = alquiler.pk
        resp = self._post('eliminar_alquiler', {}, kwargs={'id': pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_eliminar_venta(self):
        sesion = make_sesion_caja()
        venta = make_venta()
        pk = venta.pk
        resp = self._post('eliminar_venta', {}, kwargs={'id': pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_eliminar_empleado(self):
        emp = make_empleado()
        pk = emp.pk
        resp = self._post('eliminar_empleado', {}, kwargs={'id': pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_eliminar_cliente(self):
        cli = make_cliente()
        pk = cli.pk
        resp = self._post('eliminar_cliente', {}, kwargs={'id': pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_eliminar_prenda_sin_items(self):
        prenda = make_prenda()
        pk = prenda.pk
        resp = self._post('eliminar_prenda', {}, kwargs={'id': pk})
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Pagos con montos extremos
# ─────────────────────────────────────────────────────────────────────────────

class PagosMontosExtremosTests(EdgeCaseBase):

    def setUp(self):
        super().setUp()
        self.sesion = make_sesion_caja()

    def test_pago_reparacion_monto_cero_no_500(self):
        rep = make_reparacion()
        resp = self._post('agregar_pago_reparacion', {
            'monto': '0',
            'forma_pago': 'efectivo',
            'descripcion': 'Pago cero',
        }, kwargs={'id': rep.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_pago_reparacion_monto_negativo_no_500(self):
        rep = make_reparacion()
        resp = self._post('agregar_pago_reparacion', {
            'monto': '-100',
            'forma_pago': 'efectivo',
        }, kwargs={'id': rep.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_pago_reparacion_monto_texto_no_500(self):
        rep = make_reparacion()
        resp = self._post('agregar_pago_reparacion', {
            'monto': 'no-es-numero',
            'forma_pago': 'efectivo',
        }, kwargs={'id': rep.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_pago_confeccion_monto_vacio_no_500(self):
        conf = make_confeccion()
        resp = self._post('agregar_pago_confeccion', {
            'monto': '',
            'forma_pago': 'efectivo',
        }, kwargs={'id': conf.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_pago_alquiler_monto_enorme_no_500(self):
        alquiler = make_alquiler()
        resp = self._post('agregar_pago_alquiler', {
            'monto': '99999999.99',
            'forma_pago': 'efectivo',
            'descripcion': 'Pago enorme',
        }, kwargs={'id': alquiler.pk})
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Exportaciones PDF/Excel — no deben crashear aunque haya pocos datos
# ─────────────────────────────────────────────────────────────────────────────

class ExportacionesTests(EdgeCaseBase):

    def _assert_export_no_500(self, url_name, params=''):
        url = reverse(url_name)
        if params:
            url = f"{url}?{params}"
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 500, f"Export {url_name} devolvió 500")

    def test_export_empleados_pdf(self):
        self._assert_export_no_500('exportar_empleados_pdf')

    def test_export_empleados_excel(self):
        self._assert_export_no_500('exportar_empleados_excel')

    def test_export_reparaciones_pdf(self):
        # exportar_reparaciones_pdf is a helper called from reporte_reparaciones,
        # not a standalone view — test via report view with export_format param
        self._assert_export_no_500('reporte_reparaciones', 'export_format=pdf')

    def test_export_reparaciones_excel(self):
        self._assert_export_no_500('reporte_reparaciones', 'export_format=excel')

    def test_reporte_ventas_export_pdf(self):
        self._assert_export_no_500('reporte_ventas', 'export_format=pdf')

    def test_reporte_ventas_export_excel(self):
        self._assert_export_no_500('reporte_ventas', 'export_format=excel')

    def test_reporte_alquileres_export_pdf(self):
        self._assert_export_no_500('reporte_alquileres', 'export_format=pdf')

    def test_reporte_alquileres_export_excel(self):
        self._assert_export_no_500('reporte_alquileres', 'export_format=excel')

    def test_reporte_confecciones_export_pdf(self):
        self._assert_export_no_500('reporte_confecciones', 'export_format=pdf')

    def test_reporte_reparaciones_export_pdf(self):
        self._assert_export_no_500('reporte_reparaciones', 'export_format=pdf')

    def test_export_resumen_caja_pdf(self):
        self._assert_export_no_500('export_resumen_caja_pdf')

    def test_export_resumen_caja_excel(self):
        self._assert_export_no_500('export_resumen_caja_excel')


# ─────────────────────────────────────────────────────────────────────────────
# Revertir movimientos de caja
# ─────────────────────────────────────────────────────────────────────────────

class RevertirMovimientoTests(EdgeCaseBase):

    def test_revertir_movimiento_manual(self):
        sesion = make_sesion_caja()
        mov = make_movimiento_caja(sesion=sesion)
        resp = self._post('revertir_movimiento_caja', {}, kwargs={'pk': mov.pk})
        self.assertNotEqual(resp.status_code, 500)

    def test_revertir_movimiento_ya_reversado_no_500(self):
        sesion = make_sesion_caja()
        mov = make_movimiento_caja(sesion=sesion)
        # Reversarlo una vez
        self._post('revertir_movimiento_caja', {}, kwargs={'pk': mov.pk})
        # Intentar reversarlo de nuevo
        resp = self._post('revertir_movimiento_caja', {}, kwargs={'pk': mov.pk})
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard con base de datos vacía
# ─────────────────────────────────────────────────────────────────────────────

class DashboardVacioTests(TestCase):
    """El dashboard debe funcionar incluso con BD completamente vacía."""

    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_bd_vacia(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertNotEqual(resp.status_code, 500)

    def test_resumen_caja_sin_sesion(self):
        resp = self.client.get(reverse('resumen_caja'))
        self.assertNotEqual(resp.status_code, 500)

    def test_kardex_financiero_bd_vacia(self):
        resp = self.client.get(reverse('kardex_financiero'))
        self.assertNotEqual(resp.status_code, 500)

    def test_analitica_items_sin_datos(self):
        resp = self.client.get(reverse('analitica_items'))
        self.assertNotEqual(resp.status_code, 500)

    def test_analitica_operativas_sin_datos(self):
        resp = self.client.get(reverse('analitica_operativas'))
        self.assertNotEqual(resp.status_code, 500)

    def test_analitica_comparativas_sin_datos(self):
        resp = self.client.get(reverse('analitica_comparativas'))
        self.assertNotEqual(resp.status_code, 500)

    def test_lista_reparaciones_sin_datos(self):
        resp = self.client.get(reverse('lista_reparaciones'))
        self.assertNotEqual(resp.status_code, 500)

    def test_reporte_reparaciones_sin_datos(self):
        resp = self.client.get(reverse('reporte_reparaciones'))
        self.assertNotEqual(resp.status_code, 500)

    def test_reporte_ventas_sin_datos(self):
        resp = self.client.get(reverse('reporte_ventas'))
        self.assertNotEqual(resp.status_code, 500)

    def test_reporte_alquileres_sin_datos(self):
        resp = self.client.get(reverse('reporte_alquileres'))
        self.assertNotEqual(resp.status_code, 500)

    def test_reporte_confecciones_sin_datos(self):
        resp = self.client.get(reverse('reporte_confecciones'))
        self.assertNotEqual(resp.status_code, 500)
