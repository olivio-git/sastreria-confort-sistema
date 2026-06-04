"""
test_cerrar_sesion_caja.py
==========================
Cubre el cierre de sesión de caja (cerrar_sesion_caja):
  - Cerrar con el monto declarado vacío NO debe dar 500 (antes: TypeError
    'NoneType - Decimal'); el form exige el monto contado.
  - Cerrar con un monto válido cierra la sesión y calcula la diferencia.
"""
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from misastreria.models import CajaSesion
from .factories import make_user, make_sesion_caja


class CerrarSesionCajaTests(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.sesion = make_sesion_caja(usuario=self.user, monto_apertura=Decimal('100.00'))

    def test_cierre_sin_monto_declarado_no_es_500(self):
        """Monto vacío → 200 con error de validación, sesión sigue abierta."""
        resp = self.client.post(
            reverse('cerrar_sesion_caja', args=[self.sesion.pk]),
            {'monto_cierre_declarado': '', 'observaciones': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context['form'], 'monto_cierre_declarado',
                             'Declará el monto contado para poder cerrar la caja.')
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'abierta')

    def test_cierre_con_monto_valido_cierra_sesion(self):
        """Monto declarado = saldo del sistema (100 apertura) → diferencia 0, cierra."""
        resp = self.client.post(
            reverse('cerrar_sesion_caja', args=[self.sesion.pk]),
            {'monto_cierre_declarado': '100.00', 'observaciones': ''},
        )
        self.assertRedirects(resp, reverse('detalle_sesion_caja', args=[self.sesion.pk]))
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'cerrada')
        self.assertEqual(self.sesion.diferencia, Decimal('0.00'))
        self.assertEqual(self.sesion.monto_cierre_declarado, Decimal('100.00'))

    def test_cierre_con_diferencia_requiere_observaciones(self):
        """Monto declarado != saldo y sin observaciones → error, no cierra."""
        resp = self.client.post(
            reverse('cerrar_sesion_caja', args=[self.sesion.pk]),
            {'monto_cierre_declarado': '150.00', 'observaciones': ''},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context['form'], 'observaciones',
                             'Las observaciones son requeridas cuando hay diferencia.')
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, 'abierta')
