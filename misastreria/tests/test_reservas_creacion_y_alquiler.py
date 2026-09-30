"""
Reservas (`via_caja=False`) que no pasan por la transición de entrega:

  - Confección creada directamente como 'entregado' con pagos reservados: se
    liberan al crear, en la sesión del creador (verify ronda 5, WARNING 1).
  - Alquiler: la devolución es el fin del servicio; libera las reservas en la
    sesión de quien devuelve, sólo si es dueño del turno y de forma atómica
    (verify ronda 5, WARNING 2).
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.caja_signals import registrar_pago_alquiler
from misastreria.models import CajaMovimiento, Confeccion
from .factories import (
    make_administrador, make_alquiler, make_alquiler_item, make_cajero,
    make_sesion_caja, make_tipo_prenda,
)


class CrearConfeccionEntregadaConReservaTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.tp = make_tipo_prenda()
        self.client.force_login(self.admin)

    def _post(self, estado, extra=None):
        data = {
            'fecha_inicio': date.today().isoformat(),
            'color': 'Negro', 'modelo': 'Traje', 'precio': '0', 'estado': estado,
            'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0', 'items-MAX_NUM_FORMS': '1000',
            'items-0-tipo_prenda': str(self.tp.id), 'items-0-costo': '200.00', 'items-0-talla': '',
            'pago[0][monto]': '200.00', 'pago[0][forma_pago]': 'efectivo',  # sin via_caja: reserva
        }
        data.update(extra or {})
        return self.client.post(reverse('crear_confeccion'), data)

    def _reservas(self):
        return CajaMovimiento.objects.filter(
            referencia_confeccion__isnull=False, via_caja=False, movimiento_reverso__isnull=True)

    def test_entregada_al_crear_libera_la_reserva_en_la_sesion_del_creador(self):
        sesion = make_sesion_caja(usuario=self.admin)
        resp = self._post('entregado')
        self.assertEqual(resp.status_code, 302)
        c = Confeccion.objects.get()
        self.assertEqual(c.estado, 'entregado')
        self.assertFalse(self._reservas().exists())
        mov = CajaMovimiento.objects.get(referencia_confeccion=c, concepto='confeccion_pago')
        self.assertTrue(mov.via_caja)
        self.assertEqual(mov.sesion_id, sesion.pk)

    def test_pendiente_al_crear_mantiene_la_reserva(self):
        make_sesion_caja(usuario=self.admin)
        self._post('pendiente')
        self.assertEqual(self._reservas().count(), 1)

    def test_si_no_es_dueno_del_turno_no_se_crea_nada(self):
        make_sesion_caja(usuario=make_cajero())
        self._post('entregado')
        self.assertFalse(Confeccion.objects.exists())
        self.assertFalse(CajaMovimiento.objects.filter(referencia_confeccion__isnull=False).exists())


class AlquilerLiberaReservasAlDevolverTests(TestCase):
    def setUp(self):
        self.admin = make_administrador()
        self.cajero = make_cajero()
        self.alquiler = make_alquiler(estado='alquilado', total=Decimal('200.00'))
        self.item = make_alquiler_item(self.alquiler)
        self.item.prenda_item.estado = 'alquilado'
        self.item.prenda_item.save(update_fields=['estado'])
        self.url = reverse('devolver_alquiler', args=[self.alquiler.pk])

    def _reservar(self, monto, quien):
        registrar_pago_alquiler(
            self.alquiler, Decimal(monto), 'efectivo', '', quien, via_caja=False)

    def _reservas(self):
        return CajaMovimiento.objects.filter(
            referencia_alquiler=self.alquiler, via_caja=False, movimiento_reverso__isnull=True)

    def test_reserva_completa_se_libera_en_la_sesion_de_quien_devuelve(self):
        turno_viejo = make_sesion_caja(usuario=self.cajero)
        self._reservar('200', self.cajero)
        turno_viejo.estado = 'cerrada'
        turno_viejo.save()
        turno = make_sesion_caja(usuario=self.admin)
        self.client.force_login(self.admin)

        resp = self.client.post(self.url)

        self.assertEqual(resp.status_code, 302)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'devuelto')
        self.assertFalse(self._reservas().exists())
        mov = CajaMovimiento.objects.get(referencia_alquiler=self.alquiler, concepto='alquiler_pago')
        self.assertTrue(mov.via_caja)
        self.assertEqual(mov.sesion_id, turno.pk)

    def test_reserva_parcial_tambien_se_libera_al_devolver(self):
        make_sesion_caja(usuario=self.admin)
        self._reservar('50', self.admin)
        self.client.force_login(self.admin)
        self.client.post(self.url)
        self.assertFalse(self._reservas().exists())

    def test_no_dueno_del_turno_no_devuelve_ni_libera(self):
        make_sesion_caja(usuario=self.cajero)
        self._reservar('200', self.cajero)
        self.client.force_login(self.admin)
        self.client.post(self.url)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'alquilado')
        self.assertEqual(self._reservas().count(), 1)

    def test_sin_reservas_devuelve_sin_exigir_turno(self):
        self.client.force_login(self.admin)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 302)
        self.alquiler.refresh_from_db()
        self.assertEqual(self.alquiler.estado, 'devuelto')
