"""
Gestión de usuarios, rol y PIN — pantalla exclusiva de Administrador.

Va en su propio módulo (no en `views.py`, que ya pasa las 10.5k líneas). Acá
viven `lista_usuarios`, `crear_usuario`, `editar_usuario`,
`resetear_pin_usuario`, `toggle_activo_usuario` y `permisos_usuario`
(permisos adicionales por usuario), todas detrás del permiso
`gestionar_usuarios`.

Invariante (spec User Management): nunca se puede desactivar ni degradar
(quitarle el rol Administrador) al último Administrador activo del sistema,
ni actuar sobre la propia cuenta desde acá — evita que un Administrador se
bloquee a sí mismo sin querer.

Carreras: el chequeo "último Administrador" se hace con
`es_ultimo_administrador_activo(bloquear=True)` DENTRO del atomic de cada ruta
que desactiva o degrada (toggle, editar_usuario, baja de Empleado). Queda sin
cubrir el formulario de usuario del admin de Django (sólo superusuario/staff,
ninguna vista de la app lo usa): allí no hay guard de último Administrador.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission, User
from django.core.paginator import Paginator
from django.db import OperationalError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import caja_turno, roles
from .forms import CrearUsuarioForm, EditarUsuarioForm
from .models import BajaNoPermitida, Empleado, es_ultimo_administrador_activo
from .permisos import permission_required


_es_ultimo_administrador_activo = es_ultimo_administrador_activo

# Deadlock (1213) o lock wait timeout (1205) de MariaDB: otra operación tenía
# tomadas las mismas filas. La transacción se revirtió; no se guardó nada.
MENSAJE_REINTENTAR = (
    "No se pudo completar porque otra operación estaba modificando los mismos "
    "datos. Intenta de nuevo."
)


class _RolRechazado(Exception):
    """Corta el atomic de `editar_usuario` sin escribir nada (el error ya
    quedó en el formulario)."""


def puede_recibir_extras(user_obj):
    """Los extras cuelgan de un rol: sólo usuarios con al menos un rol del
    sistema y nunca superusuarios (que ya tienen todo)."""
    if user_obj.is_superuser:
        return False
    return user_obj.groups.filter(name__in=roles.ROLES.keys()).exists()


def _codenames_del_rol(user_obj):
    """Permisos de la app que el usuario recibe por sus grupos (roles)."""
    return set(
        Permission.objects.filter(
            group__user=user_obj, content_type__app_label='misastreria'
        ).values_list('codename', flat=True)
    )


def _extras_otorgados(user_obj):
    """Permisos otorgables que el usuario tiene como extra (fuera de su rol)."""
    return set(
        user_obj.user_permissions.filter(
            content_type__app_label='misastreria',
            codename__in=roles.CODENAMES_OTORGABLES,
        ).values_list('codename', flat=True)
    )


def _etiquetas_extras(codenames):
    return [roles.ETIQUETAS_OTORGABLES[c] for c in sorted(codenames)]


@login_required
@permission_required('misastreria.gestionar_usuarios')
def lista_usuarios(request):
    q = request.GET.get('q', '').strip()
    rol = request.GET.get('rol', '').strip()
    estado = request.GET.get('estado', '').strip()

    qs = User.objects.select_related('empleado', 'perfil').prefetch_related('groups').order_by('username')
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(empleado__nombres__icontains=q))
    if rol:
        qs = qs.filter(groups__name=rol)
    if estado == '1':
        qs = qs.filter(is_active=True)
    elif estado == '0':
        qs = qs.filter(is_active=False)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Resumen de permisos efectivos: por cada usuario, los extras (fuera de
    # su rol) que tiene otorgados.
    for usr in page_obj:
        usr.extras_etiquetas = _etiquetas_extras(_extras_otorgados(usr))
        usr.puede_recibir_extras = puede_recibir_extras(usr)

    return render(request, 'misastreria/usuarios/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'rol': rol,
        'estado': estado,
        'roles_choices': list(roles.ROLES.keys()),
    })


@login_required
@permission_required('misastreria.gestionar_usuarios')
def crear_usuario(request):
    if request.method == 'POST':
        form = CrearUsuarioForm(request.POST)
        if form.is_valid():
            # Atómico (WARNING 7): crear el User, sumarle sus grupos y
            # vincularlo a un Empleado son tres escrituras relacionadas — si
            # una fallara a mitad de camino no debe quedar un usuario sin
            # rol o un Empleado a medio vincular.
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=form.cleaned_data['username'],
                        password=form.cleaned_data['password'],
                    )
                    for nombre_rol in form.cleaned_data['roles']:
                        grupo, _ = Group.objects.get_or_create(name=nombre_rol)
                        user.groups.add(grupo)
                    empleado = form.cleaned_data.get('empleado')
                    if empleado:
                        empleado.user = user
                        empleado.save(update_fields=['user'])
                        # SUGGESTION 2: si el Empleado elegido ya está de baja,
                        # el usuario vinculado nace desactivado — vincular no
                        # debe "resucitar" el acceso de alguien que ya no trabaja
                        # acá.
                        if empleado.fecha_baja and user.is_active:
                            user.is_active = False
                            user.save(update_fields=['is_active'])
            except BajaNoPermitida as exc:
                form.add_error('empleado', str(exc))
                return render(request, 'misastreria/usuarios/form.html', {'form': form, 'modo': 'crear'})
            roles_txt = ', '.join(form.cleaned_data['roles'])
            messages.success(request, f"Usuario «{user.username}» creado con rol(es) {roles_txt}.")
            return redirect('lista_usuarios')
    else:
        form = CrearUsuarioForm()

    return render(request, 'misastreria/usuarios/form.html', {
        'form': form,
        'modo': 'crear',
    })


@login_required
@permission_required('misastreria.gestionar_usuarios')
def editar_usuario(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    roles_actuales = list(
        user_obj.groups.filter(name__in=roles.ROLES.keys()).values_list('name', flat=True)
    )
    empleado_actual = getattr(user_obj, 'empleado', None)

    if request.method == 'POST':
        if user_obj.pk == request.user.pk:
            messages.error(request, "No podés cambiar tus propios roles desde acá.")
            return redirect('lista_usuarios')

        form = EditarUsuarioForm(request.POST, user_obj=user_obj)
        if form.is_valid():
            nuevos_roles = set(form.cleaned_data['roles'])
            # Atómico (WARNING 7): reasignar roles + relink de Empleado son
            # varias escrituras relacionadas. El chequeo "último Administrador"
            # va DENTRO, con el lock de los Administradores activos, y relee
            # actividad Y membresía al grupo: una desactivación o degradación
            # concurrente ya no se le escapa (verify ronda 7, W2).
            try:
                with transaction.atomic():
                    if 'Administrador' not in nuevos_roles and _es_ultimo_administrador_activo(user_obj, bloquear=True):
                        form.add_error(None, "No podés quitarle el rol de Administrador al último Administrador activo.")
                        raise _RolRechazado()
                    # Sólo se tocan los grupos que SON roles del sistema
                    # (WARNING 5: antes `.groups.clear()` borraba TODOS los
                    # grupos del usuario, incluyendo cualquiera ajeno a
                    # `roles.ROLES` que pudiera tener por otro motivo).
                    # Se aplica la DIFERENCIA (no "quitar todos y volver a
                    # agregar") para no pasar por un estado sin rol, que
                    # limpiaría los permisos adicionales del usuario.
                    # Primero se agrega y después se quita, por lo mismo.
                    quitar = list(Group.objects.filter(name__in=roles.ROLES.keys()).exclude(name__in=nuevos_roles))
                    for nombre_rol in nuevos_roles:
                        grupo, _ = Group.objects.get_or_create(name=nombre_rol)
                        user_obj.groups.add(grupo)
                    if quitar:
                        user_obj.groups.remove(*quitar)

                    Empleado.objects.filter(user=user_obj).update(user=None)
                    empleado = form.cleaned_data.get('empleado')
                    if empleado:
                        empleado.user = user_obj
                        empleado.save(update_fields=['user'])
                        if empleado.fecha_baja and user_obj.is_active:
                            user_obj.is_active = False
                            user_obj.save(update_fields=['is_active'])
            except _RolRechazado:
                pass
            except BajaNoPermitida as exc:
                form.add_error('empleado', str(exc))
                return render(request, 'misastreria/usuarios/form.html', {'form': form, 'modo': 'editar', 'usuario_obj': user_obj})
            except OperationalError:
                messages.error(request, MENSAJE_REINTENTAR)
                return redirect('lista_usuarios')
            else:
                messages.success(request, f"Usuario «{user_obj.username}» actualizado.")
                return redirect('lista_usuarios')
    else:
        form = EditarUsuarioForm(user_obj=user_obj, initial={
            'roles': roles_actuales,
            'empleado': empleado_actual.pk if empleado_actual else None,
        })

    return render(request, 'misastreria/usuarios/form.html', {
        'form': form,
        'modo': 'editar',
        'usuario_obj': user_obj,
    })


@login_required
@permission_required('misastreria.gestionar_usuarios')
@require_POST
def resetear_pin_usuario(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.pk == request.user.pk:
        # WARNING 2 del reporte de verificación: `/usuarios/` no está detrás
        # del gate de PIN (sólo `/caja/` lo está), así que sin este chequeo
        # un Administrador con el PIN bloqueado podía resetear el suyo
        # propio acá y volver a fijarlo con la contraseña de su cuenta —
        # saltándose por completo el bloqueo de 5 intentos. Mismo criterio
        # que `editar_usuario`/`toggle_activo_usuario`: nunca actuar sobre
        # la propia cuenta desde esta pantalla; tiene que resetearlo OTRO
        # Administrador (o el management command `resetear_pin` con acceso
        # al servidor, para el caso de un solo Administrador).
        messages.error(request, "No podés resetear tu propio PIN. Pedile a otro Administrador que lo haga.")
        return redirect('lista_usuarios')
    caja_turno.resetear_pin(user_obj)
    messages.success(request, f"PIN de «{user_obj.username}» reseteado. Deberá fijar uno nuevo en su próximo acceso a caja.")
    return redirect('lista_usuarios')


@login_required
@permission_required('misastreria.gestionar_usuarios')
@require_POST
def toggle_activo_usuario(request, pk):
    user_obj = get_object_or_404(User, pk=pk)

    if user_obj.pk == request.user.pk:
        messages.error(request, "No podés desactivarte a vos mismo.")
        return redirect('lista_usuarios')

    try:
        with transaction.atomic():
            # Lock de los Administradores activos: dos desactivaciones cruzadas no
            # pueden pasar las dos el chequeo "queda otro" (verify ronda 6, S3).
            if user_obj.is_active and _es_ultimo_administrador_activo(user_obj, bloquear=True):
                messages.error(request, "No podés desactivar al último Administrador activo.")
                return redirect('lista_usuarios')

            empleado_vinculado = getattr(user_obj, 'empleado', None)
            if not user_obj.is_active and empleado_vinculado and empleado_vinculado.fecha_baja:
                # SUGGESTION 2: si el Empleado vinculado está de baja, reactivar el
                # usuario desde acá lo dejaría con acceso sin que nadie haya dado de
                # alta al Empleado de nuevo — la baja del Empleado manda.
                messages.error(
                    request,
                    f"No se puede reactivar: el empleado vinculado «{empleado_vinculado}» está de baja.",
                )
                return redirect('lista_usuarios')

            user_obj.is_active = not user_obj.is_active
            user_obj.save(update_fields=['is_active'])
    except OperationalError:
        messages.error(request, MENSAJE_REINTENTAR)
        return redirect('lista_usuarios')
    estado = 'activado' if user_obj.is_active else 'desactivado'
    messages.success(request, f"Usuario «{user_obj.username}» {estado}.")
    return redirect('lista_usuarios')


@login_required
@permission_required('misastreria.gestionar_usuarios')
def permisos_usuario(request, pk):
    """Grilla de permisos adicionales de un usuario (módulo x acción).

    Lo heredado del rol se muestra tildado y deshabilitado; sólo se guardan
    como extra los que NO da el rol. La lista de permisos otorgables se valida
    en el servidor (`roles.CODENAMES_OTORGABLES`): `gestionar_usuarios`,
    `supervisar_caja` y cualquier permiso de otra app se rechazan aunque
    alguien arme el POST a mano. Como en roles, nadie edita los propios.
    """
    user_obj = get_object_or_404(User, pk=pk)

    if user_obj.pk == request.user.pk:
        messages.error(request, "No podés cambiar tus propios permisos desde acá.")
        return redirect('lista_usuarios')

    if not puede_recibir_extras(user_obj):
        messages.error(
            request,
            "Sólo se pueden otorgar permisos adicionales a usuarios con al menos "
            "un rol, y nunca a superusuarios.",
        )
        return redirect('lista_usuarios')

    heredados = _codenames_del_rol(user_obj)
    extras = _extras_otorgados(user_obj)

    if request.method == 'POST':
        pedidos = set(request.POST.getlist('permisos'))
        invalidos = pedidos - roles.CODENAMES_OTORGABLES
        if invalidos:
            # Se rechaza el envío COMPLETO: un POST con algo fuera de la lista
            # no es un formulario legítimo y no debe guardar ni siquiera lo
            # válido que traiga.
            messages.error(
                request,
                "Se rechazó el envío: incluye permisos que no se pueden otorgar "
                f"({', '.join(sorted(invalidos))}). No se guardó ningún cambio.",
            )
            return redirect('permisos_usuario', pk=user_obj.pk)

        deseados = pedidos - heredados
        with transaction.atomic():
            por_codename = {
                p.codename: p for p in Permission.objects.filter(
                    content_type__app_label='misastreria', codename__in=deseados | extras,
                )
            }
            quitar = [por_codename[c] for c in extras - deseados if c in por_codename]
            agregar = [por_codename[c] for c in deseados - extras if c in por_codename]
            if quitar:
                user_obj.user_permissions.remove(*quitar)
            if agregar:
                user_obj.user_permissions.add(*agregar)
        messages.success(request, f"Permisos adicionales de «{user_obj.username}» actualizados.")
        return redirect('lista_usuarios')

    modulos = []
    for modulo in roles.modulos_otorgables():
        celdas = []
        for accion in roles.ACCIONES_GRILLA:
            codename = modulo['acciones'].get(accion)
            celdas.append({
                'accion': accion,
                'codename': codename,
                'heredado': codename in heredados,
                'marcado': codename in extras,
            } if codename else None)
        otros = [{
            'codename': codename, 'etiqueta': etiqueta,
            'heredado': codename in heredados, 'marcado': codename in extras,
        } for codename, etiqueta in modulo['otros']]
        modulos.append({'nombre': modulo['nombre'], 'celdas': celdas, 'otros': otros})

    return render(request, 'misastreria/usuarios/permisos.html', {
        'usuario_obj': user_obj,
        'roles_usuario': list(user_obj.groups.filter(name__in=roles.ROLES.keys())
                              .values_list('name', flat=True)),
        'modulos': modulos,
        'acciones': roles.ACCIONES_GRILLA,
        'n_heredados': len(heredados),
        'n_extras': len(extras - heredados),
        'extras_etiquetas': _etiquetas_extras(extras - heredados),
    })
