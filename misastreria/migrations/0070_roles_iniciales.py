from django.db import migrations


def crear_roles_y_promover_superusuarios(apps, schema_editor):
    """Corrida única: crea los 4 grupos y mete a los superusuarios existentes
    en Administrador. NUNCA se vuelve a correr (a diferencia de `post_migrate`,
    que reaplica `roles.py` en cada `migrate`), para no pisar membresías que
    el admin haya tocado a mano después de este deploy.
    """
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('auth', 'User')

    for nombre in ('Administrador', 'Cajero', 'Vendedor', 'Taller'):
        Group.objects.get_or_create(name=nombre)

    administrador = Group.objects.get(name='Administrador')
    for user in User.objects.filter(is_superuser=True):
        user.groups.add(administrador)


def eliminar_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(
        name__in=('Administrador', 'Cajero', 'Vendedor', 'Taller')
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0069_perfilusuario_empleado_user'),
    ]

    operations = [
        migrations.RunPython(crear_roles_y_promover_superusuarios, eliminar_roles),
    ]
