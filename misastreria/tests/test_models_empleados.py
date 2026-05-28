"""
test_models_empleados.py
========================
Cubre:
  - Auto-generación de código EMP-NNN
  - Capitalización de nombres y apellidos
  - Campo `activo` derivado de fecha_baja
  - __str__
  - Permiso y Falta (FK a empleado)
  - PagoComisionEmpleado (auto-código COM-NNNN)
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from misastreria.models import Empleado, Permiso, Falta, PagoComisionEmpleado
from .factories import make_empleado, make_user


class EmpleadoAutoCodigoTests(TestCase):
    """El código EMP-NNN se genera automáticamente."""

    def test_primer_empleado_codigo_001(self):
        emp = make_empleado()
        self.assertEqual(emp.codigo, 'EMP-001')

    def test_segundo_empleado_codigo_002(self):
        make_empleado()
        emp2 = make_empleado(ci='98765432')
        self.assertEqual(emp2.codigo, 'EMP-002')

    def test_codigo_no_cambia_al_editar(self):
        emp = make_empleado()
        codigo_original = emp.codigo
        emp.nombres = 'Carlos'
        emp.save()
        emp.refresh_from_db()
        self.assertEqual(emp.codigo, codigo_original)

    def test_codigo_formato_correcto(self):
        emp = make_empleado()
        self.assertRegex(emp.codigo, r'^EMP-\d{3}$')


class EmpleadoCapitalizacionTests(TestCase):
    """Nombres y apellidos se capitalizan al guardar."""

    def test_nombres_se_capitalizan(self):
        emp = make_empleado(nombres='juan carlos')
        self.assertEqual(emp.nombres, 'Juan Carlos')

    def test_nombres_ya_mayuscula_no_doble_caps(self):
        emp = make_empleado(nombres='JUAN CARLOS')
        self.assertEqual(emp.nombres, 'Juan Carlos')

    def test_apellido_paterno_capitalizado(self):
        emp = make_empleado(apellido_paterno='gonzalez')
        self.assertEqual(emp.apellido_paterno, 'Gonzalez')

    def test_apellido_materno_capitalizado(self):
        emp = make_empleado(apellido_materno='mamani')
        self.assertEqual(emp.apellido_materno, 'Mamani')

    def test_apellido_materno_vacio_no_falla(self):
        emp = make_empleado(apellido_materno='')
        self.assertEqual(emp.apellido_materno, '')


class EmpleadoActivoTests(TestCase):
    """`activo` se deriva automáticamente de fecha_baja."""

    def test_sin_fecha_baja_activo_true(self):
        emp = make_empleado(fecha_baja=None)
        self.assertTrue(emp.activo)

    def test_con_fecha_baja_activo_false(self):
        emp = make_empleado(fecha_baja=date(2024, 6, 1))
        self.assertFalse(emp.activo)

    def test_dar_baja_cambia_activo(self):
        emp = make_empleado()
        self.assertTrue(emp.activo)
        emp.fecha_baja = date.today()
        emp.save()
        emp.refresh_from_db()
        self.assertFalse(emp.activo)

    def test_reactivar_quitando_fecha_baja(self):
        emp = make_empleado(fecha_baja=date(2024, 1, 1))
        emp.fecha_baja = None
        emp.save()
        emp.refresh_from_db()
        self.assertTrue(emp.activo)


class EmpleadoStrTests(TestCase):
    """__str__ devuelve nombres + apellidos."""

    def test_str_completo(self):
        emp = make_empleado(nombres='Ana', apellido_paterno='Gomez', apellido_materno='Cruz')
        self.assertEqual(str(emp), 'Ana Gomez Cruz')

    def test_str_sin_apellido_materno(self):
        emp = make_empleado(nombres='Luis', apellido_paterno='Rios', apellido_materno='')
        self.assertEqual(str(emp), 'Luis Rios')

    def test_str_solo_nombres(self):
        emp = make_empleado(nombres='Pedro', apellido_paterno='', apellido_materno='')
        self.assertEqual(str(emp), 'Pedro')


class PermisoTests(TestCase):
    """Permiso se crea correctamente vinculado al empleado."""

    def test_crear_permiso(self):
        emp = make_empleado()
        p = Permiso.objects.create(
            empleado=emp,
            fecha_permiso=date.today(),
            motivo='Médico',
        )
        self.assertEqual(p.empleado, emp)
        self.assertIn(p, emp.permisos.all())

    def test_str_permiso(self):
        emp = make_empleado(nombres='Luis', apellido_paterno='Rios')
        p = Permiso.objects.create(empleado=emp, fecha_permiso=date(2025, 3, 10))
        self.assertIn('2025-03-10', str(p))

    def test_eliminar_empleado_elimina_permisos(self):
        emp = make_empleado()
        Permiso.objects.create(empleado=emp, fecha_permiso=date.today())
        emp_id = emp.pk
        emp.delete()
        self.assertEqual(Permiso.objects.filter(empleado_id=emp_id).count(), 0)


class FaltaTests(TestCase):
    """Falta se crea correctamente vinculada al empleado."""

    def test_crear_falta(self):
        emp = make_empleado()
        f = Falta.objects.create(
            empleado=emp,
            fecha_falta=date.today(),
            motivo='Sin aviso',
        )
        self.assertEqual(f.empleado, emp)
        self.assertIn(f, emp.faltas.all())

    def test_str_falta(self):
        emp = make_empleado(nombres='Ana', apellido_paterno='Gomez')
        f = Falta.objects.create(empleado=emp, fecha_falta=date(2025, 4, 5))
        self.assertIn('2025-04-05', str(f))


class PagoComisionEmpleadoTests(TestCase):
    """PagoComisionEmpleado genera código COM-NNNN y se guarda correctamente."""

    def test_primer_pago_codigo_0001(self):
        emp = make_empleado()
        pago = PagoComisionEmpleado.objects.create(
            empleado=emp,
            monto=Decimal('150.00'),
            via_caja=False,
        )
        self.assertEqual(pago.codigo, 'COM-0001')

    def test_segundo_pago_codigo_0002(self):
        emp = make_empleado()
        PagoComisionEmpleado.objects.create(empleado=emp, monto=Decimal('100'), via_caja=False)
        pago2 = PagoComisionEmpleado.objects.create(empleado=emp, monto=Decimal('50'), via_caja=False)
        self.assertEqual(pago2.codigo, 'COM-0002')

    def test_str_pago_comision(self):
        emp = make_empleado(nombres='Carlos', apellido_paterno='Quispe')
        pago = PagoComisionEmpleado.objects.create(
            empleado=emp, monto=Decimal('200.00'), via_caja=False,
        )
        s = str(pago)
        self.assertIn('COM-0001', s)
        self.assertIn('200', s)
