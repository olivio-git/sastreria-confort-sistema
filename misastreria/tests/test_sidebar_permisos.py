"""
Scenarios: Navbar Visibility (cosmética) — spec roles-permisos.

El sidebar oculta módulos sin permiso, pero NO es el límite de seguridad:
la URL directa sigue devolviendo 403 (ya cubierto en test_roles_matriz.py).
"""
from django.test import TestCase
from django.urls import reverse

from .factories import make_vendedor


class SidebarVisibilidadTests(TestCase):
    def test_vendedor_sin_permiso_no_ve_empleados_en_sidebar(self):
        """El link de Empleados en el sidebar (`sc-nav-label`) desaparece.

        Ojo: el dashboard también tiene una fila de "Accesos rápidos" con
        tarjetas separadas del sidebar (fuera del alcance de este cambio,
        sección propia de dashboard.html) — por eso se busca el marcador
        específico del sidebar (`sc-nav-label`) y no el href pelado.
        """
        vendedor = make_vendedor()
        self.assertFalse(vendedor.has_perm('misastreria.view_empleado'))
        self.client.force_login(vendedor)
        resp = self.client.get(reverse('dashboard'))
        self.assertNotContains(resp, '<span class="sc-nav-label">Empleados</span>')

    def test_vendedor_sin_permiso_recibe_403_por_url_directa(self):
        """La ocultación del sidebar no reemplaza el control real."""
        self.client.force_login(make_vendedor())
        resp = self.client.get(reverse('lista_empleados'))
        self.assertEqual(resp.status_code, 403)
