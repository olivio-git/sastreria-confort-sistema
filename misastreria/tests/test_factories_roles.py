"""
Cobertura de los helpers de rol/PIN agregados a factories.py (Fase 2).
"""
from django.test import TestCase

from .factories import (
    make_administrador, make_cajero, make_vendedor, make_taller,
    make_user, desbloquear_caja_test,
)


class RoleFactoriesTests(TestCase):
    def test_make_administrador_pertenece_al_grupo(self):
        user = make_administrador()
        self.assertTrue(user.groups.filter(name='Administrador').exists())

    def test_make_cajero_pertenece_al_grupo(self):
        user = make_cajero()
        self.assertTrue(user.groups.filter(name='Cajero').exists())

    def test_make_vendedor_pertenece_al_grupo(self):
        user = make_vendedor()
        self.assertTrue(user.groups.filter(name='Vendedor').exists())

    def test_make_taller_pertenece_al_grupo(self):
        user = make_taller()
        self.assertTrue(user.groups.filter(name='Taller').exists())

    def test_make_user_default_es_administrador(self):
        user = make_user()
        self.assertTrue(user.groups.filter(name='Administrador').exists())

    def test_make_user_role_none_sin_grupos(self):
        user = make_user(username='sin_rol', role=None)
        self.assertFalse(user.groups.exists())

    def test_make_user_con_pin_guarda_hash(self):
        user = make_user(username='con_pin', pin='1234')
        self.assertTrue(user.perfil.pin_hash)
        self.assertNotEqual(user.perfil.pin_hash, '1234')

    def test_desbloquear_caja_test_marca_sesion(self):
        from django.test import Client
        client = Client()
        user = make_cajero(username='cajero_pin')
        client.force_login(user)
        desbloquear_caja_test(client, user)
        session = client.session
        self.assertEqual(session['caja_pin_uid'], user.pk)
        self.assertIn('caja_pin_hasta', session)
