"""Varios empleados en el arreglo de una misma prenda, en venta y alquiler.

Era el único lugar del sistema con un solo empleado por trabajo: reparaciones,
confecciones y producción ya usaban tabla de asignaciones desde la 0048.
"""
from datetime import date, timedelta
from decimal import Decimal
import json
import re

from django.test import TestCase
from django.urls import reverse

from misastreria.models import (
    Alquiler, AlquilerItem, AlquilerItemEmpleado, Venta, VentaItem, VentaItemEmpleado,
)
from misastreria.views import _calcular_saldo_comision_empleado, _devengaciones_empleado
from .factories import (
    make_cliente, make_empleado, make_prenda, make_prenda_item,
    make_tipo_reparacion, make_user,
)


def _embebido(html, nombre):
    m = re.search(r'const ' + nombre + r' = (.*?);\n', html)
    return json.loads(m.group(1)) if m else None


class GuardarVariosEmpleadosTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        self.juan = make_empleado(nombres='Juan')
        self.ana = make_empleado(nombres='Ana', celular='+59171234599')
        self.tr = make_tipo_reparacion()
        prenda = make_prenda(nombre='Terno', precio=Decimal('500.00'))
        self.item = make_prenda_item(prenda, tipo='venta')

    def _post_venta(self, asignaciones):
        return self.client.post(reverse('crear_venta'), {
            'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
            'cliente': str(_cli_mostrador().id), 'empleado': str(_emp_mostrador().id),
            'descuento': '0', 'notas': '',
            'item_prenda_item':       [str(self.item.id)],
            'item_precio':            ['500.00'],
            'item_grupo_conjunto':    [''],
            'item_tipo_reparacion':   [str(self.tr.id)],
            'item_precio_reparacion': ['80.00'],
            'item_empleado':          [''],
            'item_monto_comision':    [''],
            'item_asignaciones':      [json.dumps(asignaciones)],
        })

    def test_tres_empleados_en_un_mismo_arreglo(self):
        pepe = make_empleado(nombres='Pepe', celular='+59171234588')
        resp = self._post_venta([
            {'empleado_id': self.juan.id, 'monto': '30.00'},
            {'empleado_id': self.ana.id,  'monto': '20.00'},
            {'empleado_id': pepe.id,      'monto': '10.00'},
        ])
        self.assertEqual(resp.status_code, 302)
        vi = Venta.objects.latest('id').items.first()
        self.assertEqual(vi.asignaciones.count(), 3)
        self.assertEqual(_calcular_saldo_comision_empleado(self.juan), Decimal('30'))
        self.assertEqual(_calcular_saldo_comision_empleado(self.ana), Decimal('20'))
        self.assertEqual(_calcular_saldo_comision_empleado(pepe), Decimal('10'))

    def test_cada_uno_devenga_lo_suyo_y_no_se_reparte(self):
        """La comisión es un monto por empleado, no un pozo a dividir."""
        self._post_venta([
            {'empleado_id': self.juan.id, 'monto': '30.00'},
            {'empleado_id': self.ana.id,  'monto': '20.00'},
        ])
        d_juan = _devengaciones_empleado(self.juan)
        self.assertEqual(d_juan['total_devengado'], Decimal('30'))
        self.assertEqual(len(d_juan['operaciones_comision']), 1)
        self.assertEqual(d_juan['operaciones_comision'][0]['comision'], Decimal('30'))

    def test_el_mismo_empleado_dos_veces_cuenta_una(self):
        """Hay restricción única en la base; se descarta antes de chocar."""
        self._post_venta([
            {'empleado_id': self.juan.id, 'monto': '30.00'},
            {'empleado_id': self.juan.id, 'monto': '15.00'},
        ])
        vi = Venta.objects.latest('id').items.first()
        self.assertEqual(vi.asignaciones.count(), 1)
        self.assertEqual(_calcular_saldo_comision_empleado(self.juan), Decimal('30'))

    def test_sin_asignaciones_no_devenga_nadie(self):
        self._post_venta([])
        self.assertEqual(Venta.objects.latest('id').items.first().asignaciones.count(), 0)
        self.assertEqual(_calcular_saldo_comision_empleado(self.juan), Decimal('0'))

    def test_el_formato_viejo_de_un_empleado_sigue_funcionando(self):
        """Durante el despliegue puede quedar una pestaña con el form anterior.
        Perder la comisión de un arreglo en silencio es plata de un empleado."""
        resp = self.client.post(reverse('crear_venta'), {
            'fecha_venta': date.today().isoformat(), 'estado': 'efectuada',
            'cliente': str(_cli_mostrador().id), 'empleado': str(_emp_mostrador().id),
            'descuento': '0', 'notas': '',
            'item_prenda_item':       [str(self.item.id)],
            'item_precio':            ['500.00'],
            'item_grupo_conjunto':    [''],
            'item_tipo_reparacion':   [str(self.tr.id)],
            'item_precio_reparacion': ['80.00'],
            'item_empleado':          [str(self.juan.id)],
            'item_monto_comision':    ['25.00'],
            # sin item_asignaciones: el formulario viejo no lo mandaba
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(_calcular_saldo_comision_empleado(self.juan), Decimal('25'))

    def test_editar_devuelve_las_asignaciones_al_formulario(self):
        self._post_venta([
            {'empleado_id': self.juan.id, 'monto': '30.00'},
            {'empleado_id': self.ana.id,  'monto': '20.00'},
        ])
        venta = Venta.objects.latest('id')
        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        iniciales = _embebido(html, 'ITEMS_INICIALES')
        asigs = iniciales[0]['asignaciones']
        self.assertEqual(len(asigs), 2)
        self.assertEqual({a['empleado_id'] for a in asigs}, {self.juan.id, self.ana.id})
        self.assertEqual({a['monto'] for a in asigs}, {30.0, 20.0})

    def test_el_formulario_trae_el_modal_de_empleados(self):
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn('emp-arreglo-modal', html)
        self.assertIn('empleados_arreglo.js', html)
        self.assertIn('item_asignaciones', html)


class AlquilerVariosEmpleadosTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        self.juan = make_empleado(nombres='Juan')
        self.ana = make_empleado(nombres='Ana', celular='+59171234599')
        prenda = make_prenda(nombre='Frac', precio_alquiler_base=Decimal('250.00'))
        self.item = make_prenda_item(prenda, tipo='alquiler')

    def test_dos_empleados_en_un_arreglo_de_alquiler(self):
        resp = self.client.post(reverse('crear_alquiler'), {
            'fecha_alquiler': date.today().isoformat(),
            'fecha_devolucion': (date.today() + timedelta(days=3)).isoformat(),
            'estado': 'alquilado', 'descuento': '0', 'notas': '',
            'adelanto': '0', 'forma_pago': 'efectivo',
            'item_prenda_item':       [str(self.item.id)],
            'item_precio':            ['250.00'],
            'item_grupo_conjunto':    [''],
            'item_tipo_reparacion':   [''],
            'item_precio_reparacion': ['40.00'],
            'item_empleado':          [''],
            'item_monto_comision':    [''],
            'item_asignaciones': [json.dumps([
                {'empleado_id': self.juan.id, 'monto': '15.00'},
                {'empleado_id': self.ana.id,  'monto': '25.00'},
            ])],
        })
        self.assertEqual(resp.status_code, 302)
        ai = Alquiler.objects.latest('id').items.first()
        self.assertEqual(ai.asignaciones.count(), 2)
        self.assertEqual(_calcular_saldo_comision_empleado(self.juan), Decimal('15'))
        self.assertEqual(_calcular_saldo_comision_empleado(self.ana), Decimal('25'))


class MigracionAditivaTests(TestCase):
    """La 0063 copió sin destruir: las columnas viejas siguen en su lugar."""

    def test_el_fk_legado_sigue_existiendo_en_los_modelos(self):
        # Si alguien lo borra, la vuelta atrás de la migración deja de ser
        # posible y el respaldo pasa a ser la única red.
        self.assertTrue(hasattr(VentaItem, 'empleado'))
        self.assertTrue(hasattr(AlquilerItem, 'empleado'))
        campos = {f.name for f in VentaItem._meta.get_fields()}
        self.assertIn('monto_comision_fijo', campos)


class GuardasDeAsignacionesTests(TestCase):
    """Hallazgos de la revisión sobre el parseo y el inventario archivado."""

    def setUp(self):
        self.client.force_login(make_user())
        self.juan = make_empleado(nombres='Juan')
        self.ana = make_empleado(nombres='Ana', celular='+59171234599')
        self.item = make_prenda_item(
            make_prenda(nombre='Terno', precio=Decimal('500.00')), tipo='venta')

    def test_un_id_malformado_no_borra_las_demas_comisiones(self):
        """Antes el int() estaba dentro del try del bucle entero: un solo
        empleado_id basura descartaba todas las filas del arreglo."""
        from misastreria.views import _parse_asignaciones_arreglo
        import json as _json
        crudo = _json.dumps([
            {'empleado_id': '3a', 'monto': '10.00'},          # basura
            {'empleado_id': self.juan.id, 'monto': '30.00'},
            {'empleado_id': self.ana.id, 'monto': '20.00'},
        ])
        filas = _parse_asignaciones_arreglo(crudo, '', '')
        self.assertEqual(filas, [(self.juan.id, Decimal('30.00')),
                                 (self.ana.id, Decimal('20.00'))])

    def test_un_json_roto_no_explota(self):
        from misastreria.views import _parse_asignaciones_arreglo
        self.assertEqual(_parse_asignaciones_arreglo('{no es json', '', ''), [])
        self.assertEqual(_parse_asignaciones_arreglo('"texto"', '', ''), [])


class PreloadNoOfreceArchivadoTests(TestCase):
    """El `?item=` esquivaba el filtro de SKU archivado que sí tiene el selector."""

    def setUp(self):
        self.client.force_login(make_user())
        self.archivada = make_prenda(nombre='Frac', precio=Decimal('900.00'), estado='BAJ')
        self.item = make_prenda_item(self.archivada, tipo='venta')

    def test_no_precarga_una_prenda_de_un_modelo_archivado(self):
        resp = self.client.get(reverse('crear_venta'), {'item': self.item.id}, follow=True)
        iniciales = _embebido(resp.content.decode(), 'ITEMS_INICIALES')
        self.assertEqual(iniciales, [])
        avisos = ' '.join(m.message for m in resp.context['messages']).lower()
        self.assertIn('no se pudo cargar', avisos)


# VentaForm exige cliente y empleado desde que una venta sin cliente deja una
# deuda sin deudor. Estos tests miden otra cosa, así que usan los de mostrador:
# el FK `empleado` del servicio no devenga comisión —eso sale de las tablas de
# asignación—, así que no interfiere con ningún assert.
from .factories import cliente_y_empleado_de_mostrador as _mostrador


def _cli_mostrador():
    return _mostrador()[0]


def _emp_mostrador():
    return _mostrador()[1]
