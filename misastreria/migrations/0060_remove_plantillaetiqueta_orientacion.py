from django.db import migrations


class Migration(migrations.Migration):
    """Elimina la columna que quedó huérfana tras abandonar el giro de plantilla.

    La 0059 agregó `orientacion` el 25/08/2026. El concepto se descartó después:
    el lienzo ES el papel, así que un diseño vertical produce un rollo vertical
    y no hace falta ninguna bandera de giro (ver LienzoEsPapelTests). El campo se
    sacó de models.py, pero nadie escribió esta migración — la columna siguió en
    la base, NOT NULL y sin DEFAULT, invisible para Django. En MariaDB estricto
    eso rompe todo INSERT de plantilla nueva.
    """

    dependencies = [
        ('misastreria', '0059_plantillaetiqueta_orientacion'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plantillaetiqueta',
            name='orientacion',
        ),
    ]
