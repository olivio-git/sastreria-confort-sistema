from .models import CajaSesion


def caja_sesion(request):
    if not request.user.is_authenticated:
        return {}
    return {
        'caja_sesion_activa': CajaSesion.objects.filter(estado='abierta').first(),
    }
