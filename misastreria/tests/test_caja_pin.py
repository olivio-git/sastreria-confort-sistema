"""
Gate de PIN de caja — PC compartida del mostrador.

Spec (Caja PIN Unlock Specification):
  - Sin PIN configurado -> redirige a configurar_pin_caja.
  - PIN correcto -> desbloquea; PIN incorrecto -> rechaza.
  - 15 min de inactividad -> vuelve a pedir el PIN.
  - 5 intentos fallidos -> bloqueado hasta que un Administrador lo resetee.
  - Administrador NO está exento del gate.
"""
from unittest import mock
from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse

from misastreria.caja_turno import perfil_de, set_pin, resetear_pin, validar_pin
from .factories import make_administrador, make_cajero, desbloquear_caja_test


def _url_desbloquear(next_url):
    return f"{reverse('desbloquear_caja')}?{urlencode({'next': next_url})}"


class SinPinConfiguradoTests(TestCase):
    def test_redirige_a_configurar_pin(self):
        cajero = make_cajero()
        self.client.force_login(cajero)
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, reverse('configurar_pin_caja'))


class PinCorrectoDesbloqueaTests(TestCase):
    def test_pin_correcto_desbloquea_y_accede(self):
        cajero = make_cajero(pin='1234')
        self.client.force_login(cajero)
        resp = self.client.post(reverse('desbloquear_caja'), {'pin': '1234'})
        self.assertRedirects(resp, reverse('lista_sesiones_caja'))
        # Ya desbloqueado: la siguiente request a /caja/ pasa derecho.
        resp2 = self.client.get(reverse('lista_sesiones_caja'))
        self.assertEqual(resp2.status_code, 200)

    def test_pin_incorrecto_no_desbloquea(self):
        cajero = make_cajero(pin='1234')
        self.client.force_login(cajero)
        self.client.post(reverse('desbloquear_caja'), {'pin': '0000'})
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, _url_desbloquear(reverse('lista_sesiones_caja')))


class InactividadRebloqueaTests(TestCase):
    def test_vencido_pide_pin_de_nuevo(self):
        cajero = make_cajero(pin='1234')
        self.client.force_login(cajero)
        desbloquear_caja_test(self.client, cajero)
        session = self.client.session
        session['caja_pin_hasta'] = session['caja_pin_hasta'] - 20 * 60  # vencido hace rato
        session.save()
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, _url_desbloquear(reverse('lista_sesiones_caja')))

    def test_vigente_desliza_el_vencimiento(self):
        cajero = make_cajero(pin='1234')
        self.client.force_login(cajero)
        desbloquear_caja_test(self.client, cajero)
        hasta_original = self.client.session['caja_pin_hasta']
        self.client.get(reverse('lista_sesiones_caja'))
        self.assertGreaterEqual(self.client.session['caja_pin_hasta'], hasta_original)


class BloqueoPorIntentosTests(TestCase):
    def test_5_intentos_fallidos_bloquea(self):
        cajero = make_cajero(pin='1234')
        for _ in range(5):
            self.assertFalse(validar_pin(cajero, '0000'))
        perfil = perfil_de(cajero)
        self.assertTrue(perfil.pin_bloqueado)

    def test_bloqueado_rechaza_aunque_el_pin_sea_correcto(self):
        cajero = make_cajero(pin='1234')
        for _ in range(5):
            validar_pin(cajero, '0000')
        self.assertFalse(validar_pin(cajero, '1234'), 'bloqueado: ni el PIN correcto debe pasar')

    def test_administrador_resetea_pin_bloqueado(self):
        cajero = make_cajero(pin='1234')
        for _ in range(5):
            validar_pin(cajero, '0000')
        resetear_pin(cajero)
        perfil = perfil_de(cajero)
        self.assertFalse(perfil.pin_bloqueado)
        self.assertEqual(perfil.pin_hash, '')
        self.assertEqual(perfil.pin_intentos_fallidos, 0)

    def test_intento_correcto_resetea_contador(self):
        cajero = make_cajero(pin='1234')
        validar_pin(cajero, '0000')
        validar_pin(cajero, '0000')
        self.assertTrue(validar_pin(cajero, '1234'))
        perfil = perfil_de(cajero)
        self.assertEqual(perfil.pin_intentos_fallidos, 0)


class AdministradorNoExentoTests(TestCase):
    def test_administrador_tambien_pasa_por_el_gate(self):
        admin = make_administrador()
        self.client.force_login(admin)
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, reverse('configurar_pin_caja'))


class ConfigurarPinTests(TestCase):
    def test_requiere_password_y_pin_dos_veces(self):
        cajero = make_cajero(username='conf_pin', password='miclave123')
        self.client.force_login(cajero)
        resp = self.client.post(reverse('configurar_pin_caja'), {
            'password': 'miclave123', 'pin': '5678', 'pin2': '5678',
        })
        self.assertRedirects(resp, reverse('lista_sesiones_caja'))
        perfil = perfil_de(cajero)
        self.assertTrue(perfil.pin_hash)

    def test_password_incorrecta_rechaza(self):
        cajero = make_cajero(username='conf_pin2', password='miclave123')
        self.client.force_login(cajero)
        resp = self.client.post(reverse('configurar_pin_caja'), {
            'password': 'incorrecta', 'pin': '5678', 'pin2': '5678',
        })
        self.assertEqual(resp.status_code, 200)
        perfil = perfil_de(cajero)
        self.assertFalse(perfil.pin_hash)

    def test_pines_no_coinciden_rechaza(self):
        cajero = make_cajero(username='conf_pin3', password='miclave123')
        self.client.force_login(cajero)
        resp = self.client.post(reverse('configurar_pin_caja'), {
            'password': 'miclave123', 'pin': '5678', 'pin2': '9999',
        })
        self.assertEqual(resp.status_code, 200)
        perfil = perfil_de(cajero)
        self.assertFalse(perfil.pin_hash)

    def test_pin_bloqueado_no_puede_reconfigurar_por_su_cuenta(self):
        """CRITICAL: conocer la contraseña de la cuenta NO alcanza para saltar
        un bloqueo de PIN — sólo un Administrador puede resetearlo (spec:
        "hasta que un Administrador lo resetee"). Si `configurar_pin_caja`
        aceptara un POST acá, cualquiera que sepa la contraseña se auto-
        desbloquearía sin pasar por un Administrador."""
        cajero = make_cajero(username='conf_pin_bloq', password='miclave123', pin='1234')
        for _ in range(5):
            validar_pin(cajero, '0000')
        self.assertTrue(perfil_de(cajero).pin_bloqueado)

        self.client.force_login(cajero)
        resp = self.client.post(reverse('configurar_pin_caja'), {
            'password': 'miclave123', 'pin': '9999', 'pin2': '9999',
        })

        perfil = perfil_de(cajero)
        self.assertTrue(perfil.pin_bloqueado, 'el bloqueo no debe poder levantarse desde configurar_pin_caja')
        self.assertFalse(validar_pin(cajero, '9999'), 'el PIN nuevo no debe haberse guardado')
        self.assertNotEqual(resp.status_code, 200)

    def test_pin_bloqueado_get_redirige_a_desbloquear(self):
        cajero = make_cajero(username='conf_pin_bloq_get', password='miclave123', pin='1234')
        for _ in range(5):
            validar_pin(cajero, '0000')
        self.client.force_login(cajero)
        resp = self.client.get(reverse('configurar_pin_caja'))
        self.assertRedirects(resp, reverse('desbloquear_caja'))

    def test_pin_ya_configurado_no_bloqueado_no_puede_reconfigurar(self):
        """Un usuario con PIN vigente (no bloqueado) tampoco debe poder
        pisarlo vía `configurar_pin_caja` — ese flujo es sólo para el primer
        PIN o para después de un reset de Administrador (que borra
        `pin_hash`); de lo contrario cualquiera con la contraseña de la
        cuenta podría cambiarle el PIN a otra persona sin pasar por
        `/usuarios/`."""
        cajero = make_cajero(username='conf_pin_ya', password='miclave123', pin='1234')
        self.client.force_login(cajero)
        resp = self.client.post(reverse('configurar_pin_caja'), {
            'password': 'miclave123', 'pin': '9999', 'pin2': '9999',
        })
        self.assertNotEqual(resp.status_code, 200)
        self.assertFalse(validar_pin(cajero, '9999'))
        self.assertTrue(validar_pin(cajero, '1234'), 'el PIN original debe seguir siendo válido')


class BloquearCajaTests(TestCase):
    def test_bloquear_caja_borra_el_desbloqueo(self):
        cajero = make_cajero(pin='1234')
        self.client.force_login(cajero)
        desbloquear_caja_test(self.client, cajero)
        self.client.post(reverse('bloquear_caja'))
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertRedirects(resp, _url_desbloquear(reverse('lista_sesiones_caja')))


class VistasFueraDeCajaNoGateadasTests(TestCase):
    """El gate sólo aplica a /caja/*, no al resto del sistema."""

    def test_dashboard_no_pide_pin(self):
        cajero = make_cajero()
        self.client.force_login(cajero)
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
