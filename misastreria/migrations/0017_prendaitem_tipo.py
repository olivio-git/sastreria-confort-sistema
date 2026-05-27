from django.db import migrations, models


def copiar_tipo_a_items(apps, schema_editor):
    PrendaItem = apps.get_model('misastreria', 'PrendaItem')
    for item in PrendaItem.objects.select_related('prenda').all():
        item.tipo = item.prenda.tipo
        item.save(update_fields=['tipo'])


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0016_remove_alquileritem_articulo_and_more'),
    ]

    operations = [
        # 1. Agregar tipo a PrendaItem con default temporal para filas existentes
        migrations.AddField(
            model_name='prendaitem',
            name='tipo',
            field=models.CharField(
                choices=[('alquiler', 'Para Alquiler'), ('venta', 'Para Venta')],
                default='alquiler',
                max_length=10,
                verbose_name='Tipo',
            ),
        ),
        # 2. Copiar prenda.tipo → cada item
        migrations.RunPython(copiar_tipo_a_items, migrations.RunPython.noop),
        # 3. Quitar tipo de PrendaInventario
        migrations.RemoveField(
            model_name='prendainventario',
            name='tipo',
        ),
    ]
