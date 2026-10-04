"""
Verifica que un usuario sin el permiso requerido reciba la página 403
estilizada (misastreria/templates/403.html), no el error crudo de Django.
"""
from django.test import TestCase
from django.urls import reverse

from .factories import make_taller


class Pagina403Tests(TestCase):
    def setUp(self):
        self.client.force_login(make_taller())  # Taller no tiene view_empleado

    def test_403_usa_template_propio(self):
        resp = self.client.get(reverse('lista_empleados'))
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, '403.html')
        self.assertContains(resp, 'permiso', status_code=403)
