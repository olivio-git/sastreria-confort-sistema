from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0009_refactor_venta_multi_item'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrdenProduccion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(blank=True, max_length=20, unique=True, verbose_name='Código')),
                ('descripcion', models.TextField(verbose_name='Descripción')),
                ('estado', models.CharField(
                    choices=[('corte', 'En Corte'), ('costura', 'En Costura'), ('terminado', 'Terminado')],
                    default='corte', max_length=20, verbose_name='Estado',
                )),
                ('fecha_inicio', models.DateField(default=django.utils.timezone.now, verbose_name='Fecha de Inicio')),
                ('fecha_estimada', models.DateField(blank=True, null=True, verbose_name='Fecha Estimada')),
                ('notas', models.TextField(blank=True, verbose_name='Notas')),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('confeccion', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ordenes_produccion',
                    to='misastreria.confeccion',
                    verbose_name='Confección asociada',
                )),
                ('empleado', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ordenes_produccion',
                    to='misastreria.empleado',
                    verbose_name='Responsable',
                )),
            ],
            options={
                'verbose_name': 'Orden de Producción',
                'verbose_name_plural': 'Órdenes de Producción',
                'ordering': ['-creado'],
            },
        ),
        migrations.CreateModel(
            name='InsumoCortado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cantidad', models.DecimalField(decimal_places=3, max_digits=10, verbose_name='Cantidad usada')),
                ('insumo', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='misastreria.insumo',
                    verbose_name='Insumo',
                )),
                ('orden', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='insumos',
                    to='misastreria.ordenproduccion',
                )),
            ],
            options={
                'verbose_name': 'Insumo Utilizado',
                'verbose_name_plural': 'Insumos Utilizados',
            },
        ),
    ]
