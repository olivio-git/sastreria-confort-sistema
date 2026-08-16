"""Símbolos de cuidado textil (ISO 3758 / GINETEX) dibujados a mapa de bits.

Por qué se dibujan y no se descargan: los símbolos de cuidado son un estándar,
no iconos de interfaz — ninguna librería tipo Lucide o Font Awesome los trae. Y
aunque los trajera, un SVG no se puede mandar a una impresora ZPL: el comando
^GF quiere un mapa de bits monocromo. Como son formas geométricas simples (cuba,
triángulo, cuadrado, plancha, círculo), sale más barato dibujarlas que arrastrar
una dependencia de rasterizado.

De cada símbolo salen las dos representaciones que hacen falta, desde el mismo
dibujo:
  · PNG, para la vista previa del navegador
  · ^GF, para la impresora

Que sea un único dibujo es lo importante: si el diseñador mostrara un icono y la
impresora otro, el operario se enteraría recién con la etiqueta pegada.

Se dibuja con supermuestreo ×4 y se reduce al final. A los tamaños de una
etiqueta (30–60 puntos) una diagonal trazada directo en 1 bit queda escalonada;
el promediado previo la deja mucho más limpia.
"""

import io
import math
import os

from PIL import Image, ImageDraw, ImageFont

# Lienzo lógico: todas las figuras se dibujan en una caja de 100×100 y después
# se escalan. Así las proporciones no dependen del tamaño pedido.
LADO = 100
SUPER = 4

_FUENTE = os.path.join(
    os.path.dirname(__file__), "static", "font", "DejaVuSans.ttf"
)


class SimboloDesconocido(KeyError):
    """Se pidió un símbolo que no está en el catálogo."""


# ─────────────────────────────────────────────────────────────────────────────
# Primitivas: las cinco formas base del estándar
# ─────────────────────────────────────────────────────────────────────────────

def _fuente(d, tam):
    try:
        return ImageFont.truetype(_FUENTE, int(tam))
    except OSError:
        return ImageFont.load_default()


def _texto_centrado(d, s, cx, cy, tam, e):
    """Escribe centrado en (cx, cy). Se usa para los números de temperatura."""
    fuente = _fuente(d, tam * e)
    izq, arriba, der, abajo = d.textbbox((0, 0), s, font=fuente)
    d.text(
        (cx * e - (der - izq) / 2 - izq, cy * e - (abajo - arriba) / 2 - arriba),
        s, font=fuente, fill=0,
    )


def _cuba(d, e, grosor=5):
    """La cuba del lavado: paredes inclinadas y borde superior ondulado."""
    g = max(1, int(grosor * e))
    # Paredes y fondo
    d.line([(12 * e, 38 * e), (24 * e, 80 * e)], fill=0, width=g)
    d.line([(24 * e, 80 * e), (76 * e, 80 * e)], fill=0, width=g)
    d.line([(76 * e, 80 * e), (88 * e, 38 * e)], fill=0, width=g)
    # Borde de agua: dos ondas entre los extremos superiores
    puntos = []
    for i in range(0, 41):
        t = i / 40
        x = 12 + t * 76
        # dos crestas, amplitud chica para que no invada el interior
        y = 38 - 4 * math.sin(t * 4 * math.pi)
        puntos.append((x * e, y * e))
    d.line(puntos, fill=0, width=g, joint="curve")


def _triangulo(d, e, grosor=5):
    """El triángulo del blanqueo."""
    g = max(1, int(grosor * e))
    d.line([(50 * e, 14 * e), (12 * e, 84 * e), (88 * e, 84 * e), (50 * e, 14 * e)],
           fill=0, width=g, joint="curve")


def _cuadrado(d, e, grosor=5):
    """El cuadrado del secado."""
    g = max(1, int(grosor * e))
    d.rectangle([12 * e, 18 * e, 88 * e, 84 * e], outline=0, width=g)


def _circulo(d, e, grosor=5):
    """El círculo del cuidado profesional."""
    g = max(1, int(grosor * e))
    d.ellipse([14 * e, 16 * e, 86 * e, 86 * e], outline=0, width=g)


def _plancha(d, e, grosor=5):
    """La plancha: base plana y cuerpo inclinado hacia la punta."""
    g = max(1, int(grosor * e))
    cuerpo = [(14, 74), (90, 74), (84, 56), (72, 40), (36, 40), (24, 48), (14, 62)]
    d.line([(x * e, y * e) for x, y in cuerpo] + [(14 * e, 74 * e)],
           fill=0, width=g, joint="curve")


def _cruz(d, e, grosor=6):
    """La X de prohibición, sobre cualquier símbolo."""
    g = max(1, int(grosor * e))
    d.line([(10 * e, 10 * e), (90 * e, 90 * e)], fill=0, width=g)
    d.line([(90 * e, 10 * e), (10 * e, 90 * e)], fill=0, width=g)


def _puntos(d, e, cuantos, cy=62, radio=5, ancho=34):
    """Los puntos de temperatura que van dentro de la plancha o la secadora."""
    if cuantos <= 0:
        return
    paso = ancho / (cuantos + 1)
    for i in range(1, cuantos + 1):
        cx = 50 - ancho / 2 + paso * i
        d.ellipse([(cx - radio) * e, (cy - radio) * e,
                   (cx + radio) * e, (cy + radio) * e], fill=0)


def _barras(d, e, cuantas, grosor=5):
    """Las barras bajo la cuba: 1 = ciclo suave, 2 = muy suave."""
    g = max(1, int(grosor * e))
    for i in range(cuantas):
        y = (88 + i * 9) * e
        d.line([(28 * e, y), (72 * e, y)], fill=0, width=g)


def _mano(d, e, grosor=4):
    """Mano estilizada dentro de la cuba, para el lavado a mano."""
    g = max(1, int(grosor * e))
    # Palma
    d.rounded_rectangle([38 * e, 52 * e, 68 * e, 72 * e], radius=5 * e,
                        outline=0, width=g)
    # Dedos
    for i in range(3):
        x = (43 + i * 8) * e
        d.line([(x, 52 * e), (x, 44 * e)], fill=0, width=g)
    # Pulgar
    d.line([(38 * e, 60 * e), (30 * e, 56 * e)], fill=0, width=g)


# ─────────────────────────────────────────────────────────────────────────────
# Catálogo
#
# Cada entrada: (etiqueta legible, grupo, función de dibujo).
# El grupo sirve para agrupar en el selector del diseñador.
# ─────────────────────────────────────────────────────────────────────────────

def _lavar(temp=None, barras=0, mano=False, prohibido=False):
    def dibujar(d, e):
        _cuba(d, e)
        if temp:
            _texto_centrado(d, str(temp), 50, 62, 26, e)
        if mano:
            _mano(d, e)
        if barras:
            _barras(d, e, barras)
        if prohibido:
            _cruz(d, e)
    return dibujar


def _blanquear(oxigeno=False, prohibido=False):
    def dibujar(d, e):
        _triangulo(d, e)
        if oxigeno:
            g = max(1, int(4 * e))
            d.line([(38 * e, 70 * e), (56 * e, 36 * e)], fill=0, width=g)
            d.line([(50 * e, 70 * e), (68 * e, 36 * e)], fill=0, width=g)
        if prohibido:
            _cruz(d, e)
    return dibujar


def _secadora(puntos=0, prohibido=False):
    def dibujar(d, e):
        _cuadrado(d, e)
        g = max(1, int(5 * e))
        d.ellipse([26 * e, 26 * e, 74 * e, 74 * e], outline=0, width=g)
        _puntos(d, e, puntos, cy=51, radio=4, ancho=26)
        if prohibido:
            _cruz(d, e)
    return dibujar


def _secar(modo):
    def dibujar(d, e):
        _cuadrado(d, e)
        g = max(1, int(5 * e))
        if modo == "colgado":              # una línea vertical: secar en cuerda
            d.line([(50 * e, 26 * e), (50 * e, 76 * e)], fill=0, width=g)
        elif modo == "plano":              # una línea horizontal: secar en plano
            d.line([(24 * e, 51 * e), (76 * e, 51 * e)], fill=0, width=g)
        elif modo == "goteo":              # arco: secar sin escurrir
            d.arc([24 * e, 20 * e, 76 * e, 48 * e], 200, 340, fill=0, width=g)
        elif modo == "sombra":             # diagonales en la esquina: a la sombra
            d.line([(18 * e, 24 * e), (38 * e, 24 * e)], fill=0, width=g)
            d.line([(18 * e, 24 * e), (18 * e, 44 * e)], fill=0, width=g)
            d.line([(18 * e, 24 * e), (44 * e, 50 * e)], fill=0, width=g)
    return dibujar


def _planchar(puntos=0, prohibido=False):
    def dibujar(d, e):
        _plancha(d, e)
        _puntos(d, e, puntos, cy=60, radio=4, ancho=30)
        if prohibido:
            _cruz(d, e)
    return dibujar


def _profesional(letra="", subrayado=0, prohibido=False):
    def dibujar(d, e):
        _circulo(d, e)
        if letra:
            _texto_centrado(d, letra, 50, 51, 34, e)
        if subrayado:
            g = max(1, int(5 * e))
            for i in range(subrayado):
                y = (90 + i * 8) * e
                d.line([(30 * e, y), (70 * e, y)], fill=0, width=g)
        if prohibido:
            _cruz(d, e)
    return dibujar


CATALOGO = {
    # Lavado
    "lavar_30":        ("Lavar a 30 °C",              "Lavado", _lavar(30)),
    "lavar_40":        ("Lavar a 40 °C",              "Lavado", _lavar(40)),
    "lavar_60":        ("Lavar a 60 °C",              "Lavado", _lavar(60)),
    "lavar_95":        ("Lavar a 95 °C",              "Lavado", _lavar(95)),
    "lavar_suave":     ("Lavado suave",               "Lavado", _lavar(40, barras=1)),
    "lavar_muy_suave": ("Lavado muy suave",           "Lavado", _lavar(30, barras=2)),
    "lavar_mano":      ("Lavar a mano",               "Lavado", _lavar(mano=True)),
    "no_lavar":        ("No lavar",                   "Lavado", _lavar(prohibido=True)),

    # Blanqueo
    "blanquear":       ("Se puede blanquear",         "Blanqueo", _blanquear()),
    "blanquear_ox":    ("Sólo blanqueo sin cloro",    "Blanqueo", _blanquear(oxigeno=True)),
    "no_blanquear":    ("No blanquear",               "Blanqueo", _blanquear(prohibido=True)),

    # Secado
    "secadora":        ("Secadora permitida",         "Secado", _secadora()),
    "secadora_baja":   ("Secadora temperatura baja",  "Secado", _secadora(puntos=1)),
    "secadora_media":  ("Secadora temperatura media", "Secado", _secadora(puntos=2)),
    "no_secadora":     ("No usar secadora",           "Secado", _secadora(prohibido=True)),
    "secar_colgado":   ("Secar colgado",              "Secado", _secar("colgado")),
    "secar_plano":     ("Secar en plano",             "Secado", _secar("plano")),
    "secar_goteo":     ("Secar sin escurrir",         "Secado", _secar("goteo")),
    "secar_sombra":    ("Secar a la sombra",          "Secado", _secar("sombra")),

    # Planchado
    "planchar_1":      ("Planchar a 110 °C",          "Planchado", _planchar(1)),
    "planchar_2":      ("Planchar a 150 °C",          "Planchado", _planchar(2)),
    "planchar_3":      ("Planchar a 200 °C",          "Planchado", _planchar(3)),
    "no_planchar":     ("No planchar",                "Planchado", _planchar(prohibido=True)),

    # Cuidado profesional
    "seco":            ("Limpieza en seco",           "Profesional", _profesional()),
    "seco_p":          ("Limpieza en seco (P)",       "Profesional", _profesional("P")),
    "seco_f":          ("Limpieza en seco (F)",       "Profesional", _profesional("F")),
    "no_seco":         ("No limpiar en seco",         "Profesional", _profesional(prohibido=True)),
    "humedo_w":        ("Limpieza en húmedo (W)",     "Profesional", _profesional("W")),
    "no_humedo":       ("No limpiar en húmedo",       "Profesional", _profesional("W", prohibido=True)),
}


def catalogo_para_json():
    """El catálogo agrupado, como lo consume el selector del diseñador."""
    grupos = {}
    for clave, (etiqueta, grupo, _) in CATALOGO.items():
        grupos.setdefault(grupo, []).append({"clave": clave, "nombre": etiqueta})
    return grupos


# ─────────────────────────────────────────────────────────────────────────────
# Render
# ─────────────────────────────────────────────────────────────────────────────

def render(clave, tam):
    """Dibuja el símbolo y devuelve una imagen de 1 bit de `tam`×`tam`."""
    if clave not in CATALOGO:
        raise SimboloDesconocido(clave)
    tam = max(8, min(400, int(tam)))

    grande = Image.new("L", (LADO * SUPER, LADO * SUPER), 255)
    d = ImageDraw.Draw(grande)
    CATALOGO[clave][2](d, SUPER)

    chico = grande.resize((tam, tam), Image.LANCZOS)
    # Umbral: por debajo de 165 se considera tinta. Un poco por encima del medio
    # para que las líneas finas no desaparezcan al reducir.
    return chico.point(lambda v: 0 if v < 165 else 255, mode="1")


def png(clave, tam):
    """El símbolo como PNG, para mostrarlo en el navegador."""
    buffer = io.BytesIO()
    # Se guarda en L y no en 1 porque algunos navegadores renderizan mal el PNG
    # de 1 bit al escalarlo en pantalla.
    render(clave, tam).convert("L").save(buffer, format="PNG")
    return buffer.getvalue()


def zpl_gf(clave, tam):
    """El símbolo como comando ^GF, listo para intercalar en una etiqueta.

    ^GFA lleva los datos en hexadecimal, fila por fila, redondeando cada fila a
    bytes completos. Un bit en 1 es un punto negro.
    """
    img = render(clave, tam)
    ancho, alto = img.size
    bytes_por_fila = (ancho + 7) // 8
    pixeles = img.load()

    filas = []
    for y in range(alto):
        fila = bytearray(bytes_por_fila)
        for x in range(ancho):
            if pixeles[x, y] == 0:          # 0 = negro en modo "1"
                fila[x // 8] |= 0x80 >> (x % 8)
        filas.append(fila.hex().upper())

    datos = "".join(filas)
    total = bytes_por_fila * alto
    return f"^GFA,{total},{total},{bytes_por_fila},{datos}"
