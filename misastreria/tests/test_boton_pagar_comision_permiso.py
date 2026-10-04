"""El botón y el modal de "Pagar comisión" en el detalle del empleado sólo se
muestran con `change_empleado` (la vista `pagar_comision_empleado` lo exige);
con sólo `view_empleado` el formulario terminaba en un 403 (verify ronda 6, S2).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from misastreria.models import ReparacionEmpleado
from .factories import (
    make_administrador, make_empleado, make_reparacion,
)


class BotonPagarComisionPermisoTests(TestCase):
    def setUp(self):
        self.empleado = make_empleado()
        rep = make_reparacion(total=Decimal('100'), fecha_entrega=date.today() - timedelta(days=3))
        ReparacionEmpleado.objects.create(
            reparacion=rep, empleado=self.empleado, monto_comision_fijo=Decimal('100'))
        self.url = reverse('detalle_empleado', kwargs={'id': self.empleado.id})

    def _solo_lectura(self):
        user = User.objects.create_user('lector', password='pw')
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label='misastreria', codename='view_empleado'))
        return User.objects.get(pk=user.pk)

    def test_solo_view_empleado_no_ve_el_boton_ni_el_formulario(self):
        self.client.force_login(self._solo_lectura())
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'modalPagarComision')
        self.assertNotContains(resp, reverse('pagar_comision_empleado', args=[self.empleado.id]))

    def test_con_change_empleado_los_ve(self):
        self.client.force_login(make_administrador(username='adm_btn'))
        resp = self.client.get(self.url)
        self.assertContains(resp, 'data-bs-target="#modalPagarComision"')
        self.assertContains(resp, reverse('pagar_comision_empleado', args=[self.empleado.id]))
