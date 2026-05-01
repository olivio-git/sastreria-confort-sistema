from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0003_cliente_ci_empleado_ci_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='empleado',
            name='codigo',
            field=models.CharField(blank=True, max_length=10, unique=True, verbose_name='Código'),
        ),
    ]
