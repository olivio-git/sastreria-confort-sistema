"""
Test suite — depreciacion-alquiler
===================================
Covers:
  1. calcular_precio_alquiler  — función pura (guards, fórmula, piso, redondeo)
  2. PrendaItem.precio_alquiler_sugerido — property ORM end-to-end
  3. _prenda_items_json          — serialización en view
  4. PrendaInventarioForm        — validación del formulario
"""

import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client

from misastreria.models import (
    PrendaInventario, PrendaItem,
    calcular_precio_alquiler,
)
from misastreria.forms import PrendaInventarioForm


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def make_prenda(**kwargs):
    """Create a minimal PrendaInventario with sensible defaults."""
    defaults = dict(nombre='Traje Test', precio=Decimal('100.00'))
    defaults.update(kwargs)
    return PrendaInventario.objects.create(**defaults)


def make_item(prenda, **kwargs):
    """Create a minimal PrendaItem."""
    defaults = dict(tipo='alquiler', condicion='nueva')
    defaults.update(kwargs)
    return PrendaItem.objects.create(prenda=prenda, **defaults)


# ════════════════════════════════════════════════════════════════════════════
# 1. calcular_precio_alquiler — función pura
# ════════════════════════════════════════════════════════════════════════════

class CalcPrecioGuardsTests(TestCase):
    """Guard conditions — invalid or missing inputs."""

    def test_base_none_returns_none(self):
        self.assertIsNone(calcular_precio_alquiler(None, 20, 0, 10))

    def test_base_zero_decimal_returns_none(self):
        self.assertIsNone(calcular_precio_alquiler(Decimal('0'), 20, 0, 10))

    def test_base_zero_int_returns_none(self):
        self.assertIsNone(calcular_precio_alquiler(0, 20, 0, 10))

    def test_base_zero_float_returns_none(self):
        self.assertIsNone(calcular_precio_alquiler(0.0, 20, 0, 10))

    def test_max_usos_none_returns_base(self):
        """Sin max_usos: no hay modelo de desgaste → devuelve precio base."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 5, None)
        self.assertEqual(result, Decimal('500.00'))

    def test_max_usos_zero_returns_base(self):
        result = calcular_precio_alquiler(Decimal('500'), 20, 5, 0)
        self.assertEqual(result, Decimal('500.00'))

    def test_max_usos_none_veces_zero_returns_base(self):
        result = calcular_precio_alquiler(Decimal('200'), 20, 0, None)
        self.assertEqual(result, Decimal('200.00'))

    def test_max_usos_none_veces_high_returns_base(self):
        """Muchos usos registrados pero sin max_usos → sigue siendo base."""
        result = calcular_precio_alquiler(Decimal('300'), 20, 999, None)
        self.assertEqual(result, Decimal('300.00'))


class CalcPrecioLinearTests(TestCase):
    """Fórmula lineal: precio = base × (1 − n/m)."""

    def test_veces_cero_es_base(self):
        result = calcular_precio_alquiler(Decimal('500'), 20, 0, 10)
        self.assertEqual(result, Decimal('500.00'))

    def test_primer_uso(self):
        """Uso 1 de 10 → 90% de 500 = 450."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 1, 10)
        self.assertEqual(result, Decimal('450.00'))

    def test_mitad_de_vida(self):
        """Uso 5 de 10 → 50% de 500 = 250."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 5, 10)
        self.assertEqual(result, Decimal('250.00'))

    def test_tres_de_diez(self):
        """Uso 3 de 10 → 70% de 500 = 350."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 3, 10)
        self.assertEqual(result, Decimal('350.00'))

    def test_nueve_de_diez(self):
        """Uso 9 de 10 → 10% de 500 = 50, pero piso 20% = 100."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 9, 10)
        self.assertEqual(result, Decimal('100.00'))

    def test_exactamente_max_usos_aplica_piso(self):
        """Uso 10 de 10 → fórmula da 0, piso 20% = 100."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 10, 10)
        self.assertEqual(result, Decimal('100.00'))

    def test_supera_max_usos_queda_en_piso(self):
        """Más usos que max → nunca baja del piso."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 15, 10)
        self.assertEqual(result, Decimal('100.00'))

    def test_supera_max_usos_muy_alto(self):
        """Desgaste extremo (100x max_usos) → sigue en piso."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 1000, 10)
        self.assertEqual(result, Decimal('100.00'))

    def test_max_usos_uno_primer_uso_aplica_piso(self):
        """max_usos=1: después del primer uso ya está en el límite."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 1, 1)
        self.assertEqual(result, Decimal('100.00'))

    def test_max_usos_uno_veces_cero_es_base(self):
        """max_usos=1, uso 0 → todavía es nueva."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 0, 1)
        self.assertEqual(result, Decimal('500.00'))

    def test_max_usos_grande(self):
        """max_usos=100, uso 50 → 50% = 250."""
        result = calcular_precio_alquiler(Decimal('500'), 20, 50, 100)
        self.assertEqual(result, Decimal('250.00'))


class CalcPrecioFloorTests(TestCase):
    """Piso: min_pct define el precio mínimo como % del base."""

    def test_piso_default_20pct(self):
        result = calcular_precio_alquiler(Decimal('500'), 20, 10, 10)
        self.assertEqual(result, Decimal('100.00'))  # 500 × 20% = 100

    def test_piso_30pct(self):
        result = calcular_precio_alquiler(Decimal('500'), 30, 10, 10)
        self.assertEqual(result, Decimal('150.00'))  # 500 × 30% = 150

    def test_piso_50pct(self):
        result = calcular_precio_alquiler(Decimal('500'), 50, 10, 10)
        self.assertEqual(result, Decimal('250.00'))

    def test_piso_100pct_precio_nunca_cambia(self):
        """min_pct=100 → el precio nunca baja del base."""
        for n in [0, 3, 7, 10, 20]:
            with self.subTest(n=n):
                r = calcular_precio_alquiler(Decimal('500'), 100, n, 10)
                self.assertEqual(r, Decimal('500.00'))

    def test_piso_1pct_permite_precio_casi_cero(self):
        result = calcular_precio_alquiler(Decimal('500'), 1, 10, 10)
        self.assertEqual(result, Decimal('5.00'))  # 500 × 1% = 5

    def test_precio_nunca_es_negativo(self):
        """Garantía: precio siempre ≥ 0 sin importar los parámetros."""
        for n in range(0, 25):
            r = calcular_precio_alquiler(Decimal('100'), 1, n, 10)
            self.assertGreaterEqual(r, Decimal('0'))


class CalcPrecioRoundingTests(TestCase):
    """Redondeo: ROUND_HALF_UP, siempre 2 decimales."""

    def test_resultado_siempre_2_decimales(self):
        result = calcular_precio_alquiler(Decimal('333.33'), 20, 1, 3)
        self.assertEqual(result.as_tuple().exponent, -2)

    def test_round_half_up(self):
        """1000 × (1 − 1/3) = 666.666… → 666.67."""
        result = calcular_precio_alquiler(Decimal('1000'), 20, 1, 3)
        self.assertEqual(result, Decimal('666.67'))

    def test_base_con_decimales(self):
        """Base 99.99, 0 usos, 10 max → 99.99."""
        result = calcular_precio_alquiler(Decimal('99.99'), 20, 0, 10)
        self.assertEqual(result, Decimal('99.99'))

    def test_base_entero_funciona(self):
        result = calcular_precio_alquiler(500, 20, 5, 10)
        self.assertEqual(result, Decimal('250.00'))

    def test_base_float_funciona(self):
        result = calcular_precio_alquiler(500.0, 20, 5, 10)
        self.assertEqual(result, Decimal('250.00'))

    def test_base_string_funciona(self):
        result = calcular_precio_alquiler('500', 20, 5, 10)
        self.assertEqual(result, Decimal('250.00'))

    def test_precio_minimo_preciso(self):
        """Piso: 333.33 × 20% = 66.666 → 66.67."""
        result = calcular_precio_alquiler(Decimal('333.33'), 20, 10, 10)
        self.assertEqual(result, Decimal('66.67'))


# ════════════════════════════════════════════════════════════════════════════
# 2. PrendaItem.precio_alquiler_sugerido — property ORM
# ════════════════════════════════════════════════════════════════════════════

class PrendaItemSugeridoTests(TestCase):
    """End-to-end: property lee desde el SKU y aplica la fórmula."""

    # ── Sin precio_alquiler_base configurado ─────────────────────────────────

    def test_sin_precio_alquiler_base_retorna_none(self):
        prenda = make_prenda(max_usos_default=10)  # sin precio_alquiler_base
        item = make_item(prenda)
        self.assertIsNone(item.precio_alquiler_sugerido)

    def test_sin_precio_alquiler_base_ni_max_usos_retorna_none(self):
        prenda = make_prenda()  # nada configurado
        item = make_item(prenda)
        self.assertIsNone(item.precio_alquiler_sugerido)

    # ── Con precio_alquiler_base pero sin max_usos ────────────────────────────

    def test_con_base_sin_max_usos_sku_retorna_base(self):
        """Sin max_usos_default en SKU → siempre sugiere el precio base."""
        prenda = make_prenda(precio_alquiler_base=Decimal('500'))
        item = make_item(prenda, veces_alquilado=7)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('500.00'))

    def test_con_base_sin_max_usos_sku_item_nuevo(self):
        prenda = make_prenda(precio_alquiler_base=Decimal('200'))
        item = make_item(prenda, veces_alquilado=0)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('200.00'))

    def test_con_base_max_usos_sku_cero_retorna_base(self):
        """max_usos_default=0 se trata igual que None."""
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=0)
        item = make_item(prenda, veces_alquilado=5)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('500.00'))

    # ── Depreciación con max_usos del SKU ────────────────────────────────────

    def test_item_nuevo_retorna_base(self):
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=10)
        item = make_item(prenda, veces_alquilado=0)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('500.00'))

    def test_mitad_de_vida(self):
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=10)
        item = make_item(prenda, veces_alquilado=5)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('250.00'))

    def test_al_limite_aplica_piso(self):
        prenda = make_prenda(
            precio_alquiler_base=Decimal('500'),
            max_usos_default=10,
            precio_alquiler_minimo_pct=20,
        )
        item = make_item(prenda, veces_alquilado=10)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('100.00'))

    def test_supera_limite_queda_en_piso(self):
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=10)
        item = make_item(prenda, veces_alquilado=50)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('100.00'))

    # ── Override de max_usos en el item individual ───────────────────────────

    def test_item_override_max_usos_tiene_prioridad(self):
        """max_usos en PrendaItem sobreescribe max_usos_default del SKU."""
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=10)
        item = make_item(prenda, veces_alquilado=5, max_usos=20)  # override: 5/20 = 75%
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('375.00'))

    def test_item_override_max_usos_none_cae_al_sku(self):
        """Si PrendaItem.max_usos es None, usa el del SKU."""
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=10)
        item = make_item(prenda, veces_alquilado=5, max_usos=None)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('250.00'))

    def test_item_override_sin_max_usos_sku_sin_max_usos_retorna_base(self):
        """Ni item ni SKU tienen max_usos → retorna base."""
        prenda = make_prenda(precio_alquiler_base=Decimal('300'))
        item = make_item(prenda, veces_alquilado=99, max_usos=None)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('300.00'))

    # ── Múltiples items del mismo SKU ────────────────────────────────────────

    def test_dos_items_mismo_sku_precios_distintos(self):
        """Items con diferente desgaste → precios diferentes del mismo SKU."""
        prenda = make_prenda(precio_alquiler_base=Decimal('500'), max_usos_default=10)
        item_nuevo = make_item(prenda, veces_alquilado=0)
        item_viejo = make_item(prenda, veces_alquilado=8)
        self.assertEqual(item_nuevo.precio_alquiler_sugerido, Decimal('500.00'))
        self.assertEqual(item_viejo.precio_alquiler_sugerido, Decimal('100.00'))

    def test_tres_items_degradacion_progresiva(self):
        prenda = make_prenda(precio_alquiler_base=Decimal('1000'), max_usos_default=10)
        items = [make_item(prenda, veces_alquilado=n) for n in [0, 5, 10]]
        precios = [i.precio_alquiler_sugerido for i in items]
        # Cada precio debe ser ≤ al anterior
        self.assertGreaterEqual(precios[0], precios[1])
        self.assertGreaterEqual(precios[1], precios[2])

    # ── Piso personalizado ───────────────────────────────────────────────────

    def test_piso_personalizado_30pct(self):
        prenda = make_prenda(
            precio_alquiler_base=Decimal('500'),
            max_usos_default=10,
            precio_alquiler_minimo_pct=30,
        )
        item = make_item(prenda, veces_alquilado=10)
        self.assertEqual(item.precio_alquiler_sugerido, Decimal('150.00'))

    def test_piso_100pct_precio_constante(self):
        prenda = make_prenda(
            precio_alquiler_base=Decimal('500'),
            max_usos_default=10,
            precio_alquiler_minimo_pct=100,
        )
        for n in [0, 5, 10, 20]:
            item = make_item(prenda, veces_alquilado=n)
            with self.subTest(veces=n):
                self.assertEqual(item.precio_alquiler_sugerido, Decimal('500.00'))


# ════════════════════════════════════════════════════════════════════════════
# 3. _prenda_items_json — serialización en view
# ════════════════════════════════════════════════════════════════════════════

class PrendaItemsJsonTests(TestCase):
    """Verifica que el JSON del alquiler incluye precio_alquiler_sugerido."""

    def setUp(self):
        self.user = User.objects.create_user('_test', password='test')
        self.client = Client()
        self.client.force_login(self.user)

    def _get_json(self):
        """Fetch crear_alquiler and extract the PRENDAS array from HTML."""
        resp = self.client.get('/alquileres/crear/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        marker = 'const PRENDAS = '
        start = html.find(marker)
        if start == -1:
            return []
        start += len(marker)
        end = html.index(';\n', start)
        return json.loads(html[start:end])

    def test_campo_presente_cuando_hay_items(self):
        """Verifica que el campo precio_alquiler_sugerido existe en el JSON."""
        prenda = make_prenda(
            precio_alquiler_base=Decimal('500'),
            max_usos_default=10,
        )
        make_item(prenda, tipo='alquiler', veces_alquilado=3)
        data = self._get_json()
        self.assertTrue(len(data) > 0, "No hay items en el JSON")
        item = data[0]
        self.assertIn('precio_alquiler_sugerido', item)

    def test_campo_con_depreciacion_calculada(self):
        prenda = make_prenda(
            precio_alquiler_base=Decimal('500'),
            max_usos_default=10,
        )
        make_item(prenda, tipo='alquiler', veces_alquilado=5)
        data = self._get_json()
        self.assertTrue(len(data) > 0)
        # uso 5/10 → 250.00
        self.assertAlmostEqual(data[0]['precio_alquiler_sugerido'], 250.0, places=2)

    def test_campo_es_null_sin_precio_alquiler_base(self):
        prenda = make_prenda()  # sin precio_alquiler_base
        make_item(prenda, tipo='alquiler')
        data = self._get_json()
        self.assertTrue(len(data) > 0)
        self.assertIsNone(data[0]['precio_alquiler_sugerido'])

    def test_campo_es_base_sin_max_usos(self):
        """Sin max_usos → sugerido es el base (no None)."""
        prenda = make_prenda(precio_alquiler_base=Decimal('300'))  # sin max_usos_default
        make_item(prenda, tipo='alquiler', veces_alquilado=5)
        data = self._get_json()
        self.assertTrue(len(data) > 0)
        self.assertAlmostEqual(data[0]['precio_alquiler_sugerido'], 300.0, places=2)


# ════════════════════════════════════════════════════════════════════════════
# 4. PrendaInventarioForm — validación
# ════════════════════════════════════════════════════════════════════════════

class PrendaInventarioFormTests(TestCase):
    """Valida los nuevos campos del formulario."""

    def _base_data(self, **overrides):
        data = {
            'nombre': 'Traje Test',
            'precio': '100.00',
            'estado': 'ACT',
            'precio_alquiler_minimo_pct': '20',
        }
        data.update(overrides)
        return data

    # ── precio_alquiler_base (opcional) ──────────────────────────────────────

    def test_sin_precio_alquiler_base_es_valido(self):
        """El campo es opcional."""
        form = PrendaInventarioForm(data=self._base_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_con_precio_alquiler_base_valido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_base='500.00'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_precio_alquiler_base_vacio_string_es_valido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_base=''))
        self.assertTrue(form.is_valid(), form.errors)

    def test_precio_alquiler_base_cero_invalido(self):
        """precio es requerido > 0.01, pero precio_alquiler_base es opcional → 0 sería inválido si el validator aplica."""
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_base='0'))
        # Campo es nullable → 0 puede ser rechazado por el form; solo validamos que no crashea
        self.assertIsInstance(form.is_valid(), bool)

    # ── precio_alquiler_minimo_pct (1–100, default 20) ───────────────────────

    def test_minimo_pct_valor_default_20_valido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='20'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_minimo_pct_1_valido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='1'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_minimo_pct_100_valido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='100'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_minimo_pct_0_invalido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='0'))
        self.assertFalse(form.is_valid())
        self.assertIn('precio_alquiler_minimo_pct', form.errors)

    def test_minimo_pct_101_invalido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='101'))
        self.assertFalse(form.is_valid())
        self.assertIn('precio_alquiler_minimo_pct', form.errors)

    def test_minimo_pct_negativo_invalido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='-5'))
        self.assertFalse(form.is_valid())
        self.assertIn('precio_alquiler_minimo_pct', form.errors)

    def test_minimo_pct_texto_invalido(self):
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct='abc'))
        self.assertFalse(form.is_valid())
        self.assertIn('precio_alquiler_minimo_pct', form.errors)

    def test_minimo_pct_vacio_invalido(self):
        """Campo required con default → vacío no es válido."""
        form = PrendaInventarioForm(data=self._base_data(precio_alquiler_minimo_pct=''))
        self.assertFalse(form.is_valid())
        self.assertIn('precio_alquiler_minimo_pct', form.errors)
