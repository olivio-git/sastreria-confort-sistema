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
        'view_confeccion', 'add_confeccion', 'change_confeccion',
        'view_alquiler', 'add_alquiler', 'change_alquiler',
        'registrar_cobro',
        'view_transaccion', 'add_transaccion',
        'abrir_caja', 'operar_caja',
        'ver_reportes_caja',
        # Sólo lectura de inventario (prendas, cortes, conjuntos).
        'view_prendainventario', 'view_corte', 'view_conjunto',
    },

    'Vendedor': {
        'acceder_sistema',
        'view_cliente', 'add_cliente', 'change_cliente',
        'view_reparacion', 'add_reparacion', 'change_reparacion',
        'view_venta', 'add_venta', 'change_venta',
        'view_confeccion', 'add_confeccion', 'change_confeccion',
        'view_alquiler', 'add_alquiler', 'change_alquiler',
        'registrar_cobro',
        # Sólo lectura de inventario (prendas, cortes, conjuntos).
        'view_prendainventario', 'view_corte', 'view_conjunto',
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


# ──────────────────────────────────────────────────────────────────────────────
# Permisos adicionales por usuario
# ──────────────────────────────────────────────────────────────────────────────
# Encima del rol, un Administrador puede sumarle a UN usuario permisos extra
# (`user.user_permissions`) desde la pantalla de usuarios. Sólo se pueden
# otorgar los que figuran acá — la lista se valida en el servidor, no sólo se
# oculta en la grilla.
#
# Quedan FUERA a propósito:
#   - `gestionar_usuarios`: administra roles, PINs y estos mismos extras; se
#     obtiene únicamente con el rol Administrador.
#   - `supervisar_caja`: ver/anular sesiones ajenas es una función de
#     supervisión, no un permiso suelto.
#   - `acceder_sistema`: lo da cualquier rol. Los extras sólo se otorgan a
#     usuarios con al menos un rol (y nunca a superusuarios), y se limpian al
#     quitarle el último rol; no reemplazan a un rol.
# Aun otorgando `operar_caja`/`abrir_caja`/`registrar_cobro`, el turno de caja
# sigue siendo una regla de propiedad (sólo el dueño de la sesión escribe en
# ella): un extra habilita la pantalla, nunca saltea al dueño del turno.

ACCIONES_GRILLA = ('ver', 'crear', 'editar', 'eliminar')

# (módulo, modelo o None, permisos personalizados [(codename, etiqueta)])
# Un modelo genera view_/add_/change_/delete_<modelo>; `solo_ver` limita a Ver.
PERMISOS_EXTRA_OTORGABLES = [
    ('Clientes', 'cliente', None, []),
    ('Reparaciones', 'reparacion', None, []),
    ('Ventas', 'venta', None, []),
    ('Confecciones', 'confeccion', None, []),
    ('Alquileres', 'alquiler', None, []),
    ('Gastos y transacciones', 'transaccion', None, []),
    ('Conceptos de gasto', 'tipogasto', None, []),
    ('Inventario (prendas)', 'prendainventario', None, []),
    ('Cortes', 'corte', ('ver',), []),
    ('Conjuntos', 'conjunto', None, []),
    ('Insumos', 'insumo', None, []),
    ('Producción', 'ordenproduccion', None, []),
    ('Empleados', 'empleado', None, []),
    ('Caja y cobros', None, None, [
        ('registrar_cobro', 'Registrar cobros'),
        ('abrir_caja', 'Abrir sesión de caja'),
        ('operar_caja', 'Operar su propia sesión de caja'),
        ('ver_reportes_caja', 'Ver reportes de caja'),
    ]),
    ('Taller', None, None, [
        ('cambiar_estado_taller', 'Cambiar estados de taller'),
    ]),
    ('Reportes y analítica', None, None, [
        ('ver_reportes', 'Ver reportes generales'),
        ('ver_analitica', 'Ver analítica'),
    ]),
    ('Etiquetas', None, None, [
        ('imprimir_etiquetas', 'Imprimir etiquetas'),
        ('configurar_etiquetas', 'Configurar etiquetas e impresora'),
    ]),
]

_PREFIJO_ACCION = {'ver': 'view', 'crear': 'add', 'editar': 'change', 'eliminar': 'delete'}


def modulos_otorgables():
    """Módulos de la grilla de permisos adicionales.

    Cada elemento: `{'nombre', 'acciones': {'ver'|'crear'|'editar'|'eliminar':
    codename}, 'otros': [(codename, etiqueta)]}`.
    """
    modulos = []
    for nombre, modelo, acciones_permitidas, otros in PERMISOS_EXTRA_OTORGABLES:
        acciones = {}
        if modelo:
            for accion in (acciones_permitidas or ACCIONES_GRILLA):
                acciones[accion] = f'{_PREFIJO_ACCION[accion]}_{modelo}'
        modulos.append({'nombre': nombre, 'acciones': acciones, 'otros': list(otros)})
    return modulos


def _etiquetas_otorgables():
    etiquetas = {}
    for modulo in modulos_otorgables():
        for accion, codename in modulo['acciones'].items():
            etiquetas[codename] = f"{modulo['nombre']}: {accion}"
        for codename, etiqueta in modulo['otros']:
            etiquetas[codename] = etiqueta
    return etiquetas


# codename -> etiqueta legible ("Insumos: ver", "Registrar cobros", ...)
ETIQUETAS_OTORGABLES = _etiquetas_otorgables()
CODENAMES_OTORGABLES = frozenset(ETIQUETAS_OTORGABLES)


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
