from django.db import migrations, models
import django.db.models.deletion


def migrar_tipo_material(apps, schema_editor):
    TipoMaterial = apps.get_model('misastreria', 'TipoMaterial')
    Insumo = apps.get_model('misastreria', 'Insumo')

    mapeo = {
        'tela': 'Tela',
        'hilo': 'Hilo',
        'accesorio': 'Accesorio',
        'entretela': 'Entretela',
        'otro': 'Otro',
    }

    tipos = {}
    for clave, nombre in mapeo.items():
        obj, _ = TipoMaterial.objects.get_or_create(nombre=nombre)
        tipos[clave] = obj

    for insumo in Insumo.objects.order_by('id'):
        valor = insumo.tipo_material_char or ''
        tipo = tipos.get(valor)
        if tipo:
            insumo.tipo_material_fk = tipo
            insumo.save(update_fields=['tipo_material_fk'])


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0014_garantia_confeccion'),
    ]

    operations = [
        # 1. Crear el modelo TipoMaterial
        migrations.CreateModel(
            name='TipoMaterial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
            ],
            options={
                'verbose_name': 'Tipo de Material',
                'verbose_name_plural': 'Tipos de Material',
                'ordering': ['nombre'],
            },
        ),
        # 2. Renombrar campo viejo y actualizar ordering
        migrations.RenameField(
            model_name='insumo',
            old_name='tipo_material',
            new_name='tipo_material_char',
        ),
        migrations.AlterModelOptions(
            name='insumo',
            options={'ordering': ['tipo_material_char', 'articulo'], 'verbose_name': 'Insumo', 'verbose_name_plural': 'Insumos'},
        ),
        # 3. Agregar campo FK temporal
        migrations.AddField(
            model_name='insumo',
            name='tipo_material_fk',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.tipomaterial',
                verbose_name='Tipo de Material',
            ),
        ),
        # 4. Migrar datos
        migrations.RunPython(migrar_tipo_material, migrations.RunPython.noop),
        # 5. Eliminar campo viejo
        migrations.RemoveField(model_name='insumo', name='tipo_material_char'),
        # 6. Renombrar FK al nombre final y restaurar ordering correcto
        migrations.RenameField(
            model_name='insumo',
            old_name='tipo_material_fk',
            new_name='tipo_material',
        ),
        migrations.AlterModelOptions(
            name='insumo',
            options={'ordering': ['tipo_material__nombre', 'articulo'], 'verbose_name': 'Insumo', 'verbose_name_plural': 'Insumos'},
        ),
    ]
