"""
"A lo sumo una CajaSesion abierta" sin depender de la base de datos.

En producción (MariaDB) Django IGNORA el UniqueConstraint condicional
`unique_caja_abierta` (models.W036), así que la regla tiene que vivir en el
código. Cubre:

  - `sesion_abierta()` / `_sesion_activa()` fallan CERRADO (error claro, sin
    elegir una sesión al azar) si hay 2+ abiertas.
  - El turno de cobro y de reversión propagan ese error como TurnoCajaError,
    o sea un mensaje al usuario y nunca un 500 ni un cobro en la caja "equivocada".
  - El Administrador puede cerrar una de las dos (force-close por pk) para
    salir de la situación.
  - `abrir_sesion_caja` re-chequea dentro del bloqueo de apertura: aunque la
    base no tenga el constraint, no crea una segunda sesión.
  - `bloqueo_apertura_caja` toma un GET_LOCK nombrado en MySQL/MariaDB y lo
    libera siempre; en otros motores no hace nada.

Para simular "la base no tiene el constraint" en SQLite se hace DROP INDEX
dentro del test (el DDL de SQLite es transaccional: el rollback de TestCase
lo restaura).
"""
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.urls import reverse

from misastreria import caja_signals, caja_turno
from misastreria.caja_turno import (
    CajasAbiertasMultiplesError, TurnoCajaError, sesion_abierta,
    verificar_turno_cobro, verificar_turno_reversion,
)
from misastreria.models import CajaMovimiento, CajaSesion

from .factories import (
    desbloquear_caja_test, make_administrador, make_cajero, make_sesion_caja,
)


def quitar_constraint_de_caja_unica():
    """Deja la BD como en MariaDB: sin `unique_caja_abierta`. En motores que
    ya no lo crean (MySQL/MariaDB) no hace falta nada."""
    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX IF EXISTS unique_caja_abierta')


class DosSesionesAbiertasFallanCerradoTests(TestCase):

    def setUp(self):
        quitar_constraint_de_caja_unica()
        self.cajero_a = make_cajero(username='cajero_a_multi')
        self.cajero_b = make_cajero(username='cajero_b_multi')
        self.sesion_a = make_sesion_caja(usuario=self.cajero_a)
        self.sesion_b = make_sesion_caja(usuario=self.cajero_b)

    def test_precondicion_hay_dos_abiertas(self):
        self.assertEqual(CajaSesion.objects.filter(estado='abierta').count(), 2)

    def test_sesion_abierta_levanta_error_claro(self):
        with self.assertRaises(CajasAbiertasMultiplesError) as ctx:
            sesion_abierta()
        self.assertIn('Administrador', str(ctx.exception))

    def test_el_error_es_un_error_de_turno(self):
        self.assertTrue(issubclass(CajasAbiertasMultiplesError, TurnoCajaError))

    def test_verificar_turno_cobro_falla_para_cualquiera_incluido_el_dueno(self):
        for usuario in (self.cajero_a, self.cajero_b, make_administrador(username='adm_multi')):
            with self.assertRaises(CajasAbiertasMultiplesError):
                verificar_turno_cobro(usuario)

    def test_verificar_turno_reversion_falla_tambien_para_administrador(self):
        with self.assertRaises(CajasAbiertasMultiplesError):
            verificar_turno_reversion(make_administrador(username='adm_multi2'))

    def test_sesion_activa_de_signals_no_elige_una_al_azar(self):
        with self.assertRaises(CajasAbiertasMultiplesError):
            caja_signals._sesion_activa()

    def test_vistas_de_cobro_muestran_mensaje_no_500(self):
        self.client.force_login(self.cajero_a)
        desbloquear_caja_test(self.client, self.cajero_a)
        resp = self.client.get(reverse('lista_sesiones_caja'))
        self.assertLess(resp.status_code, 500)
        resp = self.client.get(reverse('crear_movimiento_caja'))
        self.assertLess(resp.status_code, 500)

    def test_paginas_con_topbar_no_revientan(self):
        admin = make_administrador(username='adm_multi3')
        self.client.force_login(admin)
        for nombre in ('dashboard', 'lista_sesiones_caja'):
            resp = self.client.get(reverse(nombre))
            self.assertLess(resp.status_code, 500, nombre)

    def test_administrador_puede_cerrar_una_por_pk_y_se_normaliza(self):
        admin = make_administrador(username='adm_multi4')
        self.client.force_login(admin)
        desbloquear_caja_test(self.client, admin)
        resp = self.client.post(
            reverse('cerrar_sesion_caja', args=[self.sesion_b.pk]),
            {'monto_cierre_declarado': '100', 'observaciones': 'Cierre por doble apertura'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CajaSesion.objects.filter(estado='abierta').count(), 1)
        self.assertEqual(sesion_abierta().pk, self.sesion_a.pk)

    def test_no_se_puede_abrir_otra_mas(self):
        nuevo = make_cajero(username='cajero_c_multi')
        self.client.force_login(nuevo)
        desbloquear_caja_test(self.client, nuevo)
        resp = self.client.post(reverse('abrir_sesion_caja'), {'monto_apertura': '100'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(CajaSesion.objects.filter(estado='abierta').count(), 2)


class AbrirSesionRecheckSinConstraintTests(TestCase):
    """Sin el constraint (MariaDB) la única defensa es el re-chequeo."""

    def setUp(self):
        quitar_constraint_de_caja_unica()

    def test_segunda_apertura_es_rechazada_por_el_codigo(self):
        make_sesion_caja(usuario=make_cajero(username='cajero_a_rc'))
        nuevo = make_cajero(username='cajero_b_rc')
        self.client.force_login(nuevo)
        desbloquear_caja_test(self.client, nuevo)

        resp = self.client.post(reverse('abrir_sesion_caja'), {'monto_apertura': '100'})

        self.assertEqual(resp.status_code, 200, 're-renderiza el form con error, no un 500')
        self.assertContains(resp, 'Ya existe una sesión de caja abierta')
        self.assertEqual(CajaSesion.objects.filter(estado='abierta').count(), 1)
        self.assertEqual(CajaMovimiento.objects.filter(concepto='apertura_caja').count(), 0)

    def test_primera_apertura_sigue_funcionando(self):
        nuevo = make_cajero(username='cajero_ok_rc')
        self.client.force_login(nuevo)
        desbloquear_caja_test(self.client, nuevo)
        resp = self.client.post(reverse('abrir_sesion_caja'), {'monto_apertura': '100'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CajaSesion.objects.filter(estado='abierta').count(), 1)

    def test_apertura_toma_el_bloqueo_de_apertura(self):
        nuevo = make_cajero(username='cajero_lock_rc')
        self.client.force_login(nuevo)
        desbloquear_caja_test(self.client, nuevo)
        with mock.patch.object(
            caja_turno, 'bloqueo_apertura_caja', wraps=caja_turno.bloqueo_apertura_caja,
        ) as espia:
            self.client.post(reverse('abrir_sesion_caja'), {'monto_apertura': '100'})
        espia.assert_called_once()


class BloqueoAperturaCajaTests(TestCase):

    def test_en_sqlite_no_ejecuta_sql_de_bloqueo(self):
        if connection.vendor == 'mysql':
            self.skipTest('sólo aplica a motores sin GET_LOCK')
        with caja_turno.bloqueo_apertura_caja():
            pass

    def test_en_mysql_toma_y_libera_get_lock(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (1,)
        fake = mock.MagicMock(vendor='mysql', settings_dict={'NAME': 'bd_x'})
        fake.cursor.return_value = cursor
        with mock.patch.object(caja_turno, 'connection', fake):
            with caja_turno.bloqueo_apertura_caja():
                pass
        sqls = [c.args[0] for c in cursor.execute.call_args_list]
        self.assertTrue(sqls[0].startswith('SELECT GET_LOCK'))
        self.assertTrue(sqls[-1].startswith('SELECT RELEASE_LOCK'))

    def test_en_mysql_libera_el_lock_aunque_falle_el_cuerpo(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (1,)
        fake = mock.MagicMock(vendor='mysql', settings_dict={'NAME': 'bd_x'})
        fake.cursor.return_value = cursor
        with mock.patch.object(caja_turno, 'connection', fake):
            with self.assertRaises(RuntimeError):
                with caja_turno.bloqueo_apertura_caja():
                    raise RuntimeError('boom')
        self.assertTrue(cursor.execute.call_args_list[-1].args[0].startswith('SELECT RELEASE_LOCK'))

    def test_en_mysql_si_no_obtiene_el_lock_falla_cerrado(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (0,)
        fake = mock.MagicMock(vendor='mysql', settings_dict={'NAME': 'bd_x'})
        fake.cursor.return_value = cursor
        with mock.patch.object(caja_turno, 'connection', fake):
            with self.assertRaises(TurnoCajaError):
                with caja_turno.bloqueo_apertura_caja():
                    self.fail('no debe ejecutar el cuerpo sin el lock')


class BannerCajasMultiplesTests(TestCase):

    def test_base_avisa_de_cajas_multiples(self):
        quitar_constraint_de_caja_unica()
        make_sesion_caja(usuario=make_cajero(username='ban_a'))
        make_sesion_caja(usuario=make_cajero(username='ban_b'))
        admin = make_administrador(username='ban_adm')
        self.client.force_login(admin)
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Hay más de una caja abierta')
        self.assertNotContains(resp, 'Caja cerrada.')
