"""
caja_signals.py — Señales automáticas del módulo de caja.

Registradas en MisastreriaConfig.ready() via apps.py.
"""
from decimal import Decimal

from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import Alquiler, Venta, Confeccion, Reparacion, CajaSesion, CajaMovimiento, PagoComisionEmpleado


# ============================================================
# HELPERS
# ============================================================

def _sesion_activa():
    """Retorna la CajaSesion con estado='abierta', o None si no existe."""
    return CajaSesion.objects.filter(estado='abierta').first()


def _reversar_movimientos_activos(*, referencia_field, instance, usuario=None):
    """
    Reversa todos los CajaMovimientos activos vinculados a un servicio.
    Llamar ANTES de eliminar la instancia del servicio.
    """
    from django.db import transaction as db_transaction
    filtro = {referencia_field: instance, 'movimiento_reverso__isnull': True}
    sesion = _sesion_activa()
    # Exclude 'anulacion_cobro' to prevent reversing reversals (cycle prevention)
    for mov in CajaMovimiento.objects.filter(**filtro).exclude(concepto='anulacion_cobro'):
        if mov.fue_reversado:
            continue
        tipo_reverso = 'egreso' if mov.tipo == 'ingreso' else 'ingreso'
        with db_transaction.atomic():
            reverso = CajaMovimiento.objects.create(
                sesion=sesion,
                tipo=tipo_reverso,
                concepto='anulacion_cobro',
                origen='automatico',
                forma_pago=mov.forma_pago,
                monto=mov.monto,
                via_caja=mov.via_caja,
                cliente=mov.cliente,
                descripcion=f"Reverso automático por eliminación — {mov.codigo}",
                usuario=usuario,
                **{referencia_field: instance},
            )
            mov.movimiento_reverso = reverso
            mov.save(update_fields=['movimiento_reverso'])


# Red de seguridad: reversar movimientos de caja ANTES de borrar un servicio,
# pase lo que pase (vista, admin de Django, shell, borrado en lote). Las vistas
# eliminar_* ya llaman a _reversar_movimientos_activos explícitamente; este signal
# es idempotente con ellas (salta los ya reversados y excluye anulacion_cobro),
# así que no duplica. Su valor es cubrir los caminos de borrado que NO pasan por
# la vista, que es como nacieron phantoms históricos (ej. venta_cobro huérfano).
_SERVICIO_REFERENCIA_FIELD = {
    Alquiler:   'referencia_alquiler',
    Venta:      'referencia_venta',
    Confeccion: 'referencia_confeccion',
    Reparacion: 'referencia_reparacion',
}


@receiver(pre_delete, sender=Alquiler)
@receiver(pre_delete, sender=Venta)
@receiver(pre_delete, sender=Confeccion)
@receiver(pre_delete, sender=Reparacion)
def servicio_pre_delete_reversar_caja(sender, instance, **kwargs):
    """Reversa los movimientos de caja activos del servicio antes de eliminarlo."""
    referencia_field = _SERVICIO_REFERENCIA_FIELD.get(sender)
    if not referencia_field:
        return
    _reversar_movimientos_activos(referencia_field=referencia_field, instance=instance)


def _ajustar_total_en_caja(*, referencia_field, instance, concepto_cobro, nuevo_total, forma_pago, cliente=None, old_total=None):
    """
    Reconcilia la caja con el nuevo total de un servicio editado.

    Editar el total NO es un evento de cobro: no entra ni sale dinero porque sí.
    Lo único legítimo al editar es DEVOLVER el exceso cuando el nuevo total queda
    por debajo de lo realmente pagado (sobrepago). Nunca se crea un ingreso
    automático — eso registraría dinero que el cliente no entregó — ni un egreso
    cuando todavía hay saldo pendiente.

    - nuevo_total >= pagado  → no toca caja (el saldo pendiente se recalcula solo)
    - nuevo_total <  pagado  → devuelve el exceso (anulacion_cobro)

    `pagado` se calcula sobre los movimientos activos del servicio, excluyendo
    garantías de alquiler (que tienen su propio flujo). `concepto_cobro` y
    `old_total` se conservan por compatibilidad de firma pero ya no se usan.
    """
    from django.db.models import Sum
    if nuevo_total is None or Decimal(str(nuevo_total)) < 0:
        return
    base = CajaMovimiento.objects.filter(
        **{referencia_field: instance},
        movimiento_reverso__isnull=True,
        reverso_de__isnull=True,
    ).exclude(concepto__in=['garantia_alquiler', 'garantia_devolucion'])
    ingresos = base.filter(tipo='ingreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    egresos  = base.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    pagado = ingresos - egresos
    exceso = pagado - Decimal(str(nuevo_total))
    if exceso <= 0:
        return
    _crear_mov_auto(
        concepto='anulacion_cobro',
        monto=exceso,
        forma_pago=forma_pago or 'efectivo',
        descripcion=f"Devolución por edición — {instance} (-Bs {exceso})",
        **{referencia_field: instance},
        cliente=cliente,
    )


def _crear_mov_auto(*, concepto, monto, forma_pago, descripcion, via_caja=True, **fks):
    """
    Helper centralizado para crear movimientos automáticos.
    Checks idempotency via the referencia_* + concepto + movimiento_reverso__isnull=True query.
    Note: callers perform the idempotency check before calling this function.
    """
    if monto is None or Decimal(str(monto)) <= 0:
        return None
    sesion = _sesion_activa()
    return CajaMovimiento.objects.create(
        sesion=sesion,
        tipo=CajaMovimiento.concepto_tipo(concepto),
        concepto=concepto,
        origen='automatico',
        forma_pago=forma_pago or 'efectivo',
        monto=Decimal(str(monto)),
        via_caja=via_caja,
        fecha=timezone.now(),
        descripcion=descripcion,
        **fks,
    )


def _liberar_pagos_reservados(referencia_field, instance):
    """Convierte todos los pagos via_caja=False de un servicio a via_caja=True."""
    CajaMovimiento.objects.filter(
        **{referencia_field: instance},
        via_caja=False,
        movimiento_reverso__isnull=True,
    ).update(via_caja=True)


# ============================================================
# ALQUILER
# ============================================================

def registrar_alquiler_en_caja(instance, adelanto=Decimal('0'), forma_pago='efectivo'):
    """
    Registra el cobro inicial (adelanto) de un Alquiler en caja.
    Llamar explícitamente desde la vista DESPUÉS de recalcular_totales().
    Si adelanto == 0, no crea movimiento.
    """
    if not adelanto or adelanto <= 0:
        return
    instance.refresh_from_db()
    if CajaMovimiento.objects.filter(
        referencia_alquiler=instance,
        concepto='alquiler_cobro',
        movimiento_reverso__isnull=True,
    ).exists():
        return
    _crear_mov_auto(
        concepto='alquiler_cobro',
        monto=adelanto,
        forma_pago=forma_pago or 'efectivo',
        descripcion=f"Cobro inicial de alquiler #{instance.pk}",
        referencia_alquiler=instance,
        cliente=getattr(instance, 'cliente', None),
    )


@receiver(post_save, sender=Alquiler)
def alquiler_to_caja(sender, instance, created, **kwargs):
    """Fallback signal — deshabilitado: la vista maneja el adelanto explícitamente."""
    return


def _calcular_pagado_alquiler(alquiler):
    """
    Suma todos los movimientos activos de caja asociados al alquiler,
    excluyendo garantías. Retorna ingresos - egresos activos.
    """
    from django.db.models import Sum
    base = CajaMovimiento.objects.filter(
        referencia_alquiler=alquiler,
        movimiento_reverso__isnull=True,
        reverso_de__isnull=True,
    ).exclude(concepto__in=['garantia_alquiler', 'garantia_devolucion', 'alquiler_recargo'])
    ingresos = base.filter(tipo='ingreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    egresos  = base.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    return ingresos - egresos


def registrar_pago_alquiler(alquiler, monto, forma_pago, descripcion, usuario, via_caja=True):
    """
    Registra un pago parcial de alquiler en caja.
    Sin guarda de idempotencia — múltiples pagos son intencionales.
    """
    mov = _crear_mov_auto(
        concepto='alquiler_pago',
        monto=monto,
        forma_pago=forma_pago or 'efectivo',
        descripcion=descripcion or f"Pago de alquiler {alquiler.codigo}",
        referencia_alquiler=alquiler,
        cliente=getattr(alquiler, 'cliente', None),
        via_caja=via_caja,
    )
    if mov and usuario:
        mov.usuario = usuario
        mov.save(update_fields=['usuario'])
    if via_caja:
        alquiler.refresh_from_db()
        if alquiler.saldo_pendiente <= Decimal('0'):
            _liberar_pagos_reservados('referencia_alquiler', alquiler)


def registrar_recargo_alquiler(alquiler, monto, forma_pago, descripcion, usuario, via_caja=True):
    """
    Registra un cobro de recargo (mora por devolución tardía) de un alquiler.
    Es un ingreso EXTRA, independiente del total/saldo del alquiler — por eso
    se excluye de _calcular_pagado_alquiler. Sin guarda de idempotencia.
    """
    mov = _crear_mov_auto(
        concepto='alquiler_recargo',
        monto=monto,
        forma_pago=forma_pago or 'efectivo',
        descripcion=descripcion or f"Recargo por devolución tardía {alquiler.codigo}",
        referencia_alquiler=alquiler,
        cliente=getattr(alquiler, 'cliente', None),
        via_caja=via_caja,
    )
    if mov and usuario:
        mov.usuario = usuario
        mov.save(update_fields=['usuario'])
    return mov


def registrar_reparacion_en_caja(instance):
    """
    Registra el cobro de una Reparacion en caja cuando estado='entregado'.
    Llamar explícitamente desde la vista al crear una reparacion ya entregada.
    """
    if instance.estado != 'entregado':
        return
    total = getattr(instance, 'total', None)
    if not total or total <= 0:
        return
    if CajaMovimiento.objects.filter(
        referencia_reparacion=instance,
        concepto='reparacion_cobro',
        movimiento_reverso__isnull=True,
    ).exists():
        return
    _crear_mov_auto(
        concepto='reparacion_cobro',
        monto=total,
        forma_pago=getattr(instance, 'forma_pago', 'efectivo') or 'efectivo',
        descripcion=f"Cobro automático reparación #{instance.pk}",
        referencia_reparacion=instance,
        cliente=getattr(instance, 'cliente', None),
    )


_GARANTIA_TIPOS_MONETARIOS = ('efectivo', 'qr', 'transferencia')


def registrar_garantia_alquiler_en_caja(instance):
    """
    Crea el movimiento de ingreso por garantía monetaria de un alquiler (nueva creación).
    Solo actúa si garantia_tipo es monetario y garantia_monto > 0.
    """
    instance.refresh_from_db()
    if instance.garantia_tipo not in _GARANTIA_TIPOS_MONETARIOS:
        return
    if not instance.garantia_monto or instance.garantia_monto <= 0:
        return
    if CajaMovimiento.objects.filter(
        referencia_alquiler=instance,
        concepto='garantia_alquiler',
        movimiento_reverso__isnull=True,
    ).exists():
        return
    _crear_mov_auto(
        concepto='garantia_alquiler',
        monto=instance.garantia_monto,
        forma_pago=instance.garantia_tipo,
        descripcion=f"Garantía de alquiler {instance.codigo}",
        referencia_alquiler=instance,
        cliente=getattr(instance, 'cliente', None),
    )


def _ajustar_garantia_alquiler_en_caja(instance):
    """
    Sincroniza el movimiento de garantía al editar un alquiler.
    - Si la garantía pasó a no-monetaria → reversa el movimiento existente.
    - Si cambió monto o tipo → reversa el anterior y crea uno nuevo.
    - Si no cambió → no hace nada.
    """
    from django.db import transaction as db_transaction
    existing = CajaMovimiento.objects.filter(
        referencia_alquiler=instance,
        concepto='garantia_alquiler',
        movimiento_reverso__isnull=True,
    ).first()

    is_monetary = (
        instance.garantia_tipo in _GARANTIA_TIPOS_MONETARIOS
        and instance.garantia_monto
        and instance.garantia_monto > 0
    )

    if not is_monetary:
        if existing and not existing.fue_reversado:
            sesion = _sesion_activa()
            with db_transaction.atomic():
                reverso = CajaMovimiento.objects.create(
                    sesion=sesion,
                    tipo='egreso',
                    concepto='anulacion_cobro',
                    origen='automatico',
                    forma_pago=existing.forma_pago,
                    monto=existing.monto,
                    cliente=existing.cliente,
                    referencia_alquiler=instance,
                    descripcion=f"Garantía eliminada — {instance.codigo}",
                )
                existing.movimiento_reverso = reverso
                existing.save(update_fields=['movimiento_reverso'])
        return

    if existing:
        forma = instance.garantia_tipo
        if existing.monto == instance.garantia_monto and existing.forma_pago == forma:
            return
        # Reverse old and create new
        sesion = _sesion_activa()
        with db_transaction.atomic():
            reverso = CajaMovimiento.objects.create(
                sesion=sesion,
                tipo='egreso',
                concepto='anulacion_cobro',
                origen='automatico',
                forma_pago=existing.forma_pago,
                monto=existing.monto,
                cliente=existing.cliente,
                referencia_alquiler=instance,
                descripcion=f"Ajuste garantía — {instance.codigo}",
            )
            existing.movimiento_reverso = reverso
            existing.save(update_fields=['movimiento_reverso'])

    _crear_mov_auto(
        concepto='garantia_alquiler',
        monto=instance.garantia_monto,
        forma_pago=instance.garantia_tipo,
        descripcion=f"Garantía de alquiler {instance.codigo}",
        referencia_alquiler=instance,
        cliente=getattr(instance, 'cliente', None),
    )


def registrar_devolucion_garantia_alquiler(instance, monto_devuelto, usuario=None):
    """
    Registra la devolución de garantía al cliente como egreso.
    monto_devuelto puede ser menor al original si hay recargos aplicados.
    """
    if not monto_devuelto or Decimal(str(monto_devuelto)) <= 0:
        return
    if CajaMovimiento.objects.filter(
        referencia_alquiler=instance,
        concepto='garantia_devolucion',
        movimiento_reverso__isnull=True,
    ).exists():
        return
    sesion = _sesion_activa()
    CajaMovimiento.objects.create(
        sesion=sesion,
        tipo='egreso',
        concepto='garantia_devolucion',
        origen='automatico',
        forma_pago=instance.garantia_tipo or 'efectivo',
        monto=Decimal(str(monto_devuelto)),
        descripcion=f"Devolución de garantía — {instance.codigo}",
        referencia_alquiler=instance,
        cliente=getattr(instance, 'cliente', None),
        usuario=usuario,
    )


# ============================================================
# VENTA
# ============================================================

def _calcular_pagado_venta(venta):
    """
    Suma todos los movimientos activos de caja asociados a la venta.
    Retorna ingresos - egresos activos.
    """
    from django.db.models import Sum
    base = CajaMovimiento.objects.filter(
        referencia_venta=venta,
        movimiento_reverso__isnull=True,
        reverso_de__isnull=True,
    )
    ingresos = base.filter(tipo='ingreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    egresos  = base.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    return ingresos - egresos


def registrar_venta_en_caja(instance, adelanto=None):
    """
    Registra el movimiento de caja al crear una Venta.
    - Si adelanto is None o adelanto >= total → cobro completo (venta_cobro), estado efectuada
    - Si 0 < adelanto < total → adelanto (venta_adelanto), estado en_proceso
    - Si adelanto == 0 → no crea movimiento, estado en_proceso
    """
    instance.refresh_from_db()
    if not instance.total or instance.total <= 0:
        return

    adelanto = Decimal(str(adelanto)) if adelanto is not None else None

    if adelanto is None or adelanto >= instance.total:
        # pago completo
        if CajaMovimiento.objects.filter(
            referencia_venta=instance,
            concepto='venta_cobro',
            movimiento_reverso__isnull=True,
        ).exists():
            return
        _crear_mov_auto(
            concepto='venta_cobro',
            monto=instance.total,
            forma_pago=getattr(instance, 'forma_pago', 'efectivo') or 'efectivo',
            descripcion=f"Cobro de venta {instance.codigo}",
            referencia_venta=instance,
            cliente=getattr(instance, 'cliente', None),
        )
    elif adelanto > Decimal('0'):
        # adelanto parcial
        _crear_mov_auto(
            concepto='venta_adelanto',
            monto=adelanto,
            forma_pago=getattr(instance, 'forma_pago', 'efectivo') or 'efectivo',
            descripcion=f"Adelanto de venta {instance.codigo}",
            referencia_venta=instance,
            cliente=getattr(instance, 'cliente', None),
        )
    # si adelanto == 0 → no crear movimiento


def registrar_pago_venta(venta, monto, forma_pago, descripcion, usuario, via_caja=True):
    """
    Registra un pago parcial de venta en caja.
    Sin guarda de idempotencia — múltiples pagos son intencionales.
    Cuando el saldo llega a 0 → marca la venta como efectuada e items pasan a baja.
    Cuando via_caja=True y saldo=0 → libera también los pagos en reserva a caja.
    """
    saldo = venta.saldo_pendiente
    concepto = 'venta_saldo' if monto >= saldo else 'venta_pago'
    mov = _crear_mov_auto(
        concepto=concepto,
        monto=monto,
        forma_pago=forma_pago or 'efectivo',
        descripcion=descripcion or f"Pago de venta {venta.codigo}",
        referencia_venta=venta,
        cliente=getattr(venta, 'cliente', None),
        via_caja=via_caja,
    )
    if mov and usuario:
        mov.usuario = usuario
        mov.save(update_fields=['usuario'])
    venta.refresh_from_db()
    nuevo_saldo = venta.saldo_pendiente
    if nuevo_saldo <= Decimal('0') and venta.estado != 'efectuada':
        venta.estado = 'efectuada'
        venta.save(update_fields=['estado'])
        for item in venta.items.select_related('prenda_item').all():
            pi = item.prenda_item
            if pi and pi.estado == 'reservado':
                pi.estado = 'baja'
                pi.save(update_fields=['estado'])
    if via_caja and nuevo_saldo <= Decimal('0'):
        _liberar_pagos_reservados('referencia_venta', venta)


@receiver(post_save, sender=Venta)
def venta_to_caja(sender, instance, created, **kwargs):
    """Fallback signal — sólo aplica si total ya está fijado al momento de crear."""
    if not created:
        return
    registrar_venta_en_caja(instance)


# ============================================================
# CONFECCION
# ============================================================

@receiver(pre_save, sender=Confeccion)
def confeccion_pre_save(sender, instance, **kwargs):
    """
    CAUTO-03, CAUTO-04: Captura old_adelanto y old_estado antes del update
    para detección de deltas en post_save.
    """
    if instance.pk:
        try:
            prev = Confeccion.objects.get(pk=instance.pk)
            instance._old_adelanto = prev.adelanto or Decimal('0')
            instance._old_estado = prev.estado
        except Confeccion.DoesNotExist:
            instance._old_adelanto = Decimal('0')
            instance._old_estado = None
    else:
        instance._old_adelanto = Decimal('0')
        instance._old_estado = None


def _calcular_saldo_confeccion(confeccion):
    """Calcula el saldo pendiente: precio - (ingresos activos - egresos activos) vinculados a la confección."""
    from django.db.models import Sum
    base = CajaMovimiento.objects.filter(
        referencia_confeccion=confeccion,
        movimiento_reverso__isnull=True,
        reverso_de__isnull=True,
    )
    ingresos = base.filter(tipo='ingreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    egresos  = base.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    precio   = confeccion.precio or Decimal('0')
    return max(Decimal('0'), Decimal(str(precio)) - (ingresos - egresos))


def _calcular_pagado_confeccion(confeccion):
    """Suma ingresos activos - egresos activos de la confección.
    Sin exclusión de garantía — confección no tiene concepto monetario de garantía en caja.
    """
    from django.db.models import Sum
    base = CajaMovimiento.objects.filter(
        referencia_confeccion=confeccion,
        movimiento_reverso__isnull=True,
        reverso_de__isnull=True,
    )
    ingresos = base.filter(tipo='ingreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    egresos  = base.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    return ingresos - egresos


def registrar_pago_confeccion(confeccion, monto, forma_pago, descripcion, usuario, via_caja=True):
    """Registra un pago parcial de confección en caja.
    Sin guarda de idempotencia — múltiples pagos son intencionales.
    """
    mov = _crear_mov_auto(
        concepto='confeccion_pago',
        monto=monto,
        forma_pago=forma_pago or 'efectivo',
        descripcion=descripcion or f"Pago de confección {confeccion.codigo}",
        referencia_confeccion=confeccion,
        cliente=getattr(confeccion, 'cliente', None),
        via_caja=via_caja,
    )
    if mov and usuario:
        mov.usuario = usuario
        mov.save(update_fields=['usuario'])
    if via_caja:
        confeccion.refresh_from_db()
        if confeccion.saldo_pendiente <= Decimal('0'):
            _liberar_pagos_reservados('referencia_confeccion', confeccion)


@receiver(post_save, sender=Confeccion)
def confeccion_to_caja(sender, instance, created, **kwargs):
    """
    CAUTO-03: Adelanto al crear (si adelanto > 0) o al incrementar adelanto.
    CAUTO-04: Saldo al transitar a estado='entregado'.
    CAUTO-06: Idempotency.
    """
    forma = getattr(instance, 'forma_pago', 'efectivo') or 'efectivo'
    cliente = getattr(instance, 'cliente', None)

    nuevo_adelanto = instance.adelanto or Decimal('0')
    old_adelanto = getattr(instance, '_old_adelanto', Decimal('0'))

    # --- Bloque adelanto ---
    if created and nuevo_adelanto > 0:
        if not CajaMovimiento.objects.filter(
            referencia_confeccion=instance,
            concepto='confeccion_adelanto',
            movimiento_reverso__isnull=True,
        ).exists():
            _crear_mov_auto(
                concepto='confeccion_adelanto',
                monto=nuevo_adelanto,
                forma_pago=forma,
                descripcion=f"Adelanto automático confección #{instance.pk}",
                referencia_confeccion=instance,
                cliente=cliente,
            )
    elif not created and nuevo_adelanto > old_adelanto:
        delta = nuevo_adelanto - old_adelanto
        _crear_mov_auto(
            concepto='confeccion_adelanto',
            monto=delta,
            forma_pago=forma,
            descripcion=f"Incremento de adelanto confección #{instance.pk} (+Bs {delta})",
            referencia_confeccion=instance,
            cliente=cliente,
        )
    elif not created and nuevo_adelanto < old_adelanto:
        delta = old_adelanto - nuevo_adelanto
        _crear_mov_auto(
            concepto='anulacion_cobro',
            monto=delta,
            forma_pago=forma,
            descripcion=f"Reducción de adelanto confección #{instance.pk} (-Bs {delta})",
            referencia_confeccion=instance,
            cliente=cliente,
        )

    # --- Bloque saldo al entregar ---
    old_estado = getattr(instance, '_old_estado', None)
    if (
        not created
        and old_estado != 'entregado'
        and instance.estado == 'entregado'
    ):
        saldo_pendiente = _calcular_saldo_confeccion(instance)
        if saldo_pendiente > 0:
            if not CajaMovimiento.objects.filter(
                referencia_confeccion=instance,
                concepto='confeccion_saldo',
                movimiento_reverso__isnull=True,
            ).exists():
                _crear_mov_auto(
                    concepto='confeccion_saldo',
                    monto=saldo_pendiente,
                    forma_pago=forma,
                    descripcion=f"Saldo final confección #{instance.pk}",
                    referencia_confeccion=instance,
                    cliente=cliente,
                )


# ============================================================
# REPARACION
# ============================================================

@receiver(pre_save, sender=Reparacion)
def reparacion_pre_save(sender, instance, **kwargs):
    """
    CAUTO-05: Captura old_estado antes del update para detección de transición a 'entregado'.
    """
    if instance.pk:
        try:
            instance._old_estado = Reparacion.objects.get(pk=instance.pk).estado
        except Reparacion.DoesNotExist:
            instance._old_estado = None
    else:
        instance._old_estado = None


def _calcular_pagado_reparacion(reparacion):
    from django.db.models import Sum
    base = CajaMovimiento.objects.filter(
        referencia_reparacion=reparacion,
        movimiento_reverso__isnull=True,
        reverso_de__isnull=True,
    )
    ingresos = base.filter(tipo='ingreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    egresos  = base.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
    return ingresos - egresos


def _calcular_saldo_reparacion(reparacion):
    precio = reparacion.total or Decimal('0')
    return max(Decimal('0'), Decimal(str(precio)) - _calcular_pagado_reparacion(reparacion))


def registrar_pago_reparacion(reparacion, monto, forma_pago, descripcion, usuario, via_caja=True):
    mov = _crear_mov_auto(
        concepto='reparacion_pago',
        monto=monto,
        forma_pago=forma_pago or 'efectivo',
        descripcion=descripcion or f"Pago de reparación {reparacion.codigo}",
        referencia_reparacion=reparacion,
        cliente=getattr(reparacion, 'cliente', None),
        via_caja=via_caja,
    )
    if mov and usuario:
        mov.usuario = usuario
        mov.save(update_fields=['usuario'])
    if via_caja:
        reparacion.refresh_from_db()
        if reparacion.saldo_pendiente <= Decimal('0'):
            _liberar_pagos_reservados('referencia_reparacion', reparacion)


def registrar_pago_comision_empleado(empleado, monto, forma_pago, via_caja, descripcion, usuario):
    """
    Registra un pago de comisión a un empleado.
    - Siempre crea PagoComisionEmpleado (la fuente de verdad del saldo).
    - Si via_caja=True, además crea CajaMovimiento(concepto='comision_empleado', egreso).
    - Si via_caja=False, NO toca caja (pago fuera de caja).
    Retorna el PagoComisionEmpleado creado, o None si monto <= 0.
    """
    from django.db import transaction as db_transaction

    if monto is None or Decimal(str(monto)) <= 0:
        return None

    with db_transaction.atomic():
        pago = PagoComisionEmpleado.objects.create(
            empleado=empleado,
            monto=Decimal(str(monto)),
            forma_pago=forma_pago or 'efectivo',
            via_caja=bool(via_caja),
            descripcion=descripcion or '',
            usuario=usuario,
        )
        if via_caja:
            mov = _crear_mov_auto(
                concepto='comision_empleado',
                monto=monto,
                forma_pago=forma_pago or 'efectivo',
                descripcion=descripcion or f"Comisión {empleado} ({pago.codigo})",
                referencia_pago_comision=pago,
            )
            if mov and usuario:
                mov.usuario = usuario
                mov.save(update_fields=['usuario'])
    return pago


@receiver(post_save, sender=Reparacion)
def reparacion_to_caja(sender, instance, created, **kwargs):
    """
    CAUTO-05: Crea CajaMovimiento(concepto='reparacion_cobro') cuando estado -> 'entregado'.
             Reversa reparacion_cobro activo cuando estado retrocede desde 'entregado'.
    CAUTO-06: Idempotency.
    """
    if created:
        return
    old_estado = getattr(instance, '_old_estado', None)

    # Regresión: 'entregado' → otro estado
    if old_estado == 'entregado' and instance.estado != 'entregado':
        _reversar_movimientos_activos(referencia_field='referencia_reparacion', instance=instance)
        return

    # Transición GENUINA: otro estado → 'entregado'.
    # Un update 'entregado' → 'entregado' (ej. recalcular_total durante la creación
    # de una reparación ya entregada) NO debe generar el saldo final: ese caso lo
    # cubre registrar_reparacion_en_caja() con concepto 'reparacion_cobro'. Sin este
    # guard se generaban DOS movimientos (reparacion_saldo + reparacion_cobro).
    if instance.estado != 'entregado' or old_estado == 'entregado':
        return
    # Idempotencia: ya existe cobro o saldo final
    if CajaMovimiento.objects.filter(
        referencia_reparacion=instance,
        concepto__in=['reparacion_cobro', 'reparacion_saldo'],
        movimiento_reverso__isnull=True,
    ).exists():
        return
    saldo = _calcular_saldo_reparacion(instance)
    if saldo <= 0:
        return
    _crear_mov_auto(
        concepto='reparacion_saldo',
        monto=saldo,
        forma_pago=getattr(instance, 'forma_pago', 'efectivo') or 'efectivo',
        descripcion=f"Saldo final reparación {instance.codigo}",
        referencia_reparacion=instance,
        cliente=getattr(instance, 'cliente', None),
    )
