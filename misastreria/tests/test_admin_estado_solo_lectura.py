"""
Django admin no puede cambiar el `estado` de Reparación/Confección/Venta/
Alquiler (4ª verificación, S2).

Un cambio de estado (p. ej. a 'entregado') dispara escrituras de caja que
exigen un actor dueño del turno; el admin no tiene ninguno, así que guardar
un cambio de estado ahí termina en `TurnoCajaError` (500). Los estados se
cambian sólo desde las vistas de la app, que sí identifican a quien actúa.
"""
from django.contrib import admin
from django.test import RequestFactory, TestCase

from misastreria.models import Alquiler, Confeccion, Reparacion, Venta
from .factories import make_administrador, make_alquiler, make_confeccion, make_reparacion, make_venta


class AdminEstadoSoloLecturaTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/admin/')
        self.request.user = make_administrador(username='super')
        self.request.user.is_staff = True
        self.request.user.is_superuser = True

    def _admin(self, modelo):
        return admin.site._registry[modelo]

    def test_estado_es_solo_lectura_en_los_cuatro_servicios(self):
        casos = (
            (Reparacion, make_reparacion),
            (Confeccion, make_confeccion),
            (Venta, make_venta),
            (Alquiler, make_alquiler),
        )
        for modelo, fabrica in casos:
            with self.subTest(modelo=modelo.__name__):
                model_admin = self._admin(modelo)
                obj = fabrica()
                self.assertIn('estado', model_admin.get_readonly_fields(self.request, obj))
                self.assertNotIn('estado', model_admin.get_form(self.request, obj).base_fields)

    def test_estado_es_solo_lectura_tambien_al_crear(self):
        for modelo in (Reparacion, Confeccion, Venta, Alquiler):
            with self.subTest(modelo=modelo.__name__):
                model_admin = self._admin(modelo)
                self.assertIn('estado', model_admin.get_readonly_fields(self.request, None))

    def test_adelanto_de_confeccion_tambien_es_solo_lectura(self):
        """Cambiar el adelanto también dispara un movimiento de caja."""
        model_admin = self._admin(Confeccion)
        obj = make_confeccion()
        self.assertIn('adelanto', model_admin.get_readonly_fields(self.request, obj))

    def test_otros_campos_siguen_editables(self):
        """Triangulación: no se volvió todo solo lectura."""
        self.assertIn('color', self._admin(Confeccion).get_form(self.request, make_confeccion()).base_fields)
        self.assertIn('fecha_entrega', self._admin(Reparacion).get_form(self.request, make_reparacion()).base_fields)
