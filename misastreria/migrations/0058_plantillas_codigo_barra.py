"""Las plantillas guardadas apuntan sus barcodes al payload comprimido.

Los diseños viven como JSON en `PlantillaEtiqueta.elementos`, así que el cambio
de `{codigo}` a `{codigo_barra}` en las plantillas por defecto del código no
alcanza: la plantilla que el taller usa todos los días está en la base y se
quedaría imprimiendo el código largo, sin el ahorro de ancho ni la inmunidad al
layout de teclado.

Sólo se tocan los elementos de tipo `barcode`. Los textos siguen diciendo
`{codigo}` a propósito: ahí es donde la persona lee `PRN-015-ITM-01`.
"""

from django.db import migrations

VIEJO = '{codigo}'
NUEVO = '{codigo_barra}'


def _cambiar(apps, de, a):
    Plantilla = apps.get_model('misastreria', 'PlantillaEtiqueta')
    for plantilla in Plantilla.objects.all():
        elementos = plantilla.elementos
        if not isinstance(elementos, list):
            continue
        tocada = False
        for el in elementos:
            if not isinstance(el, dict) or el.get('tipo') != 'barcode':
                continue
            if el.get('texto') == de:
                el['texto'] = a
                tocada = True
        if tocada:
            plantilla.elementos = elementos
            plantilla.save(update_fields=['elementos'])


def adelante(apps, schema_editor):
    _cambiar(apps, VIEJO, NUEVO)


def atras(apps, schema_editor):
    _cambiar(apps, NUEVO, VIEJO)


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0057_configuracionimpresora_desplazamiento_x_and_more'),
    ]

    operations = [
        migrations.RunPython(adelante, atras),
    ]
