"""
Los permisos adicionales por usuario (`user_permissions`, ver
`roles.PERMISOS_EXTRA_OTORGABLES`) cuelgan de un rol base: un usuario sin
ningún rol no debe conservar extras. Cuando se le quita su último rol (desde
la pantalla de usuarios, el admin de Django o el shell) se limpian, en la
misma transacción de la quita, los extras otorgables. Los permisos que no
son otorgables (p. ej. `gestionar_usuarios` puesto a mano) no se tocan.

La evaluación se difiere a `transaction.on_commit` y mira los grupos ACTUALES:
`user.groups.set([...])` (lo que usa el admin de Django) quita primero y
agrega después, y evaluar en el `post_remove` vería un estado sin rol que en
realidad es transitorio (verify ronda 6, S1). `set()` corre en un `atomic`,
así que el chequeo ocurre recién cuando terminó de agregar. También cubre
`Group.user_set.clear()` (el `post_clear` inverso no trae pk_set: se capturan
los usuarios en `pre_clear`) y `Group.delete()` (que borra las filas de la
tabla intermedia sin emitir m2m_changed).
"""
import logging

from django.contrib.auth.models import Group, User
from django.db import transaction
from django.db.models.signals import m2m_changed, pre_delete
from django.dispatch import receiver

from . import roles

logger = logging.getLogger(__name__)


def limpiar_extras_si_sin_rol(user):
    if user.groups.filter(name__in=roles.ROLES.keys()).exists():
        return
    perms = user.user_permissions.filter(
        content_type__app_label='misastreria',
        codename__in=roles.CODENAMES_OTORGABLES,
    )
    if perms.exists():
        user.user_permissions.remove(*perms)


def _limpiar_al_confirmar(user_pks):
    pks = [pk for pk in user_pks if pk is not None]
    if not pks:
        return

    def _correr():
        # Corre DESPUÉS del commit: un error acá no puede revertir nada ni
        # tumbar la respuesta, y un usuario que falle no debe impedir que se
        # limpie a los demás.
        for user in User.objects.filter(pk__in=pks):
            try:
                limpiar_extras_si_sin_rol(user)
            except Exception:
                logger.exception('No se pudieron limpiar los extras del usuario %s', user.pk)

    transaction.on_commit(_correr, robust=True)


@receiver(m2m_changed, sender=User.groups.through)
def grupos_de_usuario_cambiaron(sender, instance, action, reverse, pk_set, **kwargs):
    if reverse and action == 'pre_clear' and isinstance(instance, Group):
        # El post_clear inverso no informa a quién se le quitó el grupo.
        instance._usuarios_antes_de_clear = list(instance.user_set.values_list('pk', flat=True))
        return
    if action not in ('post_remove', 'post_clear'):
        return
    if not reverse:
        _limpiar_al_confirmar([instance.pk])
    elif action == 'post_remove':
        _limpiar_al_confirmar(pk_set or ())
    else:
        _limpiar_al_confirmar(getattr(instance, '_usuarios_antes_de_clear', ()))


@receiver(pre_delete, sender=Group)
def grupo_por_borrarse(sender, instance, **kwargs):
    _limpiar_al_confirmar(list(instance.user_set.values_list('pk', flat=True)))
