"""
Guarda anti-regresion: ningun lookup/funcion que dependa de la zona horaria
sobre un DateTimeField puede entrar en misastreria/*.py.

Por que: en MySQL/MariaDB con USE_TZ=True esos lookups usan CONVERT_TZ(), que
devuelve NULL cuando el servidor no tiene las tablas de zona horaria (hosting
compartido de produccion) y el filtro no devuelve nada. Ver misastreria/fechas.py.

Que hacer en cambio:
  * filtrar -> filtro_rango('campo', desde, hasta) / rango_dia(fecha)
  * agrupar -> traer los datetimes y agrupar en Python (sumar_por_dia, fecha_local)

Los lookups sobre DateField (fecha_venta, fecha_alquiler, ...) NO pasan por
CONVERT_TZ y son seguros: si alguno de esos nombres coincide con el de un
DateTimeField, agregarlo a PERMITIDOS con una justificacion.
"""
import ast
import re
from pathlib import Path

from django.apps import apps
from django.db import models
from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parent.parent
TRANSFORMS = (
    'date', 'year', 'iso_year', 'month', 'day', 'week', 'week_day',
    'iso_week_day', 'quarter', 'hour', 'minute', 'second', 'time',
)
PATRON_LOOKUP = re.compile(r'(?:^|__)(\w+?)__(%s)(?:__\w+)?$' % '|'.join(TRANSFORMS))
FUNCIONES_TZ = re.compile(r'^(Trunc\w*|Extract\w*)$')
METODOS_TZ = {'dates', 'datetimes'}

# {(archivo relativo a misastreria/, 'campo__transform'): 'por que es seguro'}
PERMITIDOS = {}


def _campos_datetime():
    nombres = set()
    for modelo in apps.get_app_config('misastreria').get_models():
        for campo in modelo._meta.get_fields():
            if isinstance(campo, models.DateTimeField):
                nombres.add(campo.name)
    return nombres


def hallazgos_en_fuente(fuente, nombre_archivo, campos_dt):
    """Lista de (archivo, linea, texto) con usos peligrosos en ``fuente``."""
    arbol = ast.parse(fuente)
    salida = []

    def revisar_lookup(texto, linea):
        m = PATRON_LOOKUP.search(texto)
        if not m:
            return
        campo, transform = m.group(1), m.group(2)
        if campo in campos_dt and (nombre_archivo, f'{campo}__{transform}') not in PERMITIDOS:
            salida.append((nombre_archivo, linea, texto))

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.keyword) and nodo.arg:
            revisar_lookup(nodo.arg, nodo.value.lineno)
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if re.fullmatch(r'[\w]+', nodo.value):
                revisar_lookup(nodo.value, nodo.lineno)
        elif isinstance(nodo, ast.Name) and FUNCIONES_TZ.match(nodo.id):
            salida.append((nombre_archivo, nodo.lineno, nodo.id))
        elif isinstance(nodo, ast.Attribute):
            if FUNCIONES_TZ.match(nodo.attr) or nodo.attr in METODOS_TZ:
                salida.append((nombre_archivo, nodo.lineno, nodo.attr))
        elif isinstance(nodo, ast.alias) and FUNCIONES_TZ.match(nodo.name):
            salida.append((nombre_archivo, nodo.lineno if hasattr(nodo, 'lineno') else 0, nodo.name))
    return salida


class GuardaLookupsTzTests(SimpleTestCase):

    def test_el_detector_encuentra_lookups_peligrosos(self):
        campos = _campos_datetime()
        codigo = (
            "qs.filter(fecha__date__gte=d)\n"
            "qs.values('creado__month')\n"
            "qs.filter(fecha_apertura__year=2026)\n"
            "qs.annotate(d=TruncDate('fecha'))\n"
            "qs.dates('creado', 'month')\n"
        )
        self.assertEqual(len(hallazgos_en_fuente(codigo, 'x.py', campos)), 5)

    def test_el_detector_ignora_lookups_de_datefield_y_rangos(self):
        campos = _campos_datetime()
        codigo = (
            "qs.filter(fecha_venta__year=2026, fecha_alquiler__month=3)\n"
            "qs.filter(fecha__gte=a, fecha__lt=b, creado__gte=a)\n"
            "qs.values('fecha_inicio__month')\n"
        )
        self.assertEqual(hallazgos_en_fuente(codigo, 'x.py', campos), [])

    def test_no_hay_lookups_dependientes_de_zona_horaria_sobre_datetimefield(self):
        campos = _campos_datetime()
        self.assertIn('fecha', campos)
        self.assertIn('creado', campos)
        encontrados = []
        for ruta in sorted(RAIZ.rglob('*.py')):
            rel = ruta.relative_to(RAIZ).as_posix()
            if rel.startswith(('tests/', 'migrations/')):
                continue
            encontrados += hallazgos_en_fuente(ruta.read_text(encoding='utf-8'), rel, campos)
        self.assertEqual(
            encontrados, [],
            'Lookups que usan CONVERT_TZ (NULL en MariaDB sin tablas de zona '
            'horaria). Use misastreria.fechas (filtro_rango / sumar_por_dia):\n'
            + '\n'.join(f'  {a}:{l}  {t}' for a, l, t in encontrados),
        )
