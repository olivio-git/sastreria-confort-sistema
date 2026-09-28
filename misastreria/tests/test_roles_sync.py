"""
Cobertura del módulo declarativo de roles (misastreria/roles.py).

Verifica que Administrador tenga TODOS los permisos de la app y que
Cajero/Vendedor/Taller tengan exactamente los codenames de la matriz
(sin faltantes ni de más), además de que la sincronización sea idempotente.
"""
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from misastreria.roles import ROLES, CUSTOM_PERMISSIONS, ALL, aplicar_roles


class RolesSyncTests(TestCase):
    def test_administrador_tiene_todos_los_permisos(self):
        aplicar_roles()
        admin = Group.objects.get(name='Administrador')
        total_app = Permission.objects.filter(content_type__app_label='misastreria').count()
        self.assertEqual(admin.permissions.count(), total_app)
        self.assertGreater(total_app, 0)

    def test_cajero_vendedor_taller_tienen_exactamente_su_matriz(self):
        aplicar_roles()
        for nombre in ('Cajero', 'Vendedor', 'Taller'):
            codenames_esperados = ROLES[nombre]
            self.assertNotEqual(codenames_esperados, ALL)
            grupo = Group.objects.get(name=nombre)
            codenames_reales = set(grupo.permissions.values_list('codename', flat=True))
            self.assertEqual(
                codenames_reales, codenames_esperados,
                f"El grupo {nombre} no coincide con roles.ROLES['{nombre}']",
            )

    def test_permisos_custom_existen_en_bd_tras_migrar(self):
        codenames_custom = {codename for codename, _ in CUSTOM_PERMISSIONS}
        existentes = set(
            Permission.objects.filter(
                content_type__app_label='misastreria', codename__in=codenames_custom
            ).values_list('codename', flat=True)
        )
        self.assertEqual(existentes, codenames_custom)

    def test_sincronizacion_es_idempotente(self):
        aplicar_roles()
        primero = {
            g.name: set(g.permissions.values_list('codename', flat=True))
            for g in Group.objects.filter(name__in=ROLES.keys())
        }
        aplicar_roles()
        segundo = {
            g.name: set(g.permissions.values_list('codename', flat=True))
            for g in Group.objects.filter(name__in=ROLES.keys())
        }
        self.assertEqual(primero, segundo)

    def test_codename_inexistente_lanza_improperly_configured(self):
        from django.core.exceptions import ImproperlyConfigured
        roles_invalidos = dict(ROLES)
        roles_invalidos['Cajero'] = {'permiso_que_no_existe_jamas'}
        with self.assertRaises(ImproperlyConfigured):
            aplicar_roles(roles=roles_invalidos)
