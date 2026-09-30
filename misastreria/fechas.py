"""
Filtros por fecha local sobre DateTimeField, sin depender de CONVERT_TZ.

Por que existe
--------------
Con USE_TZ=True, Django implementa ``campo__date``, ``__year``, ``__month``,
``__day``, ``__week_day``, ``__hour``, ``Trunc*``, ``Extract*``, ``.dates()`` y
``.datetimes()`` sobre un DateTimeField con ``CONVERT_TZ()`` en MySQL/MariaDB.
Esa funcion devuelve NULL si el servidor no tiene cargadas las tablas de zona
horaria (es el caso del hosting compartido de produccion), y entonces el
filtro no encuentra nada.

Regla del proyecto
------------------
* DateTimeField (``CajaMovimiento.fecha``, ``CajaSesion.fecha_apertura``,
  ``creado`` de cualquier modelo, ``KardexEvento.timestamp`` ...): filtrar por
  rango semiabierto de datetimes aware ``[inicio, fin)`` con ``rango_dia`` /
  ``rango_fechas`` / ``filtro_rango``. Para agrupar por dia/mes/semana, traer
  los datetimes y agrupar en Python con ``fecha_local``.
* DateField (``fecha_venta``, ``fecha_alquiler``, ``fecha_inicio``,
  ``Transaccion.fecha`` ...): ``__gte`` / ``__lte`` / ``__year`` /
  ``__month`` son seguros (no pasan por CONVERT_TZ).

``misastreria/tests/test_sin_lookups_tz.py`` falla si se introduce un lookup
dependiente de zona horaria sobre un DateTimeField.
"""
from datetime import date, datetime, time, timedelta

from django.utils import timezone


def _a_fecha(valor):
    """date | 'YYYY-MM-DD' | ''/None/invalido -> date | None."""
    if isinstance(valor, datetime):
        return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()
    if isinstance(valor, date):
        return valor
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor).strip())
    except (ValueError, TypeError):
        return None


def _inicio_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min),
                               timezone.get_current_timezone())


def rango_dia(fecha):
    """(inicio del dia local, inicio del dia siguiente): intervalo [ini, fin)."""
    fecha = _a_fecha(fecha)
    return _inicio_del_dia(fecha), _inicio_del_dia(fecha + timedelta(days=1))


def rango_fechas(desde=None, hasta=None):
    """
    Convierte dos fechas inclusivas (date o 'YYYY-MM-DD') al intervalo
    semiabierto ``(inicio, fin)`` de datetimes aware. Un extremo vacio o
    invalido devuelve None en su lugar (sin limite), igual que el filtro
    "si hay desde/hasta" de las vistas.
    """
    d = _a_fecha(desde)
    h = _a_fecha(hasta)
    inicio = _inicio_del_dia(d) if d else None
    fin = _inicio_del_dia(h + timedelta(days=1)) if h else None
    return inicio, fin


def filtro_rango(campo, desde=None, hasta=None):
    """
    kwargs para ``.filter(**filtro_rango('fecha', desde, hasta))`` equivalentes
    a ``campo__date__gte=desde, campo__date__lte=hasta`` pero sin CONVERT_TZ.
    """
    inicio, fin = rango_fechas(desde, hasta)
    kwargs = {}
    if inicio is not None:
        kwargs[f'{campo}__gte'] = inicio
    if fin is not None:
        kwargs[f'{campo}__lt'] = fin
    return kwargs


def fecha_local(dt):
    """Fecha (date) en la zona horaria actual de un datetime aware o naive."""
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.date()


def sumar_por_dia(qs, campo='fecha', valor='monto'):
    """
    Suma ``valor`` agrupando por dia LOCAL de ``campo`` (DateTimeField) y
    devuelve ``{date: total}``. Reemplaza ``.values('campo__date').annotate(Sum)``
    que en MariaDB sin tablas de zona horaria agrupa todo bajo NULL.
    """
    from collections import defaultdict
    totales = defaultdict(lambda: 0)
    for dt, v in qs.values_list(campo, valor):
        totales[fecha_local(dt)] += v or 0
    return dict(totales)
