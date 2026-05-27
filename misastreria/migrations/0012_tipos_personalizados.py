from django.db import migrations, models
import django.db.models.deletion


def seed_tipos(apps, schema_editor):
    TipoContrato = apps.get_model('misastreria', 'TipoContrato')
    UnidadMedida = apps.get_model('misastreria', 'UnidadMedida')
    EstadoAlquiler = apps.get_model('misastreria', 'EstadoAlquiler')
    Empleado = apps.get_model('misastreria', 'Empleado')
    Insumo = apps.get_model('misastreria', 'Insumo')

    # TipoContrato — mapear desde valores anteriores
    contrato_map = {
        'fijo':        TipoContrato.objects.get_or_create(nombre='Fijo')[0],
        'contrato':    TipoContrato.objects.get_or_create(nombre='Contrato')[0],
        'porcentaje':  TipoContrato.objects.get_or_create(nombre='Porcentaje')[0],
    }
    for emp in Empleado.objects.all():
        tc = contrato_map.get(emp.tipo_contrato_old or '')
        if tc:
            emp.tipo_contrato_new = tc
            emp.save()

    # UnidadMedida — mapear desde valores anteriores
    unidad_map = {
        'metro':  UnidadMedida.objects.get_or_create(nombre='Metro')[0],
        'kg':     UnidadMedida.objects.get_or_create(nombre='Kilogramo')[0],
        'unidad': UnidadMedida.objects.get_or_create(nombre='Unidad')[0],
        'rollo':  UnidadMedida.objects.get_or_create(nombre='Rollo')[0],
    }
    # Asegurar que existan aunque no haya insumos
    for _ in unidad_map.values():
        pass
    for ins in Insumo.objects.all():
        um = unidad_map.get(ins.unidad_medida_old or 'metro')
        if not um:
            um = unidad_map['metro']
        ins.unidad_medida_new = um
        ins.save()

    # EstadoAlquiler — seed estados del sistema
    EstadoAlquiler.objects.get_or_create(nombre='alquilado', defaults={'color': 'alquilado'})
    EstadoAlquiler.objects.get_or_create(nombre='devuelto',  defaults={'color': 'devuelto'})


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0011_tipos_dinamicos'),
    ]

    operations = [
        # ── Nuevos modelos ────────────────────────────────────────────────
        migrations.CreateModel(
            name='TipoContrato',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100, unique=True)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Tipo de Contrato', 'verbose_name_plural': 'Tipos de Contrato'},
        ),
        migrations.CreateModel(
            name='UnidadMedida',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=50, unique=True)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Unidad de Medida', 'verbose_name_plural': 'Unidades de Medida'},
        ),
        migrations.CreateModel(
            name='EstadoAlquiler',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=50, unique=True)),
                ('color', models.CharField(
                    choices=[('alquilado', 'Azul (Alquilado)'), ('devuelto', 'Verde (Devuelto)'), ('warning', 'Naranja (Alerta)'), ('danger', 'Rojo (Crítico)')],
                    default='warning', max_length=20,
                )),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Estado de Alquiler', 'verbose_name_plural': 'Estados de Alquiler'},
        ),

        # ── Campos simples nuevos ─────────────────────────────────────────
        migrations.AddField('Alquiler', 'hora_devolucion',
            models.TimeField(blank=True, null=True, verbose_name='Hora de Devolución')),
        migrations.AddField('Confeccion', 'garantia',
            models.TextField(blank=True, verbose_name='Garantía')),
        migrations.AddField('ConfeccionItem', 'talla',
            models.CharField(blank=True, max_length=30, verbose_name='Talla')),

        # ── Cambio estado Alquiler: quitar choices, ampliar max_length ────
        migrations.AlterField('Alquiler', 'estado',
            models.CharField(default='alquilado', max_length=50, verbose_name='Estado')),

        # ── Empleado: agregar campo temporal tipo_contrato_old snapshot ──
        # Renombramos la columna vieja a _old para preservar datos
        migrations.RenameField('Empleado', 'tipo_contrato', 'tipo_contrato_old'),
        migrations.AddField('Empleado', 'tipo_contrato_new',
            models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.tipocontrato',
                verbose_name='Tipo de Contrato',
            )
        ),

        # ── Insumo: mismo patrón para unidad_medida ───────────────────────
        migrations.RenameField('Insumo', 'unidad_medida', 'unidad_medida_old'),
        migrations.AddField('Insumo', 'unidad_medida_new',
            models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.unidadmedida',
                verbose_name='Unidad de Medida',
            )
        ),

        # ── Seed de datos + migración de registros existentes ────────────
        migrations.RunPython(seed_tipos, reverse_seed),

        # ── Eliminar columnas viejas ──────────────────────────────────────
        migrations.RemoveField('Empleado', 'tipo_contrato_old'),
        migrations.RemoveField('Insumo', 'unidad_medida_old'),

        # ── Renombrar nuevas FK al nombre final ───────────────────────────
        migrations.RenameField('Empleado', 'tipo_contrato_new', 'tipo_contrato'),
        migrations.RenameField('Insumo', 'unidad_medida_new', 'unidad_medida'),
    ]
