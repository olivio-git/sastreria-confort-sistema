"""
test_fechas.py
==============
MariaDB de produccion (hosting compartido) NO tiene cargadas las tablas de
zona horaria, asi que CONVERT_TZ(...) devuelve NULL. Con USE_TZ=True Django
implementa __date/__year/__month/Trunc*/Extract* sobre DateTimeField con
CONVERT_TZ, por lo que esos filtros no devolvian nada.

La solucion: filtrar con rangos semiabiertos de datetimes aware
[inicio del dia local, inicio del dia siguiente) via misastreria.fechas.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.test import SimpleTestCase
from django.utils import timezone

from misastreria import fechas

LP = timezone.get_current_timezone()


def local(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=LP)


class RangoDiaTests(SimpleTestCase):

    def test_inicio_y_fin_son_medianoche_local(self):
        ini, fin = fechas.rango_dia(date(2026, 9, 30))
        self.assertEqual(ini, local(2026, 9, 30))
        self.assertEqual(fin, local(2026, 10, 1))

    def test_son_aware(self):
        ini, fin = fechas.rango_dia(date(2026, 9, 30))
        self.assertTrue(timezone.is_aware(ini))
        self.assertTrue(timezone.is_aware(fin))

    def test_offset_utc_menos_cuatro(self):
        ini, fin = fechas.rango_dia(date(2026, 9, 30))
        self.assertEqual(ini.astimezone(dt_timezone.utc),
                         datetime(2026, 9, 30, 4, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(fin.astimezone(dt_timezone.utc),
                         datetime(2026, 10, 1, 4, 0, tzinfo=dt_timezone.utc))

    def test_23_59_59_local_pertenece_al_dia(self):
        ini, fin = fechas.rango_dia(date(2026, 9, 30))
        dt = local(2026, 9, 30, 23, 59, 59)
        self.assertTrue(ini <= dt < fin)

    def test_00_00_del_dia_siguiente_queda_fuera(self):
        ini, fin = fechas.rango_dia(date(2026, 9, 30))
        self.assertFalse(ini <= local(2026, 10, 1) < fin)

    def test_las_20_local_son_00_utc_del_dia_siguiente_pero_pertenecen_al_dia_local(self):
        # 2026-09-30 20:00 La Paz == 2026-10-01 00:00 UTC
        ini, fin = fechas.rango_dia(date(2026, 9, 30))
        dt = datetime(2026, 10, 1, 0, 0, tzinfo=dt_timezone.utc)
        self.assertTrue(ini <= dt < fin)

    def test_cambio_de_mes_y_anio(self):
        ini, fin = fechas.rango_dia(date(2026, 12, 31))
        self.assertEqual(fin, local(2027, 1, 1))


class RangoFechasTests(SimpleTestCase):

    def test_desde_y_hasta_inclusivos(self):
        ini, fin = fechas.rango_fechas(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(ini, local(2026, 9, 1))
        self.assertEqual(fin, local(2026, 10, 1))

    def test_acepta_strings_iso(self):
        ini, fin = fechas.rango_fechas('2026-09-01', '2026-09-30')
        self.assertEqual(ini, local(2026, 9, 1))
        self.assertEqual(fin, local(2026, 10, 1))

    def test_vacios_y_none_dan_none(self):
        self.assertEqual(fechas.rango_fechas('', None), (None, None))
        ini, fin = fechas.rango_fechas('2026-09-01', '')
        self.assertEqual(ini, local(2026, 9, 1))
        self.assertIsNone(fin)

    def test_string_invalido_se_ignora_como_vacio(self):
        self.assertEqual(fechas.rango_fechas('basura', 'xx'), (None, None))

    def test_un_solo_dia(self):
        ini, fin = fechas.rango_fechas(date(2026, 9, 30), date(2026, 9, 30))
        self.assertEqual((ini, fin), fechas.rango_dia(date(2026, 9, 30)))


class FiltroRangoTests(SimpleTestCase):

    def test_arma_kwargs_semiabiertos(self):
        kw = fechas.filtro_rango('fecha', date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(kw, {
            'fecha__gte': local(2026, 9, 1),
            'fecha__lt': local(2026, 10, 1),
        })

    def test_omite_los_extremos_vacios(self):
        self.assertEqual(fechas.filtro_rango('creado', '', ''), {})
        self.assertEqual(list(fechas.filtro_rango('creado', None, '2026-09-30')),
                         ['creado__lt'])


class FechaLocalTests(SimpleTestCase):

    def test_fecha_local_convierte_utc_a_local(self):
        # 2026-10-01 02:00 UTC == 2026-09-30 22:00 La Paz
        dt = datetime(2026, 10, 1, 2, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(fechas.fecha_local(dt), date(2026, 9, 30))
