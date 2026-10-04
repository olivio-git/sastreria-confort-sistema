"""Admin de Empleado con cambio de usuario en el mismo guardado (verify ronda 7, W1)."""
import logging
from datetime import date
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.db import OperationalError, connection
from django.test import TestCase
from django.urls import reverse

from misastreria import views_usuarios
from misastreria.forms import EmpleadoForm
from misastreria.models import Empleado, es_ultimo_administrador_activo

from .factories import (
    make_administrador, make_cajero, make_empleado, make_vendedor,
)


class _AdminEmpleadoBase(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser('super', 's@x.com', 'pw')
        self.client.force_login(self.su)

    def _post(self, emp, **extra):
        d = {
            'ci': emp.ci or '', 'nombres': emp.nombres,
            'apellido_paterno': emp.apellido_paterno, 'apellido_materno': '',
            'celular': '+59171234567', 'activo': 'on',
            'fecha_ingreso': emp.fecha_ingreso.isoformat(),
            'user': emp.user_id or '',
            'fecha_baja': emp.fecha_baja.isoformat() if emp.fecha_baja else '',
        }
        d.update(extra)
        return self.client.post(
            reverse('admin:misastreria_empleado_change', args=[emp.pk]), d)


class W1AdminCambioDeUsuarioTests(_AdminEmpleadoBase):
    def test_vincular_ultimo_admin_y_dar_baja_en_el_mismo_post(self):
        unico = make_administrador(username='unico')
        User.objects.filter(pk=self.su.pk).update(is_active=True)
        emp = make_empleado(nombres='Nadie', ci='9')
        r = self._post(emp, user=unico.pk, fecha_baja='2026-01-10')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'último Administrador')
        unico.refresh_from_db()
        self.assertTrue(unico.is_active)
        emp.refresh_from_db()
        self.assertIsNone(emp.user_id)

    def test_vincular_ultimo_admin_a_empleado_ya_dado_de_baja(self):
        unico = make_administrador(username='unico')
        emp = make_empleado(nombres='Ex', ci='8', fecha_baja=date(2025, 1, 1))
        r = self._post(emp, user=unico.pk)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'último Administrador')
        unico.refresh_from_db()
        self.assertTrue(unico.is_active)

    def test_superusuario_no_se_desactiva_vinculandose_a_un_empleado_de_baja(self):
        make_administrador(username='otro')
        emp = make_empleado(nombres='Ex', ci='7', fecha_baja=date(2025, 1, 1))
        r = self._post(emp, user=self.su.pk)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'tu propio usuario')
        self.su.refresh_from_db()
        self.assertTrue(self.su.is_active)

    def test_vincular_admin_no_ultimo_a_empleado_de_baja_sigue_permitido(self):
        # Regresión: hay otro Administrador, la baja es legítima.
        make_administrador(username='x1')
        a2 = make_administrador(username='x2')
        emp = make_empleado(nombres='Ex', ci='6', fecha_baja=date(2025, 1, 1))
        r = self._post(emp, user=a2.pk)
        self.assertEqual(r.status_code, 302)
        a2.refresh_from_db()
        self.assertFalse(a2.is_active)

    def _staff(self):
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(
            codename__in=['change_empleado', 'view_empleado']))
        return staff

    def test_staff_sin_gestionar_usuarios_no_puede_desactivar_admin_vinculando(self):
        make_administrador(username='x1')
        a2 = make_administrador(username='x2')
        emp = make_empleado(nombres='Ex', ci='5', fecha_baja=date(2025, 1, 1))
        self.client.force_login(self._staff())
        r = self._post(emp, user=a2.pk)
        a2.refresh_from_db()
        self.assertTrue(a2.is_active)
        emp.refresh_from_db()
        self.assertIsNone(emp.user_id)
        self.assertIn(r.status_code, (200, 302))

    def test_staff_sin_gestionar_usuarios_no_puede_desvincular(self):
        cj = make_cajero(username='cj')
        emp = make_empleado(nombres='C', ci='4', user=cj)
        self.client.force_login(self._staff())
        self._post(emp, user='')
        emp.refresh_from_db()
        self.assertEqual(emp.user_id, cj.pk)

    def test_staff_sin_gestionar_no_da_de_baja_a_otro_admin_via_empleado(self):
        make_administrador(username='x1')
        a2 = make_administrador(username='x2')
        emp = make_empleado(nombres='A', ci='3', user=a2)
        self.client.force_login(self._staff())
        self._post(emp, fecha_baja='2026-01-10')
        a2.refresh_from_db()
        self.assertTrue(a2.is_active)

    def test_baja_no_permitida_en_save_model_es_mensaje_y_no_500(self):
        from misastreria.models import BajaNoPermitida
        emp = make_empleado(nombres='Z', ci='2')
        with mock.patch.object(Empleado, 'save', side_effect=BajaNoPermitida('Boom-guard')):
            r = self._post(emp, celular='+59177777777')
        self.assertEqual(r.status_code, 302)
        r2 = self.client.get(r['Location'])
        self.assertContains(r2, 'Boom-guard')


class W1FormUsaElUsuarioNuevoTests(TestCase):
    def test_form_con_campo_user_valida_con_cleaned_data(self):
        unico = make_administrador(username='unico')
        emp = make_empleado(nombres='Nadie', ci='9')

        class F(EmpleadoForm):
            class Meta(EmpleadoForm.Meta):
                fields = '__all__'
                widgets = {}
                labels = {}
                help_texts = {}

        su = User.objects.create_superuser('su', 's@x.com', 'pw')
        f = F({
            'ci': '9', 'nombres': 'Nadie', 'apellido_paterno': 'Perez',
            'apellido_materno': '', 'celular': '+59171234567',
            'fecha_ingreso': '2023-01-01', 'user': unico.pk,
            'fecha_baja': '2026-01-10', 'activo': 'on',
        }, instance=emp, actor=su)
        self.assertFalse(f.is_valid())
        self.assertTrue(f.errors)


