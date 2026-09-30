"""
Permisos adicionales por usuario (decisión del dueño, opción A).

Los 4 roles base siguen definidos en `roles.py`. Encima, un Administrador
puede sumarle a un usuario permisos EXTRA (`user.user_permissions`) desde la
pantalla de usuarios, sólo de una lista cerrada (`PERMISOS_EXTRA_OTORGABLES`).

Cubre:
  - La lista de otorgables es coherente (existen, sin gestión de usuarios).
  - Otorgar un extra habilita la vista a ESE usuario y no a otro con el
    mismo rol; revocar lo quita.
  - Lo heredado del rol se muestra tildado y deshabilitado.
  - Un permiso no otorgable (gestionar_usuarios, de otra app) se rechaza en
    el servidor y no guarda nada.
  - Nadie edita sus propios extras; sólo Administrador entra.
  - Los extras NUNCA saltean el dueño del turno de caja.
"""
import re
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from misastreria import roles
from misastreria.models import CajaMovimiento, Venta
from .factories import (
    make_administrador, make_cajero, make_vendedor, make_taller,
    make_cliente, make_empleado, make_sesion_caja, desbloquear_caja_test,
)


def _tag_input(html, codename):
    """Devuelve el <input ...> del checkbox de `codename` (o None)."""
    m = re.search(r'<input[^>]*value="%s"[^>]*>' % re.escape(codename), html)
    return m.group(0) if m else None


class AllowlistOtorgablesTests(TestCase):
    def test_todos_los_otorgables_existen_como_permisos_de_la_app(self):
        existentes = set(
            Permission.objects.filter(content_type__app_label='misastreria')
            .values_list('codename', flat=True)
        )
        self.assertTrue(roles.CODENAMES_OTORGABLES)
        self.assertEqual(set(roles.CODENAMES_OTORGABLES) - existentes, set())

    def test_gestion_de_usuarios_y_supervision_no_son_otorgables(self):
        for codename in ('gestionar_usuarios', 'supervisar_caja', 'acceder_sistema'):
            with self.subTest(codename=codename):
                self.assertNotIn(codename, roles.CODENAMES_OTORGABLES)
        self.assertIn('view_insumo', roles.CODENAMES_OTORGABLES)

    def test_grilla_agrupa_por_modulo_con_etiquetas_en_espanol(self):
        modulos = roles.modulos_otorgables()
        nombres = [m['nombre'] for m in modulos]
        self.assertIn('Insumos', nombres)
        insumos = next(m for m in modulos if m['nombre'] == 'Insumos')
        self.assertEqual(insumos['acciones']['ver'], 'view_insumo')
        self.assertEqual(insumos['acciones']['crear'], 'add_insumo')
        self.assertEqual(insumos['acciones']['editar'], 'change_insumo')
        self.assertEqual(insumos['acciones']['eliminar'], 'delete_insumo')


class OtorgarPermisoExtraTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.vend_a = make_vendedor(username='vend_a')
        self.vend_b = make_vendedor(username='vend_b')
        self.url = reverse('permisos_usuario', args=[self.vend_a.pk])

    def _get_lista_insumos(self, user):
        self.client.force_login(user)
        return self.client.get(reverse('lista_insumos')).status_code

    def test_sin_extra_vendedor_recibe_403_en_insumos(self):
        self.assertEqual(self._get_lista_insumos(self.vend_a), 403)

    def test_otorgar_extra_habilita_solo_a_ese_usuario(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url, {'permisos': ['view_insumo']})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._get_lista_insumos(User.objects.get(pk=self.vend_a.pk)), 200)
        self.assertEqual(self._get_lista_insumos(User.objects.get(pk=self.vend_b.pk)), 403)

    def test_revocar_extra_lo_quita(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {'permisos': ['view_insumo', 'add_insumo']})
        self.assertEqual(self.vend_a.user_permissions.count(), 2)
        resp = self.client.post(self.url, {'permisos': ['add_insumo']})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            list(self.vend_a.user_permissions.values_list('codename', flat=True)),
            ['add_insumo'],
        )
        self.assertEqual(self._get_lista_insumos(User.objects.get(pk=self.vend_a.pk)), 403)

    def test_guardar_sin_ninguno_quita_todos_los_extras(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {'permisos': ['view_insumo']})
        self.client.post(self.url, {})
        self.assertEqual(self.vend_a.user_permissions.count(), 0)

    def test_lo_heredado_del_rol_no_se_guarda_como_extra(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {'permisos': ['view_cliente', 'view_insumo']})
        self.assertEqual(
            list(self.vend_a.user_permissions.values_list('codename', flat=True)),
            ['view_insumo'],
        )

    def test_permisos_no_otorgables_ya_existentes_no_se_tocan(self):
        """Si por otra vía (admin de Django, shell) el usuario ya tiene un
        permiso fuera de la lista, guardar la grilla no lo borra."""
        ajeno = Permission.objects.get(codename='supervisar_caja')
        self.vend_a.user_permissions.add(ajeno)
        self.client.force_login(self.admin)
        self.client.post(self.url, {'permisos': ['view_insumo']})
        codenames = set(self.vend_a.user_permissions.values_list('codename', flat=True))
        self.assertEqual(codenames, {'supervisar_caja', 'view_insumo'})


class GrillaRenderTests(TestCase):
    def test_heredado_del_rol_va_tildado_y_deshabilitado(self):
        admin = make_administrador()
        cajero = make_cajero(username='caja_g')
        self.client.force_login(admin)
        html = self.client.get(reverse('permisos_usuario', args=[cajero.pk])).content.decode()
        heredado = _tag_input(html, 'view_cliente')
        self.assertIsNotNone(heredado)
        self.assertIn('checked', heredado)
        self.assertIn('disabled', heredado)
        libre = _tag_input(html, 'view_insumo')
        self.assertIsNotNone(libre)
        self.assertNotIn('checked', libre)
        self.assertNotIn('disabled', libre)

    def test_extra_ya_otorgado_aparece_tildado_y_editable(self):
        admin = make_administrador()
        vend = make_vendedor(username='vend_g')
        vend.user_permissions.add(Permission.objects.get(codename='view_insumo'))
        self.client.force_login(admin)
        html = self.client.get(reverse('permisos_usuario', args=[vend.pk])).content.decode()
        tag = _tag_input(html, 'view_insumo')
        self.assertIn('checked', tag)
        self.assertNotIn('disabled', tag)

    def test_gestionar_usuarios_no_aparece_en_la_grilla(self):
        admin = make_administrador()
        vend = make_vendedor(username='vend_h')
        self.client.force_login(admin)
        html = self.client.get(reverse('permisos_usuario', args=[vend.pk])).content.decode()
        self.assertIsNone(_tag_input(html, 'gestionar_usuarios'))
        self.assertIsNone(_tag_input(html, 'supervisar_caja'))


class RechazoServidorTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.vend = make_vendedor(username='vend_r')
        self.url = reverse('permisos_usuario', args=[self.vend.pk])
        self.client.force_login(self.admin)

    def _assert_nada_guardado(self):
        self.assertEqual(self.vend.user_permissions.count(), 0)

    def test_gestionar_usuarios_rechazado(self):
        self.client.post(self.url, {'permisos': ['gestionar_usuarios']})
        self._assert_nada_guardado()
        self.client.force_login(User.objects.get(pk=self.vend.pk))
        self.assertEqual(self.client.get(reverse('lista_usuarios')).status_code, 403)

    def test_supervisar_caja_rechazado(self):
        self.client.post(self.url, {'permisos': ['supervisar_caja']})
        self._assert_nada_guardado()

    def test_permiso_de_otra_app_rechazado(self):
        # `add_user` existe en la app `auth`: no es de misastreria.
        self.assertTrue(Permission.objects.filter(codename='add_user').exists())
        self.client.post(self.url, {'permisos': ['add_user']})
        self._assert_nada_guardado()

    def test_lote_mixto_no_guarda_ni_los_validos(self):
        self.client.post(self.url, {'permisos': ['view_insumo', 'gestionar_usuarios']})
        self._assert_nada_guardado()

    def test_codename_inexistente_rechazado(self):
        self.client.post(self.url, {'permisos': ['no_existe_jamas']})
        self._assert_nada_guardado()


class AccesoYAutoedicionTests(TestCase):
    def test_no_admin_recibe_403_get_y_post(self):
        vend = make_vendedor(username='vend_x')
        for maker, nombre in ((make_cajero, 'c_x'), (make_vendedor, 'v_x'), (make_taller, 't_x')):
            with self.subTest(rol=nombre):
                self.client.force_login(maker(username=nombre))
                url = reverse('permisos_usuario', args=[vend.pk])
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {'permisos': ['view_insumo']}).status_code, 403)
        self.assertEqual(vend.user_permissions.count(), 0)

    def test_nadie_edita_sus_propios_extras(self):
        admin = make_administrador()
        self.client.force_login(admin)
        url = reverse('permisos_usuario', args=[admin.pk])
        resp = self.client.post(url, {'permisos': ['view_insumo']})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(admin.user_permissions.count(), 0)

    def test_usuario_inexistente_404(self):
        self.client.force_login(make_administrador())
        self.assertEqual(self.client.get(reverse('permisos_usuario', args=[99999])).status_code, 404)


class ResumenEfectivoTests(TestCase):
    def test_lista_muestra_extras_del_usuario(self):
        admin = make_administrador()
        vend = make_vendedor(username='vend_l')
        vend.user_permissions.add(Permission.objects.get(codename='view_insumo'))
        self.client.force_login(admin)
        resp = self.client.get(reverse('lista_usuarios'))
        self.assertContains(resp, 'Insumos')
        self.assertContains(resp, reverse('permisos_usuario', args=[vend.pk]))

    def test_pagina_de_permisos_resume_rol_y_extras(self):
        admin = make_administrador()
        vend = make_vendedor(username='vend_m')
        vend.user_permissions.add(Permission.objects.get(codename='view_insumo'))
        self.client.force_login(admin)
        resp = self.client.get(reverse('permisos_usuario', args=[vend.pk]))
        self.assertEqual(resp.context['n_extras'], 1)
        self.assertEqual(resp.context['n_heredados'], len(roles.ROLES['Vendedor']))
        self.assertContains(resp, 'Vendedor')


class ExtrasNoSaltanElDuenoDelTurnoTests(TestCase):
    """El turno de caja es una regla de propiedad, no un permiso: un usuario
    con TODOS los extras otorgables sigue sin poder escribir en la sesión
    de otro."""

    def setUp(self):
        self.admin = make_administrador()
        self.dueno = make_cajero(username='dueno_caja')
        self.sesion = make_sesion_caja(usuario=self.dueno)
        self.vend = make_vendedor(username='vend_todo')
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('permisos_usuario', args=[self.vend.pk]),
            {'permisos': sorted(roles.CODENAMES_OTORGABLES)},
        )
        self.assertEqual(resp.status_code, 302)
        self.vend = User.objects.get(pk=self.vend.pk)
        # Sanity: los extras SÍ le llegaron (si no, el test no probaría nada).
        self.assertTrue(self.vend.has_perm('misastreria.operar_caja'))
        self.assertTrue(self.vend.has_perm('misastreria.abrir_caja'))
        self.assertTrue(self.vend.has_perm('misastreria.registrar_cobro'))
        self.assertFalse(self.vend.has_perm('misastreria.gestionar_usuarios'))

    def test_no_crea_movimiento_manual_en_sesion_ajena(self):
        self.client.force_login(self.vend)
        desbloquear_caja_test(self.client, self.vend)
        self.client.post(reverse('crear_movimiento_caja'), {
            'concepto': 'ingreso_manual', 'monto': '50', 'forma_pago': 'efectivo',
        })
        self.assertEqual(CajaMovimiento.objects.filter(concepto='ingreso_manual').count(), 0)

    def test_no_cobra_venta_en_sesion_ajena(self):
        cliente, empleado = make_cliente(), make_empleado()
        venta = Venta.objects.create(
            cliente=cliente, empleado=empleado,
            subtotal=Decimal('0'), total=Decimal('0'), estado='en_proceso',
        )
        Venta.objects.filter(pk=venta.pk).update(total=Decimal('300'), subtotal=Decimal('300'))
        self.client.force_login(self.vend)
        self.client.post(
            reverse('agregar_pago_venta', args=[venta.id]),
            {'monto': '100', 'forma_pago': 'efectivo', 'via_caja': 'on'},
        )
        self.assertEqual(CajaMovimiento.objects.filter(referencia_venta=venta).count(), 0)
