"""Renderer ZPL: la plantilla, hablada en el idioma de la SAT TT460.

El driver instalado es «SAT TT460 UE (203 dpi) (ZPL)», o sea que la impresora
entiende Zebra Programming Language. Mandarle ZPL crudo evita depender de
BarTender, que en su edición UltraLite (la gratuita que viene con la impresora)
no expone ni puerto ni API para automatizar, y además deja el diseño encerrado
en un .btw binario en vez de en la base de datos.

──────────────────────────────────────────────────────────────────────────────
Dónde corre esto
──────────────────────────────────────────────────────────────────────────────
`render()` es texto puro: no toca la impresora ni importa nada de Windows, así
que corre en el hosting sin problema. Se puede pedir el ZPL, mirarlo y guardarlo
sin gastar papel.

`enviar()` sí necesita Windows, porque usa win32print para escribir en el puerto
USB en modo RAW. El hosting es Linux, así que allá `enviar()` siempre falla —
por diseño. La impresión real se hace desde la PC del taller, que es la única
que tiene la impresora colgada del USB.

Por eso el import de win32print está dentro de las funciones y no arriba: este
módulo se puede importar en cualquier lado; lo que falla, si no hay Windows, es
sólo el envío.
"""

import unicodedata

from . import etiquetas, etiquetas_qr, simbolos

IMPRESORA = "SAT TT460 UE (203 dpi) (ZPL)"

# Calibración del sensor de papel. La impresora hace avanzar un par de etiquetas
# midiendo dónde está el espacio entre una y otra, y guarda el resultado. Es lo
# mismo que se logra con la secuencia de botones del manual, pero sin tener que
# acertarle a cuántos segundos hay que mantener apretado.
#
# `~` en vez de `^`: es un comando de control, se ejecuta al llegar y no forma
# parte de una etiqueta, así que no va entre ^XA y ^XZ.
ZPL_CALIBRAR = '~JC'

_ALINEACION = {'izquierda': 'L', 'centro': 'C', 'derecha': 'R'}

# Ancho medio de carácter de la fuente escalable ^A0, como fracción del ancho
# nominal. ^A0 es proporcional, así que no hay forma de medir exacto desde acá;
# 0,55 es el promedio que da la estimación más cercana en la práctica y sólo se
# usa para decidir cuánto achicar un texto con `autoajustar`.
_ANCHO_MEDIO = 0.55


def _sin_tildes(texto):
    """Pasa los acentos a su letra base.

    La fuente ^A0 no dibuja acentos ni con ^CI28: según el firmware salen como
    un cuadrito o directamente se comen el carácter. Es preferible «REPARACION»
    a «REPARACI□N» en una etiqueta que el cliente va a ver.
    """
    if not texto:
        return ''
    descompuesto = unicodedata.normalize('NFKD', str(texto))
    return ''.join(c for c in descompuesto if not unicodedata.combining(c))


def _escapar(texto):
    """`^` y `~` son los caracteres de control de ZPL: hay que neutralizarlos."""
    return _sin_tildes(texto).replace('^', ' ').replace('~', ' ').strip()


def _fuente(alto, ancho=None):
    """Comando de fuente. ZPL sólo tiene una escalable, así que la familia y el
    tracking que eligió el usuario en el diseñador acá no se pueden aplicar."""
    return f"^A0N,{int(alto)},{int(ancho or alto)}"


def _tamano_que_entra(texto, tamano, tamano_min, ancho_bloque, renglones):
    """Achica la letra hasta que el texto entre en el bloque.

    ^FB parte el texto en renglones pero no lo achica: si no entra, lo corta. Se
    estima el ancho acá y se baja el cuerpo, que es lo que hace el renderer PDF
    con medidas exactas. No van a coincidir al punto, pero sí en intención.
    """
    if not texto or ancho_bloque <= 0:
        return tamano
    disponible = ancho_bloque * max(1, renglones)
    while tamano > tamano_min:
        if len(texto) * tamano * _ANCHO_MEDIO <= disponible:
            break
        tamano -= 1
    return tamano


def _texto_a_zpl(el, datos):
    texto = _escapar(etiquetas.sustituir(el['texto'], datos))
    if not texto:
        return ''

    tamano = el['tamano']
    if el['autoajustar']:
        tamano = _tamano_que_entra(
            texto, tamano, el['tamano_min'], el['ancho_bloque'], el['renglones']
        )

    alineacion = _ALINEACION.get(el['alineacion'], 'L')
    bloque = f"^FB{el['ancho_bloque']},{el['renglones']},0,{alineacion}"
    fuente = f"^A0{el['rotacion']},{tamano},{tamano}"

    comando = f"^FO{el['x']},{el['y']}{bloque}{fuente}^FD{texto}^FS"

    if el['negrita']:
        # ^A0 no tiene versión negrita. Imprimir dos veces con un punto de
        # desplazamiento engrosa el trazo lo justo para que se note en térmica,
        # que es como se resuelve el bold en ZPL desde siempre.
        comando += f"^FO{el['x'] + 1},{el['y']}{bloque}{fuente}^FD{texto}^FS"

    return comando


def _barcode_a_zpl(el, ancho_etiqueta, datos):
    dato_original = etiquetas.sustituir(el['texto'], datos).strip()
    if not dato_original:
        return ''

    x, y = el['x'], el['y']
    rot = el['rotacion']
    modulo = el['modulo']
    altura = el['alto_barra']
    legible = 'Y' if el['mostrar_texto'] else 'N'

    if el['simbologia'] == 'qr':
        return f"^FO{x},{y}{etiquetas_qr.zpl_gf(dato_original, altura)}^FS"

    dato = _escapar(dato_original)

    if el['centrar']:
        x = max(0, (int(ancho_etiqueta) - etiquetas.ancho_code128(dato, modulo)) // 2)

    cabecera = f"^FO{x},{y}^BY{modulo},2.5,{altura}"
    if el['simbologia'] == 'code39':
        return f"{cabecera}^B3{rot},N,{altura},{legible},N^FD{dato}^FS"
    if el['simbologia'] == 'ean13':
        return f"{cabecera}^BE{rot},{altura},{legible},N^FD{dato}^FS"
    # El último parámetro de ^BC es el MODO. Sin él la impresora arranca en
    # subset B y codifica un dígito por símbolo, mientras que reportlab elige el
    # subset óptimo: el mismo payload salía angosto en la vista previa PDF y
    # ancho en la etiqueta impresa. `A` (automático) le pide a la impresora la
    # misma codificación que calcula `etiquetas.modulos_code128`, así que el
    # preview, el centrado y lo que sale del cabezal vuelven a coincidir.
    return f"{cabecera}^BC{rot},{altura},{legible},N,N,A^FD{dato}^FS"


def _simbolo_a_zpl(el, ancho_etiqueta, datos):
    # El icono se rasteriza acá, a los puntos exactos que va a ocupar en el
    # papel. Rasterizar al tamaño final y no escalar después es lo que evita que
    # las líneas finas del símbolo se pierdan.
    try:
        grafico = simbolos.zpl_gf(el['clave'], el['tam'])
    except simbolos.SimboloDesconocido:
        return ''

    partes = [f"^FO{el['x']},{el['y']}{grafico}^FS"]

    leyenda = _escapar(etiquetas.sustituir(el['leyenda'], datos))
    if leyenda:
        tam = el['tam_leyenda']
        if el['leyenda_lado'] == 'derecha':
            lx = el['x'] + el['tam'] + 6
            ly = el['y'] + max(0, (el['tam'] - tam) // 2)
            bloque = max(1, int(ancho_etiqueta) - lx)
            alineacion = 'L'
        else:
            lx = el['x']
            ly = el['y'] + el['tam'] + 4
            bloque = max(1, min(int(ancho_etiqueta) - lx, el['tam'] * 3))
            alineacion = 'C'
            # Centrar la leyenda respecto del símbolo, no de su borde izquierdo.
            lx = max(0, lx - (bloque - el['tam']) // 2)
        partes.append(
            f"^FO{lx},{ly}^FB{bloque},2,0,{alineacion}"
            f"^A0N,{tam},{tam}^FD{leyenda}^FS"
        )
    return ''.join(partes)


def _caja_a_zpl(el):
    grosor = el['grosor']
    if el['relleno']:
        # Un rectángulo sólido es un ^GB con el borde tan grueso como la caja.
        grosor = min(el['ancho'], el['alto'])
    return (f"^FO{el['x']},{el['y']}"
            f"^GB{el['ancho']},{el['alto']},{grosor},B,{el['redondeo']}^FS")


def _linea_a_zpl(el):
    if el['orientacion'] == 'vertical':
        ancho, alto = el['grosor'], el['largo']
    else:
        ancho, alto = el['largo'], el['grosor']
    return (f"^FO{el['x']},{el['y']}"
            f"^GB{ancho},{alto},{el['grosor']},B,0^FS")


def _elemento_a_zpl(el, ancho_etiqueta, datos):
    if el['tipo'] == 'texto':
        return _texto_a_zpl(el, datos)
    if el['tipo'] == 'barcode':
        return _barcode_a_zpl(el, ancho_etiqueta, datos)
    if el['tipo'] == 'simbolo':
        return _simbolo_a_zpl(el, ancho_etiqueta, datos)
    if el['tipo'] == 'linea':
        return _linea_a_zpl(el)
    if el['tipo'] == 'caja':
        return _caja_a_zpl(el)
    return ''


def _ajustes_cabezal(config):
    """Comandos de oscuridad, velocidad y tipo de papel.

    Sin `config` no se emite ninguno: la impresora usa lo que tiene guardado,
    que es exactamente el comportamiento anterior a que esto existiera.

    `render()` no lee la base a propósito — recibe la config ya cargada — para
    seguir siendo una función pura de texto, que es lo que permite generar y
    testear ZPL sin impresora ni base de datos.
    """
    if config is None:
        return []
    partes = [
        # ^MT define si el cabezal imprime contra cinta o contra papel térmico.
        # En el modo equivocado sale casi invisible.
        f"^MT{'T' if config.usa_ribbon else 'D'}",
        # ^MD es un ajuste relativo a la oscuridad guardada en la impresora.
        f'^MD{int(config.oscuridad)}',
        # ^PR: velocidad de impresión, arrastre y retroceso, en pulgadas/segundo.
        f'^PR{int(config.velocidad)},{int(config.velocidad)},{int(config.velocidad)}',
    ]

    # ^MN le dice a la impresora cómo reconocer dónde termina cada etiqueta.
    # Sólo se manda si el usuario lo eligió: declarar el tipo equivocado
    # descalibra el arrastre y el rollo empieza a salir corrido.
    tracking = {'gap': 'Y', 'continuo': 'N', 'marca': 'M'}.get(
        getattr(config, 'tipo_papel', '') or '')
    if tracking:
        partes.append(f'^MN{tracking}')

    return partes


def _corrimiento(config):
    """Cuánto correr el diseño, en puntos, para encuadrarlo con el rollo."""
    if config is None:
        return 0, 0
    return (getattr(config, 'desplazamiento_x_puntos', 0) or 0,
            getattr(config, 'desplazamiento_y_puntos', 0) or 0)


def render(elementos, ancho=None, alto=None, datos=None, copias=1, config=None):
    """Convierte una plantilla en el ZPL de UNA etiqueta.

    Deliberadamente no emite ^MM ni ^MN: la calibración del papel ya la tiene
    guardada la impresora, y pisarla desde acá es la forma más fácil de
    descalibrarla y que el rollo empiece a salir corrido.

    Sí emite ^MT, ^MD y ^PR cuando se le pasa `config` (una
    `ConfiguracionImpresora`). Esos tres no tocan el arrastre del papel — sólo
    cuánto calienta el cabezal y a qué velocidad — así que ajustarlos no
    descalibra nada.
    """
    ancho = int(ancho or etiquetas.ANCHO_DEFECTO)
    alto = int(alto or etiquetas.ALTO_DEFECTO)
    datos = etiquetas.datos_muestra(datos) if datos is None else datos

    partes = [
        '^XA',                  # arranca la etiqueta
        *_ajustes_cabezal(config),
        f'^PW{max(1, ancho)}',  # ancho de impresión
        f'^LL{max(1, alto)}',   # largo de etiqueta
        '^LH0,0',               # origen arriba a la izquierda
        '^CI28',                # entrada en UTF-8
    ]
    dx, dy = _corrimiento(config)
    for el in etiquetas.normalizar(elementos, ancho):
        if dx or dy:
            # ^FO no admite coordenadas negativas: el borde de la etiqueta es el
            # cero y no hay nada a la izquierda de eso. Un corrimiento hacia la
            # izquierda mayor que el margen del elemento lo deja pegado al borde
            # en vez de generar un ^FO inválido que la impresora descarta.
            #
            # Se corre una copia: `el` viene de normalizar() y no hay que asumir
            # que sea descartable para el que llamó.
            el = dict(el,
                      x=max(0, el['x'] + dx),
                      y=max(0, el['y'] + dy))
        comando = _elemento_a_zpl(el, ancho, datos)
        if comando:
            partes.append(comando)
    partes.append(f'^PQ{max(1, int(copias))}')   # cantidad de copias
    partes.append('^XZ')                          # cierra y dispara la impresión
    return '\n'.join(partes)


def render_lote(elementos, ancho=None, alto=None, lote=None, copias=1, config=None):
    """El ZPL de varias etiquetas seguidas, una por juego de datos.

    Es lo que se manda al imprimir todas las unidades de un SKU de una sentada.
    """
    return '\n'.join(
        render(elementos, ancho, alto, datos, copias, config)
        for datos in (lote or [])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Envío a la impresora (sólo Windows)
# ─────────────────────────────────────────────────────────────────────────────

class ImpresoraNoDisponible(RuntimeError):
    """No se puede hablar con la impresora desde este servidor."""


def _win32print():
    try:
        import win32print
    except ImportError as exc:
        raise ImpresoraNoDisponible(
            "Este servidor no es Windows: no puede mandar a la impresora "
            "térmica. Descargá el ZPL y mandalo desde la PC del taller."
        ) from exc
    return win32print


def listar_impresoras():
    """Nombres de las impresoras que ve Windows. Útil para diagnosticar."""
    win32print = _win32print()
    banderas = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(banderas)]


def estado_impresora(impresora=IMPRESORA):
    """Devuelve (status, trabajos_en_cola). status 0 significa lista."""
    win32print = _win32print()
    h = win32print.OpenPrinter(impresora)
    try:
        info = win32print.GetPrinter(h, 2)
        return info['Status'], info['cJobs']
    finally:
        win32print.ClosePrinter(h)


def enviar(zpl, impresora=IMPRESORA, titulo="Etiqueta sastrería"):
    """Manda el ZPL tal cual al puerto de la impresora.

    RAW es la clave: sin eso el driver trataría el texto como un documento a
    rasterizar y saldría el ZPL impreso como letras en vez de ejecutarse.
    """
    win32print = _win32print()
    datos = zpl.encode('utf-8')
    h = win32print.OpenPrinter(impresora)
    try:
        trabajo = win32print.StartDocPrinter(h, 1, (titulo, None, 'RAW'))
        try:
            win32print.StartPagePrinter(h)
            escritos = win32print.WritePrinter(h, datos)
            win32print.EndPagePrinter(h)
        finally:
            win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)
    return trabajo, escritos
