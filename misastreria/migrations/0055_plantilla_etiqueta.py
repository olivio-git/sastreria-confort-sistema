"""Plantillas de etiqueta editables.

Crea el modelo y carga como plantilla predeterminada el diseño que hasta ahora
estaba clavado en `views._draw_etiqueta()`. La carga es parte de la misma
migración a propósito: sin plantilla predeterminada las etiquetas de inventario,
reparaciones y confecciones no tendrían qué renderizar, así que el modelo vacío
dejaría el sistema a medias entre una migración y la siguiente.
"""

from django.db import migrations, models

from misastreria.etiquetas import (
    ALTO_DEFECTO, ANCHO_DEFECTO, elementos_por_defecto,
)


def cargar_plantilla_de_fabrica(apps, schema_editor):
    PlantillaEtiqueta = apps.get_model('misastreria', 'PlantillaEtiqueta')
    if PlantillaEtiqueta.objects.exists():
        return                       # ya hay plantillas: no pisar nada
    PlantillaEtiqueta.objects.create(
        nombre="Etiqueta Fortium",
        descripcion="Diseño original del sistema. Editable desde el diseñador.",
        ancho_puntos=ANCHO_DEFECTO,
        alto_puntos=ALTO_DEFECTO,
        elementos=elementos_por_defecto(),
        es_predeterminada=True,
    )


def borrar_plantilla_de_fabrica(apps, schema_editor):
    PlantillaEtiqueta = apps.get_model('misastreria', 'PlantillaEtiqueta')
    PlantillaEtiqueta.objects.filter(nombre="Etiqueta Fortium").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0054_reparacion_empleado_monto_fijo'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlantillaEtiqueta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True, verbose_name='Nombre')),
                ('descripcion', models.CharField(blank=True, max_length=200, verbose_name='Descripción')),
                ('ancho_puntos', models.PositiveIntegerField(default=400, verbose_name='Ancho (puntos)')),
                ('alto_puntos', models.PositiveIntegerField(default=240, verbose_name='Alto (puntos)')),
                ('elementos', models.JSONField(blank=True, default=list, verbose_name='Elementos')),
                ('es_predeterminada', models.BooleanField(default=False, help_text='La que usan las etiquetas de inventario, reparaciones y confecciones.', verbose_name='Predeterminada')),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('modificado', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Plantilla de Etiqueta',
                'verbose_name_plural': 'Plantillas de Etiquetas',
                'ordering': ['-es_predeterminada', 'nombre'],
            },
        ),
        migrations.RunPython(cargar_plantilla_de_fabrica, borrar_plantilla_de_fabrica),
    ]
