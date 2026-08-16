# Puente de impresión — notas técnicas

Programa que corre en la PC del taller y le manda ZPL a la impresora de
etiquetas. Existe porque el servidor de producción es Linux y está detrás del
NAT del taller: nunca va a poder abrir el puerto USB de la SAT.

**Para instalarlo en el taller no uses este archivo** — usá
[INSTALACION.md](INSTALACION.md), que está escrito para el usuario final.

## Cómo circula una etiqueta

```
servidor Django  ──(genera el ZPL)──>  navegador
                                          │
                                          │  POST http://127.0.0.1:9101/imprimir
                                          ▼
                                       puente  ──win32print RAW──>  SAT TT460
```

El servidor sigue haciendo lo único que puede hacer bien desde lejos: generar el
ZPL. El puente hace lo único que el servidor no puede: hablarle al USB.

En el navegador, el botón Imprimir degrada en tres pasos (`etiquetas.js`):

1. el puente local
2. impresión por el servidor — sólo sirve si Django corre en esa misma PC
3. aviso para descargar el `.zpl` a mano

## Sacar una versión nueva para el cliente

El `.exe` lo compila GitHub Actions, porque PyInstaller no compila cruzado y el
desarrollo es en Linux.

| Quiero… | Hago… | El archivo queda en… |
|---|---|---|
| Compilar cuando sea | Actions → «Puente de impresión» → **Run workflow** | Artifacts del run |
| Probar un cambio | push tocando `puente_impresion/**` | Artifacts del run |
| Entregarle algo al cliente | tag `puente-v*` sobre un commit que toque `puente_impresion/**` | Releases, con el `.exe` adjunto |

El camino que siempre funciona es el botón **Run workflow**. El del tag depende
de que el commit etiquetado haya tocado `puente_impresion/**`, porque el filtro
`paths` también se evalúa en los tags.

## Decisiones y por qué

| Tema | Decisión | Motivo |
|---|---|---|
| Distribución | Un `.exe` con `--onefile --noconsole` | El usuario es sastre: no instala Python ni abre terminales |
| Ícono | Se dibuja con Pillow en memoria | Mantiene el `.exe` como archivo único, sin recursos sueltos que se pierdan |
| Elección de impresora | Autodetección por nombre (`TT460`, `SAT`, `ZPL`…) | Escribir mal el nombre era el fallo nº1, y era silencioso |
| Config | `%APPDATA%\FortiumTailor\puente.json` | Al lado del `.exe` Windows puede negar la escritura |
| Arranque automático | `HKCU\...\Run`, sólo la primera vez | `HKCU` no pide permiso de administrador; después manda lo que elija el usuario |
| Escucha en | `127.0.0.1` únicamente | Ninguna otra PC de la red puede mandar trabajos |
| Autorización | Lista blanca de `Origin` | Que una página cualquiera no pueda gastar el rollo |
| Puerto ocupado | Cartel «ya está funcionando» y salir | Doble clic dos veces es lo más probable, y no es un error |

## Detalle que cuesta caro olvidar

El puente contesta el preflight de **Private Network Access** con
`Access-Control-Allow-Private-Network: true`.

Sin ese header, Chrome corta el pedido de una página HTTPS a `localhost` en el
preflight y nunca llega al servidor. Se ve como «el puente no responde» aunque
esté perfectamente levantado.

## Endpoints

| Método | Ruta | Devuelve |
|---|---|---|
| `GET` | `/estado` | `{ok, version, impresora, conectada}` |
| `POST` | `/imprimir` | Cuerpo: ZPL en texto plano. Devuelve `{ok, mensaje}` |

## Correrlo sin compilar (desarrollo, en Windows)

```powershell
pip install -r requirements.txt
python puente.py
```
