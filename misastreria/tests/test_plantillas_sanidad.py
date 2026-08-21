"""Chequeos estáticos sobre el árbol de plantillas.

No renderizan nada: leen los archivos. Cubren errores que Django no reporta —
ni excepción, ni warning, ni traza en el log — y que sólo se descubren mirando
la pantalla y notando algo raro.
"""
import pathlib

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
