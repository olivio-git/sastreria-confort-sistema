from django.db import migrations


def seed_forward(apps, schema_editor):
    EstadoAlquiler = apps.get_model('misastreria', 'EstadoAlquiler')
    EstadoAlquiler.objects.get_or_create(nombre='reservado', defaults={'color': 'warning'})


def seed_reverse(apps, schema_editor):
    EstadoAlquiler = apps.get_model('misastreria', 'EstadoAlquiler')
    EstadoAlquiler.objects.filter(nombre='reservado').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0033_alquiler_fecha_evento'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_reverse),
    ]
