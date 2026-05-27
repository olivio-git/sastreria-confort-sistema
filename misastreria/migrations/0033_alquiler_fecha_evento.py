from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0032_conjunto_tipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='alquiler',
            name='fecha_evento',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha del evento'),
        ),
    ]
