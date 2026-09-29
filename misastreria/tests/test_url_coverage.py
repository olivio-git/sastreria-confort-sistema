"""
Meta-test: TODA URL nombrada de misastreria/urls.py debe estar protegida por
`@permission_required`/`@any_permission_required` (marcadas con
`_permisos_requeridos` — ver `misastreria/permisos.py`) o estar en el
allowlist público explícito (`ALLOWLIST_PUBLICO`).

Esto evita que una vista nueva quede sin decorar por descuido: si alguien
agrega una vista a `urls.py` sin pasar por `.permisos`, este test falla y
nombra la URL culpable.

IMPORTANTE: `get_resolver().url_patterns` NO sirve acá porque el URLconf raíz
(`sastreria/urls.py`) sólo tiene dos entradas de nivel superior —
`admin.site.urls` e `include('misastreria.urls')` — y ninguna de las dos
tiene `name`. Un loop plano sobre `resolver.url_patterns` inspecciona CERO
patrones (confirmado: `len([p for p in get_resolver().url_patterns if
p.name])` da 0) y el test nunca puede fallar, sin importar qué tan mal
decorada esté una vista. Por eso este test importa `misastreria.urls`
directamente e inspecciona SU `urlpatterns`, la lista plana real con las
rutas nombradas (184 al momento de escribir esto).
"""
import re
from pathlib import Path

from django.test import TestCase
from django.urls import path

from misastreria import urls as misastreria_urls

# Único allowlist de URLs públicas (sin login ni permiso): la portada
# redirige a login, y login/logout son, por naturaleza, anónimas.
ALLOWLIST_PUBLICO = {'index', 'login', 'logout'}


def _nombres_sin_permiso(patrones, allowlist=ALLOWLIST_PUBLICO):
    """Devuelve los `name` de los patrones sin `_permisos_requeridos` y que
    no están en el allowlist. Extraída como función independiente para poder
    probarla también contra una lista de patrones falsa (ver
    `test_url_sin_decorar_hace_fallar_el_test`), sin necesidad de tocar el
    URLconf real del proyecto."""
    sin_cubrir = []
    for patron in patrones:
        name = getattr(patron, 'name', None)
        if name is None:
            continue  # patrones sin name (no debería haber en este proyecto)
        if name in allowlist:
            continue
        callback = patron.callback
        if not hasattr(callback, '_permisos_requeridos'):
            sin_cubrir.append(name)
    return sin_cubrir


class CoberturaDePermisosTests(TestCase):
    def test_toda_url_nombrada_tiene_permiso_o_esta_en_el_allowlist(self):
        patrones = misastreria_urls.urlpatterns

        # Sanity check del propio test: si esto inspecciona 0 patrones, es un
        # loop vacío que jamás puede fallar (exactamente el bug que este
        # archivo tenía antes de esta corrección). El número esperado se
        # calcula desde el código fuente de urls.py en vez de hardcodearse,
        # para no tener que tocar este test cada vez que se agrega una ruta.
        fuente = Path(misastreria_urls.__file__).read_text()
        # `\b` antes de "name" evita contar `pattern_name='login'` (el
        # RedirectView de `index`), que no es un `name=` de `path()`.
        esperado = len(re.findall(r"\bname='[^']+'", fuente))
        self.assertGreater(
            len(patrones), 0,
            "El test no está inspeccionando ningún patrón de URL — revisar "
            "de dónde se está tomando `urlpatterns`."
        )
        self.assertEqual(
            len(patrones), esperado,
            "La cantidad de patrones inspeccionados no coincide con las "
            "rutas nombradas en urls.py — el test podría estar mirando una "
            "lista filtrada o incompleta."
        )

        sin_cubrir = _nombres_sin_permiso(patrones)

        if sin_cubrir:
            self.fail(
                "Las siguientes URLs no tienen permission_required/"
                "any_permission_required ni están en ALLOWLIST_PUBLICO:\n"
                + "\n".join(f"  • {n}" for n in sorted(sin_cubrir))
            )

    def test_url_sin_decorar_hace_fallar_el_test(self):
        """Prueba la regla en sí misma (spec: "una vista nueva sin decorar
        hace fallar el test de cobertura, nombrando la URL culpable"): un
        patrón armado a mano, con una vista sin ningún decorador, debe
        aparecer en `_nombres_sin_permiso`."""

        def vista_de_prueba_sin_decorar(request):
            return None

        patron_falso = path(
            'ruta-de-prueba-sin-decorar/',
            vista_de_prueba_sin_decorar,
            name='vista_de_prueba_sin_decorar',
        )

        sin_cubrir = _nombres_sin_permiso([patron_falso])

        self.assertIn('vista_de_prueba_sin_decorar', sin_cubrir)
