"""
test_views_auth.py
===================
Verifica que todas las vistas protegidas redirigen a /login/ cuando
el usuario no está autenticado.

Las vistas públicas (buscar_clientes, buscar_empleados) se verifican
por separado (deben responder 200 sin login).
"""
from django.test import TestCase, Client
from django.urls import reverse


# URLs que requieren login — (url_name, kwargs o None)
PROTECTED_URLS = [
    ('dashboard',           None),
    ('lista_empleados',     None),
    ('crear_empleado',      None),
    ('lista_clientes',      None),
    ('crear_cliente',       None),
    ('lista_reparaciones',  None),
    ('crear_reparacion',    None),
    ('lista_ventas',        None),
    ('crear_venta',         None),
    ('lista_confecciones',  None),
    ('crear_confeccion',    None),
    ('lista_alquileres',    None),
    ('crear_alquiler',      None),
    ('lista_prendas',       None),
    ('crear_prenda',        None),
    ('lista_insumos',       None),
    ('crear_insumo',        None),
    ('lista_ordenes',       None),
    ('crear_orden',         None),
    ('lista_transacciones', None),
    ('crear_transaccion',   None),
    ('lista_movimientos_caja', None),
    ('lista_sesiones_caja', None),
    ('abrir_sesion_caja',   None),
    ('lista_tipo_gasto',    None),
    ('lista_conjuntos',     None),
    ('crear_conjunto',      None),
    ('reporte_empleados',   None),
    ('reporte_clientes',    None),
    ('reporte_reparaciones', None),
    ('reporte_ventas',      None),
    ('reporte_confecciones', None),
    ('reporte_alquileres',  None),
    ('resumen_caja',        None),
]


class ProtectedViewsRequireLoginTests(TestCase):
    """
    Sin estar logueado, todas las vistas protegidas deben devolver
    302 → /login/ (o la LOGIN_URL configurada).
    """

    def setUp(self):
        self.client = Client()

    def test_all_protected_urls_redirect_to_login(self):
        failed = []
        for url_name, kwargs in PROTECTED_URLS:
            try:
                url = reverse(url_name, kwargs=kwargs or {})
            except Exception as e:
                failed.append(f"reverse({url_name}) falló: {e}")
                continue

            resp = self.client.get(url)
            if resp.status_code not in (301, 302):
                failed.append(
                    f"{url_name} → status {resp.status_code} (esperaba 302)"
                )
                continue
            location = resp.get('Location', '')
            if 'login' not in location:
                failed.append(
                    f"{url_name} → redirige a '{location}' (esperaba /login/)"
                )

        if failed:
            self.fail(
                "Las siguientes vistas no redirigen a login:\n"
                + "\n".join(f"  • {msg}" for msg in failed)
            )


class PublicEndpointsTests(TestCase):
    """
    Algunos endpoints AJAX no requieren login (diseño intencional
    para permitir autocomplete desde formularios).
    """

    def setUp(self):
        self.client = Client()

    def test_buscar_clientes_sin_login_responde(self):
        """buscar_clientes no tiene @login_required — debe responder 200."""
        resp = self.client.get(reverse('buscar_clientes') + '?q=test')
        self.assertEqual(resp.status_code, 200)

    def test_buscar_clientes_devuelve_json(self):
        resp = self.client.get(reverse('buscar_clientes') + '?q=')
        self.assertEqual(resp['Content-Type'], 'application/json')


class AuthenticatedListViewsTests(TestCase):
    """Vistas de lista devuelven 200 cuando el usuario está autenticado."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('testviews', password='pass123')
        self.client = Client()
        self.client.force_login(self.user)

    def _assert_200(self, url_name, kwargs=None):
        url = reverse(url_name, kwargs=kwargs or {})
        resp = self.client.get(url)
        self.assertEqual(
            resp.status_code, 200,
            f"{url_name} devolvió {resp.status_code}, esperaba 200",
        )

    def test_dashboard(self):
        self._assert_200('dashboard')

    def test_lista_empleados(self):
        self._assert_200('lista_empleados')

    def test_lista_clientes(self):
        self._assert_200('lista_clientes')

    def test_lista_reparaciones(self):
        self._assert_200('lista_reparaciones')

    def test_lista_ventas(self):
        self._assert_200('lista_ventas')

    def test_lista_confecciones(self):
        self._assert_200('lista_confecciones')

    def test_lista_alquileres(self):
        self._assert_200('lista_alquileres')

    def test_lista_prendas(self):
        self._assert_200('lista_prendas')

    def test_lista_insumos(self):
        self._assert_200('lista_insumos')

    def test_lista_ordenes(self):
        self._assert_200('lista_ordenes')

    def test_lista_transacciones(self):
        self._assert_200('lista_transacciones')

    def test_lista_movimientos_caja(self):
        self._assert_200('lista_movimientos_caja')

    def test_lista_sesiones_caja(self):
        self._assert_200('lista_sesiones_caja')

    def test_lista_conjuntos(self):
        self._assert_200('lista_conjuntos')

    def test_reporte_empleados(self):
        self._assert_200('reporte_empleados')

    def test_reporte_clientes(self):
        self._assert_200('reporte_clientes')

    def test_reporte_reparaciones(self):
        self._assert_200('reporte_reparaciones')

    def test_reporte_ventas(self):
        self._assert_200('reporte_ventas')

    def test_reporte_alquileres(self):
        self._assert_200('reporte_alquileres')

    def test_reporte_confecciones(self):
        self._assert_200('reporte_confecciones')

    def test_reporte_transacciones(self):
        self._assert_200('reporte_transacciones')

    def test_reporte_inventario(self):
        self._assert_200('reporte_inventario')

    def test_resumen_caja(self):
        self._assert_200('resumen_caja')

    def test_crear_empleado_get(self):
        self._assert_200('crear_empleado')

    def test_crear_cliente_get(self):
        self._assert_200('crear_cliente')

    def test_crear_reparacion_get(self):
        self._assert_200('crear_reparacion')

    def test_crear_venta_get(self):
        self._assert_200('crear_venta')

    def test_crear_confeccion_get(self):
        self._assert_200('crear_confeccion')

    def test_crear_alquiler_get(self):
        self._assert_200('crear_alquiler')

    def test_crear_prenda_get(self):
        self._assert_200('crear_prenda')

    def test_crear_insumo_get(self):
        self._assert_200('crear_insumo')

    def test_crear_orden_get(self):
        self._assert_200('crear_orden')
