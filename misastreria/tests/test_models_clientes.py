"""
test_models_clientes.py
========================
Cubre:
  - Auto-generación de código CLI-NNN
  - Capitalización de nombre y apellidos
  - __str__
  - Unicidad de CI
"""
from django.test import TestCase
from django.db import IntegrityError

from misastreria.models import Cliente
from .factories import make_cliente


class ClienteAutoCodigoTests(TestCase):
    """El código CLI-NNN se genera automáticamente."""

    def test_primer_cliente_codigo_001(self):
        cli = make_cliente()
        self.assertEqual(cli.codigo, 'CLI-001')

    def test_segundo_cliente_codigo_002(self):
        make_cliente()
        cli2 = make_cliente(celular='+59171000002')
        self.assertEqual(cli2.codigo, 'CLI-002')

    def test_codigo_formato_correcto(self):
        cli = make_cliente()
        self.assertRegex(cli.codigo, r'^CLI-\d{3}$')

    def test_codigo_no_cambia_al_editar(self):
        cli = make_cliente()
        codigo_original = cli.codigo
        cli.notas = 'Buen cliente'
        cli.save()
        self.assertEqual(cli.codigo, codigo_original)


class ClienteCapitalizacionTests(TestCase):
    """Nombres y apellidos se capitalizan al guardar."""

    def test_nombres_capitalizados(self):
        cli = make_cliente(nombres='ana maria')
        self.assertEqual(cli.nombres, 'Ana Maria')

    def test_apellido_paterno_capitalizado(self):
        cli = make_cliente(apellido_paterno='mamani')
        self.assertEqual(cli.apellido_paterno, 'Mamani')

    def test_apellido_materno_capitalizado(self):
        cli = make_cliente(apellido_materno='quispe')
        self.assertEqual(cli.apellido_materno, 'Quispe')

    def test_apellido_materno_vacio_no_falla(self):
        cli = make_cliente(apellido_materno='')
        self.assertEqual(cli.apellido_materno, '')

    def test_nombres_mayusculas_no_doble(self):
        cli = make_cliente(nombres='PEDRO JOSE')
        self.assertEqual(cli.nombres, 'Pedro Jose')


class ClienteStrTests(TestCase):
    """__str__ devuelve nombres + apellidos."""

    def test_str_nombre_completo(self):
        cli = make_cliente(nombres='Maria', apellido_paterno='Lopez', apellido_materno='Rojas')
        self.assertEqual(str(cli), 'Maria Lopez Rojas')

    def test_str_sin_apellido_materno(self):
        cli = make_cliente(nombres='Juan', apellido_paterno='Rios', apellido_materno='')
        result = str(cli).strip()
        self.assertEqual(result, 'Juan Rios')


class ClienteUnicidadTests(TestCase):
    """CI debe ser único cuando se define."""

    def test_ci_unico(self):
        make_cliente(ci='12345678')
        with self.assertRaises(IntegrityError):
            make_cliente(ci='12345678', celular='+59172000002')

    def test_ci_null_permite_multiples(self):
        """Dos clientes pueden tener CI=None."""
        make_cliente(ci=None)
        make_cliente(ci=None, celular='+59172000003')
        self.assertEqual(Cliente.objects.filter(ci__isnull=True).count(), 2)
