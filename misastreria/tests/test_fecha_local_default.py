"""
test_fecha_local_default.py
============================
En producción el contenedor corre en UTC. `models.DateField(default=timezone.now)`
guardaba la fecha de `timezone.now()`, que es un datetime aware en UTC: después
de las 20:00 hora local (America/La_Paz, UTC-4) esa fecha ya cayó al día
siguiente en UTC, así que los formularios de venta/alquiler (y varios otros)
mostraban y guardaban la fecha de MAÑANA. `date.today()` en vistas tenía el
mismo problema porque toma la zona horaria del reloj del servidor (UTC en
producción), no la del negocio.

Fix: todo DateField que representa "la fecha de hoy para el negocio" usa
`django.utils.timezone.localdate` (respeta TIME_ZONE), y las vistas que
llamaban `date.today()` ahora llaman `django_tz.localdate()`.

Instante elegido a propósito para que el bug se note: 2026-09-20 01:30 UTC
== 2026-09-19 21:30 en La Paz. Son las 21:30 locales (después de las 20:00),
pero en UTC ya es el día 20. Con el bug, todo esto habría guardado/mostrado
2026-09-20; con el fix, debe guardar/mostrar 2026-09-19.
"""
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse

from misastreria.models import (
    Cliente, Corte, Confeccion, OrdenProduccion, Transaccion, Venta, Alquiler,
)
from .factories import make_user, make_prenda, make_prenda_item


UTC_DT = datetime(2026, 9, 20, 1, 30, tzinfo=dt_timezone.utc)
LOCAL_DATE = date(2026, 9, 19)


@patch('django.utils.timezone.now', return_value=UTC_DT)
class FechaLocalPorDefectoTests(TestCase):
    """'Hoy' para el negocio es la fecha en La Paz, nunca la fecha en UTC."""

    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_formulario_nueva_venta_muestra_fecha_local(self, mock_now):
        resp = self.client.get(reverse('crear_venta'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['form']['fecha_venta'].value(), LOCAL_DATE)

    def test_formulario_nuevo_alquiler_muestra_fecha_local(self, mock_now):
        resp = self.client.get(reverse('crear_alquiler'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['form']['fecha_alquiler'].value(), LOCAL_DATE)

    def test_venta_sin_fecha_explicita_guarda_fecha_local(self, mock_now):
        venta = Venta.objects.create(
            descuento=Decimal('0'), subtotal=Decimal('0'), total=Decimal('0'),
        )
        self.assertEqual(venta.fecha_venta, LOCAL_DATE)

    def test_alquiler_sin_fecha_explicita_guarda_fecha_local(self, mock_now):
        alquiler = Alquiler.objects.create(
            fecha_devolucion=date(2026, 9, 25),
            total=Decimal('200.00'), subtotal=Decimal('200.00'),
        )
        self.assertEqual(alquiler.fecha_alquiler, LOCAL_DATE)

    def test_defaults_de_otros_modelos_usan_fecha_local(self, mock_now):
        cliente = Cliente.objects.create(
            codigo='CLI-T900', nombres='Test', apellido_paterno='Prueba',
            celular='+59171234567',
        )
        self.assertEqual(cliente.fecha_registro, LOCAL_DATE)

        corte = Corte.objects.create()
        self.assertEqual(corte.fecha, LOCAL_DATE)

        confeccion = Confeccion.objects.create(codigo='CONF-T900', color='Negro', modelo='Test')
        self.assertEqual(confeccion.fecha_inicio, LOCAL_DATE)

        orden = OrdenProduccion.objects.create()
        self.assertEqual(orden.fecha_inicio, LOCAL_DATE)

        txn = Transaccion.objects.create(
            descripcion='Test', tipo_servicio='otros', cantidad=1, monto=Decimal('10.00'),
        )
        self.assertEqual(txn.fecha, LOCAL_DATE)

    def test_baja_prenda_item_usa_fecha_local(self, mock_now):
        # Uno de los `date.today()` reemplazados por `django_tz.localdate()`.
        prenda = make_prenda()
        item = make_prenda_item(prenda=prenda, estado='disponible')
        resp = self.client.post(reverse('baja_prenda_item', args=[item.id]))
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.fecha_baja, LOCAL_DATE)
