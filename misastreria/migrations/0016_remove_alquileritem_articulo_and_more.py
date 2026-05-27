# Rewritten manually to implement 6-phase atomic migration for prendas-serializadas
# See design: sdd/prendas-serializadas/design (topic_key in engram)

import django.db.models.deletion
from django.db import migrations, models


def crear_items_desde_inventario(apps, schema_editor):
    """Por cada PrendaInventario.cantidad=N, crear N PrendaItem."""
    PrendaInventario = apps.get_model('misastreria', 'PrendaInventario')
    PrendaItem = apps.get_model('misastreria', 'PrendaItem')
    for prenda in PrendaInventario.objects.all():
        cant = prenda.cantidad or 0
        for n in range(1, cant + 1):
            codigo = f"{prenda.codigo}-ITM-{n:02d}"
            PrendaItem.objects.create(
                prenda=prenda,
                codigo_item=codigo,
                condicion=prenda.condicion or 'nueva',
                estado='disponible',
                veces_alquilado=0,
            )


def asignar_items_a_alquiler_y_venta(apps, schema_editor):
    """
    Para cada AlquilerItem/VentaItem existente, asignar el primer PrendaItem
    disponible del mismo SKU. Si cantidad>1, expandir a N filas.

    NOTA: En este punto de la migración, articulo y cantidad TODAVÍA existen
    en la DB (se eliminan en Fase F). Al crear nuevos registros extra, debemos
    proporcionar articulo y cantidad (campos históricos) para satisfacer la
    restricción NOT NULL de SQLite.
    """
    AlquilerItem = apps.get_model('misastreria', 'AlquilerItem')
    VentaItem = apps.get_model('misastreria', 'VentaItem')
    PrendaItem = apps.get_model('misastreria', 'PrendaItem')

    # Alquiler
    for ai in list(AlquilerItem.objects.all()):
        cantidad = ai.cantidad or 1
        articulo = ai.articulo  # referencia al PrendaInventario (aún existe)
        items_libres = list(
            PrendaItem.objects.filter(prenda=articulo, estado='disponible')[:cantidad]
        )
        if not items_libres:
            ai.delete()
            continue
        ai.prenda_item = items_libres[0]
        ai.save()
        items_libres[0].estado = 'alquilado'
        items_libres[0].save()
        for it in items_libres[1:]:
            # artículo y cantidad requeridos por restricción NOT NULL histórica
            AlquilerItem.objects.create(
                alquiler=ai.alquiler,
                articulo=articulo,
                cantidad=1,
                prenda_item=it,
                precio_unitario=ai.precio_unitario,
                subtotal=ai.precio_unitario,
            )
            it.estado = 'alquilado'
            it.save()

    # Venta
    for vi in list(VentaItem.objects.all()):
        cantidad = vi.cantidad or 1
        articulo = vi.articulo
        items_libres = list(
            PrendaItem.objects.filter(prenda=articulo, estado='disponible')[:cantidad]
        )
        if not items_libres:
            vi.delete()
            continue
        vi.prenda_item = items_libres[0]
        vi.save()
        items_libres[0].estado = 'baja'
        items_libres[0].save()
        for it in items_libres[1:]:
            VentaItem.objects.create(
                venta=vi.venta,
                articulo=articulo,
                cantidad=1,
                prenda_item=it,
                precio_unitario=vi.precio_unitario,
                subtotal=vi.precio_unitario,
            )
            it.estado = 'baja'
            it.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0015_tipo_material_fk'),
    ]

    operations = [
        # === FASE A: Crear modelo PrendaItem ===
        migrations.CreateModel(
            name='PrendaItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo_item', models.CharField(
                    blank=True,
                    help_text='Auto-generado: <codigo SKU>-ITM-<NN>',
                    max_length=30,
                    unique=True,
                    verbose_name='Código de Item',
                )),
                ('ubicacion', models.CharField(
                    blank=True,
                    help_text='Estante, perchero, etc. Opcional.',
                    max_length=80,
                    verbose_name='Ubicación física',
                )),
                ('condicion', models.CharField(
                    choices=[('nueva', 'Nueva'), ('usada', 'Usada'), ('remate', 'Remate')],
                    default='nueva',
                    max_length=10,
                    verbose_name='Condición',
                )),
                ('estado', models.CharField(
                    choices=[('disponible', 'Disponible'), ('alquilado', 'Alquilado'), ('baja', 'Baja')],
                    default='disponible',
                    max_length=12,
                    verbose_name='Estado',
                )),
                ('veces_alquilado', models.PositiveIntegerField(default=0, verbose_name='Veces alquilado')),
                ('notas', models.TextField(blank=True, verbose_name='Notas')),
                ('creado', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de alta')),
                ('actualizado', models.DateTimeField(auto_now=True)),
                ('prenda', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='misastreria.prendainventario',
                    verbose_name='Prenda (SKU)',
                )),
            ],
            options={
                'verbose_name': 'Item de Prenda',
                'verbose_name_plural': 'Items de Prenda',
                'ordering': ['prenda__codigo', 'codigo_item'],
            },
        ),
        migrations.AddIndex(
            model_name='prendaitem',
            index=models.Index(fields=['prenda', 'estado'], name='misastreria_prenda__6ba315_idx'),
        ),

        # === FASE B: Poblar PrendaItem desde PrendaInventario.cantidad ===
        # Accede a prenda.cantidad y prenda.condicion (aún existen en DB en este punto)
        migrations.RunPython(crear_items_desde_inventario, noop),

        # === FASE C: Agregar FK nullable en AlquilerItem y VentaItem ===
        migrations.AddField(
            model_name='alquileritem',
            name='prenda_item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='alquiler_items',
                to='misastreria.prendaitem',
                verbose_name='Item de Prenda',
            ),
        ),
        migrations.AddField(
            model_name='ventaitem',
            name='prenda_item',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='venta_items',
                to='misastreria.prendaitem',
                verbose_name='Item de Prenda',
            ),
        ),

        # === FASE D: Asignar items a registros existentes ===
        # Accede a ai.articulo y ai.cantidad (aún existen en DB en este punto)
        migrations.RunPython(asignar_items_a_alquiler_y_venta, noop),

        # === FASE E: Hacer FK NOT NULL ===
        migrations.AlterField(
            model_name='alquileritem',
            name='prenda_item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='alquiler_items',
                to='misastreria.prendaitem',
                verbose_name='Item de Prenda',
            ),
        ),
        migrations.AlterField(
            model_name='ventaitem',
            name='prenda_item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='venta_items',
                to='misastreria.prendaitem',
                verbose_name='Item de Prenda',
            ),
        ),

        # === FASE F: Eliminar campos viejos ===
        migrations.RemoveField(model_name='alquileritem', name='articulo'),
        migrations.RemoveField(model_name='alquileritem', name='cantidad'),
        migrations.RemoveField(model_name='ventaitem', name='articulo'),
        migrations.RemoveField(model_name='ventaitem', name='cantidad'),
        migrations.RemoveField(model_name='prendainventario', name='cantidad'),
        migrations.RemoveField(model_name='prendainventario', name='condicion'),
        migrations.RemoveField(model_name='prendainventario', name='veces_alquilado'),
    ]
