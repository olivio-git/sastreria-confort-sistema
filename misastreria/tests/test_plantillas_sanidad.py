"""Chequeos estáticos sobre el árbol de plantillas.

No renderizan nada: leen los archivos. Cubren errores que Django no reporta —
ni excepción, ni warning, ni traza en el log — y que sólo se descubren mirando
la pantalla y notando algo raro.
"""
import pathlib
import re

from django.test import TestCase

PLANTILLAS = pathlib.Path(__file__).resolve().parent.parent / 'templates'


class ComentariosDePlantillaTests(TestCase):
    def test_ningun_comentario_corto_abarca_varias_lineas(self):
        """`{# … #}` es de UNA sola línea.

        Escrito en varias, Django no lo parsea como comentario: el texto sale
        impreso en el HTML —con los `{#` y `#}` incluidos— y queda visible en
        la pantalla del usuario. No hay error ni warning, así que se descubre
        cuando alguien lo ve en producción. Para varias líneas va
        `{% comment %} … {% endcomment %}`.
        """
        infractores = []
        for archivo in sorted(PLANTILLAS.rglob('*.html')):
            for numero, linea in enumerate(archivo.read_text().splitlines(), 1):
                if '{#' not in linea:
                    continue
                if '#}' in linea.split('{#', 1)[1]:
                    continue
                relativo = archivo.relative_to(PLANTILLAS)
                infractores.append(f'{relativo}:{numero}: {linea.strip()[:60]}')

        self.assertEqual(
            infractores, [],
            'Comentarios {# #} abiertos en varias líneas — se imprimen como '
            'texto visible. Usá {% comment %}:\n  ' + '\n  '.join(infractores)
        )


ESTATICOS_JS = pathlib.Path(__file__).resolve().parent.parent / 'static' / 'js'


def _prefijos_de_la_app():
    """Los primeros segmentos de las rutas de `misastreria.urls`.

    Se leen del urlconf y no de una lista escrita a mano para que el test no
    envejezca: una app nueva queda cubierta sin tocar este archivo.
    """
    from misastreria import urls as urls_app
    prefijos = set()
    for patron in urls_app.urlpatterns:
        primero = str(patron.pattern).split('/')[0]
        if primero and '<' not in primero:
            prefijos.add(primero)
    return prefijos


def _es_comentario(linea):
    limpia = linea.strip()
    return limpia.startswith(('//', '*', '/*', '#'))


class UrlsAbsolutasTests(TestCase):
    def test_ninguna_url_de_la_app_esta_escrita_a_mano(self):
        """Las URLs se resuelven con `{% url %}`, nunca a mano.

        Producción corre bajo `FORCE_SCRIPT_NAME = '/sistema'`, así que la ruta
        real de una vista lleva ese prefijo. Una cadena como
        `'/prendas/items/' + id + '/editar/'` escrita en un template o en un .js
        pierde el prefijo: apunta a la raíz del dominio, donde vive otro sitio.

        Lo peligroso es que en local NO se nota —no hay prefijo— y la suite
        tampoco lo ve, porque los tests corren sin él. El bug aparece sólo en
        producción y sólo cuando alguien hace clic. Por eso se chequea leyendo
        los archivos: es el único lugar donde la diferencia es visible.

        La forma correcta es que Django resuelva la URL y el JS la lea de un
        atributo: `data-accion="{% url 'editar_prenda_item' item.id %}"`.
        """
        prefijos = _prefijos_de_la_app()
        patron = re.compile(r"""['"]/(%s)(?:/|['"])""" % '|'.join(sorted(map(re.escape, prefijos))))

        archivos = list(PLANTILLAS.rglob('*.html')) + list(ESTATICOS_JS.glob('*.js'))
        infractores = []
        for archivo in sorted(archivos):
            for n, linea in enumerate(archivo.read_text(encoding='utf-8').splitlines(), 1):
                if _es_comentario(linea):
                    continue
                hallazgo = patron.search(linea)
                if hallazgo:
                    infractores.append('%s:%d: %s' % (
                        archivo.relative_to(archivo.parent.parent.parent),
                        n, linea.strip()[:90]))

        self.assertEqual(infractores, [], (
            'URL de la app escrita a mano — pierde el prefijo de '
            'FORCE_SCRIPT_NAME en producción. Usá {% url %} y pasala por un '
            'data-* al JS:\n  ' + '\n  '.join(infractores)))
