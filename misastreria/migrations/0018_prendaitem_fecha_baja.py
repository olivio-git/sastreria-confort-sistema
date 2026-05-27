from django.db import migrations, models


def backfill_fecha_baja(apps, schema_editor):
    PrendaItem = apps.get_model('misastreria', 'PrendaItem')
    for item in PrendaItem.objects.filter(estado='baja'):
        if item.fecha_baja is None:
            item.fecha_baja = item.actualizado.date()
            item.save(update_fields=['fecha_baja'])


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0017_prendaitem_tipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='prendaitem',
            name='fecha_baja',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha de Baja'),
        ),
        migrations.RunPython(backfill_fecha_baja, migrations.RunPython.noop),
    ]
