"""
Reglas de "turno de caja": quién puede operar la sesión de caja abierta.

Una sesión de caja pertenece al usuario que la abrió (`usuario_apertura`).
Sólo ese usuario (o un Administrador supervisando) puede registrar
movimientos, revertirlos o cerrarla. El cobro (pagos de venta/alquiler/
confección/reparación) exige una sesión abierta Y que sea del usuario que
está cobrando — un Administrador NO puede cobrar en el turno de otro
Cajero, tiene que abrir el suyo.

También vive acá (agregado en la Fase 5) el ciclo de vida del PIN de
desbloqueo de caja: son parte del mismo "quién puede tocar la caja ahora".
"""
from contextlib import contextmanager

from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from django.utils import timezone

INTENTOS_MAXIMOS_PIN = 5
PIN_VIGENCIA_SEGUNDOS = 15 * 60  # 15 minutos de inactividad


class TurnoCajaError(Exception):
    """Error de negocio de turno de caja — se captura en la vista y se
    muestra como `messages.error` + redirect, NUNCA como 403 (no es un
    problema de permiso, es un problema de "esta caja no es tuya ahora")."""


class CajaSinSesionError(TurnoCajaError):
    """Defensa en profundidad: ningún CajaMovimiento se crea con
    `sesion=None`. Las vistas deben evitar llegar acá llamando primero a
    `verificar_turno_cobro`; esto cubre además caminos que no pasan por una
    vista (admin de Django, shell, señales)."""


class CajasAbiertasMultiplesError(TurnoCajaError):
    """Hay 2 o más CajaSesion abiertas. No debería pasar (una sola abierta a
    la vez), pero en MariaDB el UniqueConstraint condicional `unique_caja_abierta`
    no existe (models.W036), así que la base no lo impide. Se falla CERRADO:
    ningún cobro/reversión se asienta en una caja "elegida" al azar."""


MENSAJE_CAJAS_MULTIPLES = (
    'Hay más de una caja abierta al mismo tiempo. Pedile a un Administrador '
    'que cierre las que sobran antes de seguir operando.'
)


def sesion_abierta():
    """La CajaSesion con estado='abierta', o None si no hay ninguna.

    Si por alguna falla hay 2+ abiertas levanta `CajasAbiertasMultiplesError`
    en vez de devolver "la primera": esta es la única puerta por la que el
    resto del código (turno de cobro, reversión, señales) resuelve la caja.
    """
    from .models import CajaSesion
    sesiones = list(
        CajaSesion.objects.filter(estado='abierta')
        .select_related('usuario_apertura').order_by('pk')[:2]
    )
    if len(sesiones) > 1:
        raise CajasAbiertasMultiplesError(MENSAJE_CAJAS_MULTIPLES)
    return sesiones[0] if sesiones else None


def sesion_abierta_para_mostrar():
    """Como `sesion_abierta()` pero para pantallas (topbar, dashboard) que no
    pueden reventar: devuelve `(sesion, ambigua)`. Con 2+ abiertas devuelve
    `(None, True)` — nunca muestra una caja como si fuera "la" abierta."""
    try:
        return sesion_abierta(), False
    except CajasAbiertasMultiplesError:
        return None, True


@contextmanager
def bloqueo_apertura_caja(timeout=10):
    """Serializa a quienes abren caja para que "a lo sumo una abierta" valga
    aunque la base no tenga el constraint (MariaDB).

    En MySQL/MariaDB usa un lock nombrado (`GET_LOCK`). Se eligió eso y no un
    `SELECT ... FOR UPDATE` porque bloquear "las sesiones abiertas" no sirve:
    si no hay ninguna la consulta no devuelve filas y NO frena a un INSERT
    concurrente. Un `FOR UPDATE` sobre una fila singleton obligaría a crear
    una tabla/migración sólo para esto. `GET_LOCK` no requiere esquema, es por
    conexión (se libera solo si la conexión muere) y se toma FUERA de la
    transacción de apertura: el llamador hace `atomic()` adentro, re-chequea y
    crea, y el lock se suelta recién después del commit, así el siguiente en
    la cola ya ve la sesión confirmada.

    En otros motores (SQLite en desarrollo/tests) no hace nada: ahí los
    escritores ya se serializan y el UniqueConstraint sí existe.
    """
    if connection.vendor != 'mysql':
        yield
        return
    nombre = f"caja_apertura:{connection.settings_dict['NAME']}"[:64]
    with connection.cursor() as cursor:
        cursor.execute('SELECT GET_LOCK(%s, %s)', [nombre, timeout])
        obtenido = cursor.fetchone()[0]
    if obtenido != 1:
        raise TurnoCajaError(
            'Hay otra apertura de caja en curso. Intentá de nuevo en unos segundos.'
        )
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT RELEASE_LOCK(%s)', [nombre])


def verificar_turno_cobro(user):
    """Exige una sesión abierta Y que pertenezca a `user` (Administrador
    incluido — supervisar no es lo mismo que cobrar). Devuelve la sesión si
    todo está en orden; si no, levanta TurnoCajaError con un mensaje listo
    para mostrarle al usuario.
    """
    sesion = sesion_abierta()
    if sesion is None:
        raise TurnoCajaError(
            'No hay ninguna caja abierta. Abrí tu turno antes de registrar un cobro.'
        )
    if sesion.usuario_apertura_id != user.id:
        raise TurnoCajaError(
            f'La caja abierta es de {sesion.usuario_apertura.get_username()}. '
            'Sólo quien abrió el turno puede registrar cobros en él.'
        )
    return sesion


def verificar_turno_reversion(user):
    """Para REVERTIR/ANULAR un movimiento que ya existe (no crear uno nuevo):
    el dueño del turno abierto, O un Administrador (`supervisar_caja`) —
    regla confirmada por el dueño del producto ("revertir: dueño o
    Administrador", WARNING 1 del reporte de verificación). Para movimientos
    NUEVOS (cobros, devoluciones de garantía, ajustes, etc.) usar SIEMPRE
    `verificar_turno_cobro`, que NO exime a Administrador — sólo reversiones
    de algo que ya estaba asentado tienen esta excepción de supervisión."""
    sesion = sesion_abierta()
    if sesion is None:
        raise TurnoCajaError(
            'No hay ninguna caja abierta. Abrí un turno antes de revertir este movimiento.'
        )
    if sesion.usuario_apertura_id == user.id or puede_supervisar(user):
        return sesion
    raise TurnoCajaError(
        f'La caja abierta es de {sesion.usuario_apertura.get_username()}. '
        'Sólo quien abrió el turno (o un Administrador) puede revertir movimientos en ella.'
    )


def autorizar_cambio_estado(user, estado_anterior, estado_nuevo, saldo_pendiente=None):
    """Autoriza CUALQUIER cambio de `estado` en los formularios de edición de
    Reparación/Confección (`editar_reparacion`/`editar_confeccion`) — no sólo
    la transición a 'entregado'. CRITICAL 1 del reporte de verificación:
    `ReparacionForm`/`ConfeccionForm` exponen el campo `estado` completo y el
    guard existente sólo cubría la dirección "hacia entregado"
    (`autorizar_transicion_a_entregado`); un Vendedor (tiene `change_
    reparacion` pero nunca `cambiar_estado_taller`) podía mandar
    entregado->pendiente o pendiente->en_proceso sin ningún chequeo de
    permiso — y el primer caso encima disparaba la reversión automática del
    cobro en `caja_signals.reparacion_to_caja`, escribiendo un egreso en la
    caja de quien tuviera el turno abierto en ese momento.

    Matriz (spec): "Reparaciones/Confecciones en_proceso/entregado = Admin/
    Taller only" — por lo tanto CUALQUIER cambio de estado (no sólo hacia
    'entregado') exige `cambiar_estado_taller`. Si no hay cambio real
    (`estado_anterior == estado_nuevo`, típico al reenviar el mismo form) no
    se exige nada. Si el nuevo estado es 'entregado' delega en
    `autorizar_transicion_a_entregado` (mismo permiso + turno propio si
    queda saldo pendiente)."""
    if estado_anterior == estado_nuevo:
        return
    if estado_nuevo == 'entregado':
        autorizar_transicion_a_entregado(user, saldo_pendiente)
        return
    if not user.has_perm('misastreria.cambiar_estado_taller'):
        raise TurnoCajaError('No tenés permiso para cambiar el estado de esto.')


def puede_supervisar(user):
    """Administrador (o quien tenga `supervisar_caja`) puede ver/forzar el
    cierre de CUALQUIER sesión, no sólo la propia."""
    return user.has_perm('misastreria.supervisar_caja')


def puede_ver_sesion(user, sesion):
    """Dueño de la sesión, o alguien con permiso de supervisión."""
    return sesion.usuario_apertura_id == user.id or puede_supervisar(user)


def autorizar_transicion_a_entregado(user, saldo_pendiente):
    """Reglas para marcar una reparación/confección como 'entregado' —
    ÚNICAS y compartidas por todos los caminos que pueden disparar esa
    transición: el botón dedicado (`marcar_entregado`/`entregar_confeccion`)
    Y cualquier formulario que además exponga el campo `estado`
    (`crear_reparacion`, `editar_reparacion`, `crear_confeccion`,
    `editar_confeccion` — `ReparacionForm`/`ConfeccionForm` incluyen
    `estado` entre sus campos editables, así que sin este guard alcanzaba con
    mandar `estado=entregado` en esos formularios para saltarse la regla).

    Matriz de permisos (spec): "Reparaciones/Confecciones entregado = Admin/
    Taller only". Si además queda saldo pendiente, hace falta tener la caja
    PROPIA abierta para poder cobrar ese saldo — igual que cualquier otro
    cobro. Taller nunca tiene turno propio (nunca recibe `abrir_caja`), así
    que en la práctica sólo puede entregar cuando el saldo ya es cero
    (opción (a) del reporte de verificación: "Taller sólo entrega con saldo
    en cero").

    Levanta `TurnoCajaError` con un mensaje listo para mostrarle al usuario
    si la transición no está permitida; no devuelve nada ni levanta nada si
    está todo en orden."""
    if not user.has_perm('misastreria.cambiar_estado_taller'):
        raise TurnoCajaError(
            'No tenés permiso para marcar esto como entregado.'
        )
    if saldo_pendiente and saldo_pendiente > 0:
        verificar_turno_cobro(user)


# ============================================================
# PIN de desbloqueo de caja (Fase 5)
# ============================================================

def perfil_de(user):
    """PerfilUsuario de `user`, creándolo si todavía no existe (get_or_create
    perezoso: no todos los Users tienen fila desde el arranque)."""
    from .models import PerfilUsuario
    perfil, _ = PerfilUsuario.objects.get_or_create(user=user)
    return perfil


def set_pin(user, raw_pin):
    """Fija un PIN nuevo y limpia cualquier bloqueo/intentos previos."""
    perfil = perfil_de(user)
    perfil.pin_hash = make_password(str(raw_pin))
    perfil.pin_intentos_fallidos = 0
    perfil.pin_bloqueado = False
    perfil.pin_actualizado = timezone.now()
    perfil.save(update_fields=['pin_hash', 'pin_intentos_fallidos', 'pin_bloqueado', 'pin_actualizado'])


def resetear_pin(user):
    """Acción de Administrador: borra el PIN y desbloquea. El usuario tiene
    que fijar uno nuevo la próxima vez que entre a `/caja/`."""
    perfil = perfil_de(user)
    perfil.pin_hash = ''
    perfil.pin_intentos_fallidos = 0
    perfil.pin_bloqueado = False
    perfil.pin_actualizado = None
    perfil.save(update_fields=['pin_hash', 'pin_intentos_fallidos', 'pin_bloqueado', 'pin_actualizado'])


def validar_pin(user, raw_pin):
    """Compara `raw_pin` contra el hash guardado. Cuenta intentos fallidos de
    forma atómica (select_for_update evita una carrera de dos POST casi
    simultáneos) y bloquea al 5º fallo consecutivo. Devuelve True/False; NO
    levanta excepción — la vista decide qué mostrar según el estado del
    perfil (bloqueado, sin PIN, PIN incorrecto).
    """
    from .models import PerfilUsuario
    with transaction.atomic():
        perfil = PerfilUsuario.objects.select_for_update().get_or_create(user=user)[0]
        if perfil.pin_bloqueado or not perfil.pin_hash:
            return False
        if check_password(str(raw_pin), perfil.pin_hash):
            if perfil.pin_intentos_fallidos:
                perfil.pin_intentos_fallidos = 0
                perfil.save(update_fields=['pin_intentos_fallidos'])
            return True
        perfil.pin_intentos_fallidos += 1
        if perfil.pin_intentos_fallidos >= INTENTOS_MAXIMOS_PIN:
            perfil.pin_bloqueado = True
        perfil.save(update_fields=['pin_intentos_fallidos', 'pin_bloqueado'])
        return False


def marcar_desbloqueado(request):
    """Guarda en la sesión de Django que `request.user` pasó el PIN ahora
    mismo. Cada request gateada desliza el vencimiento 15 minutos más
    (ver CajaPinMiddleware) — por eso esta misma función sirve tanto para
    el desbloqueo inicial como para el refresco de actividad."""
    request.session['caja_pin_uid'] = request.user.pk
    request.session['caja_pin_hasta'] = timezone.now().timestamp() + PIN_VIGENCIA_SEGUNDOS


def pin_vigente(request):
    """True si `request.user` desbloqueó caja hace menos de 15 minutos, en
    ESTA sesión de Django (no sobrevive a un logout ni se comparte entre
    navegadores)."""
    uid = request.session.get('caja_pin_uid')
    hasta = request.session.get('caja_pin_hasta')
    if uid != request.user.pk or not hasta:
        return False
    return timezone.now().timestamp() < hasta
