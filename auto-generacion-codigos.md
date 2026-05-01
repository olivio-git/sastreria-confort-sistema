# Plan: Estandarizar auto-generación de códigos

## Objetivo

Unificar todos los modelos al patrón `model.save()` + campo oculto en formularios + código visible en el mensaje de éxito tras la creación.

---

## Estado actual

| Modelo | Cómo genera el código | Campo en formulario |
|--------|----------------------|--------------------|
| Empleado | `model.save()` ✅ | Oculto ✅ |
| Cliente | `model.save()` ✅ | Oculto ✅ |
| Inventario | `model.save()` ✅ | Oculto ✅ |
| Venta | `model.save()` ✅ | Visible editable ❌ |
| Alquiler | `form.__init__()` ⚠️ | Visible readonly ❌ |
| Transacción | `form.__init__()` ⚠️ | Visible readonly ❌ |
| Confección | `form.__init__()` ⚠️ | Visible editable ❌ |
| **Reparación** | **Ninguno** ❌ | **Manual libre** ❌ |

---

## Patrón objetivo (ya implementado en Empleado/Cliente/Inventario)

```python
# models.py — generar en save()
def save(self, *args, **kwargs):
    if not self.codigo:
        last = Modelo.objects.order_by('-id').first()
        numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
        self.codigo = f"PRE-{numero:03d}"
    super().save(*args, **kwargs)
```

```python
# forms.py — quitar 'codigo' de fields[]
fields = ['campo1', 'campo2', ...]  # sin 'codigo'
```

```python
# views.py — capturar instancia y mostrar código en mensaje
obj = form.save()
messages.success(request, f"Registro {obj.codigo} creado con éxito.")
```

---

## Cambios por modelo

### Reparación — URGENTE (actualmente roto, código es manual)

**models.py** — agregar `save()`:
```python
def save(self, *args, **kwargs):
    if not self.codigo:
        last = Reparacion.objects.order_by('-id').first()
        numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
        self.codigo = f"REP-{numero:03d}"
    super().save(*args, **kwargs)
```

**forms.py** — quitar `'codigo'` de `ReparacionForm.fields`.
Quitar también el widget de `codigo` del dict `widgets`.

**views.py** — `crear_reparacion`:
```python
reparacion = form.save()
messages.success(request, f"Reparación {reparacion.codigo} creada con éxito.")
```

---

### Confección — URGENTE (genera en form.__init__, no en modelo)

**models.py** — agregar `save()` a `Confeccion`:
```python
def save(self, *args, **kwargs):
    if not self.codigo:
        last = Confeccion.objects.order_by('-id').first()
        numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
        self.codigo = f"CON-{numero:03d}"
    self.saldo = self.precio - self.adelanto
    super().save(*args, **kwargs)
```

> Nota: el prefijo actual en el form es `CONF-`, decidir si estandarizar a `CON-` o mantener `CONF-`. Verificar con datos existentes en BD antes de cambiar.

**forms.py** — en `ConfeccionForm`:
- Quitar `'codigo'` de `fields`
- Quitar `__init__` con la lógica de `self.initial['codigo']`
- Quitar el método `clean_codigo`

**views.py** — `crear_confeccion`:
```python
confeccion = form.save()
messages.success(request, f"Confección {confeccion.codigo} creada con éxito.")
```

---

### Alquiler — menor (funciona pero genera en form, bug potencial de concurrencia)

**models.py** — `Alquiler.save()` ya existe, agregar la generación al inicio:
```python
if not self.codigo:
    last = Alquiler.objects.order_by('-id').first()
    numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
    self.codigo = f"ALQ-{numero:03d}"
```

**forms.py** — en `AlquilerForm`:
- Quitar `'codigo'` de `fields`
- Quitar `__init__` con `self.initial['codigo']`
- Quitar el widget de `codigo`

**views.py** — `crear_alquiler`:
```python
alquiler = form.save()
messages.success(request, f"Alquiler {alquiler.codigo} creado con éxito.")
```

---

### Transacción — menor (mismo problema que Alquiler)

**models.py** — `Transaccion.save()` ya existe, mover generación al inicio del bloque `if not self.codigo`:
- Ya está implementado correctamente en `save()`. Solo quitar del form.

**forms.py** — en `TransaccionForm`:
- Quitar `'codigo'` de `fields`
- Quitar `__init__` con `self.initial['codigo']`
- Quitar el widget de `codigo`

**views.py** — `crear_transaccion`:
```python
transaccion = form.save()
messages.success(request, f"Transacción {transaccion.codigo} creada con éxito.")
```

---

### Venta — menor (genera en save(), pero el form muestra el campo)

**forms.py** — en `VentaForm`:
- Quitar `'codigo'` de `fields`
- Quitar validación `clean_codigo` (el `startswith('VEN-')`)

**views.py** — `crear_venta`:
```python
venta = form.save()
messages.success(request, f"Venta {venta.codigo} creada con éxito.")
```

---

## Orden de implementación recomendado

1. **Reparación** — caso roto, prioridad máxima
2. **Confección** — caso roto, prioridad máxima
3. **Venta** — cosmético, el save() ya funciona
4. **Alquiler** — cosmético, mover lógica al modelo
5. **Transacción** — cosmético, mover lógica al modelo

---

## Archivos afectados

| Archivo | Qué cambia |
|---------|-----------|
| `misastreria/models.py` | Agregar `save()` a Reparacion y Confeccion; mover lógica de codigo de Alquiler al inicio |
| `misastreria/forms.py` | Quitar campo `codigo` de ReparacionForm, ConfeccionForm, VentaForm, AlquilerForm, TransaccionForm |
| `misastreria/views.py` | Capturar instancia en `crear_*` y mostrar `obj.codigo` en mensaje de éxito |

No hay migraciones necesarias — los campos `codigo` ya existen en todos los modelos.
