"""
test_choke_point_guard.py
==========================
Congela el choke point de caja (architecture/caja-ownership-chokepoint,
tercera vuelta de sdd-verify): TODA escritura de `CajaMovimiento` nuevo pasa
por `caja_signals._crear_mov_auto`, que exige y verifica un `usuario`
obligatorio. Estos tests fallan si alguien reintroduce un `usuario=None`
por default, o si aparece un `CajaMovimiento.objects.create`/`bulk_create`
fuera de `caja_signals.py` sin pasar por la allowlist documentada acá abajo.

Son tests de ARQUITECTURA, no de comportamiento — leen el código fuente
(AST/inspect), no ejecutan vistas.
"""
import ast
import inspect
import os

from django.test import SimpleTestCase

from misastreria import caja_signals

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class UsuarioSinDefaultEnCajaSignalsTests(SimpleTestCase):
    """Ninguna función pública o privada de caja_signals.py puede declarar
    `usuario` con un valor por default — el choke point exige que todo
    caller lo piense explícitamente."""

    def test_ningun_usuario_tiene_default(self):
        ofensores = []
        for nombre, funcion in inspect.getmembers(caja_signals, inspect.isfunction):
            if funcion.__module__ != caja_signals.__name__:
                continue
            sig = inspect.signature(funcion)
            usuario_param = sig.parameters.get('usuario')
            if usuario_param is not None and usuario_param.default is not inspect.Parameter.empty:
                ofensores.append(f"{nombre}(usuario={usuario_param.default!r})")
        self.assertEqual(
            ofensores, [],
            "Estas funciones de caja_signals.py tienen 'usuario' con default — "
            "rompen el choke point de dueño de caja: " + ", ".join(ofensores),
        )


class CajaMovimientoCreateFueraDeCajaSignalsTests(SimpleTestCase):
    """Ningún módulo fuera de `caja_signals.py` puede escribir
    `CajaMovimiento.objects.create(...)` / `.bulk_create(...)` directamente,
    salvo los sitios documentados en `_ALLOWLIST` — cada uno con su propio
    guard de turno explícito en el mismo bloque (ver comentarios en el
    código señalado)."""

    # (ruta relativa desde misastreria/, nombre de la función que contiene
    # la llamada) -> por qué está permitido.
    _ALLOWLIST = {
        ('views.py', 'crear_movimiento_caja'):
            "movimiento manual: la vista exige verificar_turno_cobro(request.user) antes de crear.",
        ('views.py', 'revertir_movimiento_caja'):
            "reverso manual: la vista exige verificar_turno_reversion(request.user) antes de crear.",
        ('views.py', 'abrir_sesion_caja'):
            "apertura de caja: el ingreso 'apertura_caja' se crea con sesion.usuario_apertura=request.user, "
            "el creador ES el dueño por definición.",
        ('views.py', 'cerrar_sesion_caja'):
            "sobrante/faltante al cierre: mismo actor (request.user) que está cerrando esa sesión.",
        ('management/commands/backfill_reparacion_cobros.py', 'handle'):
            "backfill histórico documentado: sesion=None/usuario=None a propósito, sólo shell del servidor.",
        ('management/commands/backfill_alquiler_cobros.py', 'handle'):
            "backfill histórico documentado: sesion=None/usuario=None a propósito, sólo shell del servidor.",
        ('management/commands/backfill_confeccion_adelantos.py', 'handle'):
            "backfill histórico documentado: sesion=None/usuario=None a propósito, sólo shell del servidor.",
    }

    _EXCLUDE_DIRS = {'tests', 'migrations', '__pycache__'}

    def _archivos_a_revisar(self):
        for root, dirs, files in os.walk(_APP_DIR):
            dirs[:] = [d for d in dirs if d not in self._EXCLUDE_DIRS]
            rel_root = os.path.relpath(root, _APP_DIR)
            for f in files:
                if not f.endswith('.py'):
                    continue
                rel_path = f if rel_root == '.' else os.path.join(rel_root, f)
                if rel_path == 'caja_signals.py':
                    continue
                yield rel_path, os.path.join(root, f)

    def _es_create_de_cajamovimiento(self, node):
        """`node` es un ast.Call. True si es `CajaMovimiento.objects.create(...)`
        o `CajaMovimiento.objects.bulk_create(...)`."""
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr not in ('create', 'bulk_create'):
            return False
        objects_attr = node.func.value
        if not isinstance(objects_attr, ast.Attribute) or objects_attr.attr != 'objects':
            return False
        base = objects_attr.value
        return isinstance(base, ast.Name) and base.id == 'CajaMovimiento'

    def _funcion_contenedora(self, tree, lineno):
        """Nombre de la función (o método) más interna cuyo rango de líneas
        contiene `lineno`, o None si está a nivel de módulo."""
        mejor = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fin = getattr(node, 'end_lineno', None) or node.lineno
                if node.lineno <= lineno <= fin:
                    if mejor is None or node.lineno > mejor.lineno:
                        mejor = node
        return mejor.name if mejor else None

    def test_sin_creates_fuera_de_caja_signals_sin_allowlist(self):
        ofensores = []
        for rel_path, abs_path in self._archivos_a_revisar():
            with open(abs_path, encoding='utf-8') as fh:
                source = fh.read()
            if 'CajaMovimiento' not in source:
                continue
            tree = ast.parse(source, filename=abs_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and self._es_create_de_cajamovimiento(node):
                    funcname = self._funcion_contenedora(tree, node.lineno)
                    key = (rel_path, funcname)
                    if key not in self._ALLOWLIST:
                        ofensores.append(f"{rel_path}:{node.lineno} en {funcname!r}")
        self.assertEqual(
            ofensores, [],
            "CajaMovimiento.objects.create/bulk_create fuera de caja_signals.py "
            "y fuera de la allowlist documentada: " + ", ".join(ofensores),
        )
