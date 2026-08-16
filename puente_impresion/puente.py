"""Puente de impresión de etiquetas — corre en la PC del taller.

──────────────────────────────────────────────────────────────────────────────
Por qué existe
──────────────────────────────────────────────────────────────────────────────
La impresora está colgada del USB de esta PC. El servidor de fortiumtailor.com
es Linux y está en otra red, detrás del NAT del taller: nunca va a poder abrir
ese puerto USB, por más que se arregle el código del servidor.

El que sí está al lado de la impresora es el NAVEGADOR. Así que el camino real
de una etiqueta es:

    servidor  ──(genera el ZPL)──>  navegador  ──(HTTP a localhost)──>  puente
                                                                          │
                                                                    win32print
                                                                          │
                                                                       SAT TT460

──────────────────────────────────────────────────────────────────────────────
Para quién está escrito
──────────────────────────────────────────────────────────────────────────────
El usuario final es un sastre, no un técnico. Por eso este programa:

  · se distribuye como UN solo .exe, sin instalar Python ni nada;
  · no abre ninguna ventana de consola;
  · busca la impresora solo, sin que nadie escriba su nombre;
  · se anota solo para arrancar con Windows la primera vez;
  · vive como un ícono al lado del reloj, verde si está todo bien;
  · avisa los problemas en castellano, sin jerga.

Todo mensaje que pueda llegar a ver el usuario tiene que decirle QUÉ HACER,
no qué falló. «No encuentro la impresora, fijate que esté prendida» sirve;
«WinError 1801» no.

──────────────────────────────────────────────────────────────────────────────
Seguridad
──────────────────────────────────────────────────────────────────────────────
Escucha SÓLO en 127.0.0.1, así que nadie de la red del taller puede mandarle
trabajos: únicamente los programas de esta misma máquina. Además exige que el
pedido venga de un origen conocido, para que ninguna página abierta de casualidad
pueda gastar el rollo entero.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = '2.0'
PUERTO = 9101

# Desde qué páginas se aceptan trabajos de impresión.
ORIGENES = {
    'https://fortiumtailor.com',
    'https://www.fortiumtailor.com',
    'http://localhost:8001',
    'http://127.0.0.1:8001',
}

# Con qué palabras se reconoce una impresora de etiquetas entre todas las que
# tenga instaladas la PC. Se prueban en orden: primero lo más específico.
PISTAS_IMPRESORA = ('TT460', 'SAT ', 'ZPL', 'ZEBRA', 'ETIQUET', 'LABEL')

NOMBRE_ARRANQUE = 'FortiumTailorPuente'


def carpeta_config():
    """%APPDATA%\\FortiumTailor, creada si no está.

    La config no va al lado del .exe porque el usuario lo puede dejar en el
    Escritorio o en Descargas, y ahí Windows puede negarle la escritura.
    """
    base = Path(os.environ.get('APPDATA') or Path.home()) / 'FortiumTailor'
    base.mkdir(parents=True, exist_ok=True)
    return base


ARCHIVO_CONFIG = carpeta_config() / 'puente.json'


def leer_config():
    try:
        return json.loads(ARCHIVO_CONFIG.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def guardar_config(datos):
    try:
        ARCHIVO_CONFIG.write_text(json.dumps(datos, indent=2), encoding='utf-8')
    except OSError:
        pass  # Sin config guardada sigue funcionando; sólo no recuerda la elección.


# ─────────────────────────────────────────────────────────────────────────────
# Impresora
# ─────────────────────────────────────────────────────────────────────────────

class ErrorDeImpresion(RuntimeError):
    """Algo impidió mandar el trabajo. El mensaje va derecho al usuario."""


def _win32print():
    try:
        import win32print
    except ImportError as exc:
        raise ErrorDeImpresion(
            "Este programa sólo funciona en Windows, que es donde está "
            "conectada la impresora."
        ) from exc
    return win32print


def listar_impresoras():
    win32print = _win32print()
    banderas = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(banderas)]


def impresora_por_defecto():
    try:
        return _win32print().GetDefaultPrinter()
    except Exception:
        return None


def detectar_impresora():
    """Elige la impresora sola, para que nadie tenga que escribir su nombre.

    Escribir mal el nombre era el motivo nº1 de «no imprime y no dice por qué».
    El orden es: la que el usuario ya eligió, la que parece de etiquetas por el
    nombre, y por último la predeterminada de Windows.
    """
    try:
        disponibles = listar_impresoras()
    except ErrorDeImpresion:
        return None

    if not disponibles:
        return None

    elegida = leer_config().get('impresora')
    if elegida in disponibles:
        return elegida

    for pista in PISTAS_IMPRESORA:
        for nombre in disponibles:
            if pista in nombre.upper():
                return nombre

    predeterminada = impresora_por_defecto()
    return predeterminada if predeterminada in disponibles else disponibles[0]


def enviar(zpl, impresora):
    """Escribe el ZPL en la cola de la impresora en modo RAW.

    RAW hace que Windows pase los bytes tal cual, sin que el driver intente
    interpretarlos como un dibujo. Es la diferencia entre que la SAT reciba
    comandos ZPL y que reciba una foto de esos comandos.
    """
    win32print = _win32print()
    datos = zpl.encode('utf-8', errors='replace')

    try:
        h = win32print.OpenPrinter(impresora)
    except Exception as exc:
        raise ErrorDeImpresion(
            f"No se pudo usar «{impresora}». Fijate que esté prendida y "
            f"enchufada al USB."
        ) from exc

    try:
        trabajo = win32print.StartDocPrinter(h, 1, ("Etiqueta", None, 'RAW'))
        try:
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, datos)
            win32print.EndPagePrinter(h)
        finally:
            win32print.EndDocPrinter(h)
    finally:
        win32print.ClosePrinter(h)

    return trabajo


ZPL_PRUEBA = (
    "^XA^CI28"
    "^FO30,30^A0N,40,40^FDFORTIUM TAILOR^FS"
    "^FO30,90^A0N,28,28^FDPuente de impresion OK^FS"
    "^FO30,140^BY2^BCN,60,N,N,N^FDPRUEBA123^FS"
    "^PQ1^XZ"
)


# ─────────────────────────────────────────────────────────────────────────────
# Arranque automático con Windows
# ─────────────────────────────────────────────────────────────────────────────

def _ruta_ejecutable():
    """El comando que Windows tiene que correr para levantar esto de nuevo."""
    if getattr(sys, 'frozen', False):        # empaquetado con PyInstaller
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def arranque_activo():
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Run',
        ) as clave:
            winreg.QueryValueEx(clave, NOMBRE_ARRANQUE)
            return True
    except (OSError, FileNotFoundError):
        return False


def fijar_arranque(activar):
    """Anota o borra el programa del arranque de Windows.

    Va en HKEY_CURRENT_USER y no en LOCAL_MACHINE porque así no hace falta
    permiso de administrador: el sastre abre el .exe y listo.
    """
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Run',
            0, winreg.KEY_SET_VALUE,
        ) as clave:
            if activar:
                winreg.SetValueEx(clave, NOMBRE_ARRANQUE, 0, winreg.REG_SZ,
                                  _ruta_ejecutable())
            else:
                try:
                    winreg.DeleteValue(clave, NOMBRE_ARRANQUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Servidor HTTP
# ─────────────────────────────────────────────────────────────────────────────

class Estado:
    """Lo que el ícono necesita saber, compartido con el servidor."""
    impresora = None
    ultimo_error = ''
    etiquetas_impresas = 0


class Manejador(BaseHTTPRequestHandler):

    def _cors(self):
        origen = self.headers.get('Origin')
        if origen in ORIGENES:
            self.send_header('Access-Control-Allow-Origin', origen)
            self.send_header('Vary', 'Origin')

    def _json(self, codigo, cuerpo):
        datos = json.dumps(cuerpo).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(datos)))
        self._cors()
        self.end_headers()
        self.wfile.write(datos)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        # Chrome exige este permiso explícito cuando una página pública pide algo
        # a una dirección de red privada (Private Network Access). Sin él, el
        # fetch a localhost muere en el preflight sin llegar nunca acá.
        if self.headers.get('Access-Control-Request-Private-Network'):
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip('/') != '/estado':
            self._json(404, {'ok': False, 'error': 'Ruta no encontrada.'})
            return
        self._json(200, {
            'ok': True,
            'version': VERSION,
            'impresora': Estado.impresora,
            'conectada': bool(Estado.impresora),
        })

    def do_POST(self):
        if self.path.rstrip('/') != '/imprimir':
            self._json(404, {'ok': False, 'error': 'Ruta no encontrada.'})
            return

        if self.headers.get('Origin') not in ORIGENES:
            self._json(403, {'ok': False, 'error': 'Origen no autorizado.'})
            return

        try:
            largo = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            largo = 0
        # 5 MB es holgadísimo para ZPL, que es texto plano.
        if largo <= 0 or largo > 5 * 1024 * 1024:
            self._json(400, {'ok': False, 'error': 'Pedido vacío o demasiado grande.'})
            return

        zpl = self.rfile.read(largo).decode('utf-8', errors='replace')
        if '^XA' not in zpl:
            self._json(400, {'ok': False, 'error': 'Esto no parece una etiqueta.'})
            return

        if not Estado.impresora:
            self._json(503, {
                'ok': False,
                'error': 'No hay ninguna impresora detectada. Fijate que esté '
                         'prendida y enchufada, y volvé a probar.',
            })
            return

        try:
            enviar(zpl, Estado.impresora)
        except ErrorDeImpresion as exc:
            Estado.ultimo_error = str(exc)
            self._json(503, {'ok': False, 'error': str(exc)})
            return
        except Exception as exc:
            Estado.ultimo_error = str(exc)
            self._json(500, {'ok': False, 'error': f"No se pudo imprimir: {exc}"})
            return

        cuantas = zpl.count('^XA')
        Estado.etiquetas_impresas += cuantas
        Estado.ultimo_error = ''
        self._json(200, {
            'ok': True,
            'mensaje': f"{cuantas} etiqueta(s) enviada(s) a la impresora.",
        })

    def log_message(self, formato, *args):
        pass  # Sin consola no hay dónde escribir, y nadie lo va a leer.


# ─────────────────────────────────────────────────────────────────────────────
# Ícono al lado del reloj
# ─────────────────────────────────────────────────────────────────────────────

def _dibujar_icono(color):
    """Genera el ícono en memoria.

    Se dibuja en vez de traer un .ico como archivo aparte para que el .exe siga
    siendo UN solo archivo, sin recursos sueltos que se puedan perder.
    """
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 12, 60, 52], radius=8, fill=color)
    d.rectangle([16, 4, 48, 20], fill=color)
    d.rectangle([16, 38, 48, 60], fill='white', outline=color, width=2)
    for y in (44, 49, 54):
        d.line([20, y, 44, y], fill=color, width=2)
    return img


def crear_icono(servidor):
    import pystray

    def titulo():
        if Estado.impresora:
            return f"Puente de impresión — {Estado.impresora}"
        return "Puente de impresión — no encuentro la impresora"

    def refrescar(icono):
        Estado.impresora = detectar_impresora()
        icono.icon = _dibujar_icono('#10b981' if Estado.impresora else '#ef4444')
        icono.title = titulo()

    def al_probar(icono, _):
        refrescar(icono)
        if not Estado.impresora:
            icono.notify("No encuentro la impresora. Fijate que esté prendida "
                         "y enchufada al USB.", "Fortium Tailor")
            return
        try:
            enviar(ZPL_PRUEBA, Estado.impresora)
            icono.notify("Mandé una etiqueta de prueba. Si salió, está todo bien.",
                         "Fortium Tailor")
        except Exception as exc:
            icono.notify(f"No se pudo imprimir: {exc}", "Fortium Tailor")

    def al_elegir(nombre):
        def accion(icono, _):
            guardar_config({**leer_config(), 'impresora': nombre})
            refrescar(icono)
            icono.notify(f"Ahora imprime en {nombre}.", "Fortium Tailor")
        return accion

    def menu_impresoras():
        try:
            disponibles = listar_impresoras()
        except ErrorDeImpresion:
            disponibles = []
        if not disponibles:
            return (pystray.MenuItem("(no hay impresoras instaladas)", None,
                                     enabled=False),)
        return tuple(
            pystray.MenuItem(nombre, al_elegir(nombre),
                             checked=lambda item, n=nombre: Estado.impresora == n,
                             radio=True)
            for nombre in disponibles
        )

    def al_cambiar_arranque(icono, _):
        fijar_arranque(not arranque_activo())
        icono.update_menu()

    def al_salir(icono, _):
        servidor.shutdown()
        icono.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: titulo(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Imprimir etiqueta de prueba", al_probar, default=True),
        pystray.MenuItem("Elegir impresora", pystray.Menu(menu_impresoras)),
        pystray.MenuItem("Volver a buscar la impresora",
                         lambda icono, _: refrescar(icono)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Arrancar junto con Windows", al_cambiar_arranque,
                         checked=lambda _: arranque_activo()),
        pystray.MenuItem("Salir", al_salir),
    )

    icono = pystray.Icon(
        'fortium_puente',
        _dibujar_icono('#10b981' if Estado.impresora else '#ef4444'),
        titulo(),
        menu,
    )
    return icono


# ─────────────────────────────────────────────────────────────────────────────
# Arranque
# ─────────────────────────────────────────────────────────────────────────────

def main():
    Estado.impresora = detectar_impresora()

    try:
        servidor = ThreadingHTTPServer(('127.0.0.1', PUERTO), Manejador)
    except OSError:
        # El puerto ocupado casi siempre significa que ya hay otra copia
        # corriendo — típico de hacer doble clic dos veces. No es un error.
        _avisar_ya_corriendo()
        return 0

    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()

    # La primera vez se anota solo en el arranque de Windows. Después respeta lo
    # que el usuario haya elegido en el menú, sin volver a pisarlo.
    config = leer_config()
    if not config.get('arranque_configurado'):
        fijar_arranque(True)
        guardar_config({**config, 'arranque_configurado': True})

    try:
        icono = crear_icono(servidor)
    except Exception:
        # Sin ícono (falta pystray, o es una sesión sin escritorio) igual sirve:
        # el servidor ya está levantado y el navegador puede imprimir.
        try:
            hilo.join()
        except KeyboardInterrupt:
            servidor.shutdown()
        return 0

    icono.run()
    return 0


def _avisar_ya_corriendo():
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "El puente de impresión ya está funcionando.\n\n"
            "Fijate el ícono verde al lado del reloj.",
            "Fortium Tailor",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(main())
