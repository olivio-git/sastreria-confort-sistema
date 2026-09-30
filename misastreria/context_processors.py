from .caja_turno import sesion_abierta_para_mostrar


def caja_sesion(request):
    if not request.user.is_authenticated:
        return {}
    sesion_activa, ambigua = sesion_abierta_para_mostrar()
    return {
        'caja_sesion_activa': sesion_activa,
        # 2+ cajas abiertas (no debería pasar): la topbar/base avisan en vez de
        # mostrar una como si fuera la vigente.
        'caja_abiertas_multiples': ambigua,
        # Distinto de `caja_sesion_activa`: esa dice si HAY una caja abierta
        # (cualquiera); esta dice si el usuario logueado puede cobrar en ella
        # ahora mismo (spec: sólo el dueño del turno cobra, Admin incluido).
        # Los formularios de venta/alquiler/confección la usan para avisar
        # "no tenés turno propio" y deshabilitar las líneas de pago, en vez de
        # dejar que el operador las llene y recién se entere al enviar.
        'caja_turno_propio': bool(
            sesion_activa and sesion_activa.usuario_apertura_id == request.user.id
        ),
    }
