from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0005_remove_confeccion_chaleco_altura_botones_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='creado',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='Fecha de Creación',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='confeccion',
            name='creado',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='Fecha de Creación',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='transaccion',
            name='creado',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='Fecha de Creación',
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='cliente',
            options={
                'ordering': ['-creado'],
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
            },
        ),
        migrations.AlterModelOptions(
            name='confeccion',
            options={
                'ordering': ['-creado'],
                'verbose_name': 'Confección',
                'verbose_name_plural': 'Confecciones',
            },
        ),
        migrations.AlterModelOptions(
            name='transaccion',
            options={
                'ordering': ['-creado'],
                'verbose_name': 'Transacción',
                'verbose_name_plural': 'Transacciones',
            },
        ),
    ]
