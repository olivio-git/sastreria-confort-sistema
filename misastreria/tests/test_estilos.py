"""Chequeos estáticos sobre main.css.

Cubren parches a bugs del framework: cosas que funcionan hoy sólo porque
main.css las corrige, y que se romperían en silencio si alguien borra el
parche por creerlo redundante.
"""
import pathlib
import re

from django.test import TestCase

MAIN_CSS = (
    pathlib.Path(__file__).resolve().parent.parent
    / 'static' / 'css' / 'main.css'
)

# Las variantes de alerta que el sistema usa (mensajes de Django y avisos del
# diseñador de etiquetas).
VARIANTES = ('primary', 'secondary', 'success', 'info', 'warning', 'danger')


class ParcheAlertasTablerTests(TestCase):
    """Tabler 1.0.0-beta20 deja toda alerta sin fondo.

    Al final de su hoja redeclara `.alert` con
    `--tblr-alert-bg: var(--tblr-surface)`, y ese token no existe: el suyo se
    llama `--tblr-bg-surface`. Una `var()` sin definir invalida la propiedad
    entera, `background-color` cae a su valor inicial —transparent— y las
    alertas quedan como texto flotando sobre la página.

    Como esa regla va DESPUÉS de todas las `.alert-*`, gana por orden de
    archivo aunque tenga la misma especificidad. El parche vive en main.css,
    que carga después de Tabler.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = MAIN_CSS.read_text()

    def test_define_el_token_que_tabler_referencia_y_nunca_declara(self):
        self.assertRegex(
            self.css, r'--tblr-surface\s*:',
            'main.css tiene que definir --tblr-surface: sin él, Tabler deja '
            '--tblr-alert-bg inválida y TODAS las alertas salen transparentes.'
        )

    def test_cada_variante_de_alerta_fija_fondo_y_color(self):
        """Fondo y color siempre juntos — es la convención del proyecto.

        Un fondo sin color (o al revés) es cómo se llega a texto ilegible
        cuando cambia el tema.
        """
        faltan = []
        for variante in VARIANTES:
            bloque = re.findall(
                r'\.alert-' + variante + r'\s*\{([^}]*)\}', self.css
            )
            junto = ' '.join(bloque)
            if 'background-color' not in junto:
                faltan.append(f'.alert-{variante}: sin background-color')
            if '--tblr-alert-color' not in junto:
                faltan.append(f'.alert-{variante}: sin --tblr-alert-color')
        self.assertEqual(faltan, [], '\n  ' + '\n  '.join(faltan))
