"""Lógica de comisiones de empleados independiente de Django views/migraciones.

Se separa de views.py para poder testearse sin base de datos y para que la
migración de datos 0065 (backfill de AplicacionPagoComision) pueda reusar el
mismo algoritmo de reparto FIFO sin importar modelos de la app directamente
(las migraciones deben usar `apps.get_model`, nunca un import directo — los
modelos históricos de una migración no son los mismos objetos Python que los
de `misastreria.models`).

Por eso `asignar_pagos_fifo` no recibe modelos ni querysets: recibe listas ya
armadas y ordenadas por quien llama (la migración con `apps.get_model`, los
tests con los modelos reales), y una función `aplicar` por cada devengación
que decide cómo persistir la aplicación. Así esta función queda pura.
"""
from decimal import Decimal


def estado_asignacion(monto_comision_fijo, pagado):
    """Estado de una fila de asignación según cuánto de su comisión se pagó.

    'pendiente' si no se pagó nada, 'pagada' si se pagó todo (o más, por
    redondeo — no debería pasar pero no hay que reventar si pasa), 'parcial'
    en cualquier otro caso.
    """
    monto_comision_fijo = monto_comision_fijo or Decimal('0')
    pagado = pagado or Decimal('0')
    if pagado <= 0:
        return 'pendiente'
    if pagado >= monto_comision_fijo:
        return 'pagada'
    return 'parcial'


ESTADO_BADGE = {
    'pagada': 'badge-entregado',
    'parcial': 'badge-en_proceso',
    'pendiente': 'badge-pendiente',
}


def estado_filtro(estado):
    """Agrupa 'pagada' en un lado y 'pendiente'/'parcial' en el otro, para el
    chip de filtro Pendientes/Pagadas/Todas del detalle de empleado."""
    return 'pagada' if estado == 'pagada' else 'pendiente'


def asignar_pagos_fifo(pagos, accruals, monto_de=None):
    """Reparte `pagos` entre `accruals` en orden FIFO por ambos lados.

    pagos: iterable de objetos con `.monto`, YA ordenados cronológicamente
           ascendente (el más viejo primero) por quien llama.
    monto_de: callable(pago) -> Decimal opcional con cuánto de cada pago hay
              que repartir. Por defecto `pago.monto`; la migración 0066 pasa
              el REMANENTE sin aplicar de cada pago (monto − lo ya aplicado)
              para que re-correrla sólo reparta lo que falta (idempotencia
              por remanente, no por "tiene alguna aplicación").
    accruals: lista de dicts YA ordenados oldest-first, cada uno con:
        - 'saldo': Decimal, cuánto de esa devengación falta por cubrir
                   (monto_comision_fijo menos lo ya aplicado, si se está
                   retomando una corrida anterior — así la función es
                   idempotente si quien llama excluye pagos ya aplicados y
                   ajusta los saldos de arranque en consecuencia).
        - 'aplicar': callable(pago, monto) que persiste la aplicación
                     (crea el AplicacionPagoComision con la FK correcta).

    No avanza el índice de `accruals` hacia atrás entre pagos: una devengación
    ya agotada por un pago anterior no vuelve a recibir plata de uno
    posterior. Devuelve el sobrante total que no pudo aplicarse a ninguna
    devengación (pagos que exceden lo devengado vigente).
    """
    idx = 0
    n = len(accruals)
    sobrante = Decimal('0')
    for pago in pagos:
        restante = Decimal(monto_de(pago) if monto_de else pago.monto)
        while restante > 0:
            while idx < n and accruals[idx]['saldo'] <= 0:
                idx += 1
            if idx >= n:
                sobrante += restante
                restante = Decimal('0')
                break
            take = min(restante, accruals[idx]['saldo'])
            if take > 0:
                accruals[idx]['aplicar'](pago, take)
                accruals[idx]['saldo'] -= take
                restante -= take
    return sobrante


def parsear_clave_devengacion(clave, tipos_validos):
    """Normaliza una clave "tipo:id" del modal de pago a (tipo, int(id)).

    Rechaza (ValueError) cualquier cosa que no sea exactamente un tipo
    conocido, dos puntos y dígitos ASCII. "reparacion:05" y "reparacion:5"
    devuelven la MISMA tupla: así quien llama puede deduplicar ANTES de
    resolver y no cobrar dos veces la misma devengación con claves repetidas
    o escritas distinto.
    """
    partes = (clave or '').split(':', 1)
    if len(partes) != 2:
        raise ValueError(f"Selección inválida: «{clave}».")
    tipo, id_str = partes
    if tipo not in tipos_validos or not id_str or not all('0' <= ch <= '9' for ch in id_str):
        raise ValueError(f"Selección inválida: «{clave}».")
    id_num = int(id_str)
    if id_num <= 0:
        raise ValueError(f"Selección inválida: «{clave}».")
    return tipo, id_num


def _nombre_cliente(cliente):
    """Nombre del cliente armado desde sus campos (no `str()`: en una
    migración el modelo histórico no tiene el __str__ del modelo real)."""
    if cliente is None:
        return ''
    partes = [
        getattr(cliente, 'nombres', '') or '',
        getattr(cliente, 'apellido_paterno', '') or '',
        getattr(cliente, 'apellido_materno', '') or '',
    ]
    return ' '.join(p for p in partes if p).strip()


def detalle_snapshot(tipo_key, fila, max_length=200):
    """Texto descriptivo de una devengación (fila de asignación) para
    `AplicacionPagoComision.detalle_snapshot`: tipo, código de la operación,
    prenda/arreglo o responsabilidad, cliente y comisión.

    Se arma SÓLO con atributos de campo (nada de `str(modelo)`), así sirve
    igual para los modelos reales (pago) y los históricos de la migración
    0066. Se trunca a `max_length`: en MySQL estricto un texto más largo que
    la columna es un error 500, no un recorte silencioso.
    """
    partes = []
    if tipo_key == 'reparacion':
        op = fila.reparacion
        partes = [f'Reparación {op.codigo}', _nombre_cliente(getattr(op, 'cliente', None))]
    elif tipo_key == 'confeccion':
        op = fila.confeccion
        partes = [f'Confección {op.codigo}', _nombre_cliente(getattr(op, 'cliente', None))]
    elif tipo_key in ('venta', 'alquiler'):
        item = fila.venta_item if tipo_key == 'venta' else fila.alquiler_item
        op = item.venta if tipo_key == 'venta' else item.alquiler
        prenda = getattr(item, 'prenda_item', None)
        tipo_rep = getattr(item, 'tipo_reparacion', None)
        partes = [
            f"{'Arreglo venta' if tipo_key == 'venta' else 'Arreglo alquiler'} {op.codigo}",
            f"prenda {prenda.codigo_item}" if prenda is not None and prenda.codigo_item else '',
            getattr(tipo_rep, 'nombre', '') if tipo_rep is not None else '',
            _nombre_cliente(getattr(op, 'cliente', None)),
        ]
    elif tipo_key == 'produccion':
        partes = [f'Producción {fila.orden.codigo}', fila.get_responsabilidad_display()]
    monto = fila.monto_comision_fijo
    if monto is not None:
        partes.append(f"comisión Bs {Decimal(monto):.2f}")
    texto = ' — '.join(str(p) for p in partes if p)
    if len(texto) > max_length:
        texto = texto[:max_length - 1] + '…'
    return texto


def valor_excel_seguro(valor):
    """Neutraliza la inyección de fórmulas en celdas de texto de Excel: un
    texto que el usuario cargó (cliente, descripción, snapshot) y empieza con
    = + - @ (o tab/CR) se prefija con ' para que Excel lo trate como texto."""
    if isinstance(valor, str) and valor and valor[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + valor
    return valor
