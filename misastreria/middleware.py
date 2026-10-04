from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import CajaSesion
from . import caja_turno

# Vistas cuyo POST requiere una sesión de caja abierta.
_PROTECTED = {
    'crear_reparacion', 'editar_reparacion', 'eliminar_reparacion',
    'crear_venta', 'editar_venta', 'eliminar_venta',
    'crear_confeccion', 'editar_confeccion', 'eliminar_confeccion', 'entregar_confeccion',
    'crear_alquiler', 'editar_alquiler', 'eliminar_alquiler', 'devolver_alquiler',
    'crear_transaccion', 'editar_transaccion', 'eliminar_transaccion',
    'crear_movimiento_caja', 'revertir_movimiento_caja',
}


class CajaAbiertaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method == 'POST'
            and getattr(request, 'resolver_match', None)
            and request.resolver_match.url_name in _PROTECTED
            and not CajaSesion.objects.filter(estado='abierta').exists()
        ):
            messages.error(
                request,
                'No hay ninguna caja abierta. Abrí una sesión de caja antes de registrar operaciones.',
            )
            return redirect(reverse('lista_sesiones_caja'))

        return self.get_response(request)


# Vistas del propio gate: NUNCA se gatean a sí mismas (si no, nadie podría
# nunca llegar a la pantalla de desbloqueo).
_PIN_EXENTAS = {'desbloquear_caja', 'configurar_pin_caja', 'bloquear_caja'}


def _urls_gateadas_por_pin():
    """Nombres de URL cuyo patrón empieza con 'caja/', calculado desde
    misastreria.urls.urlpatterns — así una vista nueva bajo /caja/ queda
    protegida por el gate de PIN sin tener que acordarse de sumarla a mano.
    """
    from . import urls as _urls_module
    nombres = set()
    for pattern in _urls_module.urlpatterns:
        if not getattr(pattern, 'name', None):
            continue
        if str(pattern.pattern).startswith('caja/'):
            nombres.add(pattern.name)
    return nombres - _PIN_EXENTAS


class CajaPinMiddleware:
    """Exige un PIN de 4-6 dígitos, independiente de la sesión de Django,
    antes de dejar pasar a cualquier vista de `/caja/*` (PC compartida del
    mostrador — spec Caja PIN Unlock).

    Usa `process_view`, NO `__call__`: recién en `process_view` Django ya
    resolvió `request.resolver_match` (ver el bug de `CajaAbiertaMiddleware`
    más arriba en este mismo archivo — mismo error, no lo repetimos acá).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._urls_gateadas = None

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if self._urls_gateadas is None:
            self._urls_gateadas = _urls_gateadas_por_pin()

        url_name = getattr(request.resolver_match, 'url_name', None)
        if url_name not in self._urls_gateadas:
            return None
        if not request.user.is_authenticated:
            return None  # login_required de la vista se encarga de esto

        # Si el usuario ni siquiera tiene el permiso de la vista, que la
        # vista misma devuelva su 403 — no tiene sentido pedirle un PIN para
        # algo a lo que igual no puede entrar.
        permisos = getattr(view_func, '_permisos_requeridos', None)
        if permisos is not None:
            perms, modo = permisos
            tiene = (
                request.user.has_perms(perms) if modo == 'all'
                else any(request.user.has_perm(p) for p in perms)
            )
            if not tiene:
                return None

        if caja_turno.pin_vigente(request):
            caja_turno.marcar_desbloqueado(request)  # desliza el vencimiento 15 min
            return None

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'pin_requerido': True}, status=403)

        perfil = caja_turno.perfil_de(request.user)
        if not perfil.pin_hash:
            return redirect('configurar_pin_caja')

        if request.method == 'GET':
            next_url = request.get_full_path()
        else:
            referer = request.META.get('HTTP_REFERER', '')
            if referer and url_has_allowed_host_and_scheme(
                referer, allowed_hosts={request.get_host()}
            ):
                next_url = referer
            else:
                next_url = reverse('lista_sesiones_caja')

        return redirect(f"{reverse('desbloquear_caja')}?{urlencode({'next': next_url})}")
