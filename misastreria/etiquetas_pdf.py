"""Renderer PDF: la misma plantilla, dibujada con reportlab.

Es el camino que funciona en producción. El hosting es Linux, así que no puede
hablarle a la impresora térmica por USB; lo que sí puede es generar un PDF del
tamaño exacto del sticker y dejar que el navegador lo mande a la impresora que
sea. Vale para la SAT TT460 vía driver, para una láser con hoja de etiquetas, o
para revisar el diseño en pantalla antes de gastar rollo.

Frente al ZPL nativo se pierde algo de nitidez en térmica —el driver rasteriza
en vez de usar las fuentes del firmware— y se gana que funcione en todas partes.

──────────────────────────────────────────────────────────────────────────────
Coordenadas
──────────────────────────────────────────────────────────────────────────────
La plantilla usa el origen arriba a la izquierda con la Y creciendo hacia abajo
(ver `etiquetas.py`). reportlab usa el origen abajo a la izquierda. Toda la
conversión pasa por `_y()`, que es el único lugar donde se da vuelta el eje.

En los textos, la `y` de la plantilla es el borde SUPERIOR de la caja de texto,
mientras que reportlab dibuja desde la línea base. La diferencia es el ascendente
de la fuente, que se aproxima en `_ASCENDENTE`.
"""

import io

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code39, code128, eanbc
from reportlab.graphics.shapes import Drawing
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from . import etiquetas, etiquetas_qr, simbolos

# Fracción del cuerpo de la letra que queda por encima de la línea base. Las
# tres familias base de PostScript rondan 0,72–0,76; 0,78 deja el texto un pelo
# más abajo, que es lo que evita que un título toque el filete de arriba.
_ASCENDENTE = 0.78

# Separación entre renglones, como múltiplo del cuerpo.
_INTERLINEA = 1.15

# Rotaciones de la plantilla (heredadas de ZPL) en grados de reportlab, que gira
# en sentido antihorario. ZPL gira en horario, de ahí los signos cambiados.
_GRADOS = {'N': 0, 'R': -90, 'I': 180, 'B': 90}


def _y(alto_pt, y_puntos):
    """Y de la plantilla (desde arriba, en puntos) → Y de reportlab (desde abajo)."""
    return alto_pt - etiquetas.puntos_a_pt(y_puntos)


def _fuente(el):
    regular, negrita = etiquetas.FUENTES[el['fuente']]
    return negrita if el['negrita'] else regular


def _ancho_texto(c, texto, fuente, tamano, tracking):
    """Ancho real incluyendo el letter-spacing, que stringWidth no contempla."""
    return c.stringWidth(texto, fuente, tamano) + tracking * max(0, len(texto) - 1)


def _partir(c, texto, fuente, tamano, tracking, ancho_max):
    """Parte el texto en renglones que entren en `ancho_max`.

    Corta por palabras. Una palabra sola más ancha que el bloque se deja igual y
    se sale del margen: es preferible una etiqueta fea a una palabra mutilada, y
    además `autoajustar` normalmente lo resuelve achicando la letra.
    """
    lineas = []
    for parrafo in texto.split('\n'):
        actual = ''
        for palabra in parrafo.split():
            tentativa = f"{actual} {palabra}".strip()
            if actual and _ancho_texto(c, tentativa, fuente, tamano, tracking) > ancho_max:
                lineas.append(actual)
                actual = palabra
            else:
                actual = tentativa
        lineas.append(actual)
    return lineas


def _tamano_que_entra(c, texto, el, fuente, ancho_max):
    """Baja el cuerpo hasta que el texto entre en el bloque y en sus renglones."""
    tamano = etiquetas.puntos_a_pt(el['tamano'])
    minimo = etiquetas.puntos_a_pt(el['tamano_min'])
    tracking = etiquetas.puntos_a_pt(el['tracking'])
    while tamano > minimo:
        lineas = _partir(c, texto, fuente, tamano, tracking, ancho_max)
        cabe = len(lineas) <= el['renglones'] and all(
            _ancho_texto(c, ln, fuente, tamano, tracking) <= ancho_max for ln in lineas
        )
        if cabe:
            break
        tamano -= 0.5
    return max(tamano, minimo)


def _dibujar_texto(c, el, alto_pt, datos):
    texto = etiquetas.sustituir(el['texto'], datos)
    if not texto.strip():
        return

    fuente = _fuente(el)
    ancho_max = etiquetas.puntos_a_pt(el['ancho_bloque'])
    tracking = etiquetas.puntos_a_pt(el['tracking'])

    if el['autoajustar']:
        tamano = _tamano_que_entra(c, texto, el, fuente, ancho_max)
    else:
        tamano = etiquetas.puntos_a_pt(el['tamano'])

    lineas = _partir(c, texto, fuente, tamano, tracking, ancho_max)[:el['renglones']]

    x0 = etiquetas.puntos_a_pt(el['x'])
    base = _y(alto_pt, el['y']) - tamano * _ASCENDENTE

    c.saveState()
    c.setFillColorRGB(0, 0, 0)
    grados = _GRADOS[el['rotacion']]
    if grados:
        c.translate(x0, base)
        c.rotate(grados)
        x0 = base = 0

    for i, linea in enumerate(lineas):
        ancho = _ancho_texto(c, linea, fuente, tamano, tracking)
        if el['alineacion'] == 'centro':
            x = x0 + (ancho_max - ancho) / 2
        elif el['alineacion'] == 'derecha':
            x = x0 + ancho_max - ancho
        else:
            x = x0
        objeto = c.beginText()
        objeto.setTextOrigin(x, base - i * tamano * _INTERLINEA)
        objeto.setFont(fuente, tamano)
        # setCharSpace es el letter-spacing. Es lo que le da a la marca el aire
        # de etiqueta textil; sin esto «FORTIUM» queda apretado y ordinario.
        objeto.setCharSpace(tracking)
        objeto.textOut(linea)
        c.drawText(objeto)

    c.restoreState()


def _widget_a_pdf(c, widget, x, y, ancho_destino=None):
    """Dibuja un widget de reportlab.graphics escalado a `ancho_destino`."""
    limites = widget.getBounds()
    ancho = limites[2] - limites[0]
    alto = limites[3] - limites[1]
    if ancho <= 0 or alto <= 0:
        return 0.0

    escala = (ancho_destino / ancho) if ancho_destino else 1.0
    dibujo = Drawing(ancho * escala, alto * escala)
    widget.x = -limites[0]
    widget.y = -limites[1]
    dibujo.add(widget)
    dibujo.scale(escala, escala)
    renderPDF.draw(dibujo, c, x, y)
    return alto * escala


def _dibujar_barcode(c, el, ancho_puntos, alto_pt, datos):
    dato = etiquetas.sustituir(el['texto'], datos).strip()
    if not dato:
        return

    modulo_pt = etiquetas.puntos_a_pt(el['modulo'])
    altura_pt = etiquetas.puntos_a_pt(el['alto_barra'])
    x_puntos = el['x']

    if el['simbologia'] == 'qr':
        lado = altura_pt
        y = _y(alto_pt, el['y']) - lado
        imagen = etiquetas_qr.imagen(dato, el['alto_barra'])
        c.drawImage(ImageReader(imagen), etiquetas.puntos_a_pt(x_puntos), y,
                    width=lado, height=lado)
        return

    # Los lineales comparten el mismo cálculo de ancho que el renderer ZPL, así
    # que un código centrado cae en el mismo lugar en los dos formatos.
    if el['centrar']:
        ancho_codigo = etiquetas.ancho_code128(dato, el['modulo'])
        x_puntos = max(0, (int(ancho_puntos) - ancho_codigo) // 2)
    x = etiquetas.puntos_a_pt(x_puntos)

    if el['simbologia'] == 'ean13':
        widget = eanbc.Ean13BarcodeWidget(dato, barHeight=altura_pt,
                                          humanReadable=el['mostrar_texto'])
        limites = widget.getBounds()
        y = _y(alto_pt, el['y']) - (limites[3] - limites[1])
        _widget_a_pdf(c, widget, x, y)
        return

    constructor = code39.Standard39 if el['simbologia'] == 'code39' else code128.Code128
    argumentos = {
        'barHeight': altura_pt,
        'barWidth': modulo_pt,
        'humanReadable': el['mostrar_texto'],
        # ReportLab agrega 18 pt de zona blanca a cada lado por defecto. La
        # plantilla ya deja su propio margen; duplicarlo desplazaba y recortaba
        # el código respecto de Canvas/ZPL.
        'quiet': 0,
    }
    if el['mostrar_texto']:
        argumentos['fontSize'] = etiquetas.puntos_a_pt(el['tamano_texto'])
    if el['simbologia'] == 'code39':
        argumentos['checksum'] = 0        # el estándar del rubro va sin checksum

    codigo = constructor(dato, **argumentos)
    y = _y(alto_pt, el['y']) - getattr(codigo, 'height', altura_pt)
    codigo.drawOn(c, x, y)


def _dibujar_simbolo(c, el, alto_pt, datos):
    try:
        imagen = simbolos.render(el['clave'], el['tam'])
    except simbolos.SimboloDesconocido:
        return

    # El símbolo se rasteriza al tamaño exacto que va a ocupar en el papel, igual
    # que en ZPL. El blanco se hace transparente para que el icono no tape con un
    # recuadro lo que tenga debajo (el marco, por ejemplo).
    rgba = imagen.convert('RGBA')
    rgba.putdata([
        (0, 0, 0, 0) if pixel[0] > 127 else (0, 0, 0, 255)
        for pixel in rgba.getdata()
    ])
    buffer = io.BytesIO()
    rgba.save(buffer, format='PNG')
    buffer.seek(0)

    lado = etiquetas.puntos_a_pt(el['tam'])
    x = etiquetas.puntos_a_pt(el['x'])
    y = _y(alto_pt, el['y']) - lado
    c.drawImage(ImageReader(buffer), x, y, width=lado, height=lado, mask='auto')

    leyenda = etiquetas.sustituir(el['leyenda'], datos).strip()
    if not leyenda:
        return

    tamano = etiquetas.puntos_a_pt(el['tam_leyenda'])
    c.setFont('Helvetica', tamano)
    c.setFillColorRGB(0, 0, 0)
    if el['leyenda_lado'] == 'derecha':
        c.drawString(x + lado + etiquetas.puntos_a_pt(6),
                     y + (lado - tamano) / 2, leyenda)
    else:
        c.drawCentredString(x + lado / 2,
                            y - tamano - etiquetas.puntos_a_pt(4), leyenda)


def _dibujar_caja(c, el, alto_pt):
    x = etiquetas.puntos_a_pt(el['x'])
    ancho = etiquetas.puntos_a_pt(el['ancho'])
    alto = etiquetas.puntos_a_pt(el['alto'])
    y = _y(alto_pt, el['y']) - alto

    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    if el['relleno']:
        c.rect(x, y, ancho, alto, stroke=0, fill=1)
    else:
        # ZPL dibuja el borde hacia adentro; reportlab lo centra en el trazo. Se
        # compensa medio grosor para que el marco caiga en el mismo sitio.
        grosor = etiquetas.puntos_a_pt(el['grosor'])
        c.setLineWidth(grosor)
        ajuste = grosor / 2
        radio = etiquetas.puntos_a_pt(el['redondeo'])
        if radio > 0:
            c.roundRect(x + ajuste, y + ajuste, max(0.1, ancho - grosor),
                        max(0.1, alto - grosor), radio, stroke=1, fill=0)
        else:
            c.rect(x + ajuste, y + ajuste, max(0.1, ancho - grosor),
                   max(0.1, alto - grosor), stroke=1, fill=0)
    c.restoreState()


def _dibujar_linea(c, el, alto_pt):
    x = etiquetas.puntos_a_pt(el['x'])
    grosor = etiquetas.puntos_a_pt(el['grosor'])
    largo = etiquetas.puntos_a_pt(el['largo'])
    c.saveState()
    c.setFillColorRGB(0, 0, 0)
    if el['orientacion'] == 'vertical':
        y = _y(alto_pt, el['y']) - largo
        c.rect(x, y, grosor, largo, stroke=0, fill=1)
    else:
        y = _y(alto_pt, el['y']) - grosor
        c.rect(x, y, largo, grosor, stroke=0, fill=1)
    c.restoreState()


def _dibujar(c, elementos, ancho_puntos, alto_puntos, datos):
    """Dibuja una etiqueta completa en la página actual del canvas."""
    alto_pt = etiquetas.puntos_a_pt(alto_puntos)
    for el in etiquetas.normalizar(elementos, ancho_puntos):
        if el['tipo'] == 'texto':
            _dibujar_texto(c, el, alto_pt, datos)
        elif el['tipo'] == 'barcode':
            _dibujar_barcode(c, el, ancho_puntos, alto_pt, datos)
        elif el['tipo'] == 'simbolo':
            _dibujar_simbolo(c, el, alto_pt, datos)
        elif el['tipo'] == 'linea':
            _dibujar_linea(c, el, alto_pt)
        elif el['tipo'] == 'caja':
            _dibujar_caja(c, el, alto_pt)


def render(elementos, ancho=None, alto=None, lote=None, copias=1):
    """Genera el PDF de una o varias etiquetas, UNA por página.

    `lote` es la lista de juegos de datos: una etiqueta por cada uno. Se usa así
    y no con un dict suelto porque el caso real es imprimir de una sentada todas
    las unidades de un SKU recién dado de alta.

    Devuelve los bytes del PDF.
    """
    ancho_puntos = int(ancho or etiquetas.ANCHO_DEFECTO)
    alto_puntos = int(alto or etiquetas.ALTO_DEFECTO)
    ancho_pt = etiquetas.puntos_a_pt(ancho_puntos)
    alto_pt = etiquetas.puntos_a_pt(alto_puntos)

    lote = list(lote or [etiquetas.datos_muestra()])
    copias = max(1, int(copias))

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(ancho_pt, alto_pt))
    for datos in lote:
        for _ in range(copias):
            _dibujar(c, elementos, ancho_puntos, alto_puntos, datos)
            c.showPage()
    if not lote:
        c.showPage()          # evita un PDF vacío, que es un PDF inválido
    c.save()
    return buffer.getvalue()
