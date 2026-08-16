# Imprimir etiquetas desde el sistema en la PC del taller

El sistema corre en un servidor Linux que no puede tocar la impresora del taller. Este puente
es un programita que corre **en la PC que tiene la SAT conectada por USB** y recibe las
etiquetas desde el navegador. Se instala una vez y queda arrancando solo.

Mientras el puente esté corriendo, el botón **Imprimir** del diseñador manda etiquetas de
verdad. Si no está corriendo, el sistema ofrece descargar el `.zpl` como antes.

## Camino rápido

1. Instalá Python 3 desde [python.org](https://www.python.org/downloads/windows/), marcando
   **«Add python.exe to PATH»** en la primera pantalla del instalador.
2. Abrí PowerShell en esta carpeta y ejecutá:
   ```powershell
   pip install pywin32
   python puente.py
   ```
3. Tiene que aparecer esto:
   ```
   Puente de impresión escuchando en http://127.0.0.1:9101
   Impresora: SAT TT460 UE (203 dpi) (ZPL)
   Ctrl+C para cerrar.
   ```
4. Entrá al diseñador en el sistema y apretá **Imprimir**. Sale la etiqueta.

Si en el paso 3 aparece un **AVISO** de que Windows no ve la impresora, seguí a
[La impresora tiene otro nombre](#la-impresora-tiene-otro-nombre).

## Que arranque solo con Windows

Sin esto hay que abrir PowerShell cada mañana.

1. Apretá `Win + R`, escribí `shell:startup` y Enter. Se abre una carpeta.
2. Creá ahí un archivo `puente.bat` con este contenido, corrigiendo la ruta:
   ```bat
   @echo off
   pythonw "C:\ruta\a\puente_impresion\puente.py"
   ```

`pythonw` en vez de `python` hace que corra sin dejar una ventana negra abierta.

## Problemas

### La impresora tiene otro nombre

El nombre tiene que coincidir **exacto** con el de Windows. Para ver la lista:

```powershell
python puente.py --listar
```

Después arrancá con el nombre que corresponda:

```powershell
python puente.py --impresora "SAT TT460 UE"
```

### El botón Imprimir dice que no encuentra el puente

| Revisá | Cómo |
|---|---|
| ¿Está corriendo? | Abrí <http://127.0.0.1:9101/estado> en el navegador. Tiene que devolver un JSON con `"ok": true`. |
| ¿El navegador es el de esta PC? | El puente sólo atiende pedidos de la misma máquina. Desde otra PC del taller no funciona. |
| ¿Lo bloqueó el navegador? | Chrome puede bloquear pedidos a direcciones locales. Probá en Firefox para descartar. |

### Sale la etiqueta pero se lee mal

Eso no es problema del puente: es la configuración del cabezal. Se ajusta desde el sistema,
en **Etiquetas → Calibrar**. Subí la oscuridad de a 4 y bajá la velocidad hasta que se lea bien.

## Checklist de instalación

- [ ] `python --version` responde con 3.x
- [ ] `pip install pywin32` terminó sin errores
- [ ] `python puente.py --listar` muestra la SAT en la lista
- [ ] `python puente.py` arranca sin AVISO
- [ ] <http://127.0.0.1:9101/estado> devuelve `"conectada": true`
- [ ] El botón **Imprimir** del diseñador saca papel
- [ ] `puente.bat` está en la carpeta de inicio y sobrevive a un reinicio

## Detalles técnicos

| Tema | Decisión |
|---|---|
| Escucha en | `127.0.0.1` solamente — ninguna otra PC de la red puede mandar trabajos |
| Puerto | `9101`, cambiable con `--puerto` |
| Orígenes aceptados | Sólo los de la lista `ORIGENES` en `puente.py` |
| Envío | `win32print` en modo RAW, para que el driver no reinterprete el ZPL |
| Dependencias | `pywin32`. Todo lo demás es biblioteca estándar |
