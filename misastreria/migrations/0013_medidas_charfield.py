from django.db import migrations, models


MEDIDA_FIELDS = [
    'pantalon_largo_total', 'pantalon_contorno_cintura', 'pantalon_contorno_cadera',
    'pantalon_largo_entrepierna', 'pantalon_contorno_pierna', 'pantalon_contorno_rodilla',
    'pantalon_contorno_bota', 'pantalon_tiro_delantero', 'pantalon_tiro_trasero',
    'chaleco_contorno_busto', 'chaleco_contorno_cintura', 'chaleco_contorno_cadera',
    'chaleco_largo_talle', 'chaleco_largo_total', 'chaleco_altura_botones',
    'saco_contorno_busto', 'saco_contorno_cintura', 'saco_contorno_cadera',
    'saco_largo_talle', 'saco_largo_total', 'saco_ancho_hombros',
    'saco_ancho_espalda', 'saco_contorno_brazo', 'saco_largo_manga', 'saco_contorno_puno',
    'saco_mujer_contorno_busto', 'saco_mujer_contorno_cintura', 'saco_mujer_contorno_cadera',
    'saco_mujer_ancho_hombros', 'saco_mujer_ancho_espalda', 'saco_mujer_largo_talle',
    'saco_mujer_largo_total', 'saco_mujer_altura_busto', 'saco_mujer_separacion_busto',
    'saco_mujer_dif_talle',
    'chaleco_mujer_contorno_busto', 'chaleco_mujer_contorno_cintura', 'chaleco_mujer_contorno_cadera',
    'chaleco_mujer_largo_talle', 'chaleco_mujer_largo_total', 'chaleco_mujer_altura_busto',
    'chaleco_mujer_separacion_busto', 'chaleco_mujer_largo_delantero',
]


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0012_tipos_personalizados'),
    ]

    operations = [
        migrations.AlterField(
            model_name='confeccionitem',
            name=field,
            field=models.CharField(blank=True, max_length=20),
        )
        for field in MEDIDA_FIELDS
    ]
