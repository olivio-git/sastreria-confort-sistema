"""
factories.py — helpers compartidos para crear objetos de test mínimos.
No es un test en sí; es importado por los demás módulos.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User

from misastreria.models import (
    Cliente, Empleado, TipoContrato,
    Reparacion, ReparacionItem, TipoPrenda, TipoReparacion,
    Venta, VentaItem,
    Confeccion,
    Alquiler, AlquilerItem,
    PrendaInventario, PrendaItem,
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

def make_user(username='testuser', password='testpass123'):
    return User.objects.create_user(username=username, password=password)


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


# ──────────────────────────────────────────────────────────────────────────────
# Servicios
# ──────────────────────────────────────────────────────────────────────────────

def make_reparacion(**kwargs):
    defaults = dict(
        fecha_entrega=date.today() + timedelta(days=3),
        total=Decimal('100.00'),
    )
    defaults.update(kwargs)
    return Reparacion.objects.create(**defaults)


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


def make_venta(**kwargs):
    defaults = dict(
        descuento=Decimal('0'),
        subtotal=Decimal('0'),
        total=Decimal('0'),
    )
    defaults.update(kwargs)
    return Venta.objects.create(**defaults)


def make_confeccion(**kwargs):
    defaults = dict(
        color='Negro',
        modelo='Traje Clásico',
        precio=Decimal('500.00'),
        adelanto=Decimal('0'),
        saldo=Decimal('500.00'),
        fecha_inicio=date.today(),
    )
    defaults.update(kwargs)
    return Confeccion.objects.create(**defaults)


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
        usuario = make_user(username='cajero')
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
