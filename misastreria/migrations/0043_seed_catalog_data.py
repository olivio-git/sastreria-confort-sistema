from django.db import migrations


def seed_one(model, nombre, extra=None):
    if not model.objects.filter(nombre=nombre).exists():
        kwargs = {'nombre': nombre}
        if extra:
            kwargs.update(extra)
        model.objects.create(**kwargs)


def seed_forward(apps, schema_editor):
    EstadoAlquiler = apps.get_model('misastreria', 'EstadoAlquiler')
    TipoPrenda     = apps.get_model('misastreria', 'TipoPrenda')
    TipoReparacion = apps.get_model('misastreria', 'TipoReparacion')
    TipoMaterial   = apps.get_model('misastreria', 'TipoMaterial')
    UnidadMedida   = apps.get_model('misastreria', 'UnidadMedida')
    TipoGasto      = apps.get_model('misastreria', 'TipoGasto')

    for nombre, color in [
        ('alquilado',  'alquilado'),
        ('devuelto',   'devuelto'),
        ('reservado',  'warning'),
        ('retenido',   'warning'),
        ('dañado',     'danger'),
        ('extraviado', 'danger'),
    ]:
        seed_one(EstadoAlquiler, nombre, {'color': color})

    for nombre in [
        'Buso', 'Camisa', 'Chaleco', 'Chaleco – Mujer', 'Chaqueta',
        'Corbata', 'Faja', 'Falda', 'Otro', 'Pantalón',
        'Ropa Deportiva', 'Ropita', 'Saco', 'Saco – Mujer', 'Vestido',
    ]:
        seed_one(TipoPrenda, nombre)

    for nombre in [
        'Ajuste', 'Bordado', 'Cambio de Cremallera', 'Cortesito',
        'Costura', 'Otro', 'Parche', 'Planchado',
    ]:
        seed_one(TipoReparacion, nombre)

    for nombre in [
        'Accesorio', 'Entretela', 'Hilo', 'Lana', 'Lino', 'Otro', 'Tela',
    ]:
        seed_one(TipoMaterial, nombre)

    for nombre in [
        'Caja', 'Caja grande', 'Kilogramo', 'Metro', 'Rollo', 'Unidad',
    ]:
        seed_one(UnidadMedida, nombre)

    for nombre in [
        'Alquiler Local', 'Gastos de oficina', 'Mantenimiento',
        'Materiales', 'Otros', 'Servicios Básicos', 'Sueldos',
    ]:
        seed_one(TipoGasto, nombre)


def seed_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0042_add_ajuste_conceptos'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_reverse),
    ]
