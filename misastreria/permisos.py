"""
Decoradores de autorización a nivel de vista.

Envuelven `django.contrib.auth.decorators.permission_required` de forma que:
  1. Siempre levantan `PermissionDenied` (403 estilizado) en vez de redirigir
     a login cuando el usuario YA está autenticado pero no tiene el permiso
     — redirigir a login a un usuario logueado es confuso.
  2. Dejan una marca (`_permisos_requeridos`) en la función envuelta para que
     `test_url_coverage.py` pueda verificar automáticamente que TODA vista
     nombrada en `urls.py` está protegida (spec: cobertura total de URLs).

Reglas de armado del decorador (ver design.md):
    @login_required                          # afuera: anónimo -> login
    @permission_required('misastreria.perm') # acá: sin permiso -> 403
    @require_POST                            # si aplica
    def vista(request, ...): ...

`permission_required` exige TODOS los permisos pasados (semántica AND, igual
que `user.has_perms`). `any_permission_required` exige AL MENOS UNO (para
endpoints compartidos por varios módulos, ej. catálogos dinámicos).

`user_passes_test` ya aplica `functools.wraps(view_func)` sobre la función que
devuelve, así que la marca `_permisos_requeridos` que agregamos encima
sobrevive a un `@login_required` puesto por afuera (`wraps` copia `__dict__`).
"""
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied


def permission_required(*perms):
    def decorador(view_func):
        def chequeo(user):
            if user.has_perms(perms):
                return True
            raise PermissionDenied
        vista_envuelta = user_passes_test(chequeo)(view_func)
        vista_envuelta._permisos_requeridos = (perms, 'all')
        return vista_envuelta
    return decorador


def any_permission_required(*perms):
    def decorador(view_func):
        def chequeo(user):
            if any(user.has_perm(p) for p in perms):
                return True
            raise PermissionDenied
        vista_envuelta = user_passes_test(chequeo)(view_func)
        vista_envuelta._permisos_requeridos = (perms, 'any')
        return vista_envuelta
    return decorador
