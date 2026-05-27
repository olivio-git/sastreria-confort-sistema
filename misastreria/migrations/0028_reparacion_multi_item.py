import django.db.models.deletion
from django.db import migrations, models


def migrar_items(apps, schema_editor):
    Reparacion = apps.get_model('misastreria', 'Reparacion')
    ReparacionItem = apps.get_model('misastreria', 'ReparacionItem')
    for rep in Reparacion.objects.all():
        tipo_prenda = rep.tipo_prenda
        tipo_reparacion = rep.tipo_reparacion
        costo = rep.costo
        detalles = rep.detalles or ''
        if tipo_prenda and tipo_reparacion:
            ReparacionItem.objects.create(
                reparacion=rep,
                tipo_prenda=tipo_prenda,
                tipo_reparacion=tipo_reparacion,
                costo=costo,
                detalles=detalles,
            )
        if costo:
            rep.total = costo
            rep.save(update_fields=['total'])


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0027_alter_empleado_apellido_materno_and_more'),
    ]

    operations = [
        # 1. Añadir total a Reparacion
        migrations.AddField(
            model_name='reparacion',
            name='total',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Total'),
        ),
        # 2. Crear tabla ReparacionItem (con los campos viejos aún en Reparacion)
        migrations.CreateModel(
            name='ReparacionItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('costo', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Costo')),
                ('detalles', models.TextField(blank=True, verbose_name='Detalles')),
                ('reparacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='misastreria.reparacion')),
                ('tipo_prenda', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='misastreria.tipoprenda', verbose_name='Tipo de Prenda')),
                ('tipo_reparacion', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='misastreria.tiporeparacion', verbose_name='Tipo de Reparación')),
            ],
            options={
                'verbose_name': 'Item de Reparación',
                'verbose_name_plural': 'Items de Reparación',
            },
        ),
        # 3. Migrar datos existentes a ReparacionItem
        migrations.RunPython(migrar_items, migrations.RunPython.noop),
        # 4. Eliminar campos viejos de Reparacion
        migrations.RemoveField(model_name='reparacion', name='costo'),
        migrations.RemoveField(model_name='reparacion', name='detalles'),
        migrations.RemoveField(model_name='reparacion', name='tipo_prenda'),
        migrations.RemoveField(model_name='reparacion', name='tipo_reparacion'),
    ]
