from decimal import Decimal

from django.db import migrations


def poblar_asignaciones(apps, schema_editor):
    """Copia el empleado + porcentaje_comision existente de cada Reparacion/Confeccion
    a una fila en la tabla intermedia de asignaciones (el lead)."""
    Reparacion = apps.get_model('misastreria', 'Reparacion')
    Confeccion = apps.get_model('misastreria', 'Confeccion')
    ReparacionEmpleado = apps.get_model('misastreria', 'ReparacionEmpleado')
    ConfeccionEmpleado = apps.get_model('misastreria', 'ConfeccionEmpleado')

    rep_rows = []
    for r in Reparacion.objects.filter(empleado__isnull=False).exclude(porcentaje_comision__isnull=True):
        rep_rows.append(ReparacionEmpleado(
            reparacion_id=r.id,
            empleado_id=r.empleado_id,
            porcentaje_comision=r.porcentaje_comision or Decimal('0'),
        ))
    ReparacionEmpleado.objects.bulk_create(rep_rows, ignore_conflicts=True)

    conf_rows = []
    for c in Confeccion.objects.filter(empleado__isnull=False).exclude(porcentaje_comision__isnull=True):
        conf_rows.append(ConfeccionEmpleado(
            confeccion_id=c.id,
            empleado_id=c.empleado_id,
            porcentaje_comision=c.porcentaje_comision or Decimal('0'),
        ))
    ConfeccionEmpleado.objects.bulk_create(conf_rows, ignore_conflicts=True)


def revertir(apps, schema_editor):
    ReparacionEmpleado = apps.get_model('misastreria', 'ReparacionEmpleado')
    ConfeccionEmpleado = apps.get_model('misastreria', 'ConfeccionEmpleado')
    ReparacionEmpleado.objects.all().delete()
    ConfeccionEmpleado.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0047_confeccionempleado_reparacionempleado'),
    ]

    operations = [
        migrations.RunPython(poblar_asignaciones, revertir),
    ]
