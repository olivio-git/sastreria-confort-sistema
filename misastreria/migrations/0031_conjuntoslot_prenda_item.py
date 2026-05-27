import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0030_confeccion_pago_concepto'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='conjuntoslot',
            name='prenda_inventario',
        ),
        migrations.AddField(
            model_name='conjuntoslot',
            name='prenda_item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conjunto_slots',
                to='misastreria.prendaitem',
                verbose_name='Item de prenda',
            ),
        ),
    ]
