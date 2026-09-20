"""Backfill de AplicacionPagoComision para los PagoComisionEmpleado que ya
existían antes de la 0065.

Reparte cada pago histórico entre las devengaciones (asignaciones) del mismo
empleado por orden FIFO: el pago más viejo cubre primero la devengación más
vieja. Usa el mismo algoritmo puro que testea test_pago_comision_seleccion.py
(`misastreria.comisiones.asignar_pagos_fifo` — un módulo sin imports de
modelos de Django, así que traerlo acá no rompe la regla de "las migraciones
no importan modelos de la app": no hay modelo que importar, es sólo la
función de reparto).

Por qué FIFO y no otra regla: PagoComisionEmpleado nunca guardó a qué
devengación se destinaba cada pago — hasta la 0065 el saldo de comisión era
un solo número (Devengado − Pagado). FIFO es la única suposición razonable
sin inventar un dato que no existe: pagar lo más viejo primero.

Idempotente por REMANENTE: de cada pago sólo se reparte lo que todavía no
tiene aplicación (monto − suma de sus aplicaciones), y el saldo de arranque
de cada devengación resta lo ya aplicado. Re-correrla (o retomarla tras una
corrida cortada a mitad) no duplica nada y completa lo que faltaba, incluso
si un pago había quedado repartido sólo en parte.

Rendimiento: por empleado, una query por tipo de asignación (con
select_related para la fecha y el snapshot), una agregación por tipo para
lo ya aplicado y una para el remanente de los pagos — nada fila por fila.
Cada empleado se procesa en su propio transaction.atomic() (la migración
es no atómica a propósito): si falla a mitad, lo ya hecho queda y la
siguiente corrida sigue desde el remanente.

detalle_snapshot se arma con `misastreria.comisiones.detalle_snapshot`
(sólo atributos de campo, sirve con modelos históricos) — la misma
función que usa el pago en vivo.

Sobrante: un pago puede superar lo que hoy queda devengado (p. ej. si una
asignación se redujo después de haberse pagado). Ese sobrante se deja sin
aplicación a propósito — el saldo de comisión sigue siendo correcto
(Pagado = suma de pagos, sin cambios acá) y el detalle de empleado lo
muestra como "a favor / no aplicado" en vez de inventar una devengación
que no existe.

Reversible: `revertir` borra todas las AplicacionPagoComision (la tabla que
esta misma migración pobló). No toca PagoComisionEmpleado ni las
asignaciones — son el origen, no se tocan nunca.
"""
from datetime import date
from decimal import Decimal

from django.db import migrations, transaction
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce

from misastreria.comisiones import asignar_pagos_fifo, detalle_snapshot

_FECHA_MIN = date.min

# (clave, modelo de asignación, FK en AplicacionPagoComision,
#  select_related para fecha + snapshot, fecha de la operación)
TIPOS = [
    ('reparacion', 'ReparacionEmpleado', 'reparacion_empleado',
     ('reparacion__cliente',),
     lambda a: a.reparacion.fecha_entrega),
    ('confeccion', 'ConfeccionEmpleado', 'confeccion_empleado',
     ('confeccion__cliente',),
     lambda a: a.confeccion.fecha_entrega),
    ('venta', 'VentaItemEmpleado', 'venta_item_empleado',
     ('venta_item__venta__cliente', 'venta_item__prenda_item', 'venta_item__tipo_reparacion'),
     lambda a: a.venta_item.venta.fecha_venta),
    ('alquiler', 'AlquilerItemEmpleado', 'alquiler_item_empleado',
     ('alquiler_item__alquiler__cliente', 'alquiler_item__prenda_item', 'alquiler_item__tipo_reparacion'),
     lambda a: a.alquiler_item.alquiler.fecha_alquiler),
    ('produccion', 'OrdenProduccionEmpleado', 'produccion_empleado',
     ('orden',),
     lambda a: a.orden.fecha_estimada or a.orden.fecha_inicio),
]

_DEC = DecimalField(max_digits=12, decimal_places=2)


def _accruals_del_empleado(apps, empleado_id, AplicacionPagoComision, snapshot_max):
    """Devengaciones del empleado con saldo > 0 aún por aplicar, ordenadas
    oldest-first (fecha de la operación, tie-break por id)."""
    accruals = []
    for clave, nombre_modelo, fk_field, relacionados, fecha_fn in TIPOS:
        Modelo = apps.get_model('misastreria', nombre_modelo)
        filas = list(
            Modelo.objects.filter(empleado_id=empleado_id)
            .exclude(monto_comision_fijo=0)
            .select_related(*relacionados)
            .order_by('id')
        )
        if not filas:
            continue
        aplicado = {
            f[fk_field]: f['total'] or Decimal('0')
            for f in (
                AplicacionPagoComision.objects
                .filter(**{f'{fk_field}__in': [x.id for x in filas]})
                .values(fk_field)
                .annotate(total=Sum('monto'))
            )
        }
        for fila in filas:
            saldo = fila.monto_comision_fijo - aplicado.get(fila.id, Decimal('0'))
            if saldo <= 0:
                continue
            try:
                fecha = fecha_fn(fila)
            except Exception:
                fecha = None
            snapshot = detalle_snapshot(clave, fila, max_length=snapshot_max)

            def _aplicar(pago, monto, _fk_field=fk_field, _fila=fila, _snapshot=snapshot):
                AplicacionPagoComision.objects.create(
                    pago=pago, monto=monto, detalle_snapshot=_snapshot,
                    **{_fk_field: _fila},
                )

            accruals.append({
                'fecha': fecha or _FECHA_MIN,
                'id_orden': fila.id,
                'saldo': saldo,
                'aplicar': _aplicar,
            })
    accruals.sort(key=lambda a: (a['fecha'], a['id_orden']))
    return accruals


def poblar(apps, schema_editor):
    Empleado = apps.get_model('misastreria', 'Empleado')
    PagoComisionEmpleado = apps.get_model('misastreria', 'PagoComisionEmpleado')
    AplicacionPagoComision = apps.get_model('misastreria', 'AplicacionPagoComision')
    snapshot_max = AplicacionPagoComision._meta.get_field('detalle_snapshot').max_length

    empleado_ids = list(
        Empleado.objects.filter(pagos_comision__isnull=False)
        .distinct().order_by('id').values_list('id', flat=True)
    )

    for empleado_id in empleado_ids:
        with transaction.atomic():
            # Remanente sin aplicar de cada pago (idempotencia por remanente).
            pagos = list(
                PagoComisionEmpleado.objects.filter(empleado_id=empleado_id)
                .annotate(aplicado=Coalesce(Sum('aplicaciones__monto'), Value(Decimal('0')),
                                            output_field=_DEC))
                .filter(monto__gt=F('aplicado'))
                .order_by('fecha', 'creado', 'id')
            )
            if not pagos:
                continue
            accruals = _accruals_del_empleado(apps, empleado_id, AplicacionPagoComision, snapshot_max)
            if not accruals:
                continue
            asignar_pagos_fifo(pagos, accruals, monto_de=lambda p: p.monto - p.aplicado)


def revertir(apps, schema_editor):
    apps.get_model('misastreria', 'AplicacionPagoComision').objects.all().delete()


class Migration(migrations.Migration):

    # No atómica: cada empleado va en su propio transaction.atomic() (ver
    # docstring) para que una corrida cortada deje hecho lo ya procesado.
    atomic = False

    dependencies = [
        ('misastreria', '0065_aplicacion_pago_comision'),
    ]

    operations = [
        migrations.RunPython(poblar, revertir, atomic=False),
    ]
