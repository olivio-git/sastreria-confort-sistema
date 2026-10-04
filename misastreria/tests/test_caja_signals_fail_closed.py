"""
Contrato "falla cerrada" del choke point de caja (4ª verificación, W2/W3).

Las señales post_save de Reparación/Confección/Venta escriben movimientos
nuevos SÓLO con un actor explícito (`instance._actor_caja`, estampado por la
vista) que sea el dueño de la sesión abierta. Los factories de test infieren
el actor; estos tests lo omiten a propósito para que un cambio que "adivine"
el dueño en producción (patrón de los factories) rompa la suite.

También prueba directo `_crear_mov_auto` y
`_ajustar_garantia_alquiler_en_caja` (que además debe dejar el actor en las
filas de reverso que crea).
"""
from decimal import Decimal

from django.test import TestCase

from misastreria.caja_signals import (
    _ajustar_garantia_alquiler_en_caja, _crear_mov_auto,
    registrar_garantia_alquiler_en_caja,
)
from misastreria.caja_turno import CajaSinSesionError, TurnoCajaError
from misastreria.models import CajaMovimiento, Confeccion, Reparacion, Venta
from .factories import (
    make_administrador, make_cajero, make_vendedor,
    make_sesion_caja, make_reparacion, make_confeccion, make_alquiler,
)


def _movs(**filtro):
    return CajaMovimiento.objects.filter(**filtro).count()


class SenalReparacionFallaCerradaTests(TestCase):
    def setUp(self):
        self.dueno = make_cajero(username='dueno')
        self.rep = make_reparacion(estado='en_proceso', total=Decimal('100.00'))
        self.sesion = make_sesion_caja(usuario=self.dueno)

    def _entregar(self, actor=None):
        rep = Reparacion.objects.get(pk=self.rep.pk)
        rep.estado = 'entregado'
        if actor is not None:
            rep._actor_caja = actor
        rep.save()
        return rep

    def test_sin_actor_no_escribe_el_saldo(self):
        with self.assertRaises(TurnoCajaError):
            self._entregar()
        self.assertEqual(_movs(referencia_reparacion=self.rep), 0)

    def test_actor_ajeno_no_escribe_el_saldo(self):
        with self.assertRaises(TurnoCajaError):
            self._entregar(make_administrador())
        self.assertEqual(_movs(referencia_reparacion=self.rep), 0)

    def test_dueno_escribe_el_saldo_a_su_nombre(self):
        self._entregar(self.dueno)
        mov = CajaMovimiento.objects.get(referencia_reparacion=self.rep)
        self.assertEqual((mov.concepto, mov.monto, mov.usuario_id, mov.sesion_id),
                         ('reparacion_saldo', Decimal('100.00'), self.dueno.id, self.sesion.id))

    def _entregada_con_cobro(self):
        self._entregar(self.dueno)
        return Reparacion.objects.get(pk=self.rep.pk)

    def _regresar(self, actor=None):
        rep = Reparacion.objects.get(pk=self.rep.pk)
        rep.estado = 'pendiente'
        if actor is not None:
            rep._actor_caja = actor
        rep.save()

    def test_regresion_sin_actor_no_reversa(self):
        self._entregada_con_cobro()
        with self.assertRaises(TurnoCajaError):
            self._regresar()
        self.assertEqual(_movs(referencia_reparacion=self.rep, concepto='anulacion_cobro'), 0)

    def test_regresion_de_actor_sin_turno_ni_supervision_no_reversa(self):
        self._entregada_con_cobro()
        with self.assertRaises(TurnoCajaError):
            self._regresar(make_vendedor())
        self.assertEqual(_movs(referencia_reparacion=self.rep, concepto='anulacion_cobro'), 0)

    def test_regresion_por_administrador_no_dueno_si_reversa(self):
        """Reversión = dueño o Administrador (regla del dueño del producto)."""
        self._entregada_con_cobro()
        admin = make_administrador()
        self._regresar(admin)
        rev = CajaMovimiento.objects.get(referencia_reparacion=self.rep, concepto='anulacion_cobro')
        self.assertEqual(rev.usuario_id, admin.id)


class SenalConfeccionFallaCerradaTests(TestCase):
    def setUp(self):
        self.dueno = make_cajero(username='dueno')
        self.conf = make_confeccion(estado='en_proceso', precio=Decimal('300'), adelanto=Decimal('0'))
        self.sesion = make_sesion_caja(usuario=self.dueno)

    def _guardar(self, actor=None, **cambios):
        conf = Confeccion.objects.get(pk=self.conf.pk)
        for campo, valor in cambios.items():
            setattr(conf, campo, valor)
        if actor is not None:
            conf._actor_caja = actor
        conf.save()

    def test_entregar_sin_actor_no_escribe_el_saldo(self):
        with self.assertRaises(TurnoCajaError):
            self._guardar(estado='entregado')
        self.assertEqual(_movs(referencia_confeccion=self.conf), 0)

    def test_entregar_con_actor_ajeno_no_escribe_el_saldo(self):
        with self.assertRaises(TurnoCajaError):
            self._guardar(make_administrador(), estado='entregado')
        self.assertEqual(_movs(referencia_confeccion=self.conf), 0)

    def test_entregar_dueno_escribe_el_saldo(self):
        self._guardar(self.dueno, estado='entregado')
        mov = CajaMovimiento.objects.get(referencia_confeccion=self.conf)
        self.assertEqual((mov.concepto, mov.monto, mov.usuario_id),
                         ('confeccion_saldo', Decimal('300.00'), self.dueno.id))

    def test_cambio_de_adelanto_sin_actor_no_escribe(self):
        with self.assertRaises(TurnoCajaError):
            self._guardar(adelanto=Decimal('50'))
        self.assertEqual(_movs(referencia_confeccion=self.conf), 0)

    def test_cambio_de_adelanto_con_actor_ajeno_no_escribe(self):
        with self.assertRaises(TurnoCajaError):
            self._guardar(make_administrador(), adelanto=Decimal('50'))
        self.assertEqual(_movs(referencia_confeccion=self.conf), 0)

    def test_cambio_de_adelanto_dueno_escribe_el_delta(self):
        self._guardar(self.dueno, adelanto=Decimal('50'))
        mov = CajaMovimiento.objects.get(referencia_confeccion=self.conf)
        self.assertEqual((mov.concepto, mov.monto, mov.usuario_id),
                         ('confeccion_adelanto', Decimal('50.00'), self.dueno.id))


class SenalVentaFallaCerradaTests(TestCase):
    def setUp(self):
        self.dueno = make_cajero(username='dueno')
        self.sesion = make_sesion_caja(usuario=self.dueno)

    def _crear(self, actor=None):
        venta = Venta(descuento=Decimal('0'), subtotal=Decimal('100'), total=Decimal('100'))
        if actor is not None:
            venta._actor_caja = actor
        venta.save()
        return venta

    def test_sin_actor_no_cobra(self):
        with self.assertRaises(TurnoCajaError):
            self._crear()
        self.assertEqual(_movs(referencia_venta__isnull=False), 0)

    def test_actor_ajeno_no_cobra(self):
        with self.assertRaises(TurnoCajaError):
            self._crear(make_administrador())
        self.assertEqual(_movs(referencia_venta__isnull=False), 0)

    def test_dueno_cobra_a_su_nombre(self):
        venta = self._crear(self.dueno)
        mov = CajaMovimiento.objects.get(referencia_venta=venta)
        self.assertEqual((mov.concepto, mov.monto, mov.usuario_id),
                         ('venta_cobro', Decimal('100.00'), self.dueno.id))


class CrearMovAutoUnidadTests(TestCase):
    """`_crear_mov_auto` es el choke point: se prueba solo, sin señales ni vistas."""

    def _crear(self, usuario, **extra):
        return _crear_mov_auto(
            concepto='ingreso_manual', monto=Decimal('40'), forma_pago='efectivo',
            descripcion='prueba', usuario=usuario, **extra,
        )

    def test_sin_ninguna_sesion_levanta_sin_sesion(self):
        with self.assertRaises(CajaSinSesionError):
            self._crear(make_cajero())
        self.assertEqual(_movs(), 0)

    def test_usuario_none_levanta(self):
        make_sesion_caja(usuario=make_cajero())
        with self.assertRaises(TurnoCajaError):
            self._crear(None)
        self.assertEqual(_movs(), 0)

    def test_otro_usuario_levanta(self):
        make_sesion_caja(usuario=make_cajero(username='a'))
        with self.assertRaises(TurnoCajaError):
            self._crear(make_cajero(username='b'))
        self.assertEqual(_movs(), 0)

    def test_administrador_no_dueno_no_esta_exento(self):
        make_sesion_caja(usuario=make_cajero())
        with self.assertRaises(TurnoCajaError):
            self._crear(make_administrador())
        self.assertEqual(_movs(), 0)

    def test_reserva_tambien_exige_ser_dueno(self):
        make_sesion_caja(usuario=make_cajero())
        with self.assertRaises(TurnoCajaError):
            self._crear(make_administrador(), via_caja=False)
        self.assertEqual(_movs(), 0)

    def test_dueno_crea_con_su_usuario_y_su_sesion(self):
        cajero = make_cajero()
        sesion = make_sesion_caja(usuario=cajero)
        mov = self._crear(cajero)
        self.assertEqual((mov.usuario_id, mov.sesion_id, mov.via_caja, mov.monto),
                         (cajero.id, sesion.id, True, Decimal('40')))

    def test_dueno_reserva_con_via_caja_false_en_su_sesion(self):
        cajero = make_cajero()
        sesion = make_sesion_caja(usuario=cajero)
        mov = self._crear(cajero, via_caja=False)
        self.assertEqual((mov.via_caja, mov.sesion_id), (False, sesion.id))

    def test_monto_cero_no_crea_nada(self):
        cajero = make_cajero()
        make_sesion_caja(usuario=cajero)
        self.assertIsNone(_crear_mov_auto(
            concepto='ingreso_manual', monto=Decimal('0'), forma_pago='efectivo',
            descripcion='x', usuario=cajero,
        ))
        self.assertEqual(_movs(), 0)


class AjustarGarantiaAlquilerTests(TestCase):
    def setUp(self):
        self.dueno = make_cajero(username='dueno')
        self.sesion = make_sesion_caja(usuario=self.dueno)
        self.alq = make_alquiler(garantia_tipo='efectivo', garantia_monto=Decimal('100'))
        registrar_garantia_alquiler_en_caja(self.alq, usuario=self.dueno)

    def _editar(self, tipo, monto):
        alq = type(self.alq).objects.get(pk=self.alq.pk)
        alq.garantia_tipo = tipo
        alq.garantia_monto = monto
        return alq

    def test_sin_cambio_no_toca_caja(self):
        _ajustar_garantia_alquiler_en_caja(self._editar('efectivo', Decimal('100')), usuario=self.dueno)
        self.assertEqual(_movs(referencia_alquiler=self.alq), 1)

    def test_cambio_de_monto_reversa_y_recrea_a_nombre_del_dueno(self):
        _ajustar_garantia_alquiler_en_caja(self._editar('efectivo', Decimal('150')), usuario=self.dueno)
        reverso = CajaMovimiento.objects.get(
            referencia_alquiler=self.alq, concepto='anulacion_cobro')
        self.assertEqual((reverso.tipo, reverso.monto, reverso.usuario_id, reverso.sesion_id),
                         ('egreso', Decimal('100.00'), self.dueno.id, self.sesion.id))
        nueva = CajaMovimiento.objects.get(
            referencia_alquiler=self.alq, concepto='garantia_alquiler',
            movimiento_reverso__isnull=True)
        self.assertEqual((nueva.monto, nueva.usuario_id), (Decimal('150.00'), self.dueno.id))

    def test_garantia_no_monetaria_reversa_a_nombre_del_dueno(self):
        _ajustar_garantia_alquiler_en_caja(self._editar('descripcion', None), usuario=self.dueno)
        reverso = CajaMovimiento.objects.get(
            referencia_alquiler=self.alq, concepto='anulacion_cobro')
        self.assertEqual((reverso.tipo, reverso.usuario_id), ('egreso', self.dueno.id))
        self.assertEqual(_movs(referencia_alquiler=self.alq, concepto='garantia_alquiler',
                               movimiento_reverso__isnull=True), 0)

    def test_no_dueno_no_puede_cambiar_el_monto(self):
        for intruso in (make_administrador(), make_cajero(username='otro'), make_vendedor()):
            with self.subTest(usuario=intruso.username):
                with self.assertRaises(TurnoCajaError):
                    _ajustar_garantia_alquiler_en_caja(
                        self._editar('efectivo', Decimal('150')), usuario=intruso)
                self.assertEqual(_movs(referencia_alquiler=self.alq), 1)

    def test_no_dueno_no_puede_quitar_la_garantia(self):
        with self.assertRaises(TurnoCajaError):
            _ajustar_garantia_alquiler_en_caja(
                self._editar('', None), usuario=make_administrador())
        self.assertEqual(_movs(referencia_alquiler=self.alq), 1)

    def test_usuario_none_levanta(self):
        with self.assertRaises(TurnoCajaError):
            _ajustar_garantia_alquiler_en_caja(self._editar('efectivo', Decimal('150')), usuario=None)
        self.assertEqual(_movs(referencia_alquiler=self.alq), 1)

    def test_sin_sesion_abierta_levanta_sin_sesion(self):
        self.sesion.estado = 'cerrada'
        self.sesion.save()
        with self.assertRaises(CajaSinSesionError):
            _ajustar_garantia_alquiler_en_caja(
                self._editar('efectivo', Decimal('150')), usuario=self.dueno)
        with self.assertRaises(CajaSinSesionError):
            _ajustar_garantia_alquiler_en_caja(self._editar('', None), usuario=self.dueno)
        self.assertEqual(_movs(referencia_alquiler=self.alq), 1)
