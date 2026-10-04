"""Carrera de degradación (verify ronda 7, W2) y OperationalError -> mensaje (S1)."""
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


class W2CarreraDeDegradacionTests(TestCase):
    def setUp(self):
        self.a = make_administrador(username='a')
        self.b = make_administrador(username='b')
        self.client.force_login(self.b)

    def test_lock_relee_membresia_y_actividad(self):
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            es_ultimo_administrador_activo(self.a, bloquear=True)
        sql = ctx.captured_queries[-1]['sql']
        # La consulta bajo lock (la última) filtra por pk y RE-LEE tanto la
        # actividad como la membresía al grupo Administrador.
        self.assertIn(' IN (', sql)
        self.assertIn('auth_group', sql)
        self.assertIn('is_active', sql)

    def test_degradado_en_otra_transaccion_no_cuenta_como_admin(self):
        b_mem = User.objects.get(pk=self.b.pk)
        admin = Group.objects.get(name='Administrador')
        self.a.groups.remove(admin)  # otra transaccion degrado a A
        self.assertTrue(es_ultimo_administrador_activo(b_mem, bloquear=True))

    def test_editar_usuario_chequea_con_lock_dentro_del_atomic(self):
        llamadas = []
        orig = views_usuarios._es_ultimo_administrador_activo

        def espia(u, bloquear=False):
            llamadas.append((bloquear, connection.in_atomic_block))
            return orig(u, bloquear=bloquear)

        with mock.patch.object(views_usuarios, '_es_ultimo_administrador_activo', espia):
            self.client.post(reverse('editar_usuario', args=[self.a.pk]),
                             {'roles': ['Vendedor'], 'empleado': ''})
        self.assertTrue(llamadas)
        self.assertTrue(all(bloq for bloq, _ in llamadas))
        self.assertTrue(all(atom for _, atom in llamadas))

    def test_desactivado_concurrentemente_bloquea_la_degradacion(self):
        """A desactiva a B justo antes de que B degrade a A: al tomar el lock
        el chequeo ve a B inactivo, A es el último y no se lo degrada."""
        orig = views_usuarios._es_ultimo_administrador_activo

        def con_carrera(u, bloquear=False):
            User.objects.filter(pk=self.b.pk).update(is_active=False)
            return orig(u, bloquear=bloquear)

        with mock.patch.object(views_usuarios, '_es_ultimo_administrador_activo', con_carrera):
            r = self.client.post(reverse('editar_usuario', args=[self.a.pk]),
                                 {'roles': ['Vendedor'], 'empleado': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'último Administrador')
        self.assertTrue(User.objects.get(pk=self.a.pk).groups.filter(name='Administrador').exists())
        self.assertGreaterEqual(
            User.objects.filter(groups__name='Administrador', is_active=True).count(), 1)

    def test_degradacion_legitima_sigue_funcionando(self):
        c = make_administrador(username='c')  # hay tercero
        r = self.client.post(reverse('editar_usuario', args=[c.pk]),
                             {'roles': ['Vendedor'], 'empleado': ''})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(User.objects.get(pk=c.pk).groups.filter(name='Administrador').exists())


class S1OperationalErrorTests(TestCase):
    def setUp(self):
        self.a = make_administrador(username='a')
        self.b = make_administrador(username='b')
        self.client.force_login(self.a)
        self.client.raise_request_exception = False

    def _assert_reintentar(self, r):
        self.assertEqual(r.status_code, 302, getattr(r, 'content', b'')[:500])
        msgs = [str(m) for m in list(r.wsgi_request._messages)]
        self.assertTrue(any('intenta de nuevo' in m.lower() for m in msgs), msgs)

    def test_toggle_activo_usuario(self):
        with mock.patch.object(views_usuarios, '_es_ultimo_administrador_activo',
                               side_effect=OperationalError(1213, 'Deadlock')):
            r = self.client.post(reverse('toggle_activo_usuario', args=[self.b.pk]))
        self._assert_reintentar(r)
        self.assertTrue(User.objects.get(pk=self.b.pk).is_active)

    def test_editar_usuario(self):
        with mock.patch.object(views_usuarios, '_es_ultimo_administrador_activo',
                               side_effect=OperationalError(1205, 'Lock wait timeout')):
            r = self.client.post(reverse('editar_usuario', args=[self.b.pk]),
                                 {'roles': ['Vendedor'], 'empleado': ''})
        self._assert_reintentar(r)
        self.assertTrue(User.objects.get(pk=self.b.pk).groups.filter(name='Administrador').exists())

    def test_editar_empleado(self):
        emp = make_empleado(nombres='Ana', ci='1', user=self.b)
        with mock.patch.object(Empleado, 'save', side_effect=OperationalError(1213, 'Deadlock')):
            r = self.client.post(reverse('editar_empleado', args=[emp.pk]), {
                'ci': '1', 'nombres': 'Ana', 'apellido_paterno': 'Perez',
                'apellido_materno': '', 'celular': '71234567',
                'fecha_ingreso': '2023-01-01', 'fecha_baja': '2026-01-10',
            })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ntenta de nuevo')

    def test_abrir_sesion_caja(self):
        from misastreria import caja_turno
        from misastreria.models import CajaSesion
        from .factories import desbloquear_caja_test
        desbloquear_caja_test(self.client, self.a)
        with mock.patch.object(caja_turno, 'bloqueo_apertura_caja',
                               side_effect=OperationalError(1205, 'Lock wait timeout')):
            r = self.client.post(reverse('abrir_sesion_caja'), {'monto_apertura': '100'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ntenta de nuevo')
        self.assertFalse(CajaSesion.objects.exists())


