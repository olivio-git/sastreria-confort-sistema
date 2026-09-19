"""Copia el empleado del arreglo de cada VentaItem/AlquilerItem a la tabla de
asignaciones, para que un arreglo pueda tener más de un empleado.

Mismo movimiento que la 0048 hizo para reparaciones y confecciones, y con las
mismas tres propiedades, que son las que la hacen segura en producción:

  · ADITIVA      las columnas `empleado` y `monto_comision_fijo` de los items
                 NO se tocan. Si algo sale mal se deja de leer la tabla nueva
                 y no se perdió un solo dato.
  · REINTENTABLE `ignore_conflicts=True` contra la restricción única, así que
                 volver a correrla no duplica nada.
  · REVERSIBLE   `migrate misastreria 0062` borra lo copiado y deja todo como
                 estaba.

A diferencia de la 0048, acá se recorre con `iterator()` y se graba por lotes:
no sabemos cuántas filas hay en producción y una lista entera en memoria es una
apuesta que no hace falta hacer.
"""
from decimal import Decimal

from django.db import migrations

LOTE = 500


def _copiar(origen, destino, campo_fk):
    """Vuelca origen.empleado → destino(campo_fk, empleado, monto). Devuelve cuántas."""
    pendientes, copiadas = [], 0
    for fila in origen.objects.filter(empleado__isnull=False).iterator(chunk_size=LOTE):
        pendientes.append(destino(**{
            campo_fk: fila.id,
            'empleado_id': fila.empleado_id,
            'monto_comision_fijo': fila.monto_comision_fijo or Decimal('0'),
        }))
        if len(pendientes) >= LOTE:
            destino.objects.bulk_create(pendientes, ignore_conflicts=True)
            copiadas += len(pendientes)
            pendientes = []
    if pendientes:
        destino.objects.bulk_create(pendientes, ignore_conflicts=True)
        copiadas += len(pendientes)
    return copiadas


def poblar(apps, schema_editor):
    _copiar(apps.get_model('misastreria', 'VentaItem'),
            apps.get_model('misastreria', 'VentaItemEmpleado'), 'venta_item_id')
    _copiar(apps.get_model('misastreria', 'AlquilerItem'),
            apps.get_model('misastreria', 'AlquilerItemEmpleado'), 'alquiler_item_id')


def revertir(apps, schema_editor):
    # El origen sigue intacto en los items, así que vaciar es seguro: volver a
    # aplicar la migración reconstruye exactamente lo mismo.
    apps.get_model('misastreria', 'VentaItemEmpleado').objects.all().delete()
    apps.get_model('misastreria', 'AlquilerItemEmpleado').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0062_arreglo_multi_empleado'),
    ]

    operations = [
        migrations.RunPython(poblar, revertir),
    ]
