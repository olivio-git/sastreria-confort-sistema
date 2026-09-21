"""Una venta con saldo se puede seguir cobrando, sea cual sea su estado.

`Venta.estado` responde una pregunta: si la mercadería salió («efectuada», los
items pasan a baja) o quedó reservada («en_proceso»). El saldo responde otra:
si está la plata. El formulario de creación deja elegir el estado, y el modelo
trae 'efectuada' por defecto.

Mientras el cobro se decidió por `estado`, cualquier venta creada como
«efectuada» con un pago parcial quedaba trabada: la vista rechazaba el pago
—«La venta ya está efectuada»— y la pantalla mostraba «completamente pagada»
al lado de un saldo de Bs 100. El dinero faltante no tenía por dónde entrar.

Se descubrió en producción con VEN-067: total Bs 600, pagado Bs 500.
"""
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from misastreria.caja_signals import registrar_pago_venta
from misastreria.models import Venta
from .factories import make_user, make_venta


class PagoDeVentaEfectuadaConSaldoTests(TestCase):
    def setUp(self):
        self.usuario = make_user()
        self.client = Client()
        self.client.force_login(self.usuario)
        # Se reproduce el flujo real de `crear_venta`: la venta nace SIN total
        # —los ítems se agregan después— y recién entonces se fija el importe.
        # Importa: `venta_to_caja` es un post_save que, si el total ya está
        # puesto al crear, cobra el total entero de una. Crear con total=600
        # dispararía ese fallback y el test mediría otra cosa. El `update()`
        # evita el save() y, con él, la señal.
        self.venta = make_venta(estado='efectuada')
        Venta.objects.filter(pk=self.venta.pk).update(
            total=Decimal('600'), subtotal=Decimal('600'))
        self.venta.refresh_from_db()

        registrar_pago_venta(self.venta, Decimal('500'), 'qr', 'Pago venta',
                             self.usuario, via_caja=False)
        self.venta.refresh_from_db()

    def test_el_saldo_se_calcula_bien(self):
        self.assertEqual(self.venta.total_pagado, Decimal('500'))
        self.assertEqual(self.venta.saldo_pendiente, Decimal('100'))

    def test_se_puede_cobrar_el_saldo_de_una_venta_efectuada(self):
        respuesta = self.client.post(
            reverse('agregar_pago_venta', args=[self.venta.id]),
            {'monto': '100', 'forma_pago': 'efectivo'})
        self.assertEqual(respuesta.status_code, 302)

        self.venta.refresh_from_db()
        self.assertEqual(self.venta.saldo_pendiente, Decimal('0'),
                         'el saldo tenía que quedar saldado')
        self.assertEqual(self.venta.total_pagado, Decimal('600'))

    def test_una_venta_sin_saldo_no_acepta_mas_pagos(self):
        registrar_pago_venta(self.venta, Decimal('100'), 'efectivo', 'Saldo',
                             self.usuario, via_caja=False)
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.saldo_pendiente, Decimal('0'))

        self.client.post(reverse('agregar_pago_venta', args=[self.venta.id]),
                         {'monto': '50', 'forma_pago': 'efectivo'})
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.total_pagado, Decimal('600'),
                         'no se puede cobrar de más sobre una venta saldada')

    def test_la_pantalla_no_afirma_pago_completo_habiendo_saldo(self):
        html = self.client.get(
            reverse('detalle_venta', args=[self.venta.id])).content.decode()
        self.assertNotIn('Completamente pagada', html,
                         'la pantalla afirma pago completo con saldo pendiente')
        self.assertIn('Registrar pago', html,
                      'sin formulario de cobro, el saldo no tiene por dónde entrar')
