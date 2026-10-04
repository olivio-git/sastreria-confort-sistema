"""
Cobertura de misastreria/permisos.py — los decoradores base de autorización.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from misastreria.permisos import permission_required, any_permission_required
from .factories import make_user


def _vista_base(request):
    return HttpResponse('ok')


class PermissionRequiredTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_marca_permisos_requeridos_all(self):
        vista = permission_required('misastreria.add_cliente')(_vista_base)
        self.assertEqual(vista._permisos_requeridos, (('misastreria.add_cliente',), 'all'))

    def test_usuario_con_permiso_pasa(self):
        vista = permission_required('misastreria.add_cliente')(_vista_base)
        user = make_user(username='con_permiso', role='Cajero')  # Cajero tiene add_cliente
        request = self.factory.get('/x')
        request.user = user
        resp = vista(request)
        self.assertEqual(resp.status_code, 200)

    def test_usuario_sin_permiso_403(self):
        vista = permission_required('misastreria.add_cliente')(_vista_base)
        user = make_user(username='sin_permiso', role='Taller')  # Taller no tiene add_cliente
        request = self.factory.get('/x')
        request.user = user
        with self.assertRaises(PermissionDenied):
            vista(request)

    def test_requiere_todos_los_permisos_and(self):
        vista = permission_required('misastreria.add_cliente', 'misastreria.gestionar_usuarios')(_vista_base)
        user = make_user(username='parcial', role='Cajero')  # tiene add_cliente pero no gestionar_usuarios
        request = self.factory.get('/x')
        request.user = user
        with self.assertRaises(PermissionDenied):
            vista(request)


class AnyPermissionRequiredTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_marca_permisos_requeridos_any(self):
        vista = any_permission_required('misastreria.add_reparacion', 'misastreria.add_venta')(_vista_base)
        self.assertEqual(
            vista._permisos_requeridos,
            (('misastreria.add_reparacion', 'misastreria.add_venta'), 'any'),
        )

    def test_pasa_con_al_menos_uno(self):
        vista = any_permission_required('misastreria.add_reparacion', 'misastreria.add_venta')(_vista_base)
        user = make_user(username='cajero_or', role='Cajero')
        request = self.factory.get('/x')
        request.user = user
        resp = vista(request)
        self.assertEqual(resp.status_code, 200)

    def test_403_sin_ninguno(self):
        vista = any_permission_required('misastreria.add_reparacion', 'misastreria.add_venta')(_vista_base)
        user = make_user(username='taller_or', role='Taller')
        request = self.factory.get('/x')
        request.user = user
        with self.assertRaises(PermissionDenied):
            vista(request)


class ComposicionConLoginRequiredTests(TestCase):
    """La marca sobrevive cuando login_required envuelve por afuera (regla de
    armado del decorador: login_required siempre afuera)."""

    def test_marca_sobrevive_bajo_login_required(self):
        vista = login_required(permission_required('misastreria.add_cliente')(_vista_base))
        self.assertEqual(vista._permisos_requeridos, (('misastreria.add_cliente',), 'all'))
