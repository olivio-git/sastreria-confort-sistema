"""
Gestión de usuarios, rol y PIN — pantalla exclusiva de Administrador.

Va en su propio módulo (no en `views.py`, que ya pasa las 10.5k líneas). Acá
viven `lista_usuarios`, `crear_usuario`, `editar_usuario`,
`resetear_pin_usuario` y `toggle_activo_usuario`, todas detrás del permiso
`gestionar_usuarios`.

Invariante (spec User Management): nunca se puede desactivar ni degradar
(quitarle el rol Administrador) al último Administrador activo del sistema,
ni actuar sobre la propia cuenta desde acá — evita que un Administrador se
bloquee a sí mismo sin querer.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import caja_turno, roles
from .forms import CrearUsuarioForm, EditarUsuarioForm
from .models import Empleado
from .permisos import permission_required


def _es_ultimo_administrador_activo(user_obj):
    """True si `user_obj` es Administrador activo y no hay ningún OTRO
    Administrador activo en el sistema — el sistema quedaría sin nadie que
    pueda gestionar usuarios si se lo desactiva o degrada."""
    if not (user_obj.is_active and user_obj.groups.filter(name='Administrador').exists()):
        return False
    return not User.objects.filter(
        groups__name='Administrador', is_active=True
    ).exclude(pk=user_obj.pk).exists()


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
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            grupo, _ = Group.objects.get_or_create(name=form.cleaned_data['rol'])
            user.groups.add(grupo)
            empleado = form.cleaned_data.get('empleado')
            if empleado:
                empleado.user = user
                empleado.save(update_fields=['user'])
            messages.success(request, f"Usuario «{user.username}» creado con rol {form.cleaned_data['rol']}.")
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
    rol_actual = user_obj.groups.first()
    empleado_actual = getattr(user_obj, 'empleado', None)

    if request.method == 'POST':
        if user_obj.pk == request.user.pk:
            messages.error(request, "No podés cambiar tu propio rol desde acá.")
            return redirect('lista_usuarios')

        form = EditarUsuarioForm(request.POST, user_obj=user_obj)
        if form.is_valid():
            nuevo_rol = form.cleaned_data['rol']
            if nuevo_rol != 'Administrador' and _es_ultimo_administrador_activo(user_obj):
                form.add_error(None, "No podés quitarle el rol de Administrador al último Administrador activo.")
            else:
                user_obj.groups.clear()
                grupo, _ = Group.objects.get_or_create(name=nuevo_rol)
                user_obj.groups.add(grupo)

                Empleado.objects.filter(user=user_obj).update(user=None)
                empleado = form.cleaned_data.get('empleado')
                if empleado:
                    empleado.user = user_obj
                    empleado.save(update_fields=['user'])

                messages.success(request, f"Usuario «{user_obj.username}» actualizado.")
                return redirect('lista_usuarios')
    else:
        form = EditarUsuarioForm(user_obj=user_obj, initial={
            'rol': rol_actual.name if rol_actual else '',
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

    if user_obj.is_active and _es_ultimo_administrador_activo(user_obj):
        messages.error(request, "No podés desactivar al último Administrador activo.")
        return redirect('lista_usuarios')

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=['is_active'])
    estado = 'activado' if user_obj.is_active else 'desactivado'
    messages.success(request, f"Usuario «{user_obj.username}» {estado}.")
    return redirect('lista_usuarios')
