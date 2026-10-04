"""
factories.py — helpers compartidos para crear objetos de test mínimos.
No es un test en sí; es importado por los demás módulos.
"""
import time
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, User

from misastreria.models import (
    Cliente, Empleado, PerfilUsuario, TipoContrato,
    Reparacion, ReparacionItem, TipoPrenda, TipoReparacion,
    Venta, VentaItem,
    Confeccion,
    Alquiler, AlquilerItem,
    PrendaInventario, PrendaItem, Corte,
    Insumo,
    CajaSesion, CajaMovimiento, TipoGasto,
    Transaccion,
    OrdenProduccion, OrdenProduccionEmpleado,
    EstadoAlquiler,
    UbicacionItem,
    Conjunto,
)


# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────

def make_user(username='testuser', password='testpass123', role='Administrador', pin=None):
    """Usuario de test. Por defecto Administrador (todos los permisos) para
    que los tests que sólo necesitan "un usuario logueado cualquiera" (no
    relacionados a la matriz de roles) sigan pasando sin tocarlos uno por
    uno. Los tests que sí ejercitan la matriz de permisos deben pasar
    `role='Cajero'/'Vendedor'/'Taller'` explícitamente (o usar
    `make_cajero`/`make_vendedor`/`make_taller` más abajo).

    `role=None` crea un usuario sin ningún grupo (útil para probar el caso
    "sin permisos" / 403).
    """
    user = User.objects.create_user(username=username, password=password)
    if role:
        grupo, _ = Group.objects.get_or_create(name=role)
        user.groups.add(grupo)
    if pin is not None:
        perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
        perfil.pin_hash = make_password(str(pin))
        perfil.save(update_fields=['pin_hash'])
    return user


def make_administrador(username='admin', **kwargs):
    return make_user(username=username, role='Administrador', **kwargs)


def make_cajero(username='cajero', **kwargs):
    return make_user(username=username, role='Cajero', **kwargs)


def make_vendedor(username='vendedor', **kwargs):
    return make_user(username=username, role='Vendedor', **kwargs)


def make_taller(username='taller', **kwargs):
    return make_user(username=username, role='Taller', **kwargs)


def desbloquear_caja_test(client, user):
    """Simula que `user` ya pasó el gate de PIN de caja en `client`.

    Escribe las claves de sesión directamente en vez de pasar por la vista de
    desbloqueo real: el middleware/las vistas de PIN recién llegan en la Fase
    5, pero los tests de turno de caja (Fase 4) necesitan poder "estar
    desbloqueados" antes de eso. `client` debe tener ya un usuario logueado
    (`force_login`) — esta función sólo agrega las claves de sesión.
    """
    session = client.session
    session['caja_pin_uid'] = user.pk
    session['caja_pin_hasta'] = time.time() + 900
    session.save()


# ──────────────────────────────────────────────────────────────────────────────
# Catálogos
# ──────────────────────────────────────────────────────────────────────────────

def make_tipo_prenda(nombre='Pantalón'):
    return TipoPrenda.objects.get_or_create(nombre=nombre)[0]


def make_tipo_reparacion(nombre='Arreglo'):
    return TipoReparacion.objects.get_or_create(nombre=nombre)[0]


def make_tipo_contrato(nombre='Tiempo Completo'):
    return TipoContrato.objects.get_or_create(nombre=nombre)[0]


def make_tipo_gasto(nombre='Servicios'):
    return TipoGasto.objects.get_or_create(nombre=nombre)[0]


def make_estado_alquiler(nombre='alquilado', color='alquilado'):
    return EstadoAlquiler.objects.get_or_create(nombre=nombre, defaults={'color': color})[0]


# ──────────────────────────────────────────────────────────────────────────────
# Personas
# ──────────────────────────────────────────────────────────────────────────────

def make_empleado(**kwargs):
    defaults = dict(
        nombres='Juan',
        apellido_paterno='Perez',
        celular='+59171234567',
        fecha_ingreso=date(2023, 1, 1),
    )
    defaults.update(kwargs)
    return Empleado.objects.create(**defaults)


def make_cliente(**kwargs):
    defaults = dict(
        nombres='Maria',
        apellido_paterno='Lopez',
        celular='+59171234568',
    )
    defaults.update(kwargs)
    return Cliente.objects.create(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# Inventario
# ──────────────────────────────────────────────────────────────────────────────

def make_prenda(**kwargs):
    defaults = dict(nombre='Traje Oscuro', precio=Decimal('150.00'))
    defaults.update(kwargs)
    return PrendaInventario.objects.create(**defaults)


def make_prenda_item(prenda=None, **kwargs):
    if prenda is None:
        prenda = make_prenda()
    defaults = dict(tipo='alquiler', condicion='nueva')
    defaults.update(kwargs)
    return PrendaItem.objects.create(prenda=prenda, **defaults)


def make_corte(**kwargs):
    return Corte.objects.create(**kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# Servicios
# ──────────────────────────────────────────────────────────────────────────────

def _actor_caja_por_defecto():
    """Dueño de la caja actualmente abierta, o None si no hay ninguna.

    Choke point de caja (architecture/caja-ownership-chokepoint): las
    señales `confeccion_to_caja`/`reparacion_to_caja`/`venta_to_caja` exigen
    un `_actor_caja` explícito para escribir un CajaMovimiento nuevo — en
    producción lo estampa la vista (`request.user`) antes de guardar. Estos
    factories NO son producción: la mayoría de los tests sólo necesitan "hay
    una caja abierta" (contabilidad pura, sin importar de quién), así que
    por conveniencia se infiere el dueño de la sesión abierta — si el test
    necesita un actor DISTINTO, debe pasar `usuario=` explícitamente al
    factory."""
    from misastreria.caja_turno import sesion_abierta
    sesion = sesion_abierta()
    return sesion.usuario_apertura if sesion else None


def make_reparacion(usuario=None, **kwargs):
    defaults = dict(
        fecha_entrega=date.today() + timedelta(days=3),
        total=Decimal('100.00'),
    )
    defaults.update(kwargs)
    instance = Reparacion(**defaults)
    instance._actor_caja = usuario if usuario is not None else _actor_caja_por_defecto()
    instance.save()
    return instance


def make_reparacion_item(reparacion=None, **kwargs):
    if reparacion is None:
        reparacion = make_reparacion()
    defaults = dict(
        tipo_prenda=make_tipo_prenda(),
        tipo_reparacion=make_tipo_reparacion(),
        costo=Decimal('50.00'),
    )
    defaults.update(kwargs)
    return ReparacionItem.objects.create(reparacion=reparacion, **defaults)


def make_venta(usuario=None, **kwargs):
    defaults = dict(
        descuento=Decimal('0'),
        subtotal=Decimal('0'),
        total=Decimal('0'),
    )
    defaults.update(kwargs)
    instance = Venta(**defaults)
    instance._actor_caja = usuario if usuario is not None else _actor_caja_por_defecto()
    instance.save()
    return instance


def make_confeccion(usuario=None, **kwargs):
    defaults = dict(
        color='Negro',
        modelo='Traje Clásico',
        precio=Decimal('500.00'),
        adelanto=Decimal('0'),
        saldo=Decimal('500.00'),
        fecha_inicio=date.today(),
    )
    defaults.update(kwargs)
    instance = Confeccion(**defaults)
    instance._actor_caja = usuario if usuario is not None else _actor_caja_por_defecto()
    instance.save()
    return instance


def make_alquiler(**kwargs):
    defaults = dict(
        fecha_alquiler=date.today(),
        fecha_devolucion=date.today() + timedelta(days=3),
        total=Decimal('200.00'),
        subtotal=Decimal('200.00'),
    )
    defaults.update(kwargs)
    return Alquiler.objects.create(**defaults)


def make_alquiler_item(alquiler=None, prenda_item=None, **kwargs):
    if alquiler is None:
        alquiler = make_alquiler()
    if prenda_item is None:
        prenda_item = make_prenda_item()
    defaults = dict(
        precio_unitario=Decimal('100.00'),
        precio_reparacion=Decimal('0'),
    )
    defaults.update(kwargs)
    return AlquilerItem.objects.create(
        alquiler=alquiler, prenda_item=prenda_item, **defaults
    )


# ──────────────────────────────────────────────────────────────────────────────
# Caja
# ──────────────────────────────────────────────────────────────────────────────

def make_sesion_caja(usuario=None, **kwargs):
    if usuario is None:
        usuario = make_cajero()
    defaults = dict(
        monto_apertura=Decimal('100.00'),
        usuario_apertura=usuario,
        estado='abierta',
    )
    defaults.update(kwargs)
    return CajaSesion.objects.create(**defaults)


def make_movimiento_caja(sesion=None, **kwargs):
    if sesion is None:
        sesion = make_sesion_caja()
    defaults = dict(
        tipo='ingreso',
        concepto='ingreso_manual',
        monto=Decimal('50.00'),
        forma_pago='efectivo',
        origen='manual',
    )
    defaults.update(kwargs)
    return CajaMovimiento.objects.create(sesion=sesion, **defaults)


# ──────────────────────────────────────────────────────────────────────────────
# Producción
# ──────────────────────────────────────────────────────────────────────────────

def make_orden_produccion(**kwargs):
    defaults = dict(descripcion='Orden test', tipo='cliente', estado='corte')
    defaults.update(kwargs)
    return OrdenProduccion.objects.create(**defaults)


def make_orden_produccion_empleado(orden, empleado, responsabilidad='corte', monto=Decimal('0')):
    return OrdenProduccionEmpleado.objects.create(
        orden=orden, empleado=empleado, responsabilidad=responsabilidad,
        monto_comision_fijo=monto)


def asignar_arreglo(item, empleado, monto):
    """Asigna un empleado al arreglo de un VentaItem/AlquilerItem.

    Desde la migración 0063 la comisión de un arreglo vive en la tabla de
    asignaciones y no en el FK del item, porque un arreglo puede llevar varios
    empleados. Devuelve el item para poder encadenar en los tests.
    """
    from misastreria.models import VentaItem, VentaItemEmpleado, AlquilerItemEmpleado
    if isinstance(item, VentaItem):
        VentaItemEmpleado.objects.create(
            venta_item=item, empleado=empleado, monto_comision_fijo=monto)
    else:
        AlquilerItemEmpleado.objects.create(
            alquiler_item=item, empleado=empleado, monto_comision_fijo=monto)
    return item


def cliente_y_empleado_de_mostrador():
    """Cliente y empleado de relleno para formularios que ahora los exigen.

    `VentaForm` pide cliente y empleado desde que una venta sin cliente deja
    una deuda sin deudor. Los tests que miden otra cosa —comisiones, stock,
    cruces de inventario— necesitan pasarlos sin que interfieran con lo que
    afirman.

    Seguro para los tests de comisión: la comisión sale de las tablas de
    asignación (VentaItemEmpleado y compañía), no del FK `empleado` del
    servicio, así que este empleado no devenga nada.

    Se apoya en las factories en vez de `get_or_create` para no repetir acá
    qué campos exige cada modelo, y busca antes de crear para que llamarla
    dos veces en el mismo test no choque contra los unique.
    """
    cli = (Cliente.objects.filter(nombres='Mostrador').first()
           or make_cliente(nombres='Mostrador', celular='+59170000002'))
    emp = (Empleado.objects.filter(nombres='Mostrador').first()
           or make_empleado(nombres='Mostrador', celular='+59170000001'))
    return cli, emp
