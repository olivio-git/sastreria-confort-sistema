"""
test_documentos_hora_local.py
=============================
Con USE_TZ=True los DateTimeField viajan en UTC. Las plantillas de Django
convierten solas a America/La_Paz, pero strftime() no: imprimía el UTC crudo
y los documentos salían 4 horas adelantados respecto a la pantalla.

Cubre que el Excel de sesión de caja (apertura, cierre y movimientos) y el
__str__ de CajaSesion usen la hora local.
"""
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO

import openpyxl
from django.test import TestCase, Client
from django.urls import reverse

from misastreria.views import _fmt_dt
from .factories import make_user, make_sesion_caja, make_movimiento_caja


# 2026-07-24 23:30 UTC == 2026-07-24 19:30 en La Paz (UTC-4).
# Elegido a propósito para que el bug se note: en UTC la hora es 23:30.
UTC_DT    = datetime(2026, 7, 24, 23, 30, tzinfo=dt_timezone.utc)
LOCAL_STR = '24/07/2026 19:30'
UTC_STR   = '24/07/2026 23:30'


class FmtDtTests(TestCase):

    def test_convierte_utc_a_hora_local(self):
        self.assertEqual(_fmt_dt(UTC_DT), LOCAL_STR)

    def test_none_devuelve_el_vacio_indicado(self):
        self.assertEqual(_fmt_dt(None), '')
        self.assertEqual(_fmt_dt(None, vacio='—'), '—')

    def test_respeta_el_formato_pedido(self):
        self.assertEqual(_fmt_dt(UTC_DT, '%Y%m%d'), '20260724')


class ExcelSesionCajaHoraLocalTests(TestCase):

    def setUp(self):
        self.user   = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.sesion = make_sesion_caja(
            usuario=self.user,
            monto_apertura=Decimal('100.00'),
            fecha_apertura=UTC_DT,
        )

    def _descargar(self):
        resp = self.client.get(reverse('export_detalle_sesion_excel', args=[self.sesion.pk]))
        self.assertEqual(resp.status_code, 200)
        return openpyxl.load_workbook(BytesIO(resp.content))

    def test_fecha_apertura_y_cierre_en_hora_local(self):
        self.sesion.fecha_cierre = UTC_DT
        self.sesion.estado       = 'cerrada'
        self.sesion.save(update_fields=['fecha_cierre', 'estado'])

        ws      = self._descargar().worksheets[0]
        valores = [c.value for row in ws.iter_rows() for c in row]

        # Apertura y cierre comparten el mismo instante: debe aparecer dos veces.
        self.assertEqual(valores.count(LOCAL_STR), 2)
        self.assertNotIn(UTC_STR, valores)

    def test_movimientos_en_hora_local(self):
        make_movimiento_caja(sesion=self.sesion, fecha=UTC_DT)

        ws2     = self._descargar().worksheets[1]
        valores = [c.value for row in ws2.iter_rows() for c in row]

        self.assertIn(LOCAL_STR, valores)
        self.assertNotIn(UTC_STR, valores)

    def test_nombre_de_archivo_usa_el_dia_local(self):
        # 23:30 UTC ya es el día 25 en UTC solo a partir de las 20:00 local;
        # acá 19:30 local sigue siendo el 24, que es lo que debe ir al nombre.
        resp = self.client.get(reverse('export_detalle_sesion_excel', args=[self.sesion.pk]))
        self.assertIn('20260724', resp['Content-Disposition'])


class CajaSesionStrTests(TestCase):

    def test_str_usa_hora_local(self):
        sesion = make_sesion_caja(fecha_apertura=UTC_DT)
        self.assertIn('2026-07-24 19:30', str(sesion))
