"""Una venta no se registra sin cliente ni sin empleado.

El modelo los admite nulos —hay historia vieja sin ellos— pero el formulario
los exige. Sin cliente, una venta con saldo deja una deuda sin deudor: pasó en
producción con VEN-067, Bs 100 pendientes y nadie a quién cobrárselos. Sin
empleado, la venta no aparece al filtrar el reporte por vendedor.

El botón deshabilitado del formulario es comodidad. Lo que garantiza la regla
es la validación del servidor, que un POST armado a mano no puede saltear, y
es lo que se prueba acá.
"""
from datetime import date

from django.test import TestCase, Client
from django.urls import reverse

from misastreria.models import Venta
from .factories import (
    cliente_y_empleado_de_mostrador, make_prenda, make_prenda_item, make_user,
)


class VentaExigeClienteYEmpleadoTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client.force_login(make_user())
        self.cliente, self.empleado = cliente_y_empleado_de_mostrador()
        self.item = make_prenda_item(make_prenda(), tipo='venta')

    def _datos(self, **cambios):
        datos = {
            'fecha_venta': date.today().isoformat(),
            'estado': 'efectuada',
            'descuento': '0',
            'notas': '',
            'cliente': str(self.cliente.id),
            'empleado': str(self.empleado.id),
            'item_prenda_item':     [str(self.item.id)],
            'item_precio':          ['100.00'],
            'item_grupo_conjunto':  [''],
            'item_tipo_reparacion': [''],
            'item_costo_reparacion': [''],
            'item_asignaciones':    [''],
        }
        datos.update(cambios)
        return datos

    def test_con_los_dos_se_registra(self):
        antes = Venta.objects.count()
        r = self.client.post(reverse('crear_venta'), self._datos())
        self.assertEqual(r.status_code, 302, 'con cliente y empleado tiene que guardar')
        self.assertEqual(Venta.objects.count(), antes + 1)

    def test_sin_cliente_no_se_registra(self):
        antes = Venta.objects.count()
        r = self.client.post(reverse('crear_venta'), self._datos(cliente=''))
        self.assertEqual(r.status_code, 200, 'tenía que volver el formulario con errores')
        self.assertEqual(Venta.objects.count(), antes,
                         'se registró una venta sin cliente')

    def test_sin_empleado_no_se_registra(self):
        antes = Venta.objects.count()
        r = self.client.post(reverse('crear_venta'), self._datos(empleado=''))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Venta.objects.count(), antes,
                         'se registró una venta sin empleado')

    def test_el_formulario_marca_los_dos_campos(self):
        from misastreria.forms import VentaForm
        f = VentaForm()
        self.assertTrue(f.fields['cliente'].required)
        self.assertTrue(f.fields['empleado'].required)
