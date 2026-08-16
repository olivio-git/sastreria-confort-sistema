"""Puente de impresión: corre en la PC del taller, no en el servidor.

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

El servidor sigue haciendo lo único que puede hacer bien desde lejos: generar el
ZPL. Este proceso hace lo único que el servidor no puede: hablarle al USB.

──────────────────────────────────────────────────────────────────────────────
Cómo se usa
──────────────────────────────────────────────────────────────────────────────
    pip install pywin32
    python puente.py

Queda escuchando en http://127.0.0.1:9101 y no hay que tocarlo más. Ver el
README.md de esta carpeta para dejarlo arrancando solo con Windows.

──────────────────────────────────────────────────────────────────────────────
Seguridad
──────────────────────────────────────────────────────────────────────────────
Escucha SÓLO en 127.0.0.1 (no en 0.0.0.0), así que nadie de la red del taller
puede mandarle trabajos: únicamente los programas de esta misma máquina.

Además exige que el pedido venga de un origen de la lista `ORIGENES`. Sin eso,
cualquier página web abierta en esta PC podría gastar el rollo entero.
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = '1.0'

# El nombre exacto con el que Windows ve la impresora. Tiene que coincidir con
# el que figura en Panel de control → Dispositivos e impresoras.
IMPRESORA_DEFECTO = "SAT TT460 UE (203 dpi) (ZPL)"

PUERTO_DEFECTO = 9101

# Desde qué páginas se aceptan trabajos de impresión.
ORIGENES = {
    'https://fortiumtailor.com',
    'https://www.fortiumtailor.com',
    # Para probar con el Django local del desarrollador.
    'http://localhost:8001',
    'http://127.0.0.1:8001',
}


class ErrorDeImpresion(RuntimeError):
    """No se pudo mandar el trabajo a la impresora."""


def _win32print():
    try:
        import win32print
    except ImportError as exc:
        raise ErrorDeImpresion(
            "Falta pywin32. Instalalo con: pip install pywin32"
        ) from exc
    return win32print


def listar_impresoras():
    """Los nombres que ve Windows. Sirve para diagnosticar el nombre mal escrito,
    que es el motivo nº1 por el que esto «no imprime» sin dar error claro."""
    win32print = _win32print()
    banderas = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(banderas)]


def enviar(zpl, impresora):
    """Escribe el ZPL en la cola de la impresora en modo RAW.

    RAW es lo que hace que Windows pase los bytes tal cual, sin que el driver
    intente interpretarlos como un dibujo. Es la diferencia entre que la SAT
    reciba comandos ZPL y que reciba una imagen rasterizada de esos comandos.
    """
    win32print = _win32print()
    datos = zpl.encode('utf-8', errors='replace')

    try:
        h = win32print.OpenPrinter(impresora)
    except Exception as exc:
        disponibles = ', '.join(listar_impresoras()) or '(ninguna)'
        raise ErrorDeImpresion(
            f"No se pudo abrir «{impresora}». Impresoras disponibles: {disponibles}"
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


class Manejador(BaseHTTPRequestHandler):

    impresora = IMPRESORA_DEFECTO

    # ── Respuestas ──────────────────────────────────────────────────────────

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

    # ── Rutas ───────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        # Chrome exige este permiso explícito cuando una página pública pide
        # algo a una dirección de red privada (Private Network Access). Sin él,
        # el fetch a localhost muere en el preflight sin llegar acá.
        if self.headers.get('Access-Control-Request-Private-Network'):
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def do_GET(self):
        if self.path.rstrip('/') != '/estado':
            self._json(404, {'ok': False, 'error': 'Ruta no encontrada.'})
            return
        try:
            impresoras = listar_impresoras()
        except ErrorDeImpresion as exc:
            self._json(500, {'ok': False, 'error': str(exc)})
            return
        self._json(200, {
            'ok': True,
            'version': VERSION,
            'impresora': self.impresora,
            'conectada': self.impresora in impresoras,
            'impresoras': impresoras,
        })

    def do_POST(self):
        if self.path.rstrip('/') != '/imprimir':
            self._json(404, {'ok': False, 'error': 'Ruta no encontrada.'})
            return

        if self.headers.get('Origin') not in ORIGENES:
            self._json(403, {
                'ok': False,
                'error': 'Origen no autorizado para mandar trabajos.',
            })
            return

        try:
            largo = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            largo = 0
        # 5 MB es holgadísimo para ZPL, que es texto. Un cuerpo más grande que
        # eso es un error o un intento de llenar la memoria de esta PC.
        if largo <= 0 or largo > 5 * 1024 * 1024:
            self._json(400, {'ok': False, 'error': 'Cuerpo vacío o demasiado grande.'})
            return

        zpl = self.rfile.read(largo).decode('utf-8', errors='replace')
        if '^XA' not in zpl:
            self._json(400, {
                'ok': False,
                'error': 'Esto no parece ZPL: no aparece ^XA por ningún lado.',
            })
            return

        try:
            trabajo = enviar(zpl, self.impresora)
        except ErrorDeImpresion as exc:
            self._json(503, {'ok': False, 'error': str(exc)})
            return
        except Exception as exc:
            self._json(500, {'ok': False, 'error': f"No se pudo imprimir: {exc}"})
            return

        etiquetas = zpl.count('^XA')
        self._json(200, {
            'ok': True,
            'trabajo': trabajo,
            'mensaje': f"{etiquetas} etiqueta(s) enviada(s) a {self.impresora}.",
        })

    def log_message(self, formato, *args):
        # El log por defecto escribe una línea por request contra stderr, lo que
        # llena la consola con los chequeos de estado del navegador.
        if self.command != 'GET':
            sys.stderr.write(f"{self.address_string()} — {formato % args}\n")


def main():
    parser = argparse.ArgumentParser(description="Puente de impresión de etiquetas.")
    parser.add_argument('--impresora', default=IMPRESORA_DEFECTO,
                        help="Nombre exacto de la impresora en Windows.")
    parser.add_argument('--puerto', type=int, default=PUERTO_DEFECTO)
    parser.add_argument('--listar', action='store_true',
                        help="Muestra las impresoras que ve Windows y termina.")
    args = parser.parse_args()

    if args.listar:
        try:
            for nombre in listar_impresoras():
                print(nombre)
        except ErrorDeImpresion as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    Manejador.impresora = args.impresora

    # 127.0.0.1 y no 0.0.0.0: sólo esta máquina puede mandar trabajos.
    servidor = ThreadingHTTPServer(('127.0.0.1', args.puerto), Manejador)
    print(f"Puente de impresión escuchando en http://127.0.0.1:{args.puerto}")
    print(f"Impresora: {args.impresora}")

    try:
        impresoras = listar_impresoras()
        if args.impresora not in impresoras:
            print("\n  AVISO: Windows no ve esa impresora. Disponibles:")
            for nombre in impresoras:
                print(f"    · {nombre}")
            print("  Arrancá con --impresora \"<nombre exacto>\" si es otra.\n")
    except ErrorDeImpresion as exc:
        print(f"\n  AVISO: {exc}\n")

    print("Ctrl+C para cerrar.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
