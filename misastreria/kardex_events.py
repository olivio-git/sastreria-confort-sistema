"""Centralized helpers for emitting KardexEvento rows.

ALL lifecycle write paths must call exactly one of these. New write paths
require a new helper here — do NOT call KardexEvento.objects.create() inline.
"""
from decimal import Decimal

from django.utils import timezone


def emit_ingreso(item, descripcion=None):
    from .models import KardexEvento
    return KardexEvento.objects.create(
        tipo='ingreso',
        timestamp=item.creado,
        prenda_item=item,
        descripcion=descripcion or f'Ingreso al inventario ({item.get_condicion_display()})',
    )


def emit_alquiler(item, alquiler, monto):
    from .models import KardexEvento
    return KardexEvento.objects.create(
        tipo='alquiler',
        timestamp=timezone.now(),
        prenda_item=item,
        alquiler=alquiler,
        cliente=alquiler.cliente,
        monto=monto,
        descripcion=f'Alquilado — {alquiler.codigo}',
    )


def emit_devolucion(item, alquiler):
    from .models import KardexEvento
    return KardexEvento.objects.create(
        tipo='devolucion',
        timestamp=timezone.now(),
        prenda_item=item,
        alquiler=alquiler,
        cliente=alquiler.cliente,
        descripcion=f'Devuelto — {alquiler.codigo}',
    )


def emit_venta(item, venta, monto):
    from .models import KardexEvento
    return KardexEvento.objects.create(
        tipo='venta',
        timestamp=timezone.now(),
        prenda_item=item,
        venta=venta,
        cliente=venta.cliente,
        monto=monto,
        descripcion=f'Vendido — {venta.codigo}',
    )


def emit_baja(item):
    from .models import KardexEvento
    return KardexEvento.objects.create(
        tipo='baja',
        timestamp=timezone.now(),
        prenda_item=item,
        descripcion='Dado de baja',
    )


def delete_eventos_alquiler(alquiler):
    """Delete all eventos linked to alquiler (tipo in {'alquiler', 'devolucion'}).
    Returns deleted count. Used in editar_alquiler delete-recreate."""
    from .models import KardexEvento
    deleted, _ = KardexEvento.objects.filter(alquiler=alquiler).delete()
    return deleted


def delete_eventos_venta(venta):
    """Delete all eventos linked to venta (tipo='venta'). Returns deleted count."""
    from .models import KardexEvento
    deleted, _ = KardexEvento.objects.filter(venta=venta).delete()
    return deleted


def backfill_item(item):
    """Create historical events for an item idempotently via get_or_create.
    Returns count of NEW events inserted (0 if already backfilled)."""
    from datetime import datetime, time as time_cls
    from .models import KardexEvento

    count = 0

    # Ingreso — use the real creation timestamp (DateTimeField)
    _, created = KardexEvento.objects.get_or_create(
        prenda_item=item,
        tipo='ingreso',
        alquiler=None,
        venta=None,
        defaults={
            'timestamp': item.creado,
            'descripcion': f'Ingreso al inventario ({item.get_condicion_display()})',
        },
    )
    if created:
        count += 1

    # Alquileres y devoluciones
    for ai in item.alquiler_items.select_related('alquiler__cliente').all():
        a = ai.alquiler
        ts_alq = timezone.make_aware(datetime.combine(a.fecha_alquiler, time_cls(9, 0)))
        _, created = KardexEvento.objects.get_or_create(
            prenda_item=item,
            tipo='alquiler',
            alquiler=a,
            defaults={
                'timestamp': ts_alq,
                'cliente': a.cliente,
                'monto': ai.precio_unitario,
                'descripcion': f'Alquilado — {a.codigo} (aprox.)',
            },
        )
        if created:
            count += 1

        if a.estado != 'alquilado' and a.fecha_devolucion:
            ts_dev = timezone.make_aware(datetime.combine(a.fecha_devolucion, time_cls(18, 0)))
            _, created = KardexEvento.objects.get_or_create(
                prenda_item=item,
                tipo='devolucion',
                alquiler=a,
                defaults={
                    'timestamp': ts_dev,
                    'cliente': a.cliente,
                    'descripcion': f'Devuelto — {a.codigo} (aprox.)',
                },
            )
            if created:
                count += 1

    # Ventas
    for vi in item.venta_items.select_related('venta__cliente').all():
        v = vi.venta
        ts_v = timezone.make_aware(datetime.combine(v.fecha_venta, time_cls(9, 0)))
        _, created = KardexEvento.objects.get_or_create(
            prenda_item=item,
            tipo='venta',
            venta=v,
            defaults={
                'timestamp': ts_v,
                'cliente': v.cliente,
                'monto': vi.precio_unitario,
                'descripcion': f'Vendido — {v.codigo} (aprox.)',
            },
        )
        if created:
            count += 1

    # Baja
    if item.estado == 'baja':
        if item.fecha_baja:
            ts_b = timezone.make_aware(datetime.combine(item.fecha_baja, time_cls(23, 59)))
            desc = 'Dado de baja (aprox.)'
        else:
            ts_b = item.actualizado
            desc = 'Dado de baja (aprox.)'
        _, created = KardexEvento.objects.get_or_create(
            prenda_item=item,
            tipo='baja',
            alquiler=None,
            venta=None,
            defaults={
                'timestamp': ts_b,
                'descripcion': desc,
            },
        )
        if created:
            count += 1

    return count
