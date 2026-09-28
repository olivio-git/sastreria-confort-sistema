"""
Meta-test: TODA URL nombrada de misastreria/urls.py debe estar protegida por
`@permission_required`/`@any_permission_required` (marcadas con
`_permisos_requeridos` — ver `misastreria/permisos.py`) o estar en el
allowlist público explícito (`ALLOWLIST_PUBLICO`).

Esto evita que una vista nueva quede sin decorar por descuido: si alguien
agrega una vista a `urls.py` sin pasar por `.permisos`, este test falla y
nombra la URL culpable.
"""
from django.test import TestCase
from django.urls import get_resolver

# Único allowlist de URLs públicas (sin login ni permiso): la portada
# redirige a login, y login/logout son, por naturaleza, anónimas.
ALLOWLIST_PUBLICO = {'index', 'login', 'logout'}


def _callback_real(callback):
    """Django views suelen envolverse en múltiples decoradores; el marcador
    `_permisos_requeridos` vive en `__dict__` (ver permisos.py), así que basta
    con mirar el callback final que Django ya resolvió — no hace falta
    desenrollar manualmente porque `functools.wraps`/`user_passes_test`
    propagan `__dict__` hacia afuera en cada capa."""
    return callback


class CoberturaDePermisosTests(TestCase):
    def test_toda_url_nombrada_tiene_permiso_o_esta_en_el_allowlist(self):
        resolver = get_resolver()
        sin_cubrir = []

        for pattern in resolver.url_patterns:
            name = getattr(pattern, 'name', None)
            if name is None:
                continue  # patrones sin name (no debería haber en este proyecto)
            if name in ALLOWLIST_PUBLICO:
                continue
            callback = _callback_real(pattern.callback)
            if not hasattr(callback, '_permisos_requeridos'):
                sin_cubrir.append(name)

        if sin_cubrir:
            self.fail(
                "Las siguientes URLs no tienen permission_required/"
                "any_permission_required ni están en ALLOWLIST_PUBLICO:\n"
                + "\n".join(f"  • {n}" for n in sorted(sin_cubrir))
            )
