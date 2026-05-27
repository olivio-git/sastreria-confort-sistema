from django.db import migrations, models
import django.db.models.deletion


def migrate_ubicacion_data(apps, schema_editor):
    UbicacionItem = apps.get_model('misastreria', 'UbicacionItem')
    PrendaItem = apps.get_model('misastreria', 'PrendaItem')
    seen = {}
    for item in PrendaItem.objects.exclude(ubicacion_char=''):
        nombre = item.ubicacion_char.strip()
        if not nombre:
            continue
        if nombre not in seen:
            ub, _ = UbicacionItem.objects.get_or_create(nombre=nombre)
            seen[nombre] = ub
        item.ubicacion = seen[nombre]
        item.save(update_fields=['ubicacion'])


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0034_seed_estadoalquiler_reservado'),
    ]

    operations = [
        migrations.CreateModel(
            name='UbicacionItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=80, unique=True, verbose_name='Nombre')),
            ],
            options={
                'verbose_name': 'Ubicación',
                'verbose_name_plural': 'Ubicaciones',
                'ordering': ['nombre'],
            },
        ),
        migrations.RenameField(
            model_name='prendaitem',
            old_name='ubicacion',
            new_name='ubicacion_char',
        ),
        migrations.AddField(
            model_name='prendaitem',
            name='ubicacion',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='misastreria.ubicacionitem',
                verbose_name='Ubicación física',
            ),
        ),
        migrations.RunPython(migrate_ubicacion_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='prendaitem',
            name='ubicacion_char',
        ),
    ]
