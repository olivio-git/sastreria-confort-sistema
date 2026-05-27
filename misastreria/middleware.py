from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from .models import CajaSesion

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
