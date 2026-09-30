"""
test_choke_point_guard.py
==========================
Congela el choke point de caja (architecture/caja-ownership-chokepoint,
tercera vuelta de sdd-verify): TODA escritura de `CajaMovimiento` nuevo pasa
por `caja_signals._crear_mov_auto`, que exige y verifica un `usuario`
obligatorio. Estos tests fallan si alguien reintroduce un `usuario=None`
por default, o si aparece una escritura de `CajaMovimiento` fuera de la
allowlist documentada acá abajo.

Qué se considera "escritura" (`buscar_escrituras`):
  - `CajaMovimiento.objects.create/bulk_create/get_or_create/update_or_create`
    (con o sin alias de import: `... as CM`, `CM = CajaMovimiento`,
    `models.CajaMovimiento`).
  - Los mismos verbos sobre un related manager (`x.caja_movimientos.create`,
    `sesion.movimientos.create`).
  - Instanciar `CajaMovimiento(...)` (el `.save()` posterior no se ve, pero
    sin instanciar no hay nada que guardar).
  - Instanciar un ModelForm cuyo `Meta.model` es `CajaMovimiento` (el
    `form.save()` de `crear_movimiento_caja`).
  - `.update(...)` sobre un queryset de movimientos (`CajaMovimiento.objects
    ...filter().update` o related manager) que fije `sesion`/`sesion_id`/
    `via_caja` (o pase `**kwargs`): reasigna o libera plata entre cajas. Sólo
    las funciones de liberación de reservas están en la allowlist.
La allowlist es por (archivo, función) con un MÁXIMO de escrituras y, cuando
corresponde, el guard de turno que esa función debe llamar. `caja_signals.py`
también se revisa: sólo las funciones aprobadas pueden escribir ahí.

Límites conocidos (es un tripwire, no una garantía): NO detecta accesos
dinámicos al modelo — `getattr(CajaMovimiento, 'objects')`,
`apps.get_model('misastreria', 'CajaMovimiento')`, `type(mov).objects` —, ni
la clonación de una fila (`mov.pk = None; mov.save()`), ni SQL crudo.
Tampoco ve (verify ronda 6, W3):
  - `.update(sesion=..., via_caja=...)` sobre un queryset ligado a una
    variable (`qs = CajaMovimiento.objects.filter(...); qs.update(...)`):
    sólo se reconoce la cadena directa `CajaMovimiento.objects...update`.
  - La escritura de un campo en una instancia seguida de `save()`
    (`mov.sesion = otra; mov.via_caja = True; mov.save()`): el guard sólo
    mira instanciaciones y verbos de manager/queryset, no asignaciones.
Quien quiera saltearlo a propósito puede; el guard atrapa el descuido, y la
defensa real es el choke point (`_crear_mov_auto`) más sus tests de
comportamiento (`test_caja_signals_fail_closed`).

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


# ──────────────────────────────────────────────────────────────────────────────
# Detector
# ──────────────────────────────────────────────────────────────────────────────

_VERBOS_ESCRITURA = ('create', 'bulk_create', 'get_or_create', 'update_or_create')
_RELATED_MANAGERS = ('caja_movimientos', 'movimientos')
_MODELO = 'CajaMovimiento'


def _nombres_del_modelo(tree):
    """Nombres con los que `CajaMovimiento` es accesible en el archivo:
    él mismo, `from x import CajaMovimiento as CM`, `CM = CajaMovimiento`."""
    nombres = {_MODELO}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _MODELO and alias.asname:
                    nombres.add(alias.asname)
    cambio = True
    while cambio:  # `A = CajaMovimiento; B = A`
        cambio = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                valor = node.value
                if (isinstance(valor, ast.Name) and valor.id in nombres) or \
                        (isinstance(valor, ast.Attribute) and valor.attr in nombres):
                    if node.targets[0].id not in nombres:
                        nombres.add(node.targets[0].id)
                        cambio = True
    return nombres


def _es_modelo(expr, nombres):
    """`expr` es el modelo: `CajaMovimiento`, un alias, o `models.CajaMovimiento`."""
    return (isinstance(expr, ast.Name) and expr.id in nombres) or \
        (isinstance(expr, ast.Attribute) and expr.attr in nombres)


def _funcion_contenedora(tree, lineno):
    mejor = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fin = getattr(node, 'end_lineno', None) or node.lineno
            if node.lineno <= lineno <= fin and (mejor is None or node.lineno > mejor.lineno):
                mejor = node
    return mejor.name if mejor else None


_CAMPOS_DE_TURNO = ('sesion', 'sesion_id', 'via_caja')


def _es_queryset_de_cajamovimiento(expr, nombres):
    """`expr` es (una cadena de filter/exclude/all sobre) `CajaMovimiento.objects`
    o un related manager de movimientos."""
    while True:
        if isinstance(expr, ast.Call):
            expr = expr.func
        elif isinstance(expr, ast.Attribute):
            if expr.attr == 'objects' and _es_modelo(expr.value, nombres):
                return True
            if expr.attr in _RELATED_MANAGERS:
                return True
            expr = expr.value
        else:
            return False


def _update_toca_el_turno(call):
    """El `.update(...)` fija `sesion`/`via_caja` (o no se puede saber: `**kw`)."""
    return any(kw.arg is None or kw.arg in _CAMPOS_DE_TURNO for kw in call.keywords)


def buscar_escrituras(source, forms_de_cajamovimiento=frozenset()):
    """Lista de (lineno, nombre_de_funcion_o_None, tipo) con cada escritura
    de CajaMovimiento encontrada en `source`."""
    tree = ast.parse(source)
    nombres = _nombres_del_modelo(tree)
    hallazgos = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        tipo = None
        if isinstance(func, ast.Attribute) and func.attr == 'update':
            # Reasignar `sesion` o liberar `via_caja` sobre un queryset de
            # movimientos es una escritura que cambia a qué caja pertenece la
            # plata: sólo lo hacen las funciones de liberación de reservas.
            if _es_queryset_de_cajamovimiento(func.value, nombres) and _update_toca_el_turno(node):
                tipo = 'update de sesion/via_caja'
        elif isinstance(func, ast.Attribute) and func.attr in _VERBOS_ESCRITURA:
            receptor = func.value
            if isinstance(receptor, ast.Attribute):
                if receptor.attr == 'objects' and _es_modelo(receptor.value, nombres):
                    tipo = f'{func.attr} via objects'
                elif receptor.attr in _RELATED_MANAGERS:
                    tipo = f'{func.attr} via related manager'
        elif _es_modelo(func, nombres):
            tipo = 'instancia directa'
        elif isinstance(func, ast.Name) and func.id in forms_de_cajamovimiento:
            tipo = 'ModelForm de CajaMovimiento'
        elif isinstance(func, ast.Attribute) and func.attr in forms_de_cajamovimiento:
            tipo = 'ModelForm de CajaMovimiento'
        if tipo:
            hallazgos.append((node.lineno, _funcion_contenedora(tree, node.lineno), tipo))
    return hallazgos


def modelforms_de_cajamovimiento(source):
    """Nombres de las clases ModelForm de `source` con `Meta.model = CajaMovimiento`."""
    tree = ast.parse(source)
    nombres = _nombres_del_modelo(tree)
    forms = set()
    for clase in ast.walk(tree):
        if not isinstance(clase, ast.ClassDef):
            continue
        for meta in clase.body:
            if isinstance(meta, ast.ClassDef) and meta.name == 'Meta':
                for asign in meta.body:
                    if isinstance(asign, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == 'model' for t in asign.targets
                    ) and _es_modelo(asign.value, nombres):
                        forms.add(clase.name)
    return forms


def evaluar(hallazgos_por_archivo, allowlist):
    """Devuelve (violaciones, entradas_muertas). `hallazgos_por_archivo`:
    {ruta: [(lineno, funcion, tipo)]}. Una entrada de la allowlist permite
    hasta `max` escrituras en esa (ruta, función); de más, o en una función
    no listada, es violación. Una entrada sin ninguna escritura es "muerta"
    (allowlistea nada y esconde el sitio real)."""
    violaciones = []
    usadas = {}
    for ruta, hallazgos in hallazgos_por_archivo.items():
        for lineno, funcion, tipo in hallazgos:
            clave = (ruta, funcion)
            usadas[clave] = usadas.get(clave, 0) + 1
            permitido = allowlist.get(clave)
            if permitido is None:
                violaciones.append(f"{ruta}:{lineno} en {funcion!r} ({tipo})")
            elif usadas[clave] > permitido['max']:
                violaciones.append(
                    f"{ruta}:{lineno} en {funcion!r} ({tipo}) — supera el máximo "
                    f"de {permitido['max']} escritura(s) permitidas"
                )
    muertas = [clave for clave in allowlist if usadas.get(clave, 0) == 0]
    return violaciones, muertas


# ──────────────────────────────────────────────────────────────────────────────
# Tests del detector con código sintético (cada mutación debe ser atrapada)
# ──────────────────────────────────────────────────────────────────────────────

class DetectorDeEscriturasTests(SimpleTestCase):
    def _tipos(self, source, forms=frozenset()):
        return [t for _, _, t in buscar_escrituras(source, forms)]

    def test_atrapa_objects_create(self):
        self.assertEqual(
            self._tipos("def f():\n    CajaMovimiento.objects.create(monto=1)\n"),
            ['create via objects'])

    def test_atrapa_los_otros_verbos_de_escritura(self):
        for verbo in ('bulk_create', 'get_or_create', 'update_or_create'):
            with self.subTest(verbo=verbo):
                self.assertEqual(
                    self._tipos(f"def f():\n    CajaMovimiento.objects.{verbo}(monto=1)\n"),
                    [f'{verbo} via objects'])

    def test_atrapa_related_manager_de_servicio(self):
        self.assertEqual(
            self._tipos("def f(venta):\n    venta.caja_movimientos.create(monto=1)\n"),
            ['create via related manager'])

    def test_atrapa_related_manager_de_sesion(self):
        self.assertEqual(
            self._tipos("def f(sesion):\n    sesion.movimientos.create(monto=1)\n"),
            ['create via related manager'])

    def test_atrapa_instancia_directa_y_save(self):
        self.assertEqual(
            self._tipos("def f():\n    CajaMovimiento(monto=1).save()\n"),
            ['instancia directa'])

    def test_atrapa_import_con_alias(self):
        src = (
            "from .models import CajaMovimiento as CM\n"
            "def f():\n    CM.objects.create(monto=1)\n"
        )
        self.assertEqual(self._tipos(src), ['create via objects'])

    def test_atrapa_alias_por_asignacion(self):
        src = (
            "from .models import CajaMovimiento\n"
            "Mov = CajaMovimiento\n"
            "def f():\n    Mov.objects.get_or_create(monto=1)\n"
        )
        self.assertEqual(self._tipos(src), ['get_or_create via objects'])

    def test_atrapa_acceso_por_modulo(self):
        self.assertEqual(
            self._tipos("def f():\n    models.CajaMovimiento.objects.create(monto=1)\n"),
            ['create via objects'])

    def test_atrapa_uso_de_modelform_de_cajamovimiento(self):
        forms_src = (
            "class ManualForm(forms.ModelForm):\n"
            "    class Meta:\n        model = CajaMovimiento\n"
        )
        forms = modelforms_de_cajamovimiento(forms_src)
        self.assertEqual(forms, {'ManualForm'})
        self.assertEqual(
            self._tipos("def v(request):\n    form = ManualForm(request.POST)\n    form.save()\n", forms),
            ['ModelForm de CajaMovimiento'])

    def test_no_marca_otros_modelos_ni_lecturas(self):
        src = (
            "def f(venta):\n"
            "    Reparacion.objects.create(x=1)\n"
            "    venta.caja_movimientos.filter(x=1)\n"
            "    CajaMovimiento.objects.filter(x=1).update(descripcion='x')\n"
            "    Reparacion.objects.filter(x=1).update(sesion=1, via_caja=True)\n"
            "    sesion.movimientos.all()\n"
        )
        self.assertEqual(buscar_escrituras(src), [])

    def test_atrapa_update_de_via_caja_o_sesion_sobre_queryset(self):
        casos = {
            "CajaMovimiento.objects.filter(x=1).update(via_caja=True)": 'update de sesion/via_caja',
            "CajaMovimiento.objects.filter(x=1).update(sesion=s)": 'update de sesion/via_caja',
            "CajaMovimiento.objects.filter(x=1).update(sesion_id=1)": 'update de sesion/via_caja',
            "CajaMovimiento.objects.filter(x=1).exclude(y=2).update(via_caja=True, sesion=s)": 'update de sesion/via_caja',
            "CajaMovimiento.objects.all().update(**campos)": 'update de sesion/via_caja',
            "venta.caja_movimientos.filter(x=1).update(via_caja=True)": 'update de sesion/via_caja',
            "sesion.movimientos.update(sesion=otra)": 'update de sesion/via_caja',
        }
        for expr, tipo in casos.items():
            with self.subTest(expr=expr):
                self.assertEqual(self._tipos(f"def f():\n    {expr}\n"), [tipo])

    def test_update_de_otros_campos_o_de_otros_modelos_no_se_marca(self):
        for expr in (
            "CajaMovimiento.objects.filter(x=1).update(descripcion='x')",
            "Reparacion.objects.filter(x=1).update(sesion=1, via_caja=True)",
        ):
            with self.subTest(expr=expr):
                self.assertEqual(self._tipos(f"def f():\n    {expr}\n"), [])

    def test_update_con_alias_del_modelo(self):
        src = (
            "from .models import CajaMovimiento as CM\n"
            "def f():\n    CM.objects.filter(x=1).update(via_caja=True)\n"
        )
        self.assertEqual(self._tipos(src), ['update de sesion/via_caja'])

    def test_reporta_la_funcion_contenedora(self):
        src = "def externa():\n    def interna():\n        CajaMovimiento.objects.create(monto=1)\n"
        self.assertEqual(buscar_escrituras(src)[0][1], 'interna')

    # --- allowlist ---------------------------------------------------------

    _ALLOW = {('caja_signals.py', 'aprobada'): {'max': 1}}

    def test_evaluar_create_crudo_en_caja_signals_fuera_de_helpers_es_violacion(self):
        src = "def otra():\n    CajaMovimiento.objects.create(monto=1)\n"
        violaciones, _ = evaluar({'caja_signals.py': buscar_escrituras(src)}, self._ALLOW)
        self.assertEqual(len(violaciones), 1)
        self.assertIn("caja_signals.py:2 en 'otra'", violaciones[0])

    def test_evaluar_permite_la_funcion_aprobada(self):
        src = "def aprobada():\n    CajaMovimiento.objects.create(monto=1)\n"
        violaciones, muertas = evaluar({'caja_signals.py': buscar_escrituras(src)}, self._ALLOW)
        self.assertEqual((violaciones, muertas), ([], []))

    def test_evaluar_create_extra_dentro_de_funcion_aprobada_es_violacion(self):
        src = (
            "def aprobada():\n"
            "    CajaMovimiento.objects.create(monto=1)\n"
            "    CajaMovimiento.objects.create(monto=2)\n"
        )
        violaciones, _ = evaluar({'caja_signals.py': buscar_escrituras(src)}, self._ALLOW)
        self.assertEqual(len(violaciones), 1)
        self.assertIn('supera el máximo', violaciones[0])

    def test_evaluar_detecta_entradas_muertas(self):
        _, muertas = evaluar({'caja_signals.py': []}, self._ALLOW)
        self.assertEqual(muertas, [('caja_signals.py', 'aprobada')])


# ──────────────────────────────────────────────────────────────────────────────
# El código real
# ──────────────────────────────────────────────────────────────────────────────

class EscriturasDeCajaMovimientoTests(SimpleTestCase):
    """Toda escritura de `CajaMovimiento` del proyecto está en la allowlist,
    con su guard de turno, y la allowlist no tiene entradas muertas."""

    _EXCLUDE_DIRS = {'tests', 'migrations', '__pycache__'}

    # (ruta desde misastreria/, función) -> {max, guard, motivo}
    _ALLOWLIST = {
        ('caja_signals.py', '_crear_mov_auto'): {
            'max': 1, 'guard': 'verificar_turno_cobro',
            'motivo': "CHOKE POINT: todo movimiento nuevo; verifica dueño del turno adentro.",
        },
        ('caja_signals.py', '_reversar_movimientos_activos_impl'): {
            'max': 1, 'guard': 'verificar()',
            'motivo': "reverso: la regla de turno la inyecta el llamador (`verificar`): dueño o "
                      "Administrador, o la red de seguridad pre_delete.",
        },
        ('caja_signals.py', '_liberar_pagos_reservados'): {
            'max': 1, 'guard': 'verificar_turno_cobro',
            'motivo': "liberación de reservas: `.update(via_caja=True, sesion=...)` en la sesión "
                      "abierta de quien libera, que debe ser su dueño (atómico).",
        },
        ('caja_signals.py', '_ajustar_garantia_alquiler_en_caja'): {
            'max': 2, 'guard': '_sesion_propia_o_error',
            'motivo': "reversos de garantía (quitar/cambiar monto): exigen sesión propia del actor.",
        },
        ('views.py', 'crear_movimiento_caja'): {
            'max': 2, 'guard': 'verificar_turno_cobro',
            'motivo': "movimiento manual: escribe con form.save(commit=False)+save() (no objects.create); "
                      "2 = form del POST y form vacío del GET. Exige verificar_turno_cobro(request.user).",
        },
        ('views.py', 'revertir_movimiento_caja'): {
            'max': 1, 'guard': 'verificar_turno_reversion',
            'motivo': "reverso manual: dueño o Administrador.",
        },
        ('views.py', 'abrir_sesion_caja'): {
            'max': 1, 'guard': None,
            'motivo': "apertura: el creador es el dueño de la sesión por definición.",
        },
        ('views.py', 'cerrar_sesion_caja'): {
            'max': 2, 'guard': None,
            'motivo': "sobrante/faltante al cierre: quien cierra (dueño, o Administrador con observación "
                      "obligatoria) queda como `usuario`.",
        },
        ('management/commands/backfill_reparacion_cobros.py', 'handle'): {
            'max': 1, 'guard': None,
            'motivo': "backfill histórico documentado (sesion=None/usuario=None), sólo shell del servidor.",
        },
        ('management/commands/backfill_alquiler_cobros.py', 'handle'): {
            'max': 1, 'guard': None,
            'motivo': "backfill histórico documentado (sesion=None/usuario=None), sólo shell del servidor.",
        },
        ('management/commands/backfill_confeccion_adelantos.py', 'handle'): {
            'max': 1, 'guard': None,
            'motivo': "backfill histórico documentado (sesion=None/usuario=None), sólo shell del servidor.",
        },
    }

    def _fuentes(self):
        fuentes = {}
        for root, dirs, files in os.walk(_APP_DIR):
            dirs[:] = [d for d in dirs if d not in self._EXCLUDE_DIRS]
            rel_root = os.path.relpath(root, _APP_DIR)
            for f in files:
                if f.endswith('.py'):
                    ruta = f if rel_root == '.' else os.path.join(rel_root, f)
                    with open(os.path.join(root, f), encoding='utf-8') as fh:
                        fuentes[ruta] = fh.read()
        return fuentes

    def _hallazgos(self):
        fuentes = self._fuentes()
        forms = set()
        for source in fuentes.values():
            if _MODELO in source:
                forms |= modelforms_de_cajamovimiento(source)
        self.assertIn('CajaMovimientoManualForm', forms, 'el detector de ModelForms dejó de ver el form manual')
        return fuentes, {
            ruta: buscar_escrituras(source, forms)
            for ruta, source in fuentes.items()
            if _MODELO in source or any(f in source for f in forms)
        }

    def test_toda_escritura_esta_en_la_allowlist(self):
        _, hallazgos = self._hallazgos()
        violaciones, _ = evaluar(hallazgos, self._ALLOWLIST)
        self.assertEqual(
            violaciones, [],
            "Escrituras de CajaMovimiento fuera de la allowlist del choke point "
            "(deben pasar por caja_signals._crear_mov_auto): " + "; ".join(violaciones),
        )

    def test_la_allowlist_no_tiene_entradas_muertas(self):
        _, hallazgos = self._hallazgos()
        _, muertas = evaluar(hallazgos, self._ALLOWLIST)
        self.assertEqual(muertas, [], f"Entradas de allowlist sin ninguna escritura real: {muertas}")

    def test_cada_funcion_permitida_llama_a_su_guard_de_turno(self):
        fuentes, _ = self._hallazgos()
        sin_guard = []
        for (ruta, funcion), datos in self._ALLOWLIST.items():
            if not datos['guard']:
                continue
            tree = ast.parse(fuentes[ruta])
            nodo = next(
                (n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == funcion), None)
            self.assertIsNotNone(nodo, f'{ruta}:{funcion} no existe')
            if datos['guard'] not in ast.get_source_segment(fuentes[ruta], nodo):
                sin_guard.append(f'{ruta}:{funcion} (falta {datos["guard"]})')
        self.assertEqual(sin_guard, [])
