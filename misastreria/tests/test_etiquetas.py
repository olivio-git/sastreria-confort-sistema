"""Tests del sistema de etiquetas: núcleo, renderers PDF/ZPL y vistas.

Lo que se cuida acá es que los DOS renderers interpreten igual la misma
plantilla. Una divergencia entre el PDF y el ZPL es el peor error posible en
este módulo, porque no se ve en pantalla: se descubre con la etiqueta ya pegada
a la prenda y la pistola que no la lee.
"""

import json
import random
import re
import shutil
import string
import subprocess
import unittest
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from misastreria import etiquetas, etiquetas_pdf, etiquetas_qr, etiquetas_zpl, simbolos
from misastreria.models import ConfiguracionImpresora, PlantillaEtiqueta
from misastreria.tests.factories import (
    make_cliente, make_prenda, make_prenda_item, make_reparacion, make_user,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unidades y normalización
# ─────────────────────────────────────────────────────────────────────────────

class UnidadesTests(TestCase):

    def test_conversion_mm_ida_y_vuelta(self):
        self.assertEqual(etiquetas.mm_a_puntos(50), 400)
        self.assertEqual(etiquetas.mm_a_puntos(30), 240)
        self.assertEqual(etiquetas.puntos_a_mm(400), 50.0)

    def test_puntos_a_pt_es_la_razon_de_resoluciones(self):
        # 203 puntos de cabezal son una pulgada, o sea 72 puntos PostScript.
        self.assertAlmostEqual(etiquetas.puntos_a_pt(203), 72.0, places=6)


class NormalizacionTests(TestCase):

    def test_descarta_tipos_desconocidos(self):
        salida = etiquetas.normalizar([{'tipo': 'ovni'}, {'tipo': 'texto', 'texto': 'ok'}])
        self.assertEqual(len(salida), 1)
        self.assertEqual(salida[0]['texto'], 'ok')

    def test_linea_es_una_primitiva_real(self):
        salida = etiquetas.normalizar([
            {'tipo': 'linea', 'orientacion': 'vertical', 'largo': 100, 'grosor': 3},
        ])
        self.assertEqual(salida[0]['tipo'], 'linea')
        self.assertEqual(salida[0]['orientacion'], 'vertical')
        self.assertEqual(salida[0]['largo'], 100)

    def test_las_cajas_ignoran_rotaciones_que_los_renderers_no_soportan(self):
        salida = etiquetas.normalizar([{'tipo': 'caja', 'rotacion': 'R'}])
        self.assertEqual(salida[0]['rotacion'], 'N')

    def test_valores_basura_caen_en_el_defecto(self):
        salida = etiquetas.normalizar([{'tipo': 'texto', 'x': 'ocho', 'tamano': None}])
        self.assertEqual(salida[0]['x'], 0)
        self.assertEqual(salida[0]['tamano'], 24)

    def test_valores_fuera_de_rango_se_recortan(self):
        salida = etiquetas.normalizar([
            {'tipo': 'barcode', 'modulo': 99, 'alto_barra': -5},
        ])
        self.assertEqual(salida[0]['modulo'], 10)
        self.assertEqual(salida[0]['alto_barra'], 10)

    def test_qr_conserva_el_lado_y_aplica_un_minimo_legible(self):
        salida = etiquetas.normalizar([
            {'tipo': 'barcode', 'simbologia': 'qr', 'alto_barra': 84},
            {'tipo': 'barcode', 'simbologia': 'qr', 'alto_barra': 10},
        ])
        self.assertEqual(salida[0]['alto_barra'], 84)
        self.assertEqual(salida[1]['alto_barra'], 58)

    def test_ancho_bloque_por_defecto_usa_lo_que_queda_a_la_derecha(self):
        salida = etiquetas.normalizar([{'tipo': 'texto', 'x': 100}], ancho_etiqueta=400)
        self.assertEqual(salida[0]['ancho_bloque'], 300)

    def test_tamano_minimo_nunca_supera_al_tamano(self):
        salida = etiquetas.normalizar([
            {'tipo': 'texto', 'tamano': 12, 'tamano_min': 40},
        ])
        self.assertEqual(salida[0]['tamano_min'], 12)

    def test_los_metadatos_del_editor_sobreviven_al_guardado(self):
        # Si `nombre` o `bloqueado` se perdieran al grabar, el usuario abriría la
        # plantilla al día siguiente con todo desbloqueado y sin nombres.
        salida = etiquetas.normalizar([
            {'tipo': 'texto', 'nombre': 'Marca', 'bloqueado': True},
        ])
        self.assertEqual(salida[0]['nombre'], 'Marca')
        self.assertTrue(salida[0]['bloqueado'])

    def test_el_nombre_de_capa_se_recorta(self):
        salida = etiquetas.normalizar([{'tipo': 'texto', 'nombre': 'x' * 200}])
        self.assertEqual(len(salida[0]['nombre']), 60)

    def test_por_defecto_un_elemento_es_visible(self):
        salida = etiquetas.normalizar([{'tipo': 'texto', 'texto': 'x'}])
        self.assertTrue(salida[0]['visible'])

    def test_las_capas_apagadas_no_llegan_a_los_renderers(self):
        elementos = [{'tipo': 'texto', 'texto': 'sale', 'visible': True},
                     {'tipo': 'texto', 'texto': 'no sale', 'visible': False}]
        self.assertEqual(len(etiquetas.normalizar(elementos)), 1)

    def test_el_editor_sí_recibe_las_capas_apagadas(self):
        # El editor las necesita para poder volver a encenderlas.
        elementos = [{'tipo': 'texto', 'texto': 'a', 'visible': False}]
        self.assertEqual(len(etiquetas.normalizar(elementos, solo_visibles=False)), 1)


class SustitucionTests(TestCase):

    def test_reemplaza_campos_conocidos(self):
        texto = etiquetas.sustituir('{prenda} — {codigo}', {'prenda': 'Saco', 'codigo': 'A1'})
        self.assertEqual(texto, 'Saco — A1')

    def test_campo_desconocido_queda_tal_cual(self):
        self.assertEqual(etiquetas.sustituir('{nada}', {'prenda': 'x'}), '{nada}')

    def test_llave_suelta_no_revienta(self):
        # str.format explotaría acá; la sustitución a mano no.
        self.assertEqual(etiquetas.sustituir('50% {oferta', {}), '50% {oferta')


class ValidacionCode128Tests(TestCase):

    def test_rechaza_vacio(self):
        with self.assertRaises(etiquetas.DatoNoImprimible):
            etiquetas.validar_code128('')

    def test_rechaza_caracteres_fuera_de_ascii(self):
        with self.assertRaises(etiquetas.DatoNoImprimible) as caso:
            etiquetas.validar_code128('PRN-Ñ01')
        self.assertIn('Ñ', str(caso.exception))

    def test_rechaza_codigo_mas_ancho_que_la_etiqueta(self):
        with self.assertRaises(etiquetas.DatoNoImprimible):
            etiquetas.validar_code128('X' * 60, ancho_etiqueta=400)

    def test_acepta_un_codigo_de_item_real(self):
        self.assertEqual(
            etiquetas.validar_code128('PRN-001-ITM-01', 400), 'PRN-001-ITM-01'
        )

    def test_el_qr_no_pasa_por_code128(self):
        # El QR admite UTF-8, así que una ñ no debe rechazar la plantilla.
        elementos = [{'tipo': 'barcode', 'simbologia': 'qr', 'texto': '{codigo}'}]
        etiquetas.validar_elementos(elementos, {'codigo': 'Ñandú'}, 400)

    def test_rechaza_qr_cuya_matriz_no_cabe_en_el_lado(self):
        elementos = [{
            'tipo': 'barcode', 'simbologia': 'qr',
            'texto': 'X' * 500, 'alto_barra': 58,
        }]
        with self.assertRaises(etiquetas.DatoNoImprimible):
            etiquetas.validar_elementos(elementos, {}, 400)

    def test_rechaza_contenido_que_supera_la_capacidad_del_qr(self):
        elementos = [{
            'tipo': 'barcode', 'simbologia': 'qr',
            'texto': 'X' * 10000, 'alto_barra': 800,
        }]
        with self.assertRaises(etiquetas.DatoNoImprimible):
            etiquetas.validar_elementos(elementos, {}, 400)


class AnchoCode128Tests(TestCase):
    """El ancho que calcula el servidor y el que dibuja el editor.

    Que estos dos números se separen es el bug más caro del módulo, porque no
    se ve: el usuario acomoda el diseño contra un ancho que en el papel no
    existe y sólo se entera con la etiqueta impresa. Ya pasó una vez —el
    servidor pasó a la codificación mínima y el JS quedó contando un símbolo por
    carácter—, y los códigos de este sistema son de puros dígitos, que es
    justo el caso donde la diferencia es máxima.
    """

    def test_los_digitos_se_codifican_de_a_pares(self):
        # Subset C: «000101» son 3 símbolos, no 6. Ese es el corazón del asunto.
        self.assertEqual(etiquetas.simbolos_code128('000101'), 3)
        self.assertEqual(etiquetas.modulos_code128('000101'), 35 + 11 * 3)
        # 136 puntos a 203 ppp son 17 mm: la medida real de la etiqueta impresa.
        self.assertEqual(etiquetas.ancho_code128('000101', 2), 136)

    def test_un_digito_suelto_no_gana_nada_con_el_subset_c(self):
        self.assertEqual(etiquetas.simbolos_code128('1'), 1)
        self.assertEqual(etiquetas.simbolos_code128('123'), 3)

    def test_texto_sin_digitos_cuesta_un_simbolo_por_caracter(self):
        self.assertEqual(etiquetas.simbolos_code128('ABC'), 3)

    def test_cambiar_de_subset_cuesta_y_a_veces_no_conviene(self):
        # 14 caracteres: el tramo de dígitos paga el símbolo de cambio y aun así
        # sale más barato que codificarlo entero en B.
        self.assertEqual(etiquetas.simbolos_code128('PRN-010-ITM-01'),
                         len('PRN-010-ITM-01'))

    def test_el_vacio_no_ocupa_modulos(self):
        self.assertEqual(etiquetas.modulos_code128(''), 0)


class ParidadEditorServidorTests(SimpleTestCase):
    """El editor dibuja en JS lo que el servidor imprime en Python.

    `etiquetas.js` mantiene una copia de `simbolos_code128` porque el lienzo se
    repinta en cada arrastre y no puede ir al servidor por cada cuadro. Una
    copia sin test se desincroniza sola: este test extrae la función del archivo
    REAL y la corre contra la de Python, así que el día que una de las dos
    cambie sin la otra, falla acá y no en el rollo del sastre.
    """

    JS = Path(__file__).resolve().parent.parent / 'static' / 'js' / 'etiquetas.js'

    @staticmethod
    def _funcion_js():
        """El cuerpo de `simbolosCode128` tal como está en el archivo servido."""
        fuente = ParidadEditorServidorTests.JS.read_text(encoding='utf-8')
        inicio = fuente.index('function simbolosCode128(dato) {')
        fin = fuente.index('\n  }\n', inicio) + len('\n  }')
        return fuente[inicio:fin]

    def test_la_copia_en_js_sigue_existiendo(self):
        # Si alguien la borra o la renombra, el resto del test pasaría a ser un
        # skip silencioso y volveríamos a estar ciegos.
        self.assertIn('costeC', self._funcion_js())

    @unittest.skipUnless(shutil.which('node'), 'node no está instalado')
    def test_js_y_python_cuentan_los_mismos_simbolos(self):
        alfabeto = string.digits * 3 + string.ascii_uppercase + '-. '
        azar = random.Random(7)
        casos = [
            '000101', '001001', '1', '12', '123', '1234', 'PRN-010-ITM-01',
            'ABC123456789', 'A1B2C3', '999999999999', 'X', '12A34', '0' * 40,
        ] + [
            ''.join(azar.choice(alfabeto) for _ in range(azar.randint(1, 24)))
            for _ in range(500)
        ]

        programa = (
            self._funcion_js()
            + "\nfor (const l of require('fs').readFileSync(0,'utf8').split('\\n'))"
            + "\n  if (l) console.log(simbolosCode128(l));\n"
        )
        salida = subprocess.run(
            ['node', '-e', programa],
            input='\n'.join(casos), capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(salida.returncode, 0, salida.stderr)

        en_js = [int(n) for n in salida.stdout.split()]
        en_python = [etiquetas.simbolos_code128(c) for c in casos]
        self.assertEqual(len(en_js), len(casos))

        discrepancias = [
            (dato, js, py)
            for dato, js, py in zip(casos, en_js, en_python) if js != py
        ]
        self.assertEqual(discrepancias, [], (
            'El editor y el servidor calculan anchos distintos para el mismo '
            'código: el diseño en pantalla no es el que sale impreso.'
        ))


class EscaladoTests(TestCase):

    def test_escala_medidas_y_respeta_lo_que_no_es_medida(self):
        original = [{'tipo': 'texto', 'x': 10, 'y': 20, 'tamano': 24,
                     'texto': '{prenda}', 'alineacion': 'centro'}]
        escalado = etiquetas.escalar(original, 2.0)
        self.assertEqual(escalado[0]['x'], 20)
        self.assertEqual(escalado[0]['tamano'], 48)
        self.assertEqual(escalado[0]['texto'], '{prenda}')
        self.assertEqual(escalado[0]['alineacion'], 'centro')

    def test_el_modulo_del_codigo_no_se_sale_de_rango(self):
        escalado = etiquetas.escalar([{'tipo': 'barcode', 'modulo': 3}], 10.0)
        self.assertEqual(escalado[0]['modulo'], 10)

    def test_factor_invalido_devuelve_la_lista_sin_tocar(self):
        original = [{'tipo': 'texto', 'x': 10}]
        self.assertEqual(etiquetas.escalar(original, 0), original)


# ─────────────────────────────────────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────────────────────────────────────

class RendererZplTests(TestCase):

    def setUp(self):
        self.elementos = etiquetas.elementos_por_defecto()
        self.datos = etiquetas.datos_muestra()

    def test_estructura_minima(self):
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos)
        self.assertTrue(zpl.startswith('^XA'))
        self.assertTrue(zpl.endswith('^XZ'))
        self.assertIn('^PW400', zpl)
        self.assertIn('^LL240', zpl)

    def test_no_pisa_la_calibracion_de_la_impresora(self):
        # ^MM y ^MN descalibran el rollo: no deben salir nunca.
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos)
        self.assertNotIn('^MM', zpl)
        self.assertNotIn('^MN', zpl)

    def test_sustituye_los_campos(self):
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos)
        self.assertIn('PRN-001-ITM-01', zpl)
        self.assertNotIn('{codigo}', zpl)

    def test_quita_tildes_porque_la_fuente_no_las_dibuja(self):
        elementos = [{'tipo': 'texto', 'texto': 'REPARACIÓN'}]
        zpl = etiquetas_zpl.render(elementos, 400, 240, {})
        self.assertIn('REPARACION', zpl)
        self.assertNotIn('Ó', zpl)

    def test_neutraliza_los_caracteres_de_control_de_zpl(self):
        elementos = [{'tipo': 'texto', 'texto': 'a^b~c'}]
        zpl = etiquetas_zpl.render(elementos, 400, 240, {})
        cuerpo = zpl.split('^FD')[1].split('^FS')[0]
        self.assertEqual(cuerpo, 'a b c')

    def test_copias_se_traducen_a_pq(self):
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos, copias=7)
        self.assertIn('^PQ7', zpl)

    def test_qr_zpl_usa_la_misma_imagen_y_medida_que_pdf(self):
        zpl = etiquetas_zpl.render([
            {'tipo': 'barcode', 'simbologia': 'qr', 'texto': 'PRN-001',
             'alto_barra': 84},
        ], 400, 240, {})
        self.assertIn('^GFA,', zpl)
        self.assertNotIn('^BQ', zpl)

    def test_qr_deja_todos_los_modulos_del_mismo_ancho(self):
        """El lado tiene que ser múltiplo exacto de la matriz.

        Si no lo es, el resampleo reparte el resto de la división de forma
        despareja y quedan módulos de 2 y de 3 puntos en el mismo código, que
        es lo que hace que la pistola tenga que insistir para leerlo.
        """
        modulos = max(etiquetas_qr._matriz('PRN-001').size)
        for pedido in (84, 100, 121, 145, 200):
            lado = etiquetas_qr.imagen('PRN-001', pedido).size[0]
            self.assertEqual(lado % modulos, 0,
                             f"con {pedido} pedidos, el lado {lado} no es "
                             f"múltiplo de {modulos}")

    def test_qr_queda_cerca_del_tamano_pedido(self):
        """Cuadrar los módulos no puede costar un QR notoriamente más chico."""
        modulos = max(etiquetas_qr._matriz('PRN-001').size)
        for pedido in (84, 100, 121, 145, 200):
            lado = etiquetas_qr.imagen('PRN-001', pedido).size[0]
            self.assertLessEqual(abs(lado - pedido), modulos / 2,
                                 f"con {pedido} pedidos salió {lado}")

    def test_sin_config_no_toca_los_ajustes_de_la_impresora(self):
        """Sin config explícita se imprime como venía imprimiendo la máquina."""
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos)
        for comando in ('^MT', '^MD', '^PR'):
            self.assertNotIn(comando, zpl)

    def test_config_emite_oscuridad_velocidad_y_tipo_de_papel(self):
        config = ConfiguracionImpresora(oscuridad=12, velocidad=3, usa_ribbon=True)
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos,
                                   config=config)
        self.assertIn('^MTT', zpl)      # transferencia térmica (con cinta)
        self.assertIn('^MD12', zpl)
        self.assertIn('^PR3,3,3', zpl)

    def test_config_sin_ribbon_pide_termica_directa(self):
        config = ConfiguracionImpresora(oscuridad=0, velocidad=4, usa_ribbon=False)
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos,
                                   config=config)
        self.assertIn('^MTD', zpl)

    def test_los_ajustes_van_antes_de_los_elementos(self):
        """ZPL se interpreta en orden: si van después, la etiqueta ya se dibujó."""
        config = ConfiguracionImpresora(oscuridad=5, velocidad=2, usa_ribbon=True)
        zpl = etiquetas_zpl.render(
            [{'tipo': 'texto', 'texto': 'HOLA'}], 400, 240, {}, config=config)
        self.assertLess(zpl.index('^MD5'), zpl.index('^FDHOLA'))

    def test_sin_corrimiento_las_coordenadas_no_se_tocan(self):
        config = ConfiguracionImpresora(desplazamiento_x=0, desplazamiento_y=0)
        zpl = etiquetas_zpl.render(
            [{'tipo': 'texto', 'x': 40, 'y': 60, 'texto': 'X'}],
            400, 240, {}, config=config)
        self.assertIn('^FO40,60', zpl)

    def test_corrimiento_positivo_mueve_a_la_derecha_y_abajo(self):
        """1 mm son ~8 puntos a 203 dpi, así que 2 mm mueven unos 16."""
        config = ConfiguracionImpresora(
            desplazamiento_x=Decimal('2'), desplazamiento_y=Decimal('2'))
        self.assertEqual(config.desplazamiento_x_puntos, 16)
        zpl = etiquetas_zpl.render(
            [{'tipo': 'texto', 'x': 40, 'y': 60, 'texto': 'X'}],
            400, 240, {}, config=config)
        self.assertIn('^FO56,76', zpl)

    def test_corrimiento_negativo_mueve_a_la_izquierda_y_arriba(self):
        config = ConfiguracionImpresora(
            desplazamiento_x=Decimal('-1'), desplazamiento_y=Decimal('-1'))
        zpl = etiquetas_zpl.render(
            [{'tipo': 'texto', 'x': 40, 'y': 60, 'texto': 'X'}],
            400, 240, {}, config=config)
        self.assertIn('^FO32,52', zpl)

    def test_el_corrimiento_nunca_genera_coordenadas_negativas(self):
        """^FO no admite negativos: la impresora descartaría el elemento."""
        config = ConfiguracionImpresora(
            desplazamiento_x=Decimal('-20'), desplazamiento_y=Decimal('-20'))
        zpl = etiquetas_zpl.render(
            [{'tipo': 'texto', 'x': 10, 'y': 10, 'texto': 'X'}],
            400, 240, {}, config=config)
        self.assertIn('^FO0,0', zpl)
        self.assertNotIn('^FO-', zpl)

    def test_tipo_de_papel_vacio_no_emite_mn(self):
        """El default no toca la calibración que la impresora ya tiene."""
        config = ConfiguracionImpresora(tipo_papel='')
        zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos,
                                   config=config)
        self.assertNotIn('^MN', zpl)

    def test_tipo_de_papel_se_traduce_al_comando_correcto(self):
        for tipo, esperado in (('gap', '^MNY'), ('continuo', '^MNN'),
                               ('marca', '^MNM')):
            with self.subTest(tipo=tipo):
                config = ConfiguracionImpresora(tipo_papel=tipo)
                zpl = etiquetas_zpl.render(self.elementos, 400, 240, self.datos,
                                           config=config)
                self.assertIn(esperado, zpl)

    def test_el_comando_de_calibracion_es_de_control(self):
        """Empieza con ~ y no va entre ^XA y ^XZ: se ejecuta al llegar."""
        self.assertTrue(etiquetas_zpl.ZPL_CALIBRAR.startswith('~'))
        self.assertNotIn('^XA', etiquetas_zpl.ZPL_CALIBRAR)

    def test_negrita_imprime_dos_veces_desplazado(self):
        elementos = [{'tipo': 'texto', 'x': 10, 'y': 10, 'texto': 'X', 'negrita': True}]
        zpl = etiquetas_zpl.render(elementos, 400, 240, {})
        self.assertIn('^FO10,10', zpl)
        self.assertIn('^FO11,10', zpl)

    def test_bloque_solido_usa_el_lado_menor_como_relleno(self):
        zpl = etiquetas_zpl.render([
            {'tipo': 'caja', 'x': 10, 'y': 20, 'ancho': 100, 'alto': 20,
             'relleno': True},
        ], 400, 240, {})
        self.assertIn('^GB100,20,20,B,0', zpl)

    def test_linea_vertical_se_renderiza_como_trazo_solido(self):
        zpl = etiquetas_zpl.render([
            {'tipo': 'linea', 'x': 20, 'y': 30, 'orientacion': 'vertical',
             'largo': 120, 'grosor': 3},
        ], 400, 240, {})
        self.assertIn('^FO20,30^GB3,120,3,B,0^FS', zpl)

    def test_lote_produce_una_etiqueta_por_juego_de_datos(self):
        zpl = etiquetas_zpl.render_lote(
            self.elementos, 400, 240,
            lote=[etiquetas.datos_muestra({'codigo': 'A'}),
                  etiquetas.datos_muestra({'codigo': 'B'})],
        )
        self.assertEqual(zpl.count('^XA'), 2)

    def test_enviar_sin_windows_da_un_error_explicado(self):
        # En Linux no existe win32print: tiene que fallar con un mensaje que se
        # entienda, no con un ImportError crudo en la cara del usuario.
        with self.assertRaises(etiquetas_zpl.ImpresoraNoDisponible):
            etiquetas_zpl.enviar('^XA^XZ')


class LienzoEsPapelTests(TestCase):
    """El lienzo del diseñador y el papel de la impresora son la MISMA medida.

    Hubo una versión en la que no lo eran: la plantilla guardaba un lienzo y una
    bandera que decía que ese lienzo se apoyaba girado 90° sobre el rollo. El
    editor dibujaba el lienzo derecho y la impresora sacaba el papel; el usuario
    veía una cosa y le salía otra, sin ninguna forma de anticiparlo. Estos tests
    fijan la regla que reemplazó a esa bandera: sin giros intermedios, lo que se
    diseña es lo que se imprime, y si algo tiene que salir de costado se rota
    ESE elemento y se lo ve rotado en pantalla.
    """

    ELEMENTOS = [
        {'tipo': 'texto', 'x': 12, 'y': 8, 'texto': 'FORTIUM',
         'tamano': 24, 'ancho_bloque': 300, 'renglones': 1},
        {'tipo': 'caja', 'x': 4, 'y': 4, 'ancho': 392, 'alto': 232, 'grosor': 3},
        {'tipo': 'linea', 'x': 12, 'y': 90, 'orientacion': 'horizontal',
         'largo': 300, 'grosor': 3},
        {'tipo': 'barcode', 'x': 20, 'y': 110, 'texto': '001501',
         'simbologia': 'code128', 'modulo': 2, 'alto_barra': 70},
    ]

    def test_zpl_declara_a_la_impresora_las_medidas_del_lienzo(self):
        """^PW y ^LL son el lienzo, tal cual, sin reinterpretar."""
        zpl = etiquetas_zpl.render(self.ELEMENTOS, 240, 400, datos={})
        self.assertIn('^PW240', zpl)
        self.assertIn('^LL400', zpl)

    def test_el_pdf_mide_lo_mismo_que_el_lienzo(self):
        pdf = etiquetas_pdf.render(self.ELEMENTOS, 240, 400,
                                   lote=[{}], copias=1)
        # El tamaño de página va en el PDF como MediaBox, en puntos PostScript.
        esperado = (etiquetas.puntos_a_pt(240), etiquetas.puntos_a_pt(400))
        medida = re.search(rb'/MediaBox\s*\[([^\]]+)\]', pdf)
        self.assertIsNotNone(medida, 'el PDF no declara MediaBox')
        _, _, ancho_pt, alto_pt = [float(v) for v in medida.group(1).split()]
        self.assertAlmostEqual(ancho_pt, esperado[0], places=2)
        self.assertAlmostEqual(alto_pt, esperado[1], places=2)

    def test_las_coordenadas_del_elemento_llegan_intactas_al_zpl(self):
        """Sin giro no hay remapeo: el ^FO es el (x, y) que puso el usuario."""
        zpl = etiquetas_zpl.render(
            [{'tipo': 'texto', 'x': 37, 'y': 121, 'texto': 'X'}], 240, 400,
            datos={})
        self.assertIn('^FO37,121', zpl)

    def test_un_lienzo_vertical_no_se_acuesta_sobre_el_papel(self):
        """La regresión concreta que reportó el usuario.

        Diseño vertical de 30 × 50 mm con el código de barras horizontal. Antes
        salía un papel apaisado con el código parado; ahora el rollo es vertical
        y el código sigue horizontal, que es lo que se ve en el editor.
        """
        ancho, alto = etiquetas.mm_a_puntos(30), etiquetas.mm_a_puntos(50)
        zpl = etiquetas_zpl.render(
            [{'tipo': 'barcode', 'x': 19, 'y': 160, 'texto': '001001',
              'simbologia': 'code128', 'modulo': 2, 'alto_barra': 60}],
            ancho, alto, datos={})
        self.assertIn(f'^PW{ancho}', zpl)
        self.assertIn(f'^LL{alto}', zpl)
        # ^BCN: la N es «sin rotar». Nadie tocó la rotación del elemento.
        self.assertIn('^FO19,160', zpl)
        self.assertIn('^BCN,', zpl)

    def test_la_plantilla_no_guarda_ninguna_bandera_de_giro(self):
        plantilla = PlantillaEtiqueta(nombre='X', ancho_puntos=240,
                                      alto_puntos=400)
        self.assertFalse(hasattr(plantilla, 'orientacion'))
        self.assertFalse(hasattr(plantilla, 'girada'))
        self.assertFalse(hasattr(plantilla, 'papel_puntos'))


class RendererPdfTests(TestCase):

    def setUp(self):
        self.elementos = etiquetas.elementos_por_defecto()
        self.datos = etiquetas.datos_muestra()

    def test_genera_un_pdf_valido(self):
        pdf = etiquetas_pdf.render(self.elementos, 400, 240, [self.datos])
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 1000)

    def test_una_pagina_por_etiqueta_del_lote(self):
        lote = [etiquetas.datos_muestra({'codigo': f'A{i}'}) for i in range(3)]
        pdf = etiquetas_pdf.render(self.elementos, 400, 240, lote)
        self.assertEqual(pdf.count(b'/Type /Page\n'), 3)

    def test_copias_multiplican_las_paginas(self):
        pdf = etiquetas_pdf.render(self.elementos, 400, 240, [self.datos], copias=2)
        self.assertEqual(pdf.count(b'/Type /Page\n'), 2)

    def test_lote_vacio_no_produce_un_pdf_invalido(self):
        pdf = etiquetas_pdf.render(self.elementos, 400, 240, lote=[])
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_dibuja_todas_las_simbologias_sin_reventar(self):
        for simbologia in ('code128', 'code39', 'ean13', 'qr'):
            dato = '123456789012' if simbologia == 'ean13' else 'PRN-001'
            elementos = [{'tipo': 'barcode', 'x': 10, 'y': 10, 'texto': dato,
                          'simbologia': simbologia, 'alto_barra': 60}]
            pdf = etiquetas_pdf.render(elementos, 400, 240, [{}])
            self.assertTrue(pdf.startswith(b'%PDF'), simbologia)

    def test_dibuja_todas_las_rotaciones_sin_reventar(self):
        for rotacion in etiquetas.ROTACIONES:
            elementos = [{'tipo': 'texto', 'x': 10, 'y': 10, 'texto': 'Hola',
                          'rotacion': rotacion}]
            pdf = etiquetas_pdf.render(elementos, 400, 240, [{}])
            self.assertTrue(pdf.startswith(b'%PDF'), rotacion)

    def test_simbolo_desconocido_no_rompe_la_etiqueta(self):
        elementos = [{'tipo': 'simbolo', 'clave': 'no_existe', 'tam': 40}]
        pdf = etiquetas_pdf.render(elementos, 400, 240, [{}])
        self.assertTrue(pdf.startswith(b'%PDF'))


class CoherenciaEntreRenderersTests(TestCase):
    """Lo que los dos renderers TIENEN que interpretar igual."""

    def test_ambos_aceptan_la_plantilla_de_fabrica(self):
        elementos = etiquetas.elementos_por_defecto()
        datos = etiquetas.datos_muestra()
        self.assertTrue(etiquetas_pdf.render(elementos, 400, 240, [datos]).startswith(b'%PDF'))
        self.assertTrue(etiquetas_zpl.render(elementos, 400, 240, datos).startswith('^XA'))

    def test_ambos_aceptan_el_modelo_textil_vertical(self):
        elementos = etiquetas.elementos_textil_vertical()
        datos = etiquetas.datos_muestra()
        ancho = etiquetas.mm_a_puntos(50)
        alto = etiquetas.mm_a_puntos(100)
        self.assertTrue(etiquetas_pdf.render(elementos, ancho, alto, [datos]).startswith(b'%PDF'))
        zpl = etiquetas_zpl.render(elementos, ancho, alto, datos)
        self.assertIn('^GB360,2,2,B,0', zpl)
        self.assertEqual(zpl.count('^GFA,'), 5)

    def test_el_centrado_del_codigo_cae_en_el_mismo_x(self):
        # Los dos usan `ancho_code128`, así que el x centrado debe coincidir.
        dato = 'PRN-001-ITM-01'
        modulo = 2
        esperado = (400 - etiquetas.ancho_code128(dato, modulo)) // 2

        elementos = [{'tipo': 'barcode', 'x': 0, 'y': 100, 'texto': dato,
                      'modulo': modulo, 'centrar': True}]
        zpl = etiquetas_zpl.render(elementos, 400, 240, {})
        self.assertIn(f'^FO{esperado},100', zpl)

    def test_ambos_descartan_los_mismos_elementos(self):
        elementos = [{'tipo': 'ovni'}, {'tipo': 'texto', 'texto': 'ok'}]
        zpl = etiquetas_zpl.render(elementos, 400, 240, {})
        self.assertIn('ok', zpl)
        self.assertEqual(zpl.count('^FD'), 1)

    def test_una_capa_apagada_no_se_imprime_por_ningun_camino(self):
        elementos = [{'tipo': 'texto', 'texto': 'FANTASMA', 'visible': False},
                     {'tipo': 'texto', 'texto': 'VISIBLE', 'y': 60}]
        zpl = etiquetas_zpl.render(elementos, 400, 240, {})
        self.assertNotIn('FANTASMA', zpl)
        self.assertIn('VISIBLE', zpl)
        # En el PDF no se puede leer el texto, pero sí contar los comandos de
        # dibujo: una etiqueta con la capa apagada pesa menos que con las dos.
        con_una = etiquetas_pdf.render(elementos, 400, 240, [{}])
        elementos[0]['visible'] = True
        con_dos = etiquetas_pdf.render(elementos, 400, 240, [{}])
        self.assertLess(len(con_una), len(con_dos))


class SimbolosTests(TestCase):

    def test_el_catalogo_tiene_los_cinco_grupos_de_la_norma(self):
        grupos = simbolos.catalogo_para_json()
        self.assertEqual(
            set(grupos), {'Lavado', 'Blanqueo', 'Secado', 'Planchado', 'Profesional'}
        )

    def test_cada_simbolo_se_dibuja_en_png_y_en_zpl(self):
        for clave in simbolos.CATALOGO:
            self.assertTrue(simbolos.png(clave, 32).startswith(b'\x89PNG'), clave)
            self.assertTrue(simbolos.zpl_gf(clave, 32).startswith('^GFA,'), clave)

    def test_simbolo_desconocido_avisa(self):
        with self.assertRaises(simbolos.SimboloDesconocido):
            simbolos.render('no_existe', 32)


# ─────────────────────────────────────────────────────────────────────────────
# Datos desde los modelos
# ─────────────────────────────────────────────────────────────────────────────

class DatosDesdeModelosTests(TestCase):

    def test_item_usa_el_codigo_de_la_unidad_no_el_del_sku(self):
        prenda = make_prenda(nombre='Smoking', talla='40', color='Negro')
        item = make_prenda_item(prenda=prenda)
        datos = etiquetas.datos_de_item(item)

        self.assertEqual(datos['codigo'], item.codigo_item)
        self.assertNotEqual(datos['codigo'], prenda.codigo)
        self.assertEqual(datos['prenda'], 'Smoking')
        self.assertEqual(datos['subtitulo'], 'T 40 · NEGRO')

    def test_dos_unidades_del_mismo_sku_tienen_codigos_distintos(self):
        # Es la razón de ser de la etiqueta: distinguir dos ternos idénticos.
        prenda = make_prenda(nombre='Terno')
        uno = etiquetas.datos_de_item(make_prenda_item(prenda=prenda))
        otro = etiquetas.datos_de_item(make_prenda_item(prenda=prenda))
        self.assertNotEqual(uno['codigo'], otro['codigo'])

    def test_prenda_usa_el_codigo_del_sku(self):
        prenda = make_prenda(nombre='Camisa')
        datos = etiquetas.datos_de_prenda(prenda)
        self.assertEqual(datos['codigo'], prenda.codigo)

    def test_servicio_trae_el_cliente(self):
        cliente = make_cliente(nombres='Ana', apellido_paterno='Rojas')
        reparacion = make_reparacion(cliente=cliente)
        datos = etiquetas.datos_de_servicio(reparacion, 'REPARACIÓN')
        self.assertEqual(datos['codigo'], reparacion.codigo)
        self.assertEqual(datos['cliente'], 'Ana Rojas')
        self.assertEqual(datos['servicio'], 'REPARACIÓN')


# ─────────────────────────────────────────────────────────────────────────────
# Modelo
# ─────────────────────────────────────────────────────────────────────────────

class PlantillaEtiquetaTests(TestCase):

    def test_la_migracion_dejo_una_plantilla_predeterminada(self):
        plantilla = PlantillaEtiqueta.predeterminada()
        self.assertIsNotNone(plantilla)
        self.assertTrue(plantilla.elementos)

    def test_solo_una_puede_ser_predeterminada(self):
        primera = PlantillaEtiqueta.predeterminada()
        segunda = PlantillaEtiqueta.objects.create(
            nombre='Otra', elementos=[], es_predeterminada=True
        )
        primera.refresh_from_db()
        self.assertFalse(primera.es_predeterminada)
        self.assertTrue(segunda.es_predeterminada)

    def test_predeterminada_cae_en_la_primera_si_nadie_esta_marcada(self):
        PlantillaEtiqueta.objects.update(es_predeterminada=False)
        self.assertIsNotNone(PlantillaEtiqueta.predeterminada())

    def test_medidas_en_milimetros(self):
        plantilla = PlantillaEtiqueta(ancho_puntos=400, alto_puntos=240)
        self.assertEqual(plantilla.ancho_mm, 50.0)
        self.assertEqual(plantilla.alto_mm, 30.0)


# ─────────────────────────────────────────────────────────────────────────────
# Vistas
# ─────────────────────────────────────────────────────────────────────────────

class VistasEtiquetasTests(TestCase):

    def setUp(self):
        self.usuario = make_user()
        self.client.force_login(self.usuario)
        self.plantilla = PlantillaEtiqueta.predeterminada()

    # ── Acceso ───────────────────────────────────────────────────────────────

    def test_todas_las_pantallas_piden_login(self):
        self.client.logout()
        for nombre in ('lista_plantillas', 'disenador_etiqueta', 'etiquetas_calibrar'):
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 302, nombre)

    # ── Diseñador ────────────────────────────────────────────────────────────

    def test_lista_de_plantillas(self):
        respuesta = self.client.get(reverse('lista_plantillas'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.plantilla.nombre)
        self.assertContains(respuesta, 'Lienzo vacío')
        self.assertContains(respuesta, 'Modelo textil vertical')
        self.assertContains(respuesta, 'name="orientacion"', count=2)

    def test_disenador_sin_id_redirige_a_la_predeterminada(self):
        respuesta = self.client.get(reverse('disenador_etiqueta'))
        self.assertRedirects(
            respuesta, reverse('editar_plantilla', args=[self.plantilla.pk])
        )

    def test_disenador_con_nueva_no_redirige_pero_copia_el_diseno(self):
        respuesta = self.client.get(reverse('disenador_etiqueta') + '?nueva=1')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.context['plantilla'])
        self.assertEqual(respuesta.context['elementos'], self.plantilla.elementos)
        self.assertContains(respuesta, 'class="et-lienzo-area"')
        self.assertContains(respuesta, 'Ctrl/Cmd+clic selecciona debajo')

    def test_disenador_nuevo_puede_empezar_vacio(self):
        respuesta = self.client.get(reverse('disenador_etiqueta'), {
            'nueva': '1', 'origen': 'vacia', 'tamano': '50x30',
            'orientacion': 'horizontal',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['elementos'], [])
        self.assertEqual(respuesta.context['ancho'], etiquetas.mm_a_puntos(50))
        self.assertEqual(respuesta.context['alto'], etiquetas.mm_a_puntos(30))

    def test_disenador_nuevo_respeta_tamano_y_orientacion_vertical(self):
        respuesta = self.client.get(reverse('disenador_etiqueta'), {
            'nueva': '1', 'origen': 'predeterminada', 'tamano': '80x50',
            'orientacion': 'vertical',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['ancho'], etiquetas.mm_a_puntos(50))
        self.assertEqual(respuesta.context['alto'], etiquetas.mm_a_puntos(80))
        self.assertTrue(respuesta.context['elementos'])

    def test_disenador_nuevo_copia_una_predeterminada_vacia(self):
        self.plantilla.elementos = []
        self.plantilla.save()
        respuesta = self.client.get(reverse('disenador_etiqueta'), {
            'nueva': '1', 'origen': 'predeterminada',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['elementos'], [])

    def test_disenador_nuevo_ofrece_modelo_textil_vertical(self):
        respuesta = self.client.get(reverse('disenador_etiqueta'), {
            'nueva': '1', 'origen': 'textil', 'tamano': '100x50',
            'orientacion': 'vertical',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['ancho'], etiquetas.mm_a_puntos(50))
        self.assertEqual(respuesta.context['alto'], etiquetas.mm_a_puntos(100))
        self.assertTrue(any(
            elemento['tipo'] == 'linea'
            for elemento in respuesta.context['elementos']
        ))

    def test_guardar_crea_una_plantilla(self):
        respuesta = self.client.post(
            reverse('guardar_plantilla'),
            data=json.dumps({
                'nombre': 'Etiqueta de venta',
                'elementos': [{'tipo': 'texto', 'texto': 'Hola'}],
                'ancho': 400, 'alto': 240,
            }),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['ok'])
        self.assertTrue(PlantillaEtiqueta.objects.filter(nombre='Etiqueta de venta').exists())

    def test_guardar_sin_nombre_avisa_en_vez_de_reventar(self):
        respuesta = self.client.post(
            reverse('guardar_plantilla'),
            data=json.dumps({'nombre': '  ', 'elementos': []}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()['ok'])

    def test_guardar_con_nombre_repetido_da_un_mensaje_entendible(self):
        respuesta = self.client.post(
            reverse('guardar_plantilla'),
            data=json.dumps({'nombre': self.plantilla.nombre, 'elementos': []}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Ya existe', respuesta.json()['error'])

    def test_guardar_con_elementos_que_no_son_lista_se_rechaza(self):
        respuesta = self.client.post(
            reverse('guardar_plantilla'),
            data=json.dumps({'nombre': 'X', 'elementos': 'no soy una lista'}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_json_roto_no_tumba_la_vista(self):
        respuesta = self.client.post(
            reverse('guardar_plantilla'), data='{roto', content_type='application/json'
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_guardar_conserva_los_metadatos_de_capa(self):
        respuesta = self.client.post(
            reverse('guardar_plantilla'),
            data=json.dumps({
                'nombre': 'Con capas',
                'elementos': [{'tipo': 'texto', 'texto': 'A', 'nombre': 'Marca',
                               'bloqueado': True, 'visible': False}],
            }),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 200)
        guardada = PlantillaEtiqueta.objects.get(nombre='Con capas')
        self.assertEqual(guardada.elementos[0]['nombre'], 'Marca')
        self.assertTrue(guardada.elementos[0]['bloqueado'])
        self.assertFalse(guardada.elementos[0]['visible'])

    def test_guardar_sin_descripcion_no_borra_la_que_habia(self):
        self.plantilla.descripcion = 'Diseño original'
        self.plantilla.save()
        self.client.post(
            reverse('actualizar_plantilla', args=[self.plantilla.pk]),
            data=json.dumps({'nombre': self.plantilla.nombre, 'elementos': []}),
            content_type='application/json',
        )
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.descripcion, 'Diseño original')

    def test_guardar_con_descripcion_la_actualiza(self):
        self.client.post(
            reverse('actualizar_plantilla', args=[self.plantilla.pk]),
            data=json.dumps({'nombre': self.plantilla.nombre, 'elementos': [],
                             'descripcion': 'Nueva'}),
            content_type='application/json',
        )
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.descripcion, 'Nueva')

    def test_actualizar_no_choca_consigo_misma(self):
        respuesta = self.client.post(
            reverse('actualizar_plantilla', args=[self.plantilla.pk]),
            data=json.dumps({
                'nombre': self.plantilla.nombre,
                'elementos': [{'tipo': 'texto', 'texto': 'Nuevo'}],
            }),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.plantilla.refresh_from_db()
        self.assertEqual(len(self.plantilla.elementos), 1)

    # ── Salidas ──────────────────────────────────────────────────────────────

    def test_previsualizar_devuelve_un_pdf(self):
        respuesta = self.client.post(
            reverse('previsualizar_etiqueta'),
            data=json.dumps({'elementos': self.plantilla.elementos,
                             'ancho': 400, 'alto': 240}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_previsualizar_rechaza_un_qr_que_no_cabe(self):
        respuesta = self.client.post(
            reverse('previsualizar_etiqueta'),
            data=json.dumps({
                'elementos': [{
                    'tipo': 'barcode', 'simbologia': 'qr',
                    'texto': 'X' * 500, 'alto_barra': 58,
                }],
                'ancho': 400, 'alto': 240,
            }),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertContains(respuesta, 'necesita al menos', status_code=400)

    def test_ver_zpl_devuelve_el_texto(self):
        respuesta = self.client.post(
            reverse('zpl_etiqueta'),
            data=json.dumps({'elementos': self.plantilla.elementos}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['zpl'].startswith('^XA'))

    def test_descargar_zpl_viene_como_adjunto(self):
        respuesta = self.client.post(
            reverse('descargar_zpl_etiqueta'),
            data=json.dumps({'elementos': self.plantilla.elementos}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('attachment', respuesta['Content-Disposition'])
        self.assertIn('.zpl', respuesta['Content-Disposition'])

    def test_imprimir_en_linux_avisa_que_no_puede(self):
        # El hosting no tiene la impresora: 503 con explicación, no 500.
        respuesta = self.client.post(
            reverse('imprimir_etiqueta'),
            data=json.dumps({'elementos': self.plantilla.elementos}),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 503)
        self.assertFalse(respuesta.json()['ok'])

    def test_imprimir_rechaza_un_codigo_ilegible_antes_de_mandarlo(self):
        respuesta = self.client.post(
            reverse('imprimir_etiqueta'),
            data=json.dumps({
                'elementos': [{'tipo': 'barcode', 'texto': 'Ñ'}],
                'datos': {'codigo': 'x'},
            }),
            content_type='application/json',
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('Code 128', respuesta.json()['error'])

    def test_las_salidas_solo_aceptan_post(self):
        for nombre in ('previsualizar_etiqueta', 'zpl_etiqueta',
                       'descargar_zpl_etiqueta', 'imprimir_etiqueta'):
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 405, nombre)

    # ── Recursos del lienzo ──────────────────────────────────────────────────

    def test_simbolo_png(self):
        respuesta = self.client.get(reverse('simbolo_etiqueta', args=['seco_p']))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'image/png')

    def test_simbolo_inexistente_da_404(self):
        respuesta = self.client.get(reverse('simbolo_etiqueta', args=['no_existe']))
        self.assertEqual(respuesta.status_code, 404)

    def test_buscar_items_filtra_y_excluye_bajas(self):
        prenda = make_prenda(nombre='Smoking Azul')
        activo = make_prenda_item(prenda=prenda)
        make_prenda_item(prenda=prenda, estado='baja')

        respuesta = self.client.get(reverse('buscar_items_etiqueta'), {'q': 'Smoking'})
        codigos = [i['codigo'] for i in respuesta.json()['items']]
        self.assertIn(activo.codigo_item, codigos)
        self.assertEqual(len(codigos), 1)
        datos = respuesta.json()['items'][0]['datos']
        self.assertEqual(datos['codigo'], activo.codigo_item)
        self.assertEqual(datos['prenda'], 'Smoking Azul')

    def test_buscar_items_filtra_por_tipo(self):
        prenda = make_prenda(nombre='Chaqueta Gris')
        venta = make_prenda_item(prenda=prenda, tipo='venta')
        alquiler = make_prenda_item(prenda=prenda, tipo='alquiler')

        url = reverse('buscar_items_etiqueta')
        solo_venta = self.client.get(url, {'q': 'Chaqueta', 'tipo': 'venta'}).json()
        self.assertEqual([i['codigo'] for i in solo_venta['items']],
                         [venta.codigo_item])

        solo_alquiler = self.client.get(
            url, {'q': 'Chaqueta', 'tipo': 'alquiler'}).json()
        self.assertEqual([i['codigo'] for i in solo_alquiler['items']],
                         [alquiler.codigo_item])

        # Un tipo que no existe no filtra nada, en vez de devolver vacío: es un
        # parámetro de la interfaz, no una validación de negocio.
        todos = self.client.get(url, {'q': 'Chaqueta', 'tipo': 'zzz'}).json()
        self.assertEqual(len(todos['items']), 2)

    def test_buscar_items_devuelve_el_stock_del_sku(self):
        prenda = make_prenda(nombre='Frac Negro')
        make_prenda_item(prenda=prenda, estado='disponible')
        make_prenda_item(prenda=prenda, estado='disponible')
        make_prenda_item(prenda=prenda, estado='alquilado')
        make_prenda_item(prenda=prenda, estado='baja')     # no cuenta

        items = self.client.get(reverse('buscar_items_etiqueta'),
                                {'q': 'Frac'}).json()['items']
        self.assertEqual(len(items), 3)
        for item in items:
            # El stock es del MODELO, no de la unidad: una unidad siempre es una.
            self.assertEqual(item['stock_disponible'], 2)
            self.assertEqual(item['stock_total'], 3)
            self.assertIn(item['tipo'], ('venta', 'alquiler'))
            self.assertTrue(item['tipo_nombre'])

    # ── El rollo del asistente ───────────────────────────────────────────────

    def test_asistente_horizontal_da_un_lienzo_apaisado(self):
        """Pedir «horizontal» describe otro rollo, no una reinterpretación.

        Antes esto marcaba la plantilla como «girada» y dejaba el papel al
        revés del lienzo, así que el editor mostraba una cosa y la impresora
        sacaba otra.
        """
        respuesta = self.client.get(
            reverse('disenador_etiqueta'),
            {'nueva': 1, 'origen': 'vacia', 'tamano': '32x61',
             'orientacion': 'horizontal'})
        contexto = respuesta.context
        self.assertGreater(contexto['ancho'], contexto['alto'])
        # Las medidas del rollo 32,5 × 60,8, intercambiadas: es OTRO rollo.
        self.assertEqual(
            (contexto['ancho'], contexto['alto']),
            (etiquetas.mm_a_puntos(60.8), etiquetas.mm_a_puntos(32.5)),
        )

    def test_asistente_vertical_respeta_el_rollo_tal_como_viene(self):
        respuesta = self.client.get(
            reverse('disenador_etiqueta'),
            {'nueva': 1, 'origen': 'vacia', 'tamano': '32x61',
             'orientacion': 'vertical'})
        contexto = respuesta.context
        self.assertEqual(
            (contexto['ancho'], contexto['alto']),
            (etiquetas.mm_a_puntos(32.5), etiquetas.mm_a_puntos(60.8)),
        )

    def test_guardar_no_acepta_ninguna_bandera_de_giro(self):
        """Un payload viejo con `orientacion` no debe resucitar el concepto."""
        respuesta = self.client.post(
            reverse('guardar_plantilla'),
            data=json.dumps({
                'nombre': 'Sin giro', 'elementos': [],
                'ancho': 240, 'alto': 400, 'orientacion': 'girada',
            }),
            content_type='application/json',
        )
        self.assertTrue(respuesta.json()['ok'])
        plantilla = PlantillaEtiqueta.objects.get(nombre='Sin giro')
        self.assertEqual((plantilla.ancho_puntos, plantilla.alto_puntos),
                         (240, 400))
        self.assertFalse(hasattr(plantilla, 'orientacion'))

    def test_las_etiquetas_del_sistema_usan_la_medida_de_la_plantilla(self):
        PlantillaEtiqueta.objects.all().update(es_predeterminada=False)
        PlantillaEtiqueta.objects.create(
            nombre='Predeterminada vertical', ancho_puntos=240, alto_puntos=400,
            es_predeterminada=True,
            elementos=[{'tipo': 'texto', 'x': 10, 'y': 10, 'texto': '{codigo}',
                        'tamano': 20}])
        item = make_prenda_item()
        respuesta = self.client.get(
            reverse('exportar_etiqueta_item_pdf', args=[item.pk]))
        self.assertEqual(respuesta.status_code, 200)
        caja = re.search(rb'/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]',
                         respuesta.content)
        self.assertAlmostEqual(float(caja.group(1)),
                               etiquetas.puntos_a_pt(240), places=3)
        self.assertAlmostEqual(float(caja.group(2)),
                               etiquetas.puntos_a_pt(400), places=3)

    def test_las_pantallas_muestran_la_medida_de_la_plantilla(self):
        plantilla = PlantillaEtiqueta.objects.create(
            nombre='Vertical visible', ancho_puntos=240, alto_puntos=400,
            es_predeterminada=True, elementos=[])
        # 240 × 400 puntos son 30 × 50 mm. Los decimales salen con coma porque
        # Django localiza al español.
        for url in (reverse('eliminar_plantilla', args=[plantilla.pk]),
                    reverse('etiquetas_calibrar')):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, '30,0 × 50,0 mm')

        listado = self.client.get(reverse('lista_plantillas'))
        self.assertContains(listado, '30,0 × 50,0')

    # ── Etiquetas del sistema ────────────────────────────────────────────────

    def test_etiqueta_de_item_usa_la_plantilla_predeterminada(self):
        item = make_prenda_item()
        respuesta = self.client.get(reverse('exportar_etiqueta_item_pdf', args=[item.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_etiquetas_de_un_sku_traen_una_por_unidad(self):
        prenda = make_prenda()
        make_prenda_item(prenda=prenda)
        make_prenda_item(prenda=prenda)
        make_prenda_item(prenda=prenda, estado='baja')   # no debe salir

        respuesta = self.client.get(reverse('exportar_etiquetas_prenda_pdf', args=[prenda.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.content.count(b'/Type /Page\n'), 2)

    def test_sku_sin_unidades_activas_avisa(self):
        prenda = make_prenda()
        respuesta = self.client.get(reverse('exportar_etiquetas_prenda_pdf', args=[prenda.pk]))
        self.assertEqual(respuesta.status_code, 302)

    def test_etiqueta_de_reparacion(self):
        reparacion = make_reparacion(cliente=make_cliente())
        respuesta = self.client.get(
            reverse('exportar_etiqueta_reparacion_pdf', args=[reparacion.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_sin_plantillas_las_etiquetas_avisan_en_vez_de_reventar(self):
        PlantillaEtiqueta.objects.all().delete()
        item = make_prenda_item()
        respuesta = self.client.get(reverse('exportar_etiqueta_item_pdf', args=[item.pk]))
        self.assertEqual(respuesta.status_code, 302)

    # ── Borrado ──────────────────────────────────────────────────────────────

    def test_no_se_puede_borrar_la_unica_plantilla(self):
        respuesta = self.client.post(reverse('eliminar_plantilla', args=[self.plantilla.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(PlantillaEtiqueta.objects.filter(pk=self.plantilla.pk).exists())

    def test_al_borrar_la_predeterminada_otra_ocupa_su_lugar(self):
        otra = PlantillaEtiqueta.objects.create(nombre='Otra', elementos=[])
        self.client.post(reverse('eliminar_plantilla', args=[self.plantilla.pk]))

        otra.refresh_from_db()
        self.assertTrue(otra.es_predeterminada)
        self.assertFalse(PlantillaEtiqueta.objects.filter(pk=self.plantilla.pk).exists())

    # ── Ajustes de impresora ─────────────────────────────────────────────────

    AJUSTES_VALIDOS = {
        'oscuridad': '8',
        'velocidad': '3',
        'usa_ribbon': 'on',
        'desplazamiento_x': '1.5',
        'desplazamiento_y': '-2',
        'tipo_papel': '',
    }

    def test_el_disenador_trae_los_ajustes_de_impresora(self):
        """El modal se pinta con los valores guardados, no con los del modelo."""
        config = ConfiguracionImpresora.cargar()
        config.oscuridad = 17
        config.save()

        respuesta = self.client.get(
            reverse('editar_plantilla', args=[self.plantilla.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'et-modal-impresora')
        self.assertContains(
            respuesta,
            '<input type="number" class="form-control" id="et-oscuridad" '
            'name="oscuridad" min="-30" max="30" step="1" value="17">',
            html=True,
        )

    def test_guardar_ajustes_por_formulario_sigue_redirigiendo(self):
        respuesta = self.client.post(
            reverse('etiquetas_set_impresora'), self.AJUSTES_VALIDOS
        )
        self.assertRedirects(respuesta, reverse('etiquetas_calibrar'))
        self.assertEqual(ConfiguracionImpresora.cargar().oscuridad, 8)

    def test_guardar_ajustes_por_ajax_responde_json_y_no_redirige(self):
        """El modal del diseñador no puede recargar: se llevaría el diseño."""
        respuesta = self.client.post(
            reverse('etiquetas_set_impresora'), self.AJUSTES_VALIDOS,
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()['ok'])

        config = ConfiguracionImpresora.cargar()
        self.assertEqual(config.oscuridad, 8)
        self.assertEqual(config.velocidad, 3)
        self.assertEqual(float(config.desplazamiento_y), -2.0)

    def test_ajustes_invalidos_por_ajax_devuelven_error_sin_guardar(self):
        datos = dict(self.AJUSTES_VALIDOS, oscuridad='999')
        respuesta = self.client.post(
            reverse('etiquetas_set_impresora'), datos,
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()['ok'])
        self.assertEqual(ConfiguracionImpresora.cargar().oscuridad, 0)

    def test_ajustes_no_numericos_por_ajax_no_revientan(self):
        datos = dict(self.AJUSTES_VALIDOS, velocidad='rapido')
        respuesta = self.client.post(
            reverse('etiquetas_set_impresora'), datos,
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('números', respuesta.json()['error'])

    def test_destildar_la_cinta_por_ajax_la_apaga(self):
        """El checkbox destildado no viaja: la ausencia tiene que leerse como no."""
        datos = dict(self.AJUSTES_VALIDOS)
        del datos['usa_ribbon']
        self.client.post(
            reverse('etiquetas_set_impresora'), datos,
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertFalse(ConfiguracionImpresora.cargar().usa_ribbon)


class MuestraPorPlantillaTests(TestCase):
    """El botón «Ver muestra en PDF» de cada fila del listado.

    Estuvo roto en dos capas a la vez: el enlace no mandaba el id de la fila, y
    `_pdf` renderizaba siempre con `PlantillaEtiqueta.predeterminada()`. El
    resultado era que las tres filas abrían la misma etiqueta, y el usuario veía
    el diseño de ejemplo del sistema en vez del que acababa de editar.
    """

    def setUp(self):
        self.usuario = make_user()
        self.client.force_login(self.usuario)
        self.predeterminada = PlantillaEtiqueta.predeterminada()
        self.predeterminada.es_predeterminada = True
        self.predeterminada.ancho_puntos = 400
        self.predeterminada.alto_puntos = 240
        self.predeterminada.save()
        # Medidas bien distintas: es lo que hace visible en el PDF si se
        # renderizó la plantilla equivocada.
        self.otra = PlantillaEtiqueta.objects.create(
            nombre='Etiqueta angosta',
            elementos=[],
            ancho_puntos=200,
            alto_puntos=800,
        )

    def _media_box(self, respuesta):
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        caja = re.search(rb'/MediaBox\s*\[([^\]]*)\]', respuesta.content)
        self.assertIsNotNone(caja, 'el PDF no declara MediaBox')
        return caja.group(1).split()

    def test_cada_fila_del_listado_enlaza_a_su_propia_plantilla(self):
        html = self.client.get(reverse('lista_plantillas')).content.decode()
        for plantilla in (self.predeterminada, self.otra):
            self.assertIn(
                reverse('muestra_plantilla_pdf', kwargs={'id': plantilla.pk}),
                html,
            )

    def test_la_muestra_usa_la_plantilla_pedida_y_no_la_predeterminada(self):
        propia = self._media_box(
            self.client.get(reverse('muestra_plantilla_pdf', kwargs={'id': self.otra.pk}))
        )
        defecto = self._media_box(
            self.client.get(reverse('muestra_plantilla_pdf', kwargs={'id': self.predeterminada.pk}))
        )
        self.assertNotEqual(propia, defecto)

    def test_la_calibracion_sigue_usando_la_predeterminada(self):
        # Sin id el comportamiento no cambia: la pantalla de calibración compara
        # el diseño ACTIVO contra el rollo, no uno elegido a mano.
        sin_id = self._media_box(self.client.get(reverse('exportar_etiqueta_demo_pdf')))
        con_id = self._media_box(
            self.client.get(reverse('muestra_plantilla_pdf', kwargs={'id': self.predeterminada.pk}))
        )
        self.assertEqual(sin_id, con_id)

    def test_plantilla_inexistente_da_404(self):
        respuesta = self.client.get(reverse('muestra_plantilla_pdf', kwargs={'id': 999999}))
        self.assertEqual(respuesta.status_code, 404)

    def test_pide_login(self):
        self.client.logout()
        respuesta = self.client.get(
            reverse('muestra_plantilla_pdf', kwargs={'id': self.otra.pk})
        )
        self.assertEqual(respuesta.status_code, 302)
