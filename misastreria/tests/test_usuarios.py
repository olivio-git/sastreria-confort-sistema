"""
Pantalla de gestión de usuarios (Administrador only) — spec User Management.

Cubre:
  - Crear y vincular un usuario nuevo a un Empleado, con rol.
  - Resetear el PIN de un usuario.
  - Desactivar un usuario.
  - No-Administrador recibe 403.
  - No se puede desactivar/degradar al último Administrador activo, ni a
    uno mismo.
"""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from misastreria.caja_turno import perfil_de
from .factories import make_administrador, make_cajero, make_empleado, desbloquear_caja_test


class CrearUsuarioTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.client.force_login(self.admin)

    def test_admin_crea_y_vincula_usuario(self):
        empleado = make_empleado()
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'nueva_cajera', 'password': 'clave12345',
            'rol': 'Cajero', 'empleado': str(empleado.id),
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        user = User.objects.get(username='nueva_cajera')
        self.assertTrue(user.groups.filter(name='Cajero').exists())
        empleado.refresh_from_db()
        self.assertEqual(empleado.user_id, user.id)

    def test_crear_usuario_sin_empleado_es_valido(self):
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'sin_empleado', 'password': 'clave12345',
            'rol': 'Vendedor', 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        self.assertTrue(User.objects.filter(username='sin_empleado').exists())

    def test_username_duplicado_rechaza(self):
        make_cajero(username='repetido')
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'repetido', 'password': 'clave12345',
            'rol': 'Cajero', 'empleado': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(username='repetido').count(), 1)


class ResetearPinUsuarioTests(TestCase):
    def test_admin_resetea_pin(self):
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero(pin='1234')
        resp = self.client.post(reverse('resetear_pin_usuario', args=[cajero.pk]))
        self.assertRedirects(resp, reverse('lista_usuarios'))
        perfil = perfil_de(cajero)
        self.assertEqual(perfil.pin_hash, '')
        self.assertFalse(perfil.pin_bloqueado)


class DesactivarUsuarioTests(TestCase):
    def test_admin_desactiva_usuario(self):
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero()
        resp = self.client.post(reverse('toggle_activo_usuario', args=[cajero.pk]))
        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertFalse(cajero.is_active)

    def test_no_puede_desactivarse_a_si_mismo(self):
        admin = make_administrador()
        make_administrador(username='otro_admin')  # para no chocar con la regla del último admin
        self.client.force_login(admin)
        resp = self.client.post(reverse('toggle_activo_usuario', args=[admin.pk]))
        self.assertRedirects(resp, reverse('lista_usuarios'))
        admin.refresh_from_db()
        self.assertTrue(admin.is_active, 'no debe poder desactivarse a sí mismo')

    def test_no_puede_desactivar_al_ultimo_administrador_activo(self):
        admin = make_administrador()
        otro_admin = make_administrador(username='unico_admin_objetivo')
        self.client.force_login(admin)
        # Dejamos un solo admin activo aparte del que ejecuta la acción:
        # desactivamos a `admin` primero vía DB directa para simular que
        # `otro_admin` es el último activo.
        User.objects.filter(pk=admin.pk).update(is_active=False)
        resp = self.client.post(reverse('toggle_activo_usuario', args=[otro_admin.pk]))
        otro_admin.refresh_from_db()
        self.assertTrue(otro_admin.is_active, 'no debe poder desactivar al último Administrador activo')


class NoAdministradorBloqueadoTests(TestCase):
    def test_cajero_403_en_lista_usuarios(self):
        cajero = make_cajero()
        self.client.force_login(cajero)
        resp = self.client.get(reverse('lista_usuarios'))
        self.assertEqual(resp.status_code, 403)

    def test_cajero_403_en_crear_usuario(self):
        cajero = make_cajero()
        self.client.force_login(cajero)
        resp = self.client.get(reverse('crear_usuario'))
        self.assertEqual(resp.status_code, 403)


class EditarUsuarioTests(TestCase):
    def test_admin_cambia_rol_de_otro_usuario(self):
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero()
        resp = self.client.post(reverse('editar_usuario', args=[cajero.pk]), {
            'rol': 'Vendedor', 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertFalse(cajero.groups.filter(name='Cajero').exists())
        self.assertTrue(cajero.groups.filter(name='Vendedor').exists())

    def test_no_puede_editar_su_propio_rol(self):
        admin = make_administrador()
        self.client.force_login(admin)
        resp = self.client.post(reverse('editar_usuario', args=[admin.pk]), {
            'rol': 'Cajero', 'empleado': '',
        })
        admin.refresh_from_db()
        self.assertTrue(admin.groups.filter(name='Administrador').exists(), 'no debe poder cambiar su propio rol')

    def test_no_puede_degradar_al_ultimo_administrador_activo(self):
        admin = make_administrador()
        self.client.force_login(admin)
        otro_admin = make_administrador(username='unico_admin_objetivo')
        # `admin` (quien ejecuta la acción) queda inactivo aparte de la sesión
        # ya autenticada, para que `otro_admin` sea el ÚNICO Administrador
        # activo del sistema al momento de la degradación.
        User.objects.filter(pk=admin.pk).update(is_active=False)
        resp = self.client.post(reverse('editar_usuario', args=[otro_admin.pk]), {
            'rol': 'Cajero', 'empleado': '',
        })
        otro_admin.refresh_from_db()
        self.assertTrue(
            otro_admin.groups.filter(name='Administrador').exists(),
            'no debe poder degradar al último Administrador activo',
        )
