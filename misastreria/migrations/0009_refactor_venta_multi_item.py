from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def borrar_ventas(apps, schema_editor):
    Venta = apps.get_model('misastreria', 'Venta')
    Venta.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0008_remove_alquiler_articulo_remove_alquiler_cantidad_and_more'),
    ]

    operations = [
        migrations.RunPython(borrar_ventas, migrations.RunPython.noop),

        migrations.RemoveField(model_name='venta', name='articulo'),
        migrations.RemoveField(model_name='venta', name='cantidad'),
        migrations.RemoveField(model_name='venta', name='precio_unitario'),
        migrations.RemoveField(model_name='venta', name='precio_total'),

        migrations.AlterField(
            model_name='venta',
            name='codigo',
            field=models.CharField(blank=True, max_length=10, unique=True, verbose_name='Código'),
        ),
        migrations.AlterField(
            model_name='venta',
            name='cliente',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ventas',
                to='misastreria.cliente',
                verbose_name='Cliente',
            ),
        ),

        migrations.AddField(
            model_name='venta',
            name='empleado',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ventas',
                to='misastreria.empleado',
                verbose_name='Empleado',
            ),
        ),
        migrations.AddField(
            model_name='venta',
            name='descuento',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Descuento (%)'),
        ),
        migrations.AddField(
            model_name='venta',
            name='subtotal',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Subtotal'),
        ),
        migrations.AddField(
            model_name='venta',
            name='total',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Total'),
        ),
        migrations.AddField(
            model_name='venta',
            name='notas',
            field=models.TextField(blank=True, verbose_name='Notas'),
        ),

        migrations.CreateModel(
            name='VentaItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cantidad', models.PositiveIntegerField(default=1, verbose_name='Cantidad')),
                ('precio_unitario', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Precio Unitario')),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Subtotal')),
                ('articulo', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='misastreria.prendainventario',
                    verbose_name='Prenda',
                )),
                ('venta', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='misastreria.venta',
                )),
            ],
            options={
                'verbose_name': 'Ítem de Venta',
                'verbose_name_plural': 'Ítems de Venta',
            },
        ),
    ]
