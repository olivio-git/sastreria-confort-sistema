"""
test_edicion_comision_pagada.py
===============================
Regresión: editar una operación cuya comisión ya fue pagada.

Los helpers de guardado borraban y recreaban TODAS las filas de asignación
en cada edición. AplicacionPagoComision apunta a esas filas con SET_NULL y
tenía un CHECK de "exactamente una FK seteada", así que:

  1. editar una operación con comisión pagada → FK en NULL → violación del
     CHECK → IntegrityError (500) al guardar;
  2. aun sin el CHECK, la fila recreada no tenía aplicaciones → la comisión
     pagada volvía a figurar "Pendiente" → se podía pagar dos veces.

Se cubren los 5 tipos de operación por el camino real de edición (vista de
edición para reparación, venta y alquiler; el helper que usa la vista para
confección y producción):

  - editar sin cambios → sigue pagada, nada pendiente;
  - subir el monto → parcial con la diferencia pendiente;
  - bajar el monto por debajo de lo pagado → pendiente 0 y el excedente
    queda "a favor / no aplicado";
  - quitar al empleado → sin error; lo pagado queda como historial
    (aplicación huérfana con snapshot) y a favor del empleado;
  - intentar pagar otra vez lo ya pagado → rechazado.
"""
from datetime import date, timedelta
from decimal import Decimal
import json

from django.db import IntegrityError, transaction
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse

from misastreria.models import (
    AlquilerItemEmpleado, AplicacionPagoComision, ConfeccionEmpleado,
    OrdenProduccionEmpleado, PagoComisionEmpleado, ReparacionEmpleado,
    VentaItemEmpleado, Alquiler, Venta,
)
from misastreria.views import (
    _devengaciones_empleado, _guardar_asignaciones, _guardar_asignaciones_produccion,
)
from .factories import (
    make_cliente, make_confeccion, make_empleado, make_orden_produccion,
    make_prenda, make_prenda_item, make_reparacion, make_reparacion_item,
    make_tipo_prenda, make_tipo_reparacion, make_user,
)


def _qd(d):
    qd = QueryDict(mutable=True)
    qd.update(d)
    return qd


class _EdicionComisionPagadaMixin:
    """Escenarios comunes. Cada subclase define:
      - tipo_key: clave de ASIGNACION_MODELOS;
      - _editar(asignaciones): guarda la operación por el camino real con la
        lista [(empleado, monto_str)] y devuelve la respuesta (o None si es
        un helper);
      - _fila(empleado): la fila de asignación vigente del empleado, o None.
    """
    tipo_key = None

    def setUp(self):
        self.client.force_login(make_user())
        self.emp = make_empleado(nombres='Pagado', ci='PAG-1')
        self.otro = make_empleado(nombres='Otro', ci='OTR-1', celular='+59171234511')
        self._preparar()

    def _preparar(self):
        pass

    # ── utilidades ────────────────────────────────────────────────────────
    def _guardar(self, asignaciones):
        resp = self._editar(asignaciones)
        if resp is not None:
            self.assertEqual(resp.status_code, 302)
        return resp

    def _clave(self, fila):
        return f'{self.tipo_key}:{fila.id}'

    def _pagar(self, fila):
        return self.client.post(
            reverse('pagar_comision_empleado', kwargs={'empleado_id': self.emp.id}),
            {'sel': [self._clave(fila)], 'forma_pago': 'efectivo', 'via_caja': ''},
        )

    def _pagado_inicial(self, monto='100.00'):
        self._guardar([(self.emp, monto), (self.otro, '30.00')])
        fila = self._fila(self.emp)
        self.assertIsNotNone(fila)
        self.assertEqual(self._pagar(fila).status_code, 302)
        self.assertEqual(PagoComisionEmpleado.objects.filter(empleado=self.emp).count(), 1)
        return fila

    def _operacion(self, datos, fila):
        clave = self._clave(fila)
        ops = [o for o in datos['operaciones_comision'] if o['clave'] == clave]
        self.assertEqual(len(ops), 1, f"No se encontró la devengación {clave}")
        return ops[0]

    # ── escenarios ────────────────────────────────────────────────────────
    def test_editar_sin_cambios_mantiene_pagada(self):
        self._pagado_inicial()
        self._guardar([(self.emp, '100.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        datos = _devengaciones_empleado(self.emp)
        op = self._operacion(datos, fila)
        self.assertEqual(op['estado'], 'pagada')
        self.assertEqual(op['pendiente'], Decimal('0'))
        self.assertEqual(datos['n_pendientes_comision'], 0)
        self.assertEqual(datos['no_aplicado_comision'], Decimal('0'))
        self.assertEqual(datos['saldo_comision'], Decimal('0'))
        # La aplicación sigue enganchada a la fila vigente (no huérfana).
        ap = AplicacionPagoComision.objects.get(pago__empleado=self.emp)
        self.assertEqual(ap.asignacion.pk, fila.pk)

    def test_editar_dos_veces_sigue_pagada(self):
        self._pagado_inicial()
        self._guardar([(self.emp, '100.00'), (self.otro, '30.00')])
        self._guardar([(self.emp, '100.00'), (self.otro, '45.00')])
        op = self._operacion(_devengaciones_empleado(self.emp), self._fila(self.emp))
        self.assertEqual(op['estado'], 'pagada')

    def test_subir_monto_queda_parcial_con_la_diferencia(self):
        self._pagado_inicial()
        self._guardar([(self.emp, '150.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        datos = _devengaciones_empleado(self.emp)
        op = self._operacion(datos, fila)
        self.assertEqual(op['estado'], 'parcial')
        self.assertEqual(op['pagado'], Decimal('100'))
        self.assertEqual(op['pendiente'], Decimal('50'))
        self.assertEqual(datos['saldo_comision'], Decimal('50'))

        # Pagar de nuevo sólo cobra la diferencia.
        self.assertEqual(self._pagar(fila).status_code, 302)
        nuevo = PagoComisionEmpleado.objects.filter(empleado=self.emp).order_by('-id').first()
        self.assertEqual(nuevo.monto, Decimal('50'))
        op = self._operacion(_devengaciones_empleado(self.emp), fila)
        self.assertEqual(op['estado'], 'pagada')

    def test_bajar_monto_el_excedente_queda_a_favor(self):
        self._pagado_inicial()
        self._guardar([(self.emp, '60.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        datos = _devengaciones_empleado(self.emp)
        op = self._operacion(datos, fila)
        self.assertEqual(op['estado'], 'pagada')
        self.assertEqual(op['pendiente'], Decimal('0'))
        self.assertEqual(datos['no_aplicado_comision'], Decimal('40'))
        self.assertEqual(datos['saldo_comision'], Decimal('-40'))

    def test_quitar_empleado_pagado_no_revienta_y_queda_a_favor(self):
        self._pagado_inicial()
        self._guardar([(self.otro, '30.00')])

        self.assertIsNone(self._fila(self.emp))
        datos = _devengaciones_empleado(self.emp)
        self.assertEqual(datos['operaciones_comision'], [])
        self.assertEqual(datos['total_pagado'], Decimal('100'))
        self.assertEqual(datos['no_aplicado_comision'], Decimal('100'))
        # Historial intacto: la aplicación sigue, huérfana, con su snapshot.
        ap = AplicacionPagoComision.objects.get(pago__empleado=self.emp)
        self.assertIsNone(ap.asignacion)
        self.assertEqual(ap.monto, Decimal('100'))
        self.assertTrue(ap.detalle_snapshot)
        # El detalle del empleado sigue renderizando.
        resp = self.client.get(reverse('detalle_empleado', kwargs={'id': self.emp.id}))
        self.assertEqual(resp.status_code, 200)

    def test_no_se_puede_pagar_dos_veces_tras_editar(self):
        self._pagado_inicial()
        self._guardar([(self.emp, '100.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        self.assertEqual(self._pagar(fila).status_code, 302)
        self.assertEqual(PagoComisionEmpleado.objects.filter(empleado=self.emp).count(), 1)
        self.assertEqual(_devengaciones_empleado(self.emp)['operaciones_pendientes_comision'], [])

    # ── saldo a favor consumido primero (anti doble pago) ─────────────────
    def test_quitar_y_volver_a_agregar_no_paga_dos_veces(self):
        """Pagar → quitar al empleado (lo pagado queda a favor) → volver a
        agregarlo (fila nueva pendiente) → pagar: NO debe salir plata nueva;
        la aplicación huérfana se re-apunta a la fila nueva."""
        self._pagado_inicial()
        self._guardar([(self.otro, '30.00')])
        self._guardar([(self.emp, '100.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        datos = _devengaciones_empleado(self.emp)
        self.assertEqual(datos['no_aplicado_comision'], Decimal('100'))
        self.assertEqual(datos['saldo_comision'], Decimal('0'))

        self.assertEqual(self._pagar(fila).status_code, 302)
        self.assertEqual(PagoComisionEmpleado.objects.filter(empleado=self.emp).count(), 1)
        ap = AplicacionPagoComision.objects.get(pago__empleado=self.emp)
        self.assertEqual(ap.asignacion.pk, fila.pk)
        self.assertEqual(ap.monto, Decimal('100'))
        datos = _devengaciones_empleado(self.emp)
        self.assertEqual(self._operacion(datos, fila)['estado'], 'pagada')
        self.assertEqual(datos['no_aplicado_comision'], Decimal('0'))
        self.assertEqual(datos['saldo_comision'], Decimal('0'))

    def test_volver_a_agregar_con_mas_monto_solo_paga_la_diferencia(self):
        self._pagado_inicial()
        self._guardar([(self.otro, '30.00')])
        self._guardar([(self.emp, '150.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        self.assertEqual(self._pagar(fila).status_code, 302)
        pagos = PagoComisionEmpleado.objects.filter(empleado=self.emp).order_by('id')
        self.assertEqual(pagos.count(), 2)
        self.assertEqual(pagos.last().monto, Decimal('50'))
        datos = _devengaciones_empleado(self.emp)
        self.assertEqual(self._operacion(datos, fila)['estado'], 'pagada')
        self.assertEqual(datos['total_pagado'], Decimal('150'))
        self.assertEqual(datos['saldo_comision'], Decimal('0'))


# ──────────────────────────────────────────────────────────────────────────────
# Reparación — vista editar_reparacion
# ──────────────────────────────────────────────────────────────────────────────

class ReparacionEdicionComisionPagadaTests(_EdicionComisionPagadaMixin, TestCase):
    tipo_key = 'reparacion'

    def _preparar(self):
        self.cliente = make_cliente()
        self.tp = make_tipo_prenda()
        self.tr = make_tipo_reparacion()
        self.rep = make_reparacion(cliente=self.cliente, estado='pendiente')
        make_reparacion_item(self.rep, tipo_prenda=self.tp, tipo_reparacion=self.tr)

    def _editar(self, asignaciones):
        data = {
            'fecha_entrega': (date.today() + timedelta(days=3)).isoformat(),
            'cliente': str(self.cliente.id),
            'estado': 'pendiente',
            'forma_pago': 'efectivo',
            'items_count': '1',
            'items[0][tipo_prenda]': str(self.tp.id),
            'items[0][tipo_reparacion]': str(self.tr.id),
            'items[0][costo]': '100.00',
            'items[0][detalles]': '',
            'asignaciones_count': str(len(asignaciones)),
        }
        for i, (emp, monto) in enumerate(asignaciones):
            data[f'asignacion[{i}][empleado]'] = str(emp.id)
            data[f'asignacion[{i}][monto]'] = monto
        return self.client.post(reverse('editar_reparacion', kwargs={'id': self.rep.id}), data)

    def _fila(self, empleado):
        return ReparacionEmpleado.objects.filter(reparacion=self.rep, empleado=empleado).first()

    def test_editar_conserva_la_fila_y_el_lead(self):
        fila = self._pagado_inicial()
        self._guardar([(self.emp, '100.00'), (self.otro, '30.00')])
        self.assertEqual(self._fila(self.emp).pk, fila.pk)
        self.rep.refresh_from_db()
        self.assertEqual(self.rep.empleado_id, self.emp.id)


# ──────────────────────────────────────────────────────────────────────────────
# Confección — helper que usa editar_confeccion
# ──────────────────────────────────────────────────────────────────────────────

class ConfeccionEdicionComisionPagadaTests(_EdicionComisionPagadaMixin, TestCase):
    tipo_key = 'confeccion'

    def _preparar(self):
        self.conf = make_confeccion()

    def _editar(self, asignaciones):
        data = {'asignaciones_count': str(len(asignaciones))}
        for i, (emp, monto) in enumerate(asignaciones):
            data[f'asignacion[{i}][empleado]'] = str(emp.id)
            data[f'asignacion[{i}][monto]'] = monto
        errores = _guardar_asignaciones(
            self.conf, _qd(data), ConfeccionEmpleado, 'confeccion',
            commission_field='monto_comision_fijo', monto_key='monto', sync_lead=False)
        self.assertEqual(errores, [])
        return None

    def _fila(self, empleado):
        return ConfeccionEmpleado.objects.filter(confeccion=self.conf, empleado=empleado).first()


# ──────────────────────────────────────────────────────────────────────────────
# Producción — helper que usa editar_orden
# ──────────────────────────────────────────────────────────────────────────────

class ProduccionEdicionComisionPagadaTests(_EdicionComisionPagadaMixin, TestCase):
    tipo_key = 'produccion'

    def _preparar(self):
        self.orden = make_orden_produccion()

    def _editar(self, asignaciones):
        data = {'asignaciones_prod_count': str(len(asignaciones))}
        for i, (emp, monto) in enumerate(asignaciones):
            data[f'asignacion_prod[{i}][empleado]'] = str(emp.id)
            data[f'asignacion_prod[{i}][responsabilidad]'] = 'corte'
            data[f'asignacion_prod[{i}][monto]'] = monto
        errores = _guardar_asignaciones_produccion(self.orden, _qd(data))
        self.assertEqual(errores, [])
        return None

    def _fila(self, empleado):
        return OrdenProduccionEmpleado.objects.filter(
            orden=self.orden, empleado=empleado, responsabilidad='corte').first()

    def test_cambiar_de_fase_deja_lo_pagado_a_favor(self):
        """La fase es parte de la clave natural: mover al empleado de fase es
        quitarlo de una y agregarlo en otra, no la misma devengación."""
        self._pagado_inicial()
        errores = _guardar_asignaciones_produccion(self.orden, _qd({
            'asignaciones_prod_count': '1',
            'asignacion_prod[0][empleado]': str(self.emp.id),
            'asignacion_prod[0][responsabilidad]': 'costura',
            'asignacion_prod[0][monto]': '100.00',
        }))
        self.assertEqual(errores, [])
        datos = _devengaciones_empleado(self.emp)
        self.assertEqual(datos['no_aplicado_comision'], Decimal('100'))
        self.assertEqual(datos['saldo_comision'], Decimal('0'))


# ──────────────────────────────────────────────────────────────────────────────
# Venta — vistas crear_venta / editar_venta (los items se recrean)
# ──────────────────────────────────────────────────────────────────────────────

class VentaEdicionComisionPagadaTests(_EdicionComisionPagadaMixin, TestCase):
    tipo_key = 'venta'

    def _preparar(self):
        self.tr = make_tipo_reparacion()
        self.item = make_prenda_item(make_prenda(nombre='Terno', precio=Decimal('500.00')), tipo='venta')
        self.venta = None

    def _editar(self, asignaciones):
        data = {
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
            'item_asignaciones': [json.dumps([
                {'empleado_id': emp.id, 'monto': monto} for emp, monto in asignaciones
            ])],
        }
        if self.venta is None:
            resp = self.client.post(reverse('crear_venta'), data)
            self.venta = Venta.objects.latest('id')
            return resp
        return self.client.post(reverse('editar_venta', args=[self.venta.id]), data)

    def _fila(self, empleado):
        return VentaItemEmpleado.objects.filter(
            venta_item__venta=self.venta, empleado=empleado).first()

    def test_cambiar_prenda_y_pagar_no_paga_dos_veces(self):
        """Cambiar la prenda del arreglo deja lo pagado huérfano (no hay
        pareja (prenda, empleado)); la fila nueva figura pendiente, pero al
        pagarla se consume el saldo a favor y no sale plata nueva."""
        self._pagado_inicial()
        self.item = make_prenda_item(make_prenda(nombre='Saco', precio=Decimal('500.00')), tipo='venta')
        self._guardar([(self.emp, '100.00'), (self.otro, '30.00')])

        fila = self._fila(self.emp)
        op = self._operacion(_devengaciones_empleado(self.emp), fila)
        self.assertEqual(op['estado'], 'pendiente')

        resp = self._pagar(fila)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PagoComisionEmpleado.objects.filter(empleado=self.emp).count(), 1)
        datos = _devengaciones_empleado(self.emp)
        self.assertEqual(self._operacion(datos, fila)['estado'], 'pagada')
        self.assertEqual(datos['no_aplicado_comision'], Decimal('0'))
        # El snapshot nuevo describe la operación, no "object (n)".
        ap = AplicacionPagoComision.objects.get(pago__empleado=self.emp)
        self.assertIn(self.venta.codigo, ap.detalle_snapshot)
        self.assertIn(self.item.codigo_item, ap.detalle_snapshot)
        self.assertNotIn('object (', ap.detalle_snapshot)


# ──────────────────────────────────────────────────────────────────────────────
# Alquiler — vistas crear_alquiler / editar_alquiler (los items se recrean)
# ──────────────────────────────────────────────────────────────────────────────

class AlquilerEdicionComisionPagadaTests(_EdicionComisionPagadaMixin, TestCase):
    tipo_key = 'alquiler'

    def _preparar(self):
        self.item = make_prenda_item(
            make_prenda(nombre='Frac', precio_alquiler_base=Decimal('250.00')), tipo='alquiler')
        self.alquiler = None

    def _editar(self, asignaciones):
        data = {
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
                {'empleado_id': emp.id, 'monto': monto} for emp, monto in asignaciones
            ])],
        }
        if self.alquiler is None:
            resp = self.client.post(reverse('crear_alquiler'), data)
            self.alquiler = Alquiler.objects.latest('id')
            return resp
        return self.client.post(reverse('editar_alquiler', args=[self.alquiler.id]), data)

    def _fila(self, empleado):
        return AlquilerItemEmpleado.objects.filter(
            alquiler_item__alquiler=self.alquiler, empleado=empleado).first()


# ──────────────────────────────────────────────────────────────────────────────
# Restricción de la tabla: a lo sumo una FK de asignación
# ──────────────────────────────────────────────────────────────────────────────

class RestriccionAplicacionTests(TestCase):

    def setUp(self):
        self.emp = make_empleado()
        self.pago = PagoComisionEmpleado.objects.create(empleado=self.emp, monto=Decimal('10'))

    def test_aplicacion_huerfana_es_valida(self):
        ap = AplicacionPagoComision.objects.create(
            pago=self.pago, monto=Decimal('10'), detalle_snapshot='historial')
        self.assertIsNone(ap.asignacion)

    def test_dos_fk_a_la_vez_se_rechaza(self):
        rep = make_reparacion()
        conf = make_confeccion()
        re_ = ReparacionEmpleado.objects.create(reparacion=rep, empleado=self.emp, monto_comision_fijo=Decimal('10'))
        ce = ConfeccionEmpleado.objects.create(confeccion=conf, empleado=self.emp, monto_comision_fijo=Decimal('10'))
        with self.assertRaises(IntegrityError), transaction.atomic():
            AplicacionPagoComision.objects.create(
                pago=self.pago, monto=Decimal('10'),
                reparacion_empleado=re_, confeccion_empleado=ce)


# VentaForm exige cliente y empleado desde que una venta sin cliente deja una
# deuda sin deudor. Estos tests miden otra cosa, así que usan los de mostrador:
# el FK `empleado` del servicio no devenga comisión —eso sale de las tablas de
# asignación—, así que no interfiere con ningún assert.
from .factories import cliente_y_empleado_de_mostrador as _mostrador


def _cli_mostrador():
    return _mostrador()[0]


def _emp_mostrador():
    return _mostrador()[1]
