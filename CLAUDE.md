# Convenciones de desarrollo — Fortium Tailor

## Stack
- Django 5.2 / Python 3.13
- Bootstrap 5.3 + Bootstrap Icons 1.11
- CSS propio: `misastreria/static/css/main.css`
- JS propio: `misastreria/static/js/sistema.js`
- SQLite en local (`settings_local.py`), MySQL en producción
- Docker Compose local: Django en puerto 8001, MySQL en 3306

---

## Sistema de diseño (CSS variables)

Todas las vistas usan las variables definidas en `main.css`. Nunca usar colores
hardcodeados ni clases de Bootstrap inline que contradigan el sistema.

```
--primary:       #2563eb   (azul principal — botones, links, activo)
--primary-dark:  #1e3a8a   (navbar izquierda)
--primary-light: #dbeafe   (fondos suaves)
--success:       #10b981   (verde — botón "Nuevo", navbar derecha)
--danger:        #ef4444
--warning:       #f59e0b
--info:          #06b6d4
--bg:            #f1f5f9   (fondo general de página)
--surface:       #ffffff   (fondo de cards, tablas, filtros)
--border:        #e2e8f0
--text:          #1e293b
--text-muted:    #64748b
--radius:        0.5rem
--shadow:        sutil (1-3px)
--shadow-md:     un poco más pronunciado (navbar, dropdowns)
```

---

## Estructura de plantillas de lista

Toda vista de lista sigue **exactamente** este esqueleto:

```html
{% extends 'misastreria/base.html' %}
{% block titulo %}Nombre Módulo{% endblock %}
{% block contenido %}

<!-- 1. Encabezado de página -->
<div class="page-header">
  <h1 class="page-title"><i class="bi bi-ICONO me-2"></i>Título</h1>
  <a href="{% url 'crear_X' %}" class="btn btn-success btn-sm">
    <i class="bi bi-plus-lg me-1"></i>Nuevo X
  </a>
</div>

<!-- 2. Barra de filtros -->
<form method="get" class="filter-bar" id="filterForm">
  <!-- campos de búsqueda / selects / fechas -->
  <!-- date-shortcuts si aplica -->
  <!-- botón Limpiar siempre al final -->
</form>

<!-- 3. Tabla con wrapper -->
<div class="table-wrapper">
  <table class="table table-hover">
    <thead>...</thead>
    <tbody>
      {% for obj in page_obj %}
      <tr>...</tr>
      {% empty %}
      <tr>
        <td colspan="N">
          <div class="empty-state">
            <i class="bi bi-ICONO d-block"></i>
            Mensaje sin resultados.
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <!-- 4. Pie de tabla: total + paginación -->
  <div class="pagination-bar">
    <span>{{ total }} registro{{ total|pluralize }}</span>
    <nav>
      <ul class="pagination pagination-sm mb-0">
        {% if page_obj.has_previous %}
          <li class="page-item"><a class="page-link" href="?page=1&...">«</a></li>
          <li class="page-item"><a class="page-link" href="?page={{ page_obj.previous_page_number }}&...">‹</a></li>
        {% endif %}
        <li class="page-item active">
          <span class="page-link">{{ page_obj.number }} / {{ page_obj.paginator.num_pages }}</span>
        </li>
        {% if page_obj.has_next %}
          <li class="page-item"><a class="page-link" href="?page={{ page_obj.next_page_number }}&...">›</a></li>
          <li class="page-item"><a class="page-link" href="?page={{ page_obj.paginator.num_pages }}&...">»</a></li>
        {% endif %}
      </ul>
    </nav>
  </div>
</div>
{% endblock %}
```

### Reglas de plantilla
- **Nunca** `container py-4` ni estilos inline de fondo (`style="background-color:..."`)
- La plantilla base ya envuelve todo en `.page-container` (max 1400px, padding 1.5rem)
- Los mensajes de Django se renderizan en `base.html` — no duplicarlos en las vistas hijas
- `{% load static %}` ya está en `base.html`; no repetirlo salvo en `{% block extra_js %}`

---

## Barra de filtros

```html
<form method="get" class="filter-bar">
  <div class="filter-group" style="flex:1;min-width:180px">
    <label>Buscar</label>
    <input type="text" name="q" class="form-control"
           placeholder="..." value="{{ q }}" data-debounce="400">
  </div>

  <!-- selects de estado / tipo -->
  <div class="filter-group">
    <label>Estado</label>
    <select name="estado" class="form-select" data-debounce="0">
      <option value="">Todos</option>
      ...
    </select>
  </div>

  <!-- rango de fechas -->
  <div class="filter-group">
    <label>Desde</label>
    <input type="date" name="desde" class="form-control" value="{{ desde }}">
  </div>
  <div class="filter-group">
    <label>Hasta</label>
    <input type="date" name="hasta" class="form-control" value="{{ hasta }}">
  </div>

  <!-- acciones: shortcuts + limpiar -->
  <div class="filter-group justify-content-end">
    <label class="invisible">.</label>
    <div class="d-flex gap-2 flex-wrap">
      <div class="date-shortcuts">
        <a href="?periodo=semana" class="btn btn-outline-secondary {% if periodo == 'semana' %}active{% endif %}">Semana</a>
        <a href="?periodo=mes"    class="btn btn-outline-secondary {% if periodo == 'mes' %}active{% endif %}">Mes</a>
        <a href="?periodo=3meses" class="btn btn-outline-secondary {% if periodo == '3meses' or not periodo %}active{% endif %}">3 meses</a>
      </div>
      <a href="{% url 'lista_X' %}" class="btn btn-outline-secondary">Limpiar</a>
    </div>
  </div>
</form>
```

- `data-debounce="400"` en el campo de texto → auto-submit después de 400ms
- `data-debounce="0"` en selects → auto-submit inmediato al cambiar
- Los módulos con datos temporales (reparaciones, ventas, confecciones, alquileres,
  transacciones) usan `date-shortcuts`
- Inventario y Clientes **no** usan `date-shortcuts` (no son datos temporales)

---

## Badges de estado

Usar siempre la clase doble `badge-estado badge-<valor>`. El valor viene directo
del campo del modelo en minúsculas (o el valor de la choice).

```html
<span class="badge-estado badge-{{ obj.estado }}">{{ obj.get_estado_display }}</span>
```

| Clase CSS           | Fondo      | Texto      | Uso                          |
|---------------------|------------|------------|------------------------------|
| `badge-pendiente`   | amarillo   | café oscuro| Reparaciones, confecciones   |
| `badge-en_proceso`  | azul claro | azul oscuro| En proceso                   |
| `badge-entregado`   | verde claro| verde oscuro| Entregado / Activo / Ingreso |
| `badge-alquilado`   | azul claro | azul oscuro| Alquileres activos           |
| `badge-devuelto`    | verde claro| verde oscuro| Devuelto                     |
| `badge-activo`      | verde claro| verde oscuro| Empleados activos            |
| `badge-inactivo`    | rojo claro | rojo oscuro | Empleados inactivos          |

Para badges de modelos que no tienen clase directa (ej. Transaccion tipo `ingreso`/`gasto`,
Inventario `ACT`/`BAJ`) se mapea manualmente en el template:

```html
<!-- Transaccion -->
<span class="badge-estado {% if t.tipo_transaccion == 'ingreso' %}badge-entregado{% else %}badge-pendiente{% endif %}">

<!-- Inventario -->
<span class="badge-estado {% if inv.estado == 'ACT' %}badge-entregado{% else %}badge-inactivo{% endif %}">
```

---

## Botones de acción en tabla

```html
<div class="btn-actions">
  <!-- solo iconos, sin texto, con title para tooltip -->
  <a href="..." class="btn btn-sm btn-outline-primary"   title="Editar">   <i class="bi bi-pencil"></i></a>
  <a href="..." class="btn btn-sm btn-outline-secondary" title="PDF">      <i class="bi bi-file-pdf"></i></a>
  <a href="..." class="btn btn-sm btn-outline-success"   title="Acción">   <i class="bi bi-check-circle"></i></a>
  <a href="..." class="btn btn-sm btn-outline-danger"    title="Eliminar"> <i class="bi bi-trash"></i></a>
</div>
```

Orden estándar: **Editar → PDF/Recibo → Acción especial → Eliminar**

---

## Patrón de vistas (views.py)

```python
@login_required
def lista_X(request):
    q        = request.GET.get('q', '').strip()
    estado   = request.GET.get('estado', '').strip()   # si aplica
    desde    = request.GET.get('desde', '').strip()
    hasta    = request.GET.get('hasta', '').strip()
    periodo  = request.GET.get('periodo', '').strip()

    hoy = date.today()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat(); hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat(); hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    qs = ModeloX.objects.all().order_by('-campo_fecha')
    if q:
        qs = qs.filter(Q(codigo__icontains=q) | Q(cliente__nombres__icontains=q) | ...)
    if estado:
        qs = qs.filter(estado=estado)
    if desde:
        qs = qs.filter(campo_fecha__gte=desde)
    if hasta:
        qs = qs.filter(campo_fecha__lte=hasta)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/X/lista.html', {
        'page_obj': page_obj,
        'total':    total,
        'q':        q,
        'estado':   estado,
        'desde':    desde,
        'hasta':    hasta,
        'periodo':  periodo,
        'estado_choices': ModeloX.ESTADO_CHOICES,
    })
```

### Reglas de vista
- Orden descendente siempre: `-campo_fecha` o `-creado`
- Paginación: **15 registros** por página
- Sin `print()` de debug en ninguna vista
- El filtro de 3 meses es el **default** para módulos de servicio
  (reparaciones, ventas, confecciones, alquileres, transacciones)
- Inventario y Clientes **no** tienen filtro de fecha por defecto
- Inventario muestra `estado=ACT` por defecto
- `buscar_clientes` (endpoint AJAX) no lleva `@login_required` para permitir
  autocomplete desde formularios

---

## Navbar activo

En `base.html`, el link activo de la navbar se detecta con:

```html
class="nav-link {% if request.resolver_match.url_name == 'dashboard' %}active{% endif %}"
```

Solo el dashboard usa esta técnica actualmente. Los demás links no marcan activo
(posible mejora futura sin urgencia).

---

## JS — comportamientos automáticos (sistema.js)

| Atributo HTML                        | Comportamiento                                              |
|--------------------------------------|-------------------------------------------------------------|
| `data-debounce="N"`                  | Auto-submit del form padre tras N ms sin escribir           |
| `data-debounce="0"` en `<select>`    | Submit inmediato al cambiar el select                       |
| `data-col-toggle="tableId"`          | Dropdown para mostrar/ocultar columnas (estado en localStorage) |
| `data-cliente-search="hiddenInputId"`| Autocomplete AJAX contra `/clientes/buscar/` con 300ms debounce |

El JS se carga globalmente desde `base.html` — no repetirlo en `{% block extra_js %}`.

---

## Autocomplete de cliente en formularios

Los formularios que requieren seleccionar un cliente usan el widget de autocomplete:

```html
<!-- Campo visible para tipear -->
<input type="text" data-cliente-search="id_cliente"
       data-endpoint="{% url 'buscar_clientes' %}"
       class="form-control" placeholder="Buscar cliente…">
<!-- Campo oculto que guarda el ID -->
<input type="hidden" name="cliente" id="id_cliente" value="{{ form.cliente.value|default:'' }}">
```

El endpoint `buscar_clientes` devuelve JSON `[{id, ci, nombre}]` (top 10).

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `misastreria/static/css/main.css` | Sistema de diseño completo (variables, componentes) |
| `misastreria/static/js/sistema.js` | Debounce, column toggle, cliente autocomplete |
| `misastreria/templates/misastreria/base.html` | Layout base, navbar, mensajes globales |
| `misastreria/views.py` | Todas las vistas (un solo archivo, ~1100 líneas) |
| `misastreria/urls.py` | Todas las rutas del módulo |
| `misastreria/models.py` | Todos los modelos |
| `misastreria/forms.py` | Todos los formularios |
| `sastreria/settings_local.py` | Config local (SQLite, DEBUG=True) — **no commiteado** |

## Excepciones a JS inline en templates

En casos donde el estado visual debe restaurarse **antes del primer render**
para evitar flash (ej. checkboxes que persisten en localStorage), se permite
un `<script>` inline mínimo junto al elemento, únicamente para setear
el estado inicial. Toda lógica de comportamiento sigue en `sistema.js`.

Ejemplo aceptado:
<script>
  if (localStorage.getItem('auto_buscar') !== 'false')
    document.getElementById('toggleAutoBuscar').checked = true;
</script>