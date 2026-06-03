"""
test_confeccion_pagos_divididos.py
==================================
Cubre el pago dividido (varias formas de pago en un mismo cobro) de Confecciones:
  - Adelanto inicial dividido al crear  -> N movimientos confeccion_pago
  - Pago dividido en el detalle           -> N movimientos confeccion_pago
  - Validación: el total no puede exceder el saldo
Cada línea {monto, forma_pago} se registra como un movimiento confeccion_pago
(el único concepto que el UniqueConstraint permite múltiple).
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from .factories import (
    make_user, make_confeccion, make_sesion_caja, make_tipo_prenda,
)
from misastreria.models import Confeccion, ConfeccionItem, CajaMovimiento


def _movs_pago(confeccion):
    return CajaMovimiento.objects.filter(
        referencia_confeccion=confeccion,
        concepto='confeccion_pago',
        movimiento_reverso__isnull=True,
    )


class CrearConfeccionAdelantoDivididoTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.sesion = make_sesion_caja()
        self.tp = make_tipo_prenda()

    def _post_crear(self, extra):
        data = {
            'fecha_inicio': date.today().isoformat(),
            'color': 'Negro', 'modelo': 'Traje', 'precio': '0',
            'estado': 'pendiente',
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-tipo_prenda': str(self.tp.id),
            'items-0-costo': '300.00',
            'items-0-talla': '',
        }
        data.update(extra)
        return self.client.post(reverse('crear_confeccion'), data)

    def test_adelanto_dividido_crea_dos_movimientos(self):
        resp = self._post_crear({
            'via_caja': 'on',
            'pago[0][monto]': '200.00', 'pago[0][forma_pago]': 'efectivo',
            'pago[1][monto]': '100.00', 'pago[1][forma_pago]': 'qr',
        })
        self.assertEqual(resp.status_code, 302)
        c = Confeccion.objects.latest('id')
        self.assertEqual(c.precio, Decimal('300.00'))
        movs = _movs_pago(c)
        self.assertEqual(movs.count(), 2)
        formas = sorted(m.forma_pago for m in movs)
        self.assertEqual(formas, ['efectivo', 'qr'])
        self.assertEqual(c.total_pagado, Decimal('300.00'))
        self.assertEqual(c.saldo_pendiente, Decimal('0'))

    def test_sin_adelanto_no_crea_movimientos(self):
        resp = self._post_crear({'via_caja': 'on'})
        self.assertEqual(resp.status_code, 302)
        c = Confeccion.objects.latest('id')
        self.assertEqual(_movs_pago(c).count(), 0)
        self.assertEqual(c.saldo_pendiente, Decimal('300.00'))

    def test_adelanto_excede_precio_no_registra(self):
        resp = self._post_crear({
            'via_caja': 'on',
            'pago[0][monto]': '400.00', 'pago[0][forma_pago]': 'efectivo',
        })
        self.assertEqual(resp.status_code, 302)
        c = Confeccion.objects.latest('id')
        # excede el precio (300) -> no se registra adelanto
        self.assertEqual(_movs_pago(c).count(), 0)


class AgregarPagoConfeccionDivididoTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.sesion = make_sesion_caja()
        self.conf = make_confeccion(precio=Decimal('500.00'), saldo=Decimal('500.00'))

    def test_pago_dividido_en_detalle(self):
        resp = self.client.post(
            reverse('agregar_pago_confeccion', kwargs={'id': self.conf.id}),
            {
                'via_caja': 'on', 'descripcion': '',
                'pago[0][monto]': '300.00', 'pago[0][forma_pago]': 'transferencia',
                'pago[1][monto]': '200.00', 'pago[1][forma_pago]': 'efectivo',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.conf.refresh_from_db()
        self.assertEqual(_movs_pago(self.conf).count(), 2)
        self.assertEqual(self.conf.total_pagado, Decimal('500.00'))
        self.assertEqual(self.conf.saldo_pendiente, Decimal('0'))

    def test_pago_excede_saldo_no_registra(self):
        resp = self.client.post(
            reverse('agregar_pago_confeccion', kwargs={'id': self.conf.id}),
            {
                'via_caja': 'on',
                'pago[0][monto]': '600.00', 'pago[0][forma_pago]': 'efectivo',
            },
        )
        # no redirige (queda en la página con error), no registra nada
        self.assertEqual(_movs_pago(self.conf).count(), 0)

    def test_pago_simple_modal_sigue_funcionando(self):
        """El modal 'Completar pago' envía monto/forma_pago simples (back-compat)."""
        resp = self.client.post(
            reverse('agregar_pago_confeccion', kwargs={'id': self.conf.id}),
            {'monto': '500.00', 'forma_pago': 'efectivo', 'via_caja': 'on'},
        )
        self.assertEqual(resp.status_code, 302)
        self.conf.refresh_from_db()
        self.assertEqual(_movs_pago(self.conf).count(), 1)
        self.assertEqual(self.conf.saldo_pendiente, Decimal('0'))
