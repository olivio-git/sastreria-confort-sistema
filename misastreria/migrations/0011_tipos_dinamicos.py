from django.db import migrations, models
import django.db.models.deletion


# ── Datos de siembra ─────────────────────────────────────────────────────────

# (choice_value, nombre_display, plantilla)
TIPOS_PRENDA_SEED = [
    ('camisa',        'Camisa',         ''),
    ('pantalon',      'Pantalón',       'pantalon'),
    ('chaqueta',      'Chaqueta',       ''),
    ('vestido',       'Vestido',        ''),
    ('falda',         'Falda',          ''),
    ('chaleco',       'Chaleco',        'chaleco'),
    ('saco',          'Saco',           'saco'),
    ('saco_mujer',    'Saco – Mujer',   'saco_mujer'),
    ('chaleco_mujer', 'Chaleco – Mujer','chaleco_mujer'),
    ('otro',          'Otro',           ''),
]

TIPOS_REPARACION_SEED = [
    ('costura',           'Costura'),
    ('parche',            'Parche'),
    ('cambio_cremallera', 'Cambio de Cremallera'),
    ('ajuste',            'Ajuste'),
    ('otro',              'Otro'),
]


def seed_and_migrate(apps, schema_editor):
    TipoPrenda     = apps.get_model('misastreria', 'TipoPrenda')
    TipoReparacion = apps.get_model('misastreria', 'TipoReparacion')
    Reparacion     = apps.get_model('misastreria', 'Reparacion')
    ConfeccionItem = apps.get_model('misastreria', 'ConfeccionItem')

    # Crear todos los tipos de prenda y reparación
    prenda_map = {}
    for val, nombre, plantilla in TIPOS_PRENDA_SEED:
        tp = TipoPrenda.objects.create(nombre=nombre, plantilla=plantilla)
        prenda_map[val] = tp

    reparacion_map = {}
    for val, nombre in TIPOS_REPARACION_SEED:
        tr = TipoReparacion.objects.create(nombre=nombre)
        reparacion_map[val] = tr

    otro_prenda     = prenda_map['otro']
    otro_reparacion = reparacion_map['otro']

    # Migrar Reparacion.tipo_prenda_old / tipo_reparacion_old → FK
    for r in Reparacion.objects.all():
        old_prenda = r.tipo_prenda_old or ''
        old_rep    = r.tipo_reparacion_old or ''

        if old_prenda == 'otro' and r.otro_prenda:
            tp, _ = TipoPrenda.objects.get_or_create(
                nombre=r.otro_prenda.strip(), defaults={'plantilla': ''}
            )
        else:
            tp = prenda_map.get(old_prenda, otro_prenda)

        if old_rep == 'otro' and r.otro_reparacion:
            tr, _ = TipoReparacion.objects.get_or_create(nombre=r.otro_reparacion.strip())
        else:
            tr = reparacion_map.get(old_rep, otro_reparacion)

        r.tipo_prenda_new     = tp
        r.tipo_reparacion_new = tr
        r.save()

    # Migrar ConfeccionItem.tipo_prenda_old → FK
    confeccion_prenda_vals = {'pantalon', 'chaleco', 'saco', 'saco_mujer', 'chaleco_mujer'}
    for item in ConfeccionItem.objects.all():
        old = item.tipo_prenda_old or ''
        item.tipo_prenda_new = prenda_map.get(old) if old in confeccion_prenda_vals else otro_prenda
        item.save()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0010_ordenproduccion_insumocortado'),
    ]

    operations = [
        # 1. Crear modelos TipoPrenda y TipoReparacion
        migrations.CreateModel(
            name='TipoPrenda',
            fields=[
                ('id',        models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nombre',    models.CharField(max_length=100)),
                ('plantilla', models.CharField(
                    blank=True, default='',
                    choices=[
                        ('', 'Sin medidas'), ('pantalon', 'Pantalón'), ('chaleco', 'Chaleco'),
                        ('saco', 'Saco'), ('saco_mujer', 'Saco Mujer'), ('chaleco_mujer', 'Chaleco Mujer'),
                    ],
                    max_length=20,
                )),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Tipo de Prenda', 'verbose_name_plural': 'Tipos de Prenda'},
        ),
        migrations.CreateModel(
            name='TipoReparacion',
            fields=[
                ('id',     models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=100)),
            ],
            options={'ordering': ['nombre'], 'verbose_name': 'Tipo de Reparación', 'verbose_name_plural': 'Tipos de Reparación'},
        ),

        # 2. Añadir campos FK temporales (nullable) junto a los viejos CharField
        migrations.AddField(
            model_name='reparacion',
            name='tipo_prenda_new',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.tipoprenda',
                verbose_name='Tipo de Prenda',
            ),
        ),
        migrations.AddField(
            model_name='reparacion',
            name='tipo_reparacion_new',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.tiporeparacion',
                verbose_name='Tipo de Reparación',
            ),
        ),
        migrations.AddField(
            model_name='confeccionitem',
            name='tipo_prenda_new',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='misastreria.tipoprenda',
                verbose_name='Tipo de Prenda',
            ),
        ),

        # 3. Renombrar viejos CharField para que convivan durante RunPython
        migrations.RenameField('reparacion',     'tipo_prenda',     'tipo_prenda_old'),
        migrations.RenameField('reparacion',     'tipo_reparacion', 'tipo_reparacion_old'),
        migrations.RenameField('confeccionitem', 'tipo_prenda',     'tipo_prenda_old'),

        # 4. Sembrar datos y migrar registros existentes
        migrations.RunPython(seed_and_migrate, noop),

        # 5. Eliminar viejos CharField y campos auxiliares
        migrations.RemoveField('reparacion', 'tipo_prenda_old'),
        migrations.RemoveField('reparacion', 'tipo_reparacion_old'),
        migrations.RemoveField('reparacion', 'otro_prenda'),
        migrations.RemoveField('reparacion', 'otro_reparacion'),
        migrations.RemoveField('confeccionitem', 'tipo_prenda_old'),

        # 6. Renombrar _new → nombre final
        migrations.RenameField('reparacion',     'tipo_prenda_new',     'tipo_prenda'),
        migrations.RenameField('reparacion',     'tipo_reparacion_new', 'tipo_reparacion'),
        migrations.RenameField('confeccionitem', 'tipo_prenda_new',     'tipo_prenda'),

        # 7. Hacer FK de Reparacion NOT NULL
        migrations.AlterField(
            model_name='reparacion',
            name='tipo_prenda',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.tipoprenda',
                verbose_name='Tipo de Prenda',
            ),
        ),
        migrations.AlterField(
            model_name='reparacion',
            name='tipo_reparacion',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='misastreria.tiporeparacion',
                verbose_name='Tipo de Reparación',
            ),
        ),
        # ConfeccionItem.tipo_prenda queda nullable (el form lo permite vacío)
    ]
