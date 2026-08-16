"""Núcleo compartido del sistema de etiquetas.

Una etiqueta es una lista de elementos (textos, códigos de barras, símbolos de
cuidado, cajas) guardada como JSON en `PlantillaEtiqueta.elementos`. Esa misma
lista se dibuja por dos caminos distintos:

    plantilla JSON
          │
          ├──► etiquetas_pdf.render()  → reportlab → PDF → cualquier impresora
          │
          └──► etiquetas_zpl.render()  → ZPL       → SAT TT460 vía USB

El PDF es el camino que funciona en el hosting (Linux). El ZPL es el nativo de
la impresora térmica: sale más nítido, pero sólo se puede mandar desde la PC del
taller, que es la que tiene la impresora conectada.

Este módulo es lo que ambos comparten: unidades, catálogo de campos,
sustitución de datos y normalización de elementos. No importa reportlab ni PIL a
propósito — así se puede usar desde cualquier lado sin arrastrar dependencias.

──────────────────────────────────────────────────────────────────────────────
Sistema de coordenadas
──────────────────────────────────────────────────────────────────────────────
Todo se guarda en PUNTOS DE CABEZAL a 203 dpi, que es la resolución nativa de la
SAT TT460. Se eligió esa unidad y no milímetros porque es la única en la que la
impresora no redondea: un punto es un punto. El PDF convierte a puntos PostScript
al dibujar, que es una multiplicación exacta.

El origen es la esquina SUPERIOR IZQUIERDA y la Y crece hacia abajo, igual que en
ZPL y que en el lienzo del navegador. El renderer PDF es el que da vuelta la Y,
porque reportlab usa el origen abajo a la izquierda.

Para los textos, `y` es el BORDE SUPERIOR de la caja de texto, no la línea base.
"""

from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# Unidades
# ─────────────────────────────────────────────────────────────────────────────

PPP = 203                      # puntos por pulgada del cabezal de la SAT TT460
PUNTOS_POR_MM = PPP / 25.4     # 7,9921 puntos por milímetro
PUNTOS_POR_PT = PPP / 72.0     # 2,8194 puntos por punto PostScript


def mm_a_puntos(mm):
    """Milímetros → puntos de cabezal."""
    return int(round(float(mm) * PUNTOS_POR_MM))


def puntos_a_mm(puntos):
    """Puntos de cabezal → milímetros (para mostrar en pantalla)."""
    return round(float(puntos) / PUNTOS_POR_MM, 1)


def puntos_a_pt(puntos):
    """Puntos de cabezal → puntos PostScript (lo que entiende reportlab)."""
    return float(puntos) / PUNTOS_POR_PT


# Tamaños de rollo habituales, en milímetros. Son los mismos que ya ofrecía la
# página de calibración: se conservan para no obligar a remedir el rollo.
TAMANOS_MM = {
    '40x25':  (40, 25),
    '50x25':  (50, 25),
    '50x30':  (50, 30),
    '58x40':  (58, 40),
    '60x30':  (60, 30),
    '60x40':  (60, 40),
    '80x50':  (80, 50),
    '100x50': (100, 50),
    # El rollo que trae cargado la SAT TT460 de fábrica.
    '32x61':  (32.5, 60.8),
}
TAMANO_DEFECTO = '50x30'

ANCHO_DEFECTO = mm_a_puntos(TAMANOS_MM[TAMANO_DEFECTO][0])   # 400
ALTO_DEFECTO = mm_a_puntos(TAMANOS_MM[TAMANO_DEFECTO][1])    # 240

NEGOCIO = "FORTIUM TAILOR"


def tamanos_para_selector():
    """Los tamaños de rollo como los consume el <select> del diseñador."""
    return [
        {
            'clave': clave,
            'nombre': f"{ancho:g} × {alto:g} mm",
            'ancho': mm_a_puntos(ancho),
            'alto': mm_a_puntos(alto),
        }
        for clave, (ancho, alto) in TAMANOS_MM.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Campos sustituibles
#
# Son los {marcadores} que el usuario puede intercalar en cualquier texto. Se
# listan acá y no en la vista porque el diseñador los ofrece en un menú: si
# mañana se agrega uno, aparece solo en la interfaz.
# ─────────────────────────────────────────────────────────────────────────────

CAMPOS = {
    'codigo':     'Código de barras',
    'prenda':     'Nombre de la prenda',
    'subtitulo':  'Subtítulo (talla · color)',
    'detalle':    'Detalle',
    'talla':      'Talla',
    'color':      'Color',
    'modelo':     'Modelo / línea',
    'referencia': 'Código de referencia',
    'condicion':  'Condición (nueva/usada/remate)',
    'ubicacion':  'Ubicación física',
    'precio':     'Precio',
    'cliente':    'Cliente',
    'servicio':   'Servicio (REPARACIÓN, CONFECCIÓN…)',
    'fecha':      'Fecha de hoy',
    'taller':     'Nombre del taller',
}


def datos_muestra(extra=None):
    """Datos ficticios para la vista previa del diseñador.

    No son datos reales a propósito: sirven para que el usuario vea cómo queda
    un texto de largo verosímil antes de que exista el registro.
    """
    datos = {
        'codigo':     'PRN-001-ITM-01',
        'prenda':     'Terno Clásico',
        'subtitulo':  'T M · NEGRO',
        'detalle':    'Casimir italiano',
        'talla':      'M',
        'color':      'Negro',
        'modelo':     'Slim Fit',
        'referencia': 'SM-2024-042',
        'condicion':  'Nueva',
        'ubicacion':  'Perchero A-3',
        'precio':     '350 Bs',
        'cliente':    'Juan Pérez',
        'servicio':   '',
        'fecha':      date.today().strftime('%d/%m/%Y'),
        'taller':     NEGOCIO,
    }
    datos.update(extra or {})
    return datos


def _texto_o_vacio(valor):
    return '' if valor is None else str(valor)


def datos_de_item(item):
    """Campos de etiqueta para UNA unidad física de inventario (PrendaItem).

    Es el caso principal: `codigo_item` (PRN-010-ITM-01) identifica el traje
    concreto que cuelga del perchero, no el modelo. Dos ternos idénticos tienen
    códigos distintos, que es lo que permite saber cuál se llevó cada cliente.
    """
    prenda = item.prenda
    subtitulo = ' · '.join(filter(None, [
        f"T {prenda.talla}" if prenda.talla else None,
        prenda.color.upper() if prenda.color else None,
    ]))
    return datos_muestra({
        'codigo':     item.codigo_item,
        'prenda':     prenda.nombre or '—',
        'subtitulo':  subtitulo,
        'detalle':    _texto_o_vacio(prenda.modelo),
        'talla':      _texto_o_vacio(prenda.talla),
        'color':      _texto_o_vacio(prenda.color),
        'modelo':     _texto_o_vacio(prenda.modelo),
        'referencia': _texto_o_vacio(prenda.codigo_referencia),
        'condicion':  item.get_condicion_display(),
        'ubicacion':  str(item.ubicacion) if item.ubicacion else '',
        'precio':     f"{prenda.precio} Bs" if prenda.precio is not None else '',
        'cliente':    '',
        'servicio':   '',
    })


def datos_de_prenda(prenda):
    """Campos de etiqueta para un SKU completo (PrendaInventario).

    Ojo: el código acá es el del SKU (PRN-010), o sea que identifica el MODELO.
    Diez camisas iguales comparten etiqueta. Sirve para precio y reposición, no
    para trazabilidad — para eso está `datos_de_item`.
    """
    subtitulo = ' · '.join(filter(None, [
        f"T {prenda.talla}" if prenda.talla else None,
        prenda.color.upper() if prenda.color else None,
    ]))
    return datos_muestra({
        'codigo':     prenda.codigo,
        'prenda':     prenda.nombre or '—',
        'subtitulo':  subtitulo,
        'detalle':    _texto_o_vacio(prenda.modelo),
        'talla':      _texto_o_vacio(prenda.talla),
        'color':      _texto_o_vacio(prenda.color),
        'modelo':     _texto_o_vacio(prenda.modelo),
        'referencia': _texto_o_vacio(prenda.codigo_referencia),
        'condicion':  '',
        'ubicacion':  '',
        'precio':     f"{prenda.precio} Bs" if prenda.precio is not None else '',
        'cliente':    '',
        'servicio':   '',
    })


def datos_de_servicio(obj, servicio):
    """Campos de etiqueta para una Reparación o Confección.

    Estas etiquetas van prendidas a la prenda del cliente mientras está en el
    taller, así que lo que importa es de quién es y qué trabajo lleva.
    """
    cliente = getattr(obj, 'cliente', None)
    nombre = '—'
    if cliente:
        nombre = f"{cliente.nombres} {cliente.apellido_paterno}".strip()
    return datos_muestra({
        'codigo':     obj.codigo,
        'prenda':     nombre,
        'subtitulo':  servicio,
        'detalle':    '',
        'talla':      '',
        'color':      '',
        'modelo':     '',
        'referencia': '',
        'condicion':  '',
        'ubicacion':  '',
        'precio':     '',
        'cliente':    nombre,
        'servicio':   servicio,
    })


def sustituir(texto, datos):
    """Reemplaza {campo} por su valor. Un campo desconocido queda tal cual.

    Se hace a mano y no con str.format porque una llave suelta escrita por el
    usuario ("50% {oferta") reventaría el format, y acá simplemente se ignora.
    """
    resultado = _texto_o_vacio(texto)
    for clave, valor in (datos or {}).items():
        resultado = resultado.replace('{' + clave + '}', _texto_o_vacio(valor))
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de elementos
#
# El JSON viene del navegador, así que puede traer cualquier cosa: strings donde
# van números, claves faltantes, valores fuera de rango. Se normaliza UNA vez,
# acá, y los dos renderers reciben elementos ya validados. Así es imposible que
# el PDF y el ZPL interpreten distinto el mismo campo, que es exactamente el
# tipo de divergencia que el usuario descubriría con la etiqueta ya pegada.
# ─────────────────────────────────────────────────────────────────────────────

TIPOS = ('texto', 'barcode', 'simbolo', 'caja', 'linea')

# Fuentes. En PDF se mapean a las tres familias base de PostScript; en ZPL no
# hay familias (sólo la escalable ^A0), así que allá el campo se ignora. Está
# documentado en el diseñador para que no sorprenda.
FUENTES = {
    'sans':  ('Helvetica', 'Helvetica-Bold'),
    'serif': ('Times-Roman', 'Times-Bold'),
    'mono':  ('Courier', 'Courier-Bold'),
}
FUENTE_DEFECTO = 'sans'

ALINEACIONES = ('izquierda', 'centro', 'derecha')
ROTACIONES = ('N', 'R', 'I', 'B')          # normal, 90°, 180°, 270°
SIMBOLOGIAS = ('code128', 'code39', 'ean13', 'qr')


def _entero(origen, clave, defecto=0, minimo=None, maximo=None):
    try:
        valor = int(float(origen.get(clave, defecto)))
    except (TypeError, ValueError):
        valor = int(defecto)
    if minimo is not None:
        valor = max(minimo, valor)
    if maximo is not None:
        valor = min(maximo, valor)
    return valor


def _decimal(origen, clave, defecto=0.0, minimo=None, maximo=None):
    try:
        valor = float(origen.get(clave, defecto))
    except (TypeError, ValueError):
        valor = float(defecto)
    if minimo is not None:
        valor = max(minimo, valor)
    if maximo is not None:
        valor = min(maximo, valor)
    return valor


def _opcion(origen, clave, permitidas, defecto):
    valor = str(origen.get(clave, defecto) or defecto).lower()
    return valor if valor in permitidas else defecto


def normalizar_elemento(bruto, ancho_etiqueta):
    """Deja un elemento con todas sus claves, del tipo correcto y en rango.

    Devuelve None si el elemento no es representable (tipo desconocido). Los
    renderers pueden asumir que todo lo que sale de acá es dibujable.
    """
    if not isinstance(bruto, dict):
        return None

    tipo = str(bruto.get('tipo', 'texto')).lower()
    if tipo not in TIPOS:
        return None

    el = {
        'tipo': tipo,
        'x': _entero(bruto, 'x', 0, minimo=0),
        'y': _entero(bruto, 'y', 0, minimo=0),
        'rotacion': str(bruto.get('rotacion', 'N')).upper(),
        # Metadatos del editor. `visible` sí afecta al render —una capa apagada
        # no se imprime, que es cómo se prueban variantes de un diseño sin tener
        # que borrar elementos—. `nombre` y `bloqueado` son sólo para el editor,
        # pero se guardan igual: si se perdieran al grabar, el usuario abriría la
        # plantilla al día siguiente con todas las capas desbloqueadas y sin
        # nombre, y pensaría que se rompió algo.
        'visible': bruto.get('visible', True) is not False,
        'bloqueado': bool(bruto.get('bloqueado', False)),
        'nombre': _texto_o_vacio(bruto.get('nombre', ''))[:60],
    }
    if el['rotacion'] not in ROTACIONES:
        el['rotacion'] = 'N'

    if tipo == 'texto':
        el.update({
            'texto': _texto_o_vacio(bruto.get('texto', '')),
            'tamano': _entero(bruto, 'tamano', 24, minimo=6, maximo=400),
            'fuente': _opcion(bruto, 'fuente', FUENTES, FUENTE_DEFECTO),
            'negrita': bool(bruto.get('negrita', False)),
            'alineacion': _opcion(bruto, 'alineacion', ALINEACIONES, 'izquierda'),
            'renglones': _entero(bruto, 'renglones', 1, minimo=1, maximo=9),
            # Letter-spacing. Es lo que le da el aire de etiqueta textil a la
            # marca. Sólo lo aplica el PDF: ZPL no sabe separar caracteres.
            'tracking': _decimal(bruto, 'tracking', 0.0, minimo=0.0, maximo=40.0),
            # Achicar la letra hasta que entre en el ancho del bloque, en vez de
            # cortar el texto. Un nombre de prenda largo entra igual, más chico.
            'autoajustar': bool(bruto.get('autoajustar', False)),
            'tamano_min': _entero(bruto, 'tamano_min', 10, minimo=4, maximo=400),
        })
        # Sin ancho de bloque explícito, el texto usa lo que queda de etiqueta a
        # su derecha.
        el['ancho_bloque'] = _entero(
            bruto, 'ancho_bloque', 0, minimo=0
        ) or max(1, int(ancho_etiqueta) - el['x'])
        if el['tamano_min'] > el['tamano']:
            el['tamano_min'] = el['tamano']

    elif tipo == 'barcode':
        el.update({
            'texto': _texto_o_vacio(bruto.get('texto', '{codigo}')) or '{codigo}',
            'simbologia': _opcion(bruto, 'simbologia', SIMBOLOGIAS, 'code128'),
            'modulo': _entero(bruto, 'modulo', 2, minimo=1, maximo=10),
            'alto_barra': _entero(bruto, 'alto_barra', 100, minimo=10, maximo=800),
            'mostrar_texto': bool(bruto.get('mostrar_texto', True)),
            'centrar': bool(bruto.get('centrar', False)),
            'tamano_texto': _entero(bruto, 'tamano_texto', 18, minimo=6, maximo=100),
        })
        if el['simbologia'] == 'qr':
            el['alto_barra'] = max(58, el['alto_barra'])

    elif tipo == 'simbolo':
        el.update({
            'clave': str(bruto.get('clave', '')),
            'tam': _entero(bruto, 'tam', 48, minimo=16, maximo=300),
            'leyenda': _texto_o_vacio(bruto.get('leyenda', '')),
            'leyenda_lado': 'derecha' if bruto.get('leyenda_lado') == 'derecha' else 'abajo',
            'tam_leyenda': _entero(bruto, 'tam_leyenda', 14, minimo=4, maximo=100),
        })

    elif tipo == 'linea':
        orientacion = 'vertical' if bruto.get('orientacion') == 'vertical' else 'horizontal'
        # Compatibilidad con el primer prototipo, que guardaba ancho/alto.
        largo_defecto = bruto.get('alto' if orientacion == 'vertical' else 'ancho', 120)
        el.update({
            'orientacion': orientacion,
            'largo': _entero(bruto, 'largo', largo_defecto, minimo=1, maximo=4000),
            'grosor': _entero(bruto, 'grosor', 2, minimo=1, maximo=50),
        })

    elif tipo == 'caja':
        # PDF y ZPL representan cajas por ancho/alto; no existe una rotación
        # equivalente en ambos caminos. Una línea vertical se expresa invirtiendo
        # sus dimensiones, no con una vista previa que luego imprima distinto.
        el['rotacion'] = 'N'
        el.update({
            'ancho': _entero(bruto, 'ancho', 200, minimo=1, maximo=4000),
            'alto': _entero(bruto, 'alto', 2, minimo=1, maximo=4000),
            'grosor': _entero(bruto, 'grosor', 2, minimo=1, maximo=200),
            'redondeo': _entero(bruto, 'redondeo', 0, minimo=0, maximo=100),
            'relleno': bool(bruto.get('relleno', False)),
        })

    return el


def normalizar(elementos, ancho_etiqueta=ANCHO_DEFECTO, solo_visibles=True):
    """Normaliza la lista entera, descartando lo que no se puede dibujar.

    `solo_visibles=False` la usa el editor, que necesita las capas apagadas para
    poder volver a encenderlas. Los renderers usan el valor por defecto.
    """
    salida = []
    for bruto in (elementos or []):
        el = normalizar_elemento(bruto, ancho_etiqueta)
        if el is None:
            continue
        if solo_visibles and not el['visible']:
            continue
        salida.append(el)
    return salida


# ─────────────────────────────────────────────────────────────────────────────
# Ancho de un Code 128
#
# Un Code 128 subset B ocupa 35 módulos fijos (arranque + checksum + cierre) más
# 11 por carácter. Multiplicado por el ancho de módulo da el ancho real en
# puntos. Lo necesitan los dos renderers: el ZPL para centrar y elegir grosor de
# barra, y la validación para rechazar códigos que no entran.
# ─────────────────────────────────────────────────────────────────────────────

def modulos_code128(dato):
    return 35 + 11 * len(dato)


def ancho_code128(dato, modulo):
    return modulos_code128(dato) * modulo


class DatoNoImprimible(ValueError):
    """El contenido no se puede codificar o no entra en la etiqueta."""


def validar_code128(dato, ancho_etiqueta=ANCHO_DEFECTO):
    """Comprueba que el texto entre en un Code 128 B y quepa en la etiqueta.

    El subset B cubre ASCII 32..126. Una tilde o una ñ no tienen representación:
    la impresora, según el firmware, las omite o rechaza la etiqueta entera, y
    en los dos casos sale un código que la pistola no lee.

    Se valida acá y no en cada vista porque todos los caminos que imprimen
    —diseñador, lote, exportación— tienen que pasar por el mismo control.
    """
    dato = _texto_o_vacio(dato).strip()
    if not dato:
        raise DatoNoImprimible("El código de barras está vacío.")

    malos = sorted({c for c in dato if not 32 <= ord(c) <= 126})
    if malos:
        raise DatoNoImprimible(
            "El código tiene caracteres que Code 128 no puede representar: "
            + " ".join(f"«{c}»" for c in malos)
        )

    # Con el módulo más fino posible (1 punto). Si ni así entra, no hay diseño
    # que lo arregle: hay que acortar el código.
    if ancho_code128(dato, 1) > int(ancho_etiqueta):
        raise DatoNoImprimible(
            f"«{dato}» es demasiado largo: ni con la barra más fina entra en "
            f"los {puntos_a_mm(ancho_etiqueta):g} mm de ancho de la etiqueta."
        )
    return dato


def validar_elementos(elementos, datos, ancho_etiqueta=ANCHO_DEFECTO):
    """Valida los códigos de barras de una plantilla ya sustituida.

    Se corre ANTES de imprimir: una etiqueta ilegible se descubre cuando la
    pistola no la lee, y para entonces ya está pegada a la prenda.
    """
    for el in normalizar(elementos, ancho_etiqueta):
        if el['tipo'] != 'barcode':
            continue
        dato = sustituir(el['texto'], datos).strip()
        if el['simbologia'] == 'qr':
            from . import etiquetas_qr
            try:
                etiquetas_qr.validar(dato, el['alto_barra'])
            except etiquetas_qr.QrNoCabe as exc:
                raise DatoNoImprimible(str(exc)) from exc
            continue
        validar_code128(dato, ancho_etiqueta)


# ─────────────────────────────────────────────────────────────────────────────
# Plantilla de fábrica
#
# Es la transcripción del diseño que hasta ahora estaba clavado en
# `views._draw_etiqueta()`: marca en dos niveles, filete, nombre de prenda,
# subtítulo, símbolos de cuidado, código de barras y código legible.
#
# Se conserva como punto de partida editable, no como diseño fijo: el usuario
# abre el diseñador y encuentra la etiqueta que ya conoce, y de ahí la mueve.
# Las coordenadas están calculadas para 50 × 30 mm (400 × 240 puntos).
# ─────────────────────────────────────────────────────────────────────────────

def elementos_por_defecto():
    return [
        # Marco fino y aireado, como una etiqueta textil de gama alta.
        {'tipo': 'caja', 'x': 6, 'y': 6, 'ancho': 388, 'alto': 228,
         'grosor': 2, 'redondeo': 7},

        # Firma en dos niveles. La serif aporta el contraste editorial; la sans
        # espaciada debajo mantiene legibilidad en térmica.
        {'tipo': 'texto', 'x': 24, 'y': 14, 'ancho_bloque': 352,
         'texto': 'FORTIUM', 'fuente': 'serif', 'negrita': True,
         'tamano': 24, 'tracking': 5, 'alineacion': 'centro'},
        {'tipo': 'texto', 'x': 24, 'y': 41, 'ancho_bloque': 352,
         'texto': 'TAILOR', 'fuente': 'sans', 'negrita': True,
         'tamano': 11, 'tracking': 3.5, 'alineacion': 'centro'},
        {'tipo': 'caja', 'x': 44, 'y': 58, 'ancho': 312, 'alto': 2, 'grosor': 2},

        # Nombre de la prenda. Se achica solo si es largo, en vez de cortarse.
        {'tipo': 'texto', 'x': 24, 'y': 66, 'ancho_bloque': 352,
         'texto': '{prenda}', 'fuente': 'serif', 'negrita': True,
         'tamano': 26, 'tamano_min': 16, 'autoajustar': True,
         'alineacion': 'centro'},
        {'tipo': 'texto', 'x': 24, 'y': 98, 'ancho_bloque': 352,
         'texto': '{subtitulo}', 'fuente': 'sans',
         'tamano': 14, 'tracking': 2, 'autoajustar': True, 'tamano_min': 10,
         'alineacion': 'centro'},

        # Símbolos de cuidado: limpieza en seco, no usar cloro, plancha suave.
        {'tipo': 'simbolo', 'x': 92, 'y': 140, 'tam': 30, 'clave': 'seco_p',
         'leyenda': 'SECO', 'tam_leyenda': 10},
        {'tipo': 'simbolo', 'x': 185, 'y': 140, 'tam': 30, 'clave': 'no_blanquear',
         'leyenda': 'SIN CLORO', 'tam_leyenda': 10},
        {'tipo': 'simbolo', 'x': 278, 'y': 140, 'tam': 30, 'clave': 'planchar_1',
         'leyenda': 'SUAVE', 'tam_leyenda': 10},

        # Trazabilidad. Es lo único operativo que lleva la etiqueta: sin precios
        # ni fechas, que envejecen mal pegados a una prenda.
        {'tipo': 'barcode', 'x': 0, 'y': 188, 'texto': '{codigo}',
         'simbologia': 'code128', 'modulo': 2, 'alto_barra': 24,
         'mostrar_texto': False, 'centrar': True},
        {'tipo': 'texto', 'x': 24, 'y': 216, 'ancho_bloque': 352,
         'texto': '{codigo}', 'fuente': 'sans',
         'tamano': 14, 'tracking': 1, 'alineacion': 'centro'},
    ]


def elementos_textil_vertical():
    """Diseño técnico vertical inspirado en etiquetas interiores de sastrería."""
    return [
        {'tipo': 'caja', 'x': 8, 'y': 8, 'ancho': 384, 'alto': 783,
         'grosor': 2, 'nombre': 'Marco exterior'},

        {'tipo': 'texto', 'x': 24, 'y': 24, 'ancho_bloque': 352,
         'texto': '{taller}', 'fuente': 'serif', 'negrita': True,
         'tamano': 32, 'tamano_min': 20, 'autoajustar': True,
         'alineacion': 'centro', 'nombre': 'Marca'},
        {'tipo': 'linea', 'x': 20, 'y': 76, 'largo': 360, 'grosor': 2,
         'nombre': 'Divisor de marca'},

        {'tipo': 'texto', 'x': 30, 'y': 94, 'ancho_bloque': 170,
         'texto': 'Talla', 'fuente': 'serif', 'negrita': True, 'tamano': 22,
         'alineacion': 'centro', 'nombre': 'Título talla'},
        {'tipo': 'linea', 'x': 214, 'y': 84, 'largo': 58, 'grosor': 2,
         'orientacion': 'vertical', 'nombre': 'Divisor de talla'},
        {'tipo': 'texto', 'x': 232, 'y': 94, 'ancho_bloque': 138,
         'texto': '{talla}', 'fuente': 'serif', 'negrita': True, 'tamano': 22,
         'alineacion': 'centro', 'nombre': 'Valor talla'},
        {'tipo': 'linea', 'x': 20, 'y': 148, 'largo': 360, 'grosor': 2,
         'nombre': 'Divisor de talla inferior'},

        {'tipo': 'texto', 'x': 28, 'y': 164, 'ancho_bloque': 344,
         'texto': 'Orden / Código  :  {codigo}', 'fuente': 'serif', 'tamano': 15,
         'autoajustar': True, 'tamano_min': 10, 'nombre': 'Orden de corte'},
        {'tipo': 'texto', 'x': 28, 'y': 190, 'ancho_bloque': 344,
         'texto': 'Modelo             :  {modelo}', 'fuente': 'serif', 'tamano': 15,
         'autoajustar': True, 'tamano_min': 10, 'nombre': 'Modelo'},
        {'tipo': 'texto', 'x': 28, 'y': 216, 'ancho_bloque': 344,
         'texto': 'Código tela       :  {referencia}', 'fuente': 'serif', 'tamano': 15,
         'autoajustar': True, 'tamano_min': 10, 'nombre': 'Código de tela'},
        {'tipo': 'texto', 'x': 28, 'y': 242, 'ancho_bloque': 344,
         'texto': 'Color                :  {color}', 'fuente': 'serif', 'tamano': 15,
         'autoajustar': True, 'tamano_min': 10, 'nombre': 'Color'},
        {'tipo': 'linea', 'x': 20, 'y': 276, 'largo': 360, 'grosor': 2,
         'nombre': 'Divisor de datos'},

        {'tipo': 'texto', 'x': 28, 'y': 290, 'ancho_bloque': 344,
         'texto': 'Composición de tela', 'fuente': 'serif', 'tamano': 16,
         'alineacion': 'centro', 'nombre': 'Título composición'},
        {'tipo': 'texto', 'x': 28, 'y': 318, 'ancho_bloque': 344,
         'texto': '100% LANA', 'fuente': 'serif', 'negrita': True, 'tamano': 22,
         'alineacion': 'centro', 'nombre': 'Composición'},
        {'tipo': 'linea', 'x': 20, 'y': 356, 'largo': 360, 'grosor': 2,
         'nombre': 'Divisor de composición'},

        {'tipo': 'texto', 'x': 28, 'y': 372, 'ancho_bloque': 344,
         'texto': 'Instrucciones de cuidado', 'fuente': 'serif', 'tamano': 16,
         'alineacion': 'centro', 'nombre': 'Título cuidados'},
        {'tipo': 'simbolo', 'x': 42, 'y': 406, 'tam': 38, 'clave': 'no_lavar',
         'nombre': 'No lavar'},
        {'tipo': 'simbolo', 'x': 111, 'y': 406, 'tam': 38, 'clave': 'no_blanquear',
         'nombre': 'No blanquear'},
        {'tipo': 'simbolo', 'x': 180, 'y': 406, 'tam': 38, 'clave': 'no_secadora',
         'nombre': 'No usar secadora'},
        {'tipo': 'simbolo', 'x': 249, 'y': 406, 'tam': 38, 'clave': 'planchar_1',
         'nombre': 'Plancha suave'},
        {'tipo': 'simbolo', 'x': 318, 'y': 406, 'tam': 38, 'clave': 'seco_p',
         'nombre': 'Limpieza P'},
        {'tipo': 'linea', 'x': 20, 'y': 466, 'largo': 360, 'grosor': 2,
         'nombre': 'Divisor de cuidados'},

        {'tipo': 'barcode', 'x': 0, 'y': 500, 'texto': '{codigo}',
         'simbologia': 'code128', 'modulo': 1, 'alto_barra': 96,
         'mostrar_texto': False, 'centrar': True, 'nombre': 'Código de barras'},
        {'tipo': 'texto', 'x': 28, 'y': 606, 'ancho_bloque': 344,
         'texto': '{codigo}', 'fuente': 'mono', 'tamano': 14,
         'alineacion': 'centro', 'nombre': 'Código legible'},
        {'tipo': 'linea', 'x': 20, 'y': 638, 'largo': 360, 'grosor': 2,
         'nombre': 'Divisor de pie'},
        {'tipo': 'texto', 'x': 28, 'y': 710, 'ancho_bloque': 344,
         'texto': 'HECHO EN BOLIVIA', 'fuente': 'serif', 'negrita': True,
         'tamano': 19, 'alineacion': 'centro', 'nombre': 'Origen'},
    ]


def escalar(elementos, factor):
    """Reescala una plantilla entera por un factor.

    Sirve para pasar un diseño de un tamaño de rollo a otro sin rehacerlo. Se
    usa UN solo factor y no uno por eje a propósito: escalar la X distinto que
    la Y deformaría los símbolos de cuidado (que son cuadrados por norma) y
    descuadraría la relación entre alto de barra y ancho de módulo.
    """
    factor = float(factor)
    if factor <= 0:
        return list(elementos or [])

    # Qué claves son medidas y hay que escalar. Las que no están acá (texto,
    # alineación, simbología, renglones…) se copian tal cual.
    MEDIDAS = (
        'x', 'y', 'ancho', 'alto', 'grosor', 'redondeo', 'ancho_bloque',
        'tamano', 'tamano_min', 'tracking', 'tam', 'tam_leyenda',
        'alto_barra', 'tamano_texto', 'largo',
    )

    salida = []
    for bruto in (elementos or []):
        if not isinstance(bruto, dict):
            continue
        el = dict(bruto)
        for clave in MEDIDAS:
            if clave not in el:
                continue
            try:
                valor = float(el[clave]) * factor
            except (TypeError, ValueError):
                continue
            # El tracking admite decimales; el resto son puntos enteros.
            el[clave] = round(valor, 2) if clave == 'tracking' else int(round(valor))
        # El ancho de módulo del código de barras es un entero chico (1..10):
        # escalarlo linealmente lo saca de rango enseguida, así que se ajusta
        # aparte y con tope.
        if 'modulo' in el:
            try:
                el['modulo'] = max(1, min(10, int(round(float(el['modulo']) * factor))))
            except (TypeError, ValueError):
                pass
        salida.append(el)
    return salida
