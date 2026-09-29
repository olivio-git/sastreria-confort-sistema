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
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from misastreria.caja_turno import perfil_de, validar_pin
from .factories import make_administrador, make_cajero, make_empleado, desbloquear_caja_test


class CrearUsuarioTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.client.force_login(self.admin)

    def test_admin_crea_y_vincula_usuario(self):
        empleado = make_empleado()
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'nueva_cajera', 'password': 'clave12345',
            'roles': ['Cajero'], 'empleado': str(empleado.id),
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        user = User.objects.get(username='nueva_cajera')
        self.assertTrue(user.groups.filter(name='Cajero').exists())
        empleado.refresh_from_db()
        self.assertEqual(empleado.user_id, user.id)

    def test_crear_usuario_sin_empleado_es_valido(self):
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'sin_empleado', 'password': 'clave12345',
            'roles': ['Vendedor'], 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        self.assertTrue(User.objects.filter(username='sin_empleado').exists())

    def test_username_duplicado_rechaza(self):
        make_cajero(username='repetido')
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'repetido', 'password': 'clave12345',
            'roles': ['Cajero'], 'empleado': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(username='repetido').count(), 1)

    def test_admin_crea_usuario_con_varios_roles(self):
        """WARNING 5 (reporte de verificación): personal de mostrador que
        cobra Y vende necesita Cajero + Vendedor a la vez — un solo rol por
        usuario no alcanza para expresar eso."""
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'mostrador_multi', 'password': 'clave12345',
            'roles': ['Cajero', 'Vendedor'], 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        user = User.objects.get(username='mostrador_multi')
        self.assertTrue(user.groups.filter(name='Cajero').exists())
        self.assertTrue(user.groups.filter(name='Vendedor').exists())

    def test_sin_ningun_rol_rechaza(self):
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'sin_rol', 'password': 'clave12345',
            'roles': [], 'empleado': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username='sin_rol').exists())


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

    def test_e2e_admin_resetea_bloqueo_luego_usuario_configura_y_desbloquea(self):
        """SUGGESTION 4 (verify report): flujo completo de punta a punta —
        el PIN de un Cajero se bloquea por intentos fallidos, un
        Administrador lo resetea desde `/usuarios/`, y RECIÉN AHÍ (con
        `pin_hash` vacío) el Cajero puede fijar un PIN nuevo vía
        `configurar_pin_caja` y usarlo para entrar a una vista de `/caja/`.
        Encadena el reset de admin con el gate de PIN real (no llama a los
        helpers de dominio directamente para el tramo del Cajero)."""
        admin = make_administrador()
        cajero = make_cajero(username='e2e_pin', password='clave12345', pin='1234')
        for _ in range(5):
            validar_pin(cajero, '0000')
        self.assertTrue(perfil_de(cajero).pin_bloqueado)

        # 1) Administrador resetea desde la pantalla de usuarios.
        self.client.force_login(admin)
        resp = self.client.post(reverse('resetear_pin_usuario', args=[cajero.pk]))
        self.assertRedirects(resp, reverse('lista_usuarios'))
        self.assertEqual(perfil_de(cajero).pin_hash, '')
        self.client.logout()

        # 2) El Cajero entra y, al no tener PIN, es mandado a configurar uno.
        self.client.force_login(cajero)
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, reverse('configurar_pin_caja'))

        # 3) Configura un PIN nuevo (contraseña de cuenta + PIN dos veces).
        resp = self.client.post(reverse('configurar_pin_caja'), {
            'password': 'clave12345', 'pin': '4321', 'pin2': '4321',
        })
        self.assertRedirects(resp, reverse('lista_sesiones_caja'))

        # 4) Ya desbloqueado, entra directo a la vista de caja.
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertEqual(resp.status_code, 200)

        # 5) El bloqueo vence: vuelve a pedir el PIN, y el nuevo PIN sirve.
        session = self.client.session
        session['caja_pin_hasta'] = session['caja_pin_hasta'] - 20 * 60
        session.save()
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, f"{reverse('desbloquear_caja')}?next=%2Fcaja%2Fsesiones%2F")
        resp = self.client.post(reverse('desbloquear_caja'), {'pin': '4321'})
        self.assertRedirects(resp, reverse('lista_sesiones_caja'))


class EmpleadoDeBajaVinculoTests(TestCase):
    """SUGGESTION 2 (reporte de verificación): vincular un Empleado que ya
    tiene `fecha_baja` no debe dejar el usuario activo, y no se puede
    reactivar por `toggle_activo_usuario` un usuario cuyo Empleado sigue de
    baja — la baja del Empleado manda sobre el estado del User."""

    def test_vincular_empleado_de_baja_al_crear_desactiva_el_usuario(self):
        admin = make_administrador()
        self.client.force_login(admin)
        empleado_de_baja = make_empleado(fecha_baja=date.today())
        resp = self.client.post(reverse('crear_usuario'), {
            'username': 'ligado_a_baja', 'password': 'clave12345',
            'roles': ['Cajero'], 'empleado': str(empleado_de_baja.id),
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        user = User.objects.get(username='ligado_a_baja')
        self.assertFalse(user.is_active, 'no debe nacer activo si el Empleado ya está de baja')

    def test_vincular_empleado_de_baja_al_editar_desactiva_el_usuario(self):
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero()
        empleado_de_baja = make_empleado(fecha_baja=date.today())
        resp = self.client.post(reverse('editar_usuario', args=[cajero.pk]), {
            'roles': ['Cajero'], 'empleado': str(empleado_de_baja.id),
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertFalse(cajero.is_active, 'vincular a un Empleado de baja debe desactivar al usuario')

    def test_toggle_activo_no_reactiva_si_el_empleado_sigue_de_baja(self):
        admin = make_administrador()
        self.client.force_login(admin)
        empleado_de_baja = make_empleado(fecha_baja=date.today())
        cajero = make_cajero()
        empleado_de_baja.user = cajero
        empleado_de_baja.save(update_fields=['user'])
        User.objects.filter(pk=cajero.pk).update(is_active=False)

        resp = self.client.post(reverse('toggle_activo_usuario', args=[cajero.pk]))

        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertFalse(
            cajero.is_active,
            'no se puede reactivar un usuario cuyo Empleado vinculado sigue de baja',
        )


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
            'roles': ['Vendedor'], 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertFalse(cajero.groups.filter(name='Cajero').exists())
        self.assertTrue(cajero.groups.filter(name='Vendedor').exists())

    def test_no_puede_editar_su_propio_rol(self):
        admin = make_administrador()
        self.client.force_login(admin)
        resp = self.client.post(reverse('editar_usuario', args=[admin.pk]), {
            'roles': ['Cajero'], 'empleado': '',
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
            'roles': ['Cajero'], 'empleado': '',
        })
        otro_admin.refresh_from_db()
        self.assertTrue(
            otro_admin.groups.filter(name='Administrador').exists(),
            'no debe poder degradar al último Administrador activo',
        )

    def test_editar_agrega_un_rol_sin_perder_el_existente(self):
        """WARNING 5: un usuario Cajero pasa a ser Cajero+Vendedor (personal
        de mostrador) sin que se le caiga el rol que ya tenía."""
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero()
        resp = self.client.post(reverse('editar_usuario', args=[cajero.pk]), {
            'roles': ['Cajero', 'Vendedor'], 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertTrue(cajero.groups.filter(name='Cajero').exists())
        self.assertTrue(cajero.groups.filter(name='Vendedor').exists())

    def test_editar_no_pisa_grupos_que_no_son_roles_del_sistema(self):
        """WARNING 5: antes `user_obj.groups.clear()` borraba TODOS los
        grupos del usuario, no sólo los 4 roles del sistema — si alguna vez
        se agrega un grupo ajeno (ej. integración externa), editar el rol no
        debe tocarlo."""
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero()
        grupo_externo, _ = Group.objects.get_or_create(name='ExternoDeMuestra')
        cajero.groups.add(grupo_externo)
        resp = self.client.post(reverse('editar_usuario', args=[cajero.pk]), {
            'roles': ['Vendedor'], 'empleado': '',
        })
        self.assertRedirects(resp, reverse('lista_usuarios'))
        cajero.refresh_from_db()
        self.assertTrue(cajero.groups.filter(name='ExternoDeMuestra').exists())
        self.assertFalse(cajero.groups.filter(name='Cajero').exists())
        self.assertTrue(cajero.groups.filter(name='Vendedor').exists())

    def test_no_puede_quitarle_administrador_al_ultimo_admin_activo(self):
        """Mismo invariante que desactivar, pero editando la lista de roles:
        quitar 'Administrador' de sus roles no debe poder dejar el sistema
        sin ningún Administrador activo."""
        admin = make_administrador()
        self.client.force_login(admin)
        otro_admin = make_administrador(username='unico_admin_multi')
        User.objects.filter(pk=admin.pk).update(is_active=False)
        resp = self.client.post(reverse('editar_usuario', args=[otro_admin.pk]), {
            'roles': ['Cajero', 'Vendedor'], 'empleado': '',
        })
        otro_admin.refresh_from_db()
        self.assertTrue(
            otro_admin.groups.filter(name='Administrador').exists(),
            'no debe poder quitarle el rol de Administrador al último Administrador activo',
        )

    def test_editar_sin_ningun_rol_rechaza(self):
        admin = make_administrador()
        self.client.force_login(admin)
        cajero = make_cajero()
        resp = self.client.post(reverse('editar_usuario', args=[cajero.pk]), {
            'roles': [], 'empleado': '',
        })
        self.assertEqual(resp.status_code, 200)
        cajero.refresh_from_db()
        self.assertTrue(cajero.groups.filter(name='Cajero').exists(), 'no debe quedar sin rol')
