"""
Las pantallas de inventario (prendas, detalle de prenda, conjuntos) las ven
Cajero y Vendedor sólo en lectura: los botones de Crear/Editar/Eliminar (que
devolverían 403) no se muestran sin el permiso correspondiente, pero sí a
quien lo tiene (Administrador, o un extra por usuario).
Origen: verify ronda 5, SUGGESTION 1.
"""
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from misastreria.models import Conjunto
from .factories import (
    make_administrador, make_cajero, make_prenda, make_prenda_item, make_vendedor,
)


class BotonesDeInventarioSegunPermisoTests(TestCase):
    def setUp(self):
        self.prenda = make_prenda()
        self.item = make_prenda_item(self.prenda)
        self.conjunto = Conjunto.objects.create(nombre='Terno', tipo='alquiler')
        p = self.prenda.pk
        self.prohibidas = {
            'lista_prendas': [
                reverse('crear_prenda'), reverse('editar_prenda', args=[p]),
                reverse('eliminar_prenda', args=[p]),
            ],
            'detalle_prenda': [
                reverse('editar_prenda', args=[p]),
                reverse('editar_prenda_item', args=[self.item.pk]),
                reverse('mover_prenda_item', args=[self.item.pk]),
                reverse('baja_prenda_item', args=[self.item.pk]),
            ],
            'lista_conjuntos': [
                reverse('crear_conjunto'),
                reverse('editar_conjunto', args=[self.conjunto.pk]),
                reverse('eliminar_conjunto', args=[self.conjunto.pk]),
            ],
        }
        self.args = {'detalle_prenda': [p]}

    def _html(self, nombre):
        resp = self.client.get(reverse(nombre, args=self.args.get(nombre, [])))
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def _assert_ocultos(self, user):
        self.client.force_login(user)
        for nombre, urls in self.prohibidas.items():
            html = self._html(nombre)
            for url in urls:
                with self.subTest(vista=nombre, url=url, rol=user.username):
                    self.assertNotIn(f'"{url}"', html)

    def test_cajero_no_ve_botones_de_escritura(self):
        self._assert_ocultos(make_cajero())

    def test_vendedor_no_ve_botones_de_escritura(self):
        self._assert_ocultos(make_vendedor())

    def test_administrador_los_ve(self):
        self.client.force_login(make_administrador())
        for nombre, urls in self.prohibidas.items():
            html = self._html(nombre)
            for url in urls:
                with self.subTest(vista=nombre, url=url):
                    self.assertIn(url, html)

    def test_extra_de_editar_prenda_muestra_solo_los_botones_de_editar(self):
        vend = make_vendedor()
        vend.user_permissions.add(Permission.objects.get(codename='change_prendainventario'))
        vend = User.objects.get(pk=vend.pk)
        self.client.force_login(vend)
        html = self._html('lista_prendas')
        self.assertIn(reverse('editar_prenda', args=[self.prenda.pk]), html)
        self.assertNotIn(f'"{reverse("crear_prenda")}"', html)
        self.assertNotIn(reverse('eliminar_prenda', args=[self.prenda.pk]), html)
