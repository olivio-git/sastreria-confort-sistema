from django.db import migrations, models


def poblar_desde_kardex(apps, schema_editor):
    """Recupera el momento real de devolución de los alquileres históricos.

    El dato nunca se guardó en Alquiler, pero kardex_events.emit_devolucion()
    viene estampando un KardexEvento tipo='devolucion' con timestamp real desde
    siempre. Ese es el registro de la verdad: lo usamos para reconstruir.
    """
    Alquiler = apps.get_model('misastreria', 'Alquiler')
    KardexEvento = apps.get_model('misastreria', 'KardexEvento')

    # Primer evento de devolución por alquiler = momento en que se cerró.
    primeros = {}
    eventos = (KardexEvento.objects
               .filter(tipo='devolucion', alquiler_id__isnull=False)
               .order_by('alquiler_id', 'timestamp')
               .values_list('alquiler_id', 'timestamp'))
    for alquiler_id, ts in eventos:
        primeros.setdefault(alquiler_id, ts)

    pendientes = Alquiler.objects.filter(
        estado='devuelto', fecha_devolucion_real__isnull=True,
    ).only('id')
    for alquiler in pendientes.iterator():
        ts = primeros.get(alquiler.id)
        if ts:
            Alquiler.objects.filter(pk=alquiler.pk).update(fecha_devolucion_real=ts)


def revertir(apps, schema_editor):
    """El campo se elimina en la marcha atrás; no hay nada que deshacer."""


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0060_remove_plantillaetiqueta_orientacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='alquiler',
            name='fecha_devolucion_real',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='Devuelto el',
                help_text='Momento real en que las prendas volvieron. Lo estampa la pantalla de devolución.',
            ),
        ),
        migrations.RunPython(poblar_desde_kardex, revertir),
    ]
