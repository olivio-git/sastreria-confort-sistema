"""QR compartido por PDF y ZPL.

La impresora puede elegir una versión distinta al usar ^BQ según el largo del
dato. Rasterizar una sola matriz garantiza que ambos caminos impriman el mismo
QR, con el mismo nivel de corrección y tamaño exterior.
"""

import qrcode
from PIL import Image


CORRECCION = qrcode.constants.ERROR_CORRECT_M


class QrNoCabe(ValueError):
    """La matriz necesita más puntos que el lado solicitado."""


def _matriz(dato):
    qr = qrcode.QRCode(
        error_correction=CORRECCION,
        box_size=1,
        border=4,
    )
    qr.add_data(str(dato))
    try:
        qr.make(fit=True)
    except (qrcode.exceptions.DataOverflowError, ValueError) as exc:
        raise QrNoCabe("El contenido es demasiado largo para un código QR.") from exc
    return qr.make_image(fill_color='black', back_color='white').convert('1')


def imagen(dato, tam):
    """El QR rasterizado, con todos los módulos del mismo ancho.

    El lado se recorta al múltiplo entero de la matriz más cercano por debajo
    del pedido. Escalar a un tamaño arbitrario con NEAREST repartiría el resto
    de la división de forma despareja — unos módulos de 2 puntos y otros de 3 —
    y un QR con módulos de distinto ancho es justamente lo que hace que la
    pistola tenga que insistir para leerlo.

    Se redondea al múltiplo MÁS CERCANO, no al de abajo. Truncar hacia abajo
    parece más prudente, pero con factores de escala chicos se come muchísimo:
    pedir 84 puntos sobre una matriz de 29 daría 58, un 31% menos de lo
    diseñado. Redondeando da 87 — se pasa por 3 puntos en vez de perder 26.

    Es decir: el lado real puede diferir del pedido en menos de medio módulo.
    A cambio, todos los módulos miden exactamente lo mismo, que es lo que
    necesita la pistola para leerlo de una.
    """
    tam = max(1, int(tam))
    base = _matriz(dato)
    minimo = max(base.size)
    if tam < minimo:
        raise QrNoCabe(
            f"El QR necesita al menos {minimo} puntos por lado para estos datos; "
            f"el diseño le asigna {tam}."
        )
    escala = max(1, round(tam / minimo))
    return base.resize((escala * minimo, escala * minimo), Image.Resampling.NEAREST)


def validar(dato, tam):
    imagen(dato, tam)


def zpl_gf(dato, tam):
    img = imagen(dato, tam)
    ancho, alto = img.size
    bytes_por_fila = (ancho + 7) // 8
    pixeles = img.load()
    filas = []
    for y in range(alto):
        fila = bytearray(bytes_por_fila)
        for x in range(ancho):
            if pixeles[x, y] == 0:
                fila[x // 8] |= 0x80 >> (x % 8)
        filas.append(fila.hex().upper())
    datos = ''.join(filas)
    total = bytes_por_fila * alto
    return f"^GFA,{total},{total},{bytes_por_fila},{datos}"
