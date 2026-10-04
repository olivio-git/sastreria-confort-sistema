"""
La baja de un Empleado con usuario vinculado desactiva a ese usuario, así
que es una operación de gestión de usuarios y no de RR.HH.:

  - Poner, cambiar o quitar `fecha_baja` en un Empleado vinculado exige
    `gestionar_usuarios` (el extra `change_empleado` alcanza para el resto de
    los campos, no para éste).
  - Nunca se afecta a uno mismo ni al último Administrador activo (también
    vale para Administradores).
  - El guard de dominio está en `Empleado.save`, por lo que ninguna otra ruta
    (admin, shell, otra vista) puede saltearlo.

Origen: verify ronda 5, CRITICAL 1 (un Vendedor con todos los extras dejaba
al sistema sin Administradores).
"""
from datetime import date

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from misastreria import roles
from misastreria.models import BajaNoPermitida, Empleado
from .factories import make_administrador, make_cajero, make_empleado, make_vendedor


def _con_todos_los_extras(user):
    perms = Permission.objects.filter(
        content_type__app_label='misastreria', codename__in=roles.CODENAMES_OTORGABLES,
    )
    user.user_permissions.add(*perms)
    return User.objects.get(pk=user.pk)


def _datos(emp, **extra):
    d = {
        'ci': emp.ci or '', 'nombres': emp.nombres,
        'apellido_paterno': emp.apellido_paterno, 'apellido_materno': '',
        'celular_pais': '+591', 'celular': '71234567', 'tipo_contrato': '',
        'fecha_ingreso': emp.fecha_ingreso.isoformat(),
    }
    d.update(extra)
    return d


class BajaDeEmpleadoVinculadoTests(TestCase):
    def setUp(self):
        self.admin = make_administrador(username='admin')
        self.emp_admin = make_empleado(nombres='Ana', user=self.admin)
        self.vend = _con_todos_los_extras(make_vendedor(username='vend'))
        self.url = reverse('editar_empleado', args=[self.emp_admin.pk])

    def test_vendedor_con_extras_no_puede_dar_de_baja_al_ultimo_admin(self):
        self.client.force_login(self.vend)
        self.client.post(self.url, _datos(self.emp_admin, fecha_baja='2026-01-10'))
        self.admin.refresh_from_db()
        self.emp_admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertIsNone(self.emp_admin.fecha_baja)

    def test_sin_gestionar_usuarios_no_se_da_baja_a_un_usuario_no_admin(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='999', user=cajero)
        self.client.force_login(self.vend)
        self.client.post(reverse('editar_empleado', args=[emp.pk]),
                         _datos(emp, fecha_baja='2026-01-10'))
        cajero.refresh_from_db()
        emp.refresh_from_db()
        self.assertTrue(cajero.is_active)
        self.assertIsNone(emp.fecha_baja)

    def test_sin_gestionar_usuarios_los_otros_campos_si_se_editan(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='999', user=cajero)
        self.client.force_login(self.vend)
        self.client.post(reverse('editar_empleado', args=[emp.pk]),
                         _datos(emp, nombres='Bruno', fecha_baja='2026-01-10'))
        emp.refresh_from_db()
        self.assertEqual(emp.nombres, 'Bruno')
        self.assertIsNone(emp.fecha_baja)

    def test_el_campo_sale_deshabilitado_sin_gestionar_usuarios(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='999', user=cajero)
        self.client.force_login(self.vend)
        resp = self.client.get(reverse('editar_empleado', args=[emp.pk]))
        self.assertTrue(resp.context['form'].fields['fecha_baja'].disabled)
        self.assertNotContains(resp, 'data-clear-target="id_fecha_baja"')

    def test_el_campo_sale_habilitado_para_admin(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='999', user=cajero)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('editar_empleado', args=[emp.pk]))
        self.assertFalse(resp.context['form'].fields['fecha_baja'].disabled)

    def test_admin_no_se_da_de_baja_a_si_mismo(self):
        otro = make_administrador(username='admin2')
        self.client.force_login(self.admin)
        self.client.post(self.url, _datos(self.emp_admin, fecha_baja='2026-01-10'))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(otro.is_active)

    def test_admin_no_da_de_baja_al_ultimo_admin_activo(self):
        # Otro admin (sin empleado) que da de baja al único otro admin activo
        # sería posible; acá el único admin activo es el del empleado y quien
        # actúa es un usuario con gestionar_usuarios que NO es admin activo
        # aparte: se simula con un segundo admin ya inactivo.
        actor = make_administrador(username='actor')
        self.admin.is_active = False
        self.admin.save()
        # `actor` es ahora el único activo; su propio empleado no puede darse de baja.
        emp_actor = make_empleado(nombres='Actor', ci='777', user=actor)
        self.client.force_login(actor)
        self.client.post(reverse('editar_empleado', args=[emp_actor.pk]),
                         _datos(emp_actor, fecha_baja='2026-01-10'))
        actor.refresh_from_db()
        self.assertTrue(actor.is_active)

    def test_admin_da_de_baja_a_otro_usuario_que_no_es_el_ultimo_admin(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='999', user=cajero)
        self.client.force_login(self.admin)
        self.client.post(reverse('editar_empleado', args=[emp.pk]),
                         _datos(emp, fecha_baja='2026-01-10'))
        cajero.refresh_from_db()
        emp.refresh_from_db()
        self.assertEqual(emp.fecha_baja, date(2026, 1, 10))
        self.assertFalse(cajero.is_active)

    def test_admin_da_de_baja_a_otro_admin_si_queda_otro_activo(self):
        otro = make_administrador(username='admin2')
        emp = make_empleado(nombres='Otro', ci='555', user=otro)
        self.client.force_login(self.admin)
        self.client.post(reverse('editar_empleado', args=[emp.pk]),
                         _datos(emp, fecha_baja='2026-01-10'))
        otro.refresh_from_db()
        self.assertFalse(otro.is_active)

    def test_empleado_sin_usuario_se_da_de_baja_solo_con_change_empleado(self):
        emp = make_empleado(nombres='Sin', ci='321')
        self.client.force_login(self.vend)
        self.client.post(reverse('editar_empleado', args=[emp.pk]),
                         _datos(emp, fecha_baja='2026-01-10'))
        emp.refresh_from_db()
        self.assertEqual(emp.fecha_baja, date(2026, 1, 10))
        self.assertFalse(emp.activo)

    def test_quitar_la_baja_tambien_exige_gestionar_usuarios(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='999', user=cajero, fecha_baja=date(2026, 1, 1))
        self.client.force_login(self.vend)
        self.client.post(reverse('editar_empleado', args=[emp.pk]), _datos(emp))
        emp.refresh_from_db()
        self.assertEqual(emp.fecha_baja, date(2026, 1, 1))


class GuardDeDominioTests(TestCase):
    def test_save_rechaza_desactivar_al_ultimo_admin_activo(self):
        admin = make_administrador()
        emp = make_empleado(user=admin)
        emp.fecha_baja = date(2026, 1, 10)
        with self.assertRaises(BajaNoPermitida):
            emp.save()
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)
        self.assertIsNone(Empleado.objects.get(pk=emp.pk).fecha_baja)

    def test_save_permite_la_baja_si_hay_otro_admin_activo(self):
        make_administrador(username='a1')
        a2 = make_administrador(username='a2')
        emp = make_empleado(user=a2)
        emp.fecha_baja = date(2026, 1, 10)
        emp.save()
        a2.refresh_from_db()
        self.assertFalse(a2.is_active)


class EmpleadoAdminBajaTests(TestCase):
    """Django admin: la baja de un Empleado vinculado sigue las mismas reglas
    que `EmpleadoForm(actor=)`. Antes: la baja del último Administrador daba
    un 500 (BajaNoPermitida sin capturar) y un superusuario podía darse de
    baja a sí mismo (verify ronda 6, W2)."""

    def setUp(self):
        self.su = User.objects.create_superuser('super', 's@x.com', 'pw')
        self.client.force_login(self.su)

    def _post(self, emp, **extra):
        data = {
            'ci': emp.ci or '', 'nombres': emp.nombres,
            'apellido_paterno': emp.apellido_paterno, 'apellido_materno': '',
            'celular': '+59171234567', 'activo': 'on',
            'fecha_ingreso': emp.fecha_ingreso.isoformat(),
            'user': emp.user_id or '',
        }
        data.update(extra)
        return self.client.post(
            reverse('admin:misastreria_empleado_change', args=[emp.pk]), data)

    def test_baja_del_ultimo_admin_muestra_error_y_no_500(self):
        admin = make_administrador(username='unico')
        emp = make_empleado(nombres='Ana', ci='1', user=admin)
        resp = self._post(emp, fecha_baja='2026-01-10')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'último Administrador activo')
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)
        self.assertIsNone(Empleado.objects.get(pk=emp.pk).fecha_baja)

    def test_superusuario_no_se_da_de_baja_a_si_mismo(self):
        emp = make_empleado(nombres='Su', ci='2', user=self.su)
        resp = self._post(emp, fecha_baja='2026-01-10')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'tu propio usuario')
        self.su.refresh_from_db()
        self.assertTrue(self.su.is_active)
        self.assertIsNone(Empleado.objects.get(pk=emp.pk).fecha_baja)

    def test_baja_de_un_usuario_comun_funciona(self):
        cajero = make_cajero(username='caj')
        emp = make_empleado(nombres='Beto', ci='3', user=cajero)
        resp = self._post(emp, fecha_baja='2026-01-10')
        self.assertEqual(resp.status_code, 302)
        cajero.refresh_from_db()
        self.assertFalse(cajero.is_active)


class BloqueoDeAdministradoresTests(TestCase):
    """Dos Administradores que se dan de baja a la vez podían pasar ambos el
    chequeo "queda otro activo" y dejar al sistema sin ninguno (verify ronda 6,
    S3). La baja ahora bloquea (SELECT ... FOR UPDATE) las filas de los
    Administradores activos dentro de la misma transacción que desactiva: la
    segunda transacción espera, y al reevaluar ya ve al otro inactivo.

    SQLite (los tests) ignora FOR UPDATE, así que se prueba la lógica: que se
    pida el lock y que el chequeo bajo lock lea el estado real de la base y no
    el del objeto en memoria. La exclusión mutua en sí la da InnoDB."""

    def setUp(self):
        from unittest import mock
        self.mock = mock
        self.a = make_administrador(username='a')
        self.b = make_administrador(username='b')

    def test_con_bloqueo_usa_el_estado_de_la_base_y_no_el_de_memoria(self):
        from misastreria.models import es_ultimo_administrador_activo
        a_en_memoria = User.objects.get(pk=self.a.pk)  # activo en memoria
        # Otra transacción ya dio de baja a b (la base dice: a es el último).
        User.objects.filter(pk=self.b.pk).update(is_active=False)
        self.assertTrue(es_ultimo_administrador_activo(a_en_memoria, bloquear=True))
        # Y al revés: a fue desactivado por otra transacción -> ya no cuenta.
        User.objects.filter(pk=self.b.pk).update(is_active=True)
        User.objects.filter(pk=self.a.pk).update(is_active=False)
        self.assertFalse(es_ultimo_administrador_activo(a_en_memoria, bloquear=True))

    def test_empleado_save_con_baja_pide_el_lock_de_los_administradores(self):
        emp = make_empleado(nombres='Ana', ci='1', user=self.a)
        emp.fecha_baja = date(2026, 1, 10)
        with self.mock.patch('django.db.models.query.QuerySet.select_for_update',
                             autospec=True, side_effect=lambda qs, *a, **k: qs) as sfu:
            emp.save()
        self.assertTrue(sfu.called)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_active)

    def test_segunda_baja_mutua_es_rechazada(self):
        ea = make_empleado(nombres='Ana', ci='1', user=self.a)
        eb = make_empleado(nombres='Beto', ci='2', user=self.b)
        ea.fecha_baja = date(2026, 1, 10)
        ea.save()
        eb.fecha_baja = date(2026, 1, 10)
        with self.assertRaises(BajaNoPermitida):
            eb.save()
        self.b.refresh_from_db()
        self.assertTrue(self.b.is_active)

    def test_toggle_activo_usuario_pide_el_lock(self):
        self.client.force_login(self.a)
        with self.mock.patch('django.db.models.query.QuerySet.select_for_update',
                             autospec=True, side_effect=lambda qs, *a, **k: qs) as sfu:
            self.client.post(reverse('toggle_activo_usuario', args=[self.b.pk]))
        self.assertTrue(sfu.called)
        self.b.refresh_from_db()
        self.assertFalse(self.b.is_active)
