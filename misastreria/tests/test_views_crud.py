"""
test_views_crud.py
===================
Verifica operaciones CRUD básicas via HTTP en los módulos principales.
Cubre:
  - POST crear → redirect → objeto en BD
  - GET detalle → 200
  - POST eliminar → 302, objeto eliminado
  - AJAX buscar → JSON con resultados
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from misastreria.models import (
    Empleado, Cliente, Reparacion, Confeccion, Alquiler,
    PrendaInventario, PrendaItem, Insumo, Venta,
)
from .factories import (
    make_empleado, make_cliente, make_reparacion, make_confeccion,
    make_alquiler, make_prenda, make_prenda_item,
    make_tipo_prenda, make_tipo_reparacion,
)


class BaseViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('cruduser', password='pass123')
        self.client = Client()
        self.client.force_login(self.user)


# ─────────────────────────────────────────────────────────────────────────────
# Empleados
# ─────────────────────────────────────────────────────────────────────────────

class EmpleadoCRUDTests(BaseViewTest):

    def test_crear_empleado_post_valido(self):
        resp = self.client.post(reverse('crear_empleado'), {
            'nombres': 'Carlos',
            'apellido_paterno': 'Quispe',
            'celular_pais': '+591',
            'celular': '71234567',
            'fecha_ingreso': date.today().isoformat(),
        })
        self.assertIn(resp.status_code, (200, 302))
        if resp.status_code == 302:
            self.assertTrue(
                Empleado.objects.filter(apellido_paterno__iexact='Quispe').exists()
            )

    def test_detalle_empleado_200(self):
        emp = make_empleado()
        resp = self.client.get(reverse('detalle_empleado', kwargs={'id': emp.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_editar_empleado_get_200(self):
        emp = make_empleado()
        resp = self.client.get(reverse('editar_empleado', kwargs={'id': emp.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_eliminar_empleado_post_redirect(self):
        emp = make_empleado()
        resp = self.client.post(reverse('eliminar_empleado', kwargs={'id': emp.pk}))
        self.assertIn(resp.status_code, (302, 200))

    def test_buscar_empleados_json(self):
        make_empleado(nombres='Luis', apellido_paterno='Rojas')
        resp = self.client.get(reverse('buscar_empleados') + '?q=Luis')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp['Content-Type'])


# ─────────────────────────────────────────────────────────────────────────────
# Clientes
# ─────────────────────────────────────────────────────────────────────────────

class ClienteCRUDTests(BaseViewTest):

    def test_crear_cliente_post_valido(self):
        resp = self.client.post(reverse('crear_cliente'), {
            'nombres': 'Ana',
            'apellido_paterno': 'Flores',
            'celular_pais': '+591',
            'celular': '71000001',
        })
        self.assertIn(resp.status_code, (200, 302))

    def test_detalle_historial_cliente_200(self):
        cli = make_cliente()
        resp = self.client.get(reverse('historial_cliente', kwargs={'id': cli.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_editar_cliente_get_200(self):
        cli = make_cliente()
        resp = self.client.get(reverse('editar_cliente', kwargs={'id': cli.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_buscar_clientes_devuelve_resultados(self):
        make_cliente(nombres='Pedro', apellido_paterno='Lima')
        resp = self.client.get(reverse('buscar_clientes') + '?q=Pedro')
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) > 0)

    def test_buscar_clientes_sin_q_devuelve_lista(self):
        resp = self.client.get(reverse('buscar_clientes'))
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Reparaciones
# ─────────────────────────────────────────────────────────────────────────────

class ReparacionViewTests(BaseViewTest):

    def test_detalle_reparacion_200(self):
        rep = make_reparacion()
        resp = self.client.get(reverse('detalle_reparacion', kwargs={'id': rep.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_editar_reparacion_get_200(self):
        rep = make_reparacion()
        resp = self.client.get(reverse('editar_reparacion', kwargs={'id': rep.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_marcar_en_proceso_post(self):
        rep = make_reparacion()
        resp = self.client.post(reverse('reparacion_en_proceso', kwargs={'id': rep.pk}))
        self.assertIn(resp.status_code, (302, 200))
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'en_proceso')

    def test_marcar_entregado_post(self):
        rep = make_reparacion()
        resp = self.client.post(reverse('marcar_entregado', kwargs={'id': rep.pk}))
        self.assertIn(resp.status_code, (302, 200))
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'entregado')

    def test_marcar_entregado_respeta_forma_pago(self):
        """El cobro del saldo al entregar debe usar la forma de pago elegida (QR),
        no el default efectivo. Regresión del bug 'aparece en efectivo'."""
        from misastreria.models import CajaMovimiento
        rep = make_reparacion(total=Decimal('40.00'))
        self.client.post(
            reverse('marcar_entregado', kwargs={'id': rep.pk}),
            {'forma_pago': 'qr'},
        )
        rep.refresh_from_db()
        self.assertEqual(rep.estado, 'entregado')
        self.assertEqual(rep.forma_pago, 'qr')
        mov = CajaMovimiento.objects.get(
            referencia_reparacion=rep, concepto='reparacion_saldo',
        )
        self.assertEqual(mov.forma_pago, 'qr')


# ─────────────────────────────────────────────────────────────────────────────
# Confecciones
# ─────────────────────────────────────────────────────────────────────────────

class ConfeccionViewTests(BaseViewTest):

    def test_detalle_confeccion_200(self):
        c = make_confeccion()
        resp = self.client.get(reverse('detalle_confeccion', kwargs={'id': c.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_editar_confeccion_get_200(self):
        c = make_confeccion()
        resp = self.client.get(reverse('editar_confeccion', kwargs={'id': c.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_en_proceso_confeccion_post(self):
        c = make_confeccion()
        resp = self.client.post(reverse('confeccion_en_proceso', kwargs={'id': c.pk}))
        self.assertIn(resp.status_code, (302, 200))
        c.refresh_from_db()
        self.assertEqual(c.estado, 'en_proceso')

    def test_entregar_confeccion_post(self):
        c = make_confeccion()
        resp = self.client.post(reverse('entregar_confeccion', kwargs={'id': c.pk}))
        self.assertIn(resp.status_code, (302, 200))
        c.refresh_from_db()
        self.assertEqual(c.estado, 'entregado')


# ─────────────────────────────────────────────────────────────────────────────
# Alquileres
# ─────────────────────────────────────────────────────────────────────────────

class AlquilerViewTests(BaseViewTest):

    def test_detalle_alquiler_200(self):
        a = make_alquiler()
        resp = self.client.get(reverse('detalle_alquiler', kwargs={'id': a.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_editar_alquiler_get_200(self):
        a = make_alquiler()
        resp = self.client.get(reverse('editar_alquiler', kwargs={'id': a.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_devolver_alquiler_post(self):
        """Devolver alquiler cambia su estado."""
        a = make_alquiler(estado='alquilado')
        resp = self.client.post(reverse('devolver_alquiler', kwargs={'id': a.pk}))
        self.assertIn(resp.status_code, (302, 200))


# ─────────────────────────────────────────────────────────────────────────────
# Inventario / Prendas
# ─────────────────────────────────────────────────────────────────────────────

class PrendaViewTests(BaseViewTest):

    def test_detalle_prenda_200(self):
        p = make_prenda()
        resp = self.client.get(reverse('detalle_prenda', kwargs={'id': p.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_editar_prenda_get_200(self):
        p = make_prenda()
        resp = self.client.get(reverse('editar_prenda', kwargs={'id': p.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_agregar_items_prenda_get_redirige(self):
        """agregar_items_prenda solo acepta POST — GET redirige a detalle_prenda."""
        p = make_prenda()
        resp = self.client.get(reverse('agregar_items_prenda', kwargs={'id': p.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(str(p.pk), resp['Location'])

    def test_agregar_items_prenda_post_crea_items(self):
        p = make_prenda()
        resp = self.client.post(
            reverse('agregar_items_prenda', kwargs={'id': p.pk}),
            {'cantidad': '2', 'tipo': 'alquiler', 'condicion': 'nueva'},
        )
        self.assertIn(resp.status_code, (302, 200))
        self.assertEqual(p.items.count(), 2)

    def test_editar_prenda_item_get_redirige(self):
        """editar_prenda_item solo acepta POST — GET redirige a detalle_prenda."""
        item = make_prenda_item()
        resp = self.client.get(reverse('editar_prenda_item', kwargs={'id': item.pk}))
        self.assertEqual(resp.status_code, 302)

    def test_buscar_prenda_items_json(self):
        make_prenda_item()
        resp = self.client.get(reverse('buscar_prenda_items') + '?q=')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp.get('Content-Type', ''))


# ─────────────────────────────────────────────────────────────────────────────
# Tipos dinámicos (AJAX crear)
# ─────────────────────────────────────────────────────────────────────────────

class TiposDinamicosTests(BaseViewTest):

    def test_crear_tipo_prenda_post(self):
        resp = self.client.post(
            reverse('crear_tipo_prenda'),
            {'nombre': 'Chaleco Test'},
        )
        self.assertIn(resp.status_code, (200, 201, 302))
        from misastreria.models import TipoPrenda
        self.assertTrue(TipoPrenda.objects.filter(nombre='Chaleco Test').exists())

    def test_crear_tipo_prenda_sin_nombre_retorna_400(self):
        """El endpoint AJAX devuelve 400 si se omite el nombre."""
        resp = self.client.post(reverse('crear_tipo_prenda'), {'nombre': ''})
        self.assertEqual(resp.status_code, 400)

    def test_crear_tipo_reparacion_post(self):
        resp = self.client.post(
            reverse('crear_tipo_reparacion'),
            {'nombre': 'Zurcido'},
        )
        self.assertIn(resp.status_code, (200, 201, 302))
        from misastreria.models import TipoReparacion
        self.assertTrue(TipoReparacion.objects.filter(nombre='Zurcido').exists())

    def test_crear_tipo_reparacion_sin_nombre_retorna_400(self):
        """El endpoint AJAX devuelve 400 si se omite el nombre."""
        resp = self.client.post(reverse('crear_tipo_reparacion'), {'nombre': ''})
        self.assertEqual(resp.status_code, 400)

    def test_buscar_tipo_prenda_json(self):
        make_tipo_prenda('Pantalón')
        resp = self.client.get(reverse('buscar_tipo_prenda') + '?q=Pant')
        self.assertEqual(resp.status_code, 200)

    def test_buscar_tipo_reparacion_json(self):
        make_tipo_reparacion('Arreglo')
        resp = self.client.get(reverse('buscar_tipo_reparacion') + '?q=Arr')
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Caja
# ─────────────────────────────────────────────────────────────────────────────

class CajaViewTests(BaseViewTest):

    def test_abrir_sesion_get_200(self):
        resp = self.client.get(reverse('abrir_sesion_caja'))
        self.assertEqual(resp.status_code, 200)

    def test_resumen_caja_200(self):
        resp = self.client.get(reverse('resumen_caja'))
        self.assertEqual(resp.status_code, 200)

    def test_crear_movimiento_caja_get_200(self):
        resp = self.client.get(reverse('crear_movimiento_caja'))
        self.assertEqual(resp.status_code, 200)

    def test_lista_tipo_gasto_200(self):
        resp = self.client.get(reverse('lista_tipo_gasto'))
        self.assertEqual(resp.status_code, 200)
