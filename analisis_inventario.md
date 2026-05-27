# Análisis general — Fortium Tailor
# Modelos de datos, formularios y hoja de ruta de servicios

---

## 1. El problema central: formularios de ítem único

Todos los servicios actuales (Alquiler, Venta, Confección, Reparación) están modelados como
formularios de un solo artículo / una sola acción. Eso no refleja la realidad:

- Un cliente alquila **un traje + camisa + corbata + chaleco** en una sola operación
- Una venta puede incluir **varios artículos**
- Una confección a veces es **saco + pantalón** (el traje completo)
- Una reparación puede tener **varias tareas sobre la misma prenda** (cambiar cierre + acotar)

El modelo correcto para esto es el **patrón Pedido-Detalle** (header / line items),
estándar en cualquier sistema de comercio o servicio:

```
Pedido (cabecera)              DetallePedido (líneas)
─────────────────              ──────────────────────
cliente                        pedido FK
fecha                          artículo / descripción
descuento %                    cantidad
subtotal                       precio unitario
total                          subtotal (cantidad × precio)
estado
notas
```

La cabecera tiene los datos del cliente y la operación global.
Cada línea tiene un artículo, cantidad y precio.
El total se calcula sumando las líneas y aplicando el descuento.

---

## 2. Qué servicio necesita pedido-detalle y qué no

| Servicio     | ¿Multi-ítem? | Razón                                                          |
|--------------|:------------:|----------------------------------------------------------------|
| Alquiler     | ✅ SÍ        | Un cliente lleva varios artículos en una sola operación        |
| Venta        | ✅ SÍ        | Se pueden vender varios artículos juntos                       |
| Confección   | ⚠️ QUIZÁS   | Normalmente una prenda, pero un "traje" es saco+pantalón       |
| Reparación   | ⚠️ QUIZÁS   | Una prenda, pero puede tener múltiples tareas/trabajos         |
| Transacción  | ❌ NO        | Es un registro contable, no un pedido                          |

Recomendación: empezar con Alquiler y Venta (impacto inmediato).
Confección y Reparación pueden hacerse en una segunda etapa.

---

## 3. Modelo propuesto — Alquiler con multi-ítem

```python
class Alquiler(models.Model):
    # Cabecera
    codigo          # auto ALQ-001
    cliente         # FK nullable
    fecha_alquiler
    fecha_devolucion
    descuento       # DecimalField, porcentaje (0-100), default 0
    subtotal        # calculado: suma de líneas
    total           # subtotal × (1 - descuento/100)
    estado          # alquilado / devuelto / parcial
    notas
    empleado        # FK nullable

class AlquilerItem(models.Model):
    # Líneas
    alquiler        # FK → Alquiler
    articulo        # FK → Inventario (prenda_alquiler)
    cantidad
    precio_unitario # se copia del inventario pero editable
    subtotal        # cantidad × precio_unitario (calculado)
```

El formulario en pantalla sería:

```
┌─ Datos del alquiler ──────────────────────────────────┐
│ Cliente: [autocomplete]   Fecha alquiler: [date]       │
│ Fecha devolución: [date]  Empleado: [select]           │
│ Notas: [textarea]                                      │
└────────────────────────────────────────────────────────┘

┌─ Artículos ────────────────────────────────────────────┐
│ Artículo          │ Cant │ Precio unit │ Subtotal │ [-] │
│ [Traje Negro T42] │  1   │   150.00    │  150.00  │ ×   │
│ [Camisa Blanca]   │  1   │    50.00    │   50.00  │ ×   │
│ [Corbata]         │  2   │    20.00    │   40.00  │ ×   │
│ [+ Agregar artículo]                                   │
├────────────────────────────────────────────────────────┤
│                        Subtotal:         240.00        │
│                        Descuento:  [5] % -12.00        │
│                        Total:            228.00        │
└────────────────────────────────────────────────────────┘
```

El mismo patrón aplica a Venta.

---

## 4. Modelo de Inventario — separar en dos modelos

El `Inventario` actual mezcla conceptos que tienen lógica diferente.
La solución es separarlo:

### 4a. PrendaInventario (lo que se vende o alquila)

Las prendas también pueden tener su propio código de referencia, igual que las telas.
En el rubro se llama **código de modelo** o **referencia de estilo** — puede ser un código
del proveedor, del fabricante, o interno del negocio. No siempre existe, por eso es nullable.

Ejemplos reales:
- Un traje de proveedor con código `SM-2024-042`
- Una camisa con referencia `CAM-BL-38` (camisa blanca talla 38)
- Una prenda sin código → simplemente `"Smoking / Negro / T40"`

```python
class PrendaInventario(models.Model):
    TIPO = [
        ('venta',    'Para Venta'),
        ('alquiler', 'Para Alquiler'),
    ]
    CONDICION = [
        ('nueva',  'Nueva'),
        ('usada',  'Usada'),
        ('remate', 'Remate'),
    ]
    codigo              # auto (interno del sistema)
    tipo                # venta / alquiler
    nombre              # "Traje de Novio", "Smoking", "Vestido"
    modelo              # nullable — nombre de modelo/línea: "Classic", "Slim Fit"
    talla               # nullable — "40", "M", "XL"
    color               # nullable — "Negro", "Azul marino"
    codigo_referencia   # nullable — código externo: "SM-2024-042", "CAM-BL-38"
    condicion           # nueva / usada / remate (solo aplica a tipo=alquiler)
    veces_alquilado     # PositiveIntegerField, default 0 — se incrementa automáticamente
    cantidad            # stock actual
    stock_minimo        # nullable
    precio              # precio actual (el dueño lo ajusta según condición)
    estado              # ACT / BAJ
    notas
```

`__str__` inteligente:
- Si tiene código de referencia → `"Traje SM-2024-042 / Negro / T42"`
- Si no → `"Traje de Novio / Negro / T42"`
- Resuelve el problema de los "TRAJE TRAJE TRAJE" en los selectores.

### 4a-bis. Ciclo de vida de prendas de alquiler

El ciclo que describe el negocio:

```
Nueva (precio: 100) ──→ Usada (precio: 75) ──→ Remate (precio: 50) ──→ Vendida / Baja
       ↑ compra                ↑ tras N alquileres         ↑ fin de vida útil
```

**¿Quién decide el cambio de condición?**
El dueño — no el sistema automáticamente. El sistema muestra `veces_alquilado`
como referencia, pero el dueño decide cuándo bajar la condición y ajustar el precio.
Esto es intencional: no todos los artículos envejecen igual.

**¿Cómo se ve en la lista de inventario?**

| Prenda              | Condición | Veces alquilado | Precio |
|---------------------|-----------|:---------------:|--------|
| Traje Negro T42     | Nueva     | 2               | 100.00 |
| Traje Negro T42     | Usada     | 14              | 75.00  |
| Smoking Blanco T40  | Remate    | 28              | 50.00  |

**El remate como salida:** cuando una prenda llega a condición `remate`,
puede pasar a `tipo=venta` y aparecer en el selector de Ventas a precio rebajado.
Eso la saca del ciclo de alquiler y la convierte en venta directa.

**Tracking individual vs. por lote:**
Si hay 3 trajes negros T42 idénticos, hay dos opciones:

| Opción | Cómo se registra | Ventaja | Limitación |
|--------|-----------------|---------|------------|
| Por lote | Un registro con `cantidad=3` | Simple | `veces_alquilado` es el total del lote, no por pieza |
| Individual | Tres registros con `cantidad=1` cada uno | Tracking exacto por pieza | Más registros, más gestión |

**Recomendación:** para prendas de alto valor (trajes de novio, smokings),
registrar individual — cada pieza tiene su propia condición y contador.
Para accesorios de bajo valor (corbatas, pañuelos), registrar por lote.
El campo `notas` puede usarse para distinguir piezas: "Traje N°1", "Traje N°2".

### 4b. Insumo (materia prima — telas, hilos, accesorios)

Separado de prendas porque tiene lógica diferente:
se mide en metros/kg, tiene referencia de proveedor, tiene colección.

```python
class Insumo(models.Model):
    TIPO_MATERIAL = [
        ('tela',      'Tela'),
        ('hilo',      'Hilo'),
        ('accesorio', 'Accesorio'),   # botones, cierres, cremalleras
        ('entretela', 'Entretela'),
        ('otro',      'Otro'),
    ]
    UNIDAD_MEDIDA = [
        ('metro',  'Metro'),
        ('kg',     'Kilogramo'),
        ('unidad', 'Unidad'),
        ('rollo',  'Rollo'),
    ]

    codigo              # auto INS-001
    tipo_material       # choices arriba
    articulo            # nombre base: "Tela", "Hilo poliéster", "Botón"
    coleccion           # nullable — el "cuaderno": "Paramount", "Elegance"
    color               # nullable — "Azul", "Negro", "Crudo"
    codigo_referencia   # nullable — "029292-1-2233" (código del proveedor/rollo)
    tipo_tela           # nullable — "Gabardina", "Tafetán", "Seda", "Lino"
    unidad_medida       # choices
    cantidad            # DecimalField (para metros con fracciones)
    stock_minimo        # nullable
    precio_costo        # nullable — precio por metro/kg/unidad
    estado              # ACT / BAJ
    proveedor           # CharField nullable
    notas
```

`__str__` inteligente:
- Si tiene colección y color → `"Paramount / Azul"`
- Si tiene código de referencia → `"Tela 029292-1-2233"`
- Fallback → `"Gabardina Negra"`

---

## 5. Flujo de Producción (Corte → Costura → Terminado)

Este es el flujo interno que el cliente hace manualmente en hojas.
Modelado como `OrdenProduccion`:

```python
class OrdenProduccion(models.Model):
    ESTADO = [
        ('corte',     'En Corte'),
        ('costura',   'En Costura'),
        ('terminado', 'Terminado'),
    ]

    codigo              # auto PROD-001
    descripcion         # qué se está haciendo
    confeccion          # FK nullable — si es para un pedido de cliente
    estado              # corte / costura / terminado
    fecha_inicio
    fecha_estimada      # nullable
    empleado            # FK nullable
    notas

    # Cuando terminado, el resultado puede:
    # a) Quedar vinculado a la confeccion (entrega directa al cliente)
    # b) Entrar a PrendaInventario (stock propio)
    resultado_inventario  # FK nullable → PrendaInventario
```

**Insumos consumidos** (cuando el flujo madure):
```python
class InsumoCortado(models.Model):
    orden       # FK → OrdenProduccion
    insumo      # FK → Insumo
    cantidad    # cuánto se usó (metros, unidades)
```

Esto permite saber cuánta tela se consumió por orden, y descontar del stock de insumos.

---

## 6. Funcionalidades especiales del módulo Alquiler

### 6a. Búsqueda/filtro por atributos de prenda

En la lista de alquileres se quiere poder buscar o filtrar no solo por cliente o código,
sino por atributos de la prenda alquilada: **color, talla, nombre/tipo de prenda**.

Esto es natural una vez que `AlquilerItem` apunta a `PrendaInventario` (que tiene color,
talla y nombre estructurados). Los filtros en la lista de alquileres se extienden para incluir:

```
[Buscar: texto libre]  [Color: ___]  [Talla: ___]  [Prenda: ___]  [Estado]  [Período]
```

Implementación: filtros sobre `items__articulo__color`, `items__articulo__talla`, etc.
En tanto el modelo `PrendaInventario` tenga esos campos, el filtro es directo.

---

### 6b. "Confeccionar similar a este alquiler"

Si a un cliente le gustó lo que alquiló y quiere encargarse una prenda confeccionada
a medida similar, el flujo sería:

```
Lista de alquileres
  └─ [botón: Confeccionar similar]
       └─ Abre formulario de nueva Confección
            pre-cargado con:
              - cliente (del alquiler)
              - tipo de prenda (del artículo alquilado)
              - color (del artículo alquilado)
            editable:
              - todas las medidas (porque es a medida, no el mismo talle)
              - precio, fecha entrega, empleado, etc.
```

El botón en la tabla de alquileres navega a `crear_confeccion?desde_alquiler=<id>`.
La view de confección detecta el parámetro, consulta el alquiler y pre-llena los campos
correspondientes. El usuario puede modificar cualquier dato antes de guardar.

**Qué se copia del alquiler:**
- Cliente → se pre-selecciona en el autocomplete
- Tipo de prenda → se pre-selecciona
- Color → se pre-llena si existe en el formulario de confección
- Observaciones → opcionalmente un texto automático: "Basado en alquiler ALQ-042"

**Qué NO se copia:**
- Medidas (son del cliente, no de la prenda alquilada — aunque si el cliente ya tiene
  medidas registradas en su historial, podrían traerse de ahí en el futuro)
- Precio (la confección tiene otro costo que el alquiler)

Este flujo es una acción de un clic que ahorra re-ingresar datos y crea una trazabilidad
natural entre el alquiler que inspiró la confección y el pedido resultante.

---

## 7. Mapa de servicios del navbar y sus dependencias

```
Servicios actuales:
  Clientes        → sin dependencias externas, está bien
  Empleados       → sin dependencias externas, está bien
  Reparaciones    → funciona, mejora futura: multi-tarea
  Transacciones   → funciona, no necesita cambios estructurales

Servicios que necesitan refactor antes de avanzar:
  Ventas          → necesita PrendaInventario + patrón multi-ítem
  Alquileres      → necesita PrendaInventario + patrón multi-ítem
  Confecciones    → mejora con Insumos, posible multi-pieza

Servicios nuevos posibles:
  Insumos/Telas   → modelo Insumo (independiente, no bloquea nada)
  Producción      → OrdenProduccion (depende de Insumo)
  Inventario v2   → PrendaInventario reemplaza Inventario actual
```

---

## 7. Hoja de ruta — en qué orden atacar

### Etapa 1 — Bases (desbloquea todo lo demás)
1. Crear modelo `PrendaInventario` (reemplaza `Inventario` actual con migración limpia)
2. Crear modelo `Insumo` (nuevo, independiente)
3. Migrar datos existentes de `Inventario` → `PrendaInventario`

### Etapa 2 — Refactor de servicios principales
4. Refactorizar `Alquiler` con patrón multi-ítem (AlquilerItem)
5. Refactorizar `Venta` con patrón multi-ítem (VentaItem)
6. Actualizar selectores para usar `PrendaInventario` filtrado por tipo

### Etapa 3 — Producción
7. Crear `OrdenProduccion` con flujo Corte → Costura → Terminado
8. Vincular a `Confeccion` y opcionalmente a `PrendaInventario`
9. Consumo de `Insumo` por orden (InsumoCortado)

### Etapa 4 — Mejoras
10. Reparaciones multi-tarea
11. Confecciones multi-pieza
12. Alertas de stock mínimo (Insumo y PrendaInventario)
13. Reportes de costo de materiales

---

## 8. Lo que NO hacer todavía

- BOM automático vinculado a cada confección (muy complejo, poco valor ahora)
- Tracking individual por prenda de alquiler (número de serie, historial de lavados)
- Módulo de proveedores / compras
- Múltiples almacenes o sucursales
