"""
Los permisos adicionales por usuario (`user_permissions`, ver
`roles.PERMISOS_EXTRA_OTORGABLES`) cuelgan de un rol base: un usuario sin
ningún rol no debe conservar extras. Cuando se le quita su último rol (desde
la pantalla de usuarios, el admin de Django o el shell) se limpian, en la
misma transacción de la quita, los extras otorgables. Los permisos que no
son otorgables (p. ej. `gestionar_usuarios` puesto a mano) no se tocan.
"""
from django.contrib.auth.models import Group, User
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from . import roles


def limpiar_extras_si_sin_rol(user):
    if user.groups.filter(name__in=roles.ROLES.keys()).exists():
        return
    perms = user.user_permissions.filter(
        content_type__app_label='misastreria',
        codename__in=roles.CODENAMES_OTORGABLES,
    )
    if perms.exists():
        user.user_permissions.remove(*perms)


@receiver(m2m_changed, sender=User.groups.through)
def grupos_de_usuario_cambiaron(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ('post_remove', 'post_clear'):
        return
    if not reverse:
        limpiar_extras_si_sin_rol(instance)
    elif action == 'post_remove' and isinstance(instance, Group):
        for user in User.objects.filter(pk__in=pk_set or ()):
            limpiar_extras_si_sin_rol(user)
