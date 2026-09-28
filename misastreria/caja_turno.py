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
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
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


def sesion_abierta():
    """La CajaSesion con estado='abierta', o None si no hay ninguna."""
    from .models import CajaSesion
    return CajaSesion.objects.filter(estado='abierta').first()


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


def puede_supervisar(user):
    """Administrador (o quien tenga `supervisar_caja`) puede ver/forzar el
    cierre de CUALQUIER sesión, no sólo la propia."""
    return user.has_perm('misastreria.supervisar_caja')


def puede_ver_sesion(user, sesion):
    """Dueño de la sesión, o alguien con permiso de supervisión."""
    return sesion.usuario_apertura_id == user.id or puede_supervisar(user)


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
