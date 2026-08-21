"""Mapeo de mensajes de Django a variantes de alerta de Tabler.

Tabler pinta el fondo de una alerta con `--tblr-alert-bg`, y la clase base
`.alert` lo deja en `transparent`. El color sale de `.alert-<variante>`: si esa
clase no existe, la alerta queda SIN fondo y con el color heredado — texto casi
invisible sobre la página. No hay error, ni warning, ni nada en el log.

Por eso el partial mapea explícitamente y nunca deja pasar texto arbitrario.
"""
from django.contrib.messages import constants
from django.template.loader import render_to_string
from django.test import TestCase

# Las variantes de alerta que Tabler realmente define. Cualquier otra deja la
# alerta transparente.
VARIANTES_TABLER = {
    'primary', 'secondary', 'success', 'info', 'warning', 'danger',
    'light', 'dark', 'muted',
}


class _Mensaje:
    """Imita lo justo de django.contrib.messages.storage.base.Message."""

    def __init__(self, texto, level, extra_tags=''):
        self.message = texto
        self.level = level
        self.extra_tags = extra_tags

    @property
    def level_tag(self):
        return constants.DEFAULT_TAGS.get(self.level, '')

    @property
    def tags(self):
        return ' '.join(t for t in (self.extra_tags, self.level_tag) if t)

    def __str__(self):
        return self.message


def _variante(mensaje):
    html = render_to_string('misastreria/_partials/mensajes.html', {'messages': [mensaje]})
    clases = html.split('class="', 1)[1].split('"', 1)[0].split()
    variantes = [c[len('alert-'):] for c in clases
                 if c.startswith('alert-') and c != 'alert-dismissible']
    assert len(variantes) == 1, f'se esperaba una sola variante, salieron {variantes}'
    return variantes[0]


class MensajesTests(TestCase):

    def test_cada_nivel_cae_en_una_variante_que_tabler_define(self):
        for level in (constants.DEBUG, constants.INFO, constants.SUCCESS,
                      constants.WARNING, constants.ERROR):
            with self.subTest(level=constants.DEFAULT_TAGS.get(level)):
                variante = _variante(_Mensaje('hola', level))
                self.assertIn(variante, VARIANTES_TABLER)

    def test_los_niveles_conocidos_usan_el_color_esperado(self):
        esperado = {
            constants.SUCCESS: 'success',
            constants.INFO:    'info',
            constants.WARNING: 'warning',
            constants.ERROR:   'danger',
        }
        for level, variante in esperado.items():
            with self.subTest(level=constants.DEFAULT_TAGS.get(level)):
                self.assertEqual(_variante(_Mensaje('hola', level)), variante)

    def test_debug_no_produce_una_clase_inexistente(self):
        # `alert-debug` no existe en Tabler: la alerta salía transparente.
        self.assertEqual(_variante(_Mensaje('hola', constants.DEBUG)), 'secondary')

    def test_los_extra_tags_no_se_filtran_a_la_clase(self):
        # `tags` incluye los extra_tags ("safe success"); `level_tag` no. Meter
        # `tags` en la clase generaba `alert-safe success` y rompía el fondo.
        for extra in ('safe', 'mi-tag', 'toast persistente'):
            with self.subTest(extra=extra):
                mensaje = _Mensaje('hola', constants.SUCCESS, extra_tags=extra)
                self.assertIn(extra.split()[0], mensaje.tags)  # el extra existe
                self.assertEqual(_variante(mensaje), 'success')  # pero no llega a la clase

    def test_sin_mensajes_no_renderiza_nada(self):
        html = render_to_string('misastreria/_partials/mensajes.html', {'messages': []})
        self.assertNotIn('alert', html)
