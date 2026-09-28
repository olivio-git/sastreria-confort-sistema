"""
Fuente única de verdad del mapeo rol -> permiso.

Este módulo NO importa nada de `models.py` a nivel de módulo (evita import
circular, ya que `PerfilUsuario.Meta.permissions` usa `CUSTOM_PERMISSIONS`).

Para cambiar qué puede hacer un rol: editar `ROLES` acá y correr
`python3 manage.py sync_roles` (o simplemente hacer `migrate`, que dispara
`aplicar_roles()` vía `post_migrate`). No hace falta tocar ninguna vista.
"""

# Permisos personalizados (no derivados de add_/change_/delete_/view_ de un
# modelo). Se registran en `PerfilUsuario.Meta.permissions`.
CUSTOM_PERMISSIONS = [
    ('acceder_sistema', 'Puede acceder al sistema'),
    ('registrar_cobro', 'Puede registrar cobros'),
    ('cambiar_estado_taller', 'Puede cambiar estados de taller (en proceso/entregado)'),
    ('abrir_caja', 'Puede abrir una sesión de caja'),
    ('operar_caja', 'Puede operar su propia sesión de caja'),
    ('supervisar_caja', 'Puede supervisar todas las sesiones de caja'),
    ('ver_reportes_caja', 'Puede ver reportes de caja'),
    ('ver_reportes', 'Puede ver reportes generales'),
    ('ver_analitica', 'Puede ver analítica'),
    ('imprimir_etiquetas', 'Puede imprimir etiquetas'),
    ('configurar_etiquetas', 'Puede configurar diseño/calibración de impresora de etiquetas'),
    ('gestionar_usuarios', 'Puede gestionar usuarios del sistema'),
]

# Sentinel: Administrador recibe TODOS los permisos de la app, sin listar
# cada uno (así nunca queda desactualizado si se agrega un modelo nuevo).
ALL = '__all__'

ROLES = {
    'Administrador': ALL,

    'Cajero': {
        'acceder_sistema',
        'view_cliente', 'add_cliente', 'change_cliente',
        'view_reparacion', 'add_reparacion', 'change_reparacion',
        'view_venta', 'add_venta', 'change_venta',
        'view_confeccion',
        'view_alquiler', 'add_alquiler', 'change_alquiler',
        'registrar_cobro',
        'view_transaccion', 'add_transaccion',
        'abrir_caja', 'operar_caja',
        'ver_reportes_caja',
    },

    'Vendedor': {
        'acceder_sistema',
        'view_cliente', 'add_cliente', 'change_cliente',
        'view_reparacion', 'add_reparacion', 'change_reparacion',
        'view_venta', 'add_venta', 'change_venta',
        'view_confeccion', 'add_confeccion', 'change_confeccion',
        'view_alquiler', 'add_alquiler', 'change_alquiler',
        'registrar_cobro',
    },

    'Taller': {
        'acceder_sistema',
        'cambiar_estado_taller',
        'view_reparacion', 'view_confeccion',
        'add_prendainventario', 'change_prendainventario', 'delete_prendainventario', 'view_prendainventario',
        'add_corte', 'change_corte', 'view_corte',
        'imprimir_etiquetas',
        'add_insumo', 'change_insumo', 'delete_insumo', 'view_insumo',
        'add_ordenproduccion', 'change_ordenproduccion', 'delete_ordenproduccion', 'view_ordenproduccion',
    },
}


def aplicar_roles(roles=None):
    """Crea/actualiza los 4 grupos y su set exacto de permisos.

    Idempotente: se puede llamar tantas veces como se quiera (cada `migrate`
    la vuelve a correr vía `post_migrate`). `group.permissions.set(...)`
    deja `roles.py` como única fuente de verdad — si se quita un permiso acá,
    se lo quita del grupo en el próximo `migrate`/`sync_roles`.
    """
    from django.contrib.auth.models import Group, Permission
    from django.core.exceptions import ImproperlyConfigured

    roles = ROLES if roles is None else roles

    todos_los_permisos = Permission.objects.filter(content_type__app_label='misastreria')
    codenames_existentes = set(todos_los_permisos.values_list('codename', flat=True))

    for nombre, codenames in roles.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        if codenames == ALL:
            grupo.permissions.set(todos_los_permisos)
            continue
        faltantes = codenames - codenames_existentes
        if faltantes:
            raise ImproperlyConfigured(
                f"roles.py: el rol '{nombre}' referencia permisos inexistentes "
                f"en la app misastreria: {sorted(faltantes)}"
            )
        permisos = Permission.objects.filter(
            content_type__app_label='misastreria', codename__in=codenames
        )
        grupo.permissions.set(permisos)
