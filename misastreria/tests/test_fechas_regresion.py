"""
Regresion: los reportes/dashboard deben contar bien movimientos pegados al
borde del dia local, en especial los de la tarde-noche (UTC ya es el dia
siguiente) y los de la madrugada (UTC aun es el dia anterior).

Estos tests son los que fallaban en MariaDB sin tablas de zona horaria
(CONVERT_TZ -> NULL -> 0 filas). En SQLite pasan antes y despues.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from misastreria import views
from .factories import (
    make_user, make_sesion_caja, make_movimiento_caja, make_cliente,
    make_reparacion, desbloquear_caja_test,
)
from misastreria.models import PerfilUsuario
from django.contrib.auth.hashers import make_password

LP = timezone.get_current_timezone()


def local(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=LP)


class Base(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = Client()
        self.client.force_login(self.user)
        self.sesion = make_sesion_caja(usuario=self.user)
        self.hoy = timezone.localdate()

    def mov(self, dia, hh, mm=0, ss=0, tipo='ingreso', monto='10.00',
            concepto=None):
        concepto = concepto or ('ingreso_manual' if tipo == 'ingreso' else 'egreso_manual')
        return make_movimiento_caja(
            sesion=self.sesion, tipo=tipo, monto=Decimal(monto),
            concepto=concepto, fecha=local(dia.year, dia.month, dia.day, hh, mm, ss),
        )


class DashboardTests(Base):

    def setUp(self):
        super().setUp()
        # Mes fijo en el pasado reciente no sirve: el dashboard usa "hoy" real.
        # Usamos hoy y el primer dia del mes, cuidando que exista mes previo.
        self.primero = self.hoy.replace(day=1)

    def test_caja_hoy_incluye_hasta_23_59_59_local_y_excluye_medianoche_siguiente(self):
        self.mov(self.hoy, 0, 0, 0, monto='1.00')           # incluido
        self.mov(self.hoy, 23, 59, 59, monto='2.00')        # incluido (UTC ya es manana)
        self.mov(self.hoy - timedelta(days=1), 23, 59, 59, monto='100.00')  # ayer
        self.mov(self.hoy + timedelta(days=1), 0, 0, 0, monto='200.00')     # manana
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['caja_hoy']['ingresos'], Decimal('3.00'))

    def test_caja_hoy_egresos_y_saldo(self):
        self.mov(self.hoy, 21, 0, tipo='ingreso', monto='30.00')
        self.mov(self.hoy, 21, 30, tipo='egreso', monto='12.00')
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['caja_hoy']['egresos'], Decimal('12.00'))
        self.assertEqual(r.context['caja_hoy']['saldo'], Decimal('18.00'))

    def test_kpis_mes_actual_cuenta_movimientos_de_noche_y_madrugada(self):
        self.mov(self.primero, 0, 0, 0, monto='5.00')       # madrugada del dia 1
        self.mov(self.hoy, 22, 0, monto='7.00')             # noche de hoy
        antes = self.primero - timedelta(days=1)
        self.mov(antes, 23, 59, 59, monto='1000.00')        # mes anterior
        kpis = views._dashboard_kpis(self.hoy)
        self.assertEqual(kpis['ingresos_mes'], Decimal('12.00'))
        self.assertEqual(kpis['ingresos_anterior'], Decimal('1000.00'))

    def test_kpis_egresos_mes(self):
        self.mov(self.hoy, 20, 0, tipo='egreso', monto='9.00')
        self.assertEqual(views._dashboard_kpis(self.hoy)['egresos_mes'], Decimal('9.00'))

    def test_kpis_clientes_nuevos_por_fecha_local(self):
        c1 = make_cliente(ci='111')
        c2 = make_cliente(ci='222', nombres='Otro')
        # c1 creado hoy 23:30 local; c2 creado el mes anterior 23:30 local.
        from misastreria.models import Cliente
        Cliente.objects.filter(pk=c1.pk).update(
            creado=local(self.hoy.year, self.hoy.month, self.hoy.day, 23, 30))
        antes = self.primero - timedelta(days=1)
        Cliente.objects.filter(pk=c2.pk).update(
            creado=local(antes.year, antes.month, antes.day, 23, 30))
        self.assertEqual(views._dashboard_kpis(self.hoy)['clientes_nuevos'], 1)

    def test_donut_agrupa_por_servicio_en_el_mes(self):
        mes_inicio = max(self.primero, views.FECHA_MIGRACION_CAJA)
        self.mov(mes_inicio, 23, 0, concepto='venta_cobro', monto='40.00')
        self.mov(self.hoy, 21, 0, concepto='reparacion_cobro', monto='15.00')
        donut = {d['label']: d['value'] for d in views._dashboard_donut_chart(self.hoy)}
        self.assertEqual(donut.get('Venta'), 40.0)
        self.assertEqual(donut.get('Reparación'), 15.0)

    def test_trend_agrupa_por_semana_local(self):
        # Un movimiento la noche del domingo local (UTC ya es lunes) debe
        # caer en la semana del lunes anterior, no en la siguiente.
        lunes = self.hoy - timedelta(days=self.hoy.weekday())
        domingo_ant = lunes - timedelta(days=1)
        if domingo_ant < views.FECHA_MIGRACION_CAJA:
            self.skipTest('antes de la migracion de caja')
        self.mov(domingo_ant, 22, 0, monto='8.00')
        self.mov(self.hoy, 1, 0, monto='3.00')
        trend = views._dashboard_trend_chart(self.hoy)
        etiquetas = {t['label']: t['ingresos'] for t in trend}
        sem_ant = (domingo_ant - timedelta(days=domingo_ant.weekday())).strftime('%-d/%-m')
        sem_act = lunes.strftime('%-d/%-m')
        self.assertEqual(etiquetas[sem_ant], 8.0)
        self.assertEqual(etiquetas[sem_act], 3.0)


class CajaReportesTests(Base):

    def setUp(self):
        super().setUp()
        # Las vistas /caja/* piden PIN (CajaPinMiddleware): el usuario lo
        # tiene configurado y ya lo ingresó en esta sesión.
        PerfilUsuario.objects.update_or_create(
            user=self.user, defaults={'pin_hash': make_password('1234')})
        desbloquear_caja_test(self.client, self.user)
        self.ayer = self.hoy - timedelta(days=1)

    def test_lista_movimientos_filtra_por_dia_local(self):
        self.mov(self.ayer, 23, 59, 59)
        self.mov(self.hoy, 0, 0, 0)
        self.mov(self.hoy, 23, 59, 59)
        r = self.client.get(reverse('lista_movimientos_caja'),
                            {'desde': self.hoy.isoformat(), 'hasta': self.hoy.isoformat()})
        self.assertEqual(r.context['total'], 2)

    def test_lista_movimientos_solo_desde(self):
        self.mov(self.ayer, 23, 59, 59)
        self.mov(self.hoy, 0, 0, 0)
        r = self.client.get(reverse('lista_movimientos_caja'), {'desde': self.hoy.isoformat()})
        self.assertEqual(r.context['total'], 1)

    def test_lista_movimientos_fecha_invalida_se_ignora(self):
        self.mov(self.hoy, 12)
        r = self.client.get(reverse('lista_movimientos_caja'), {'desde': 'xx', 'hasta': 'yy'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total'], 1)

    def test_resumen_caja_hoy(self):
        self.mov(self.ayer, 23, 59, 59, monto='100.00')
        self.mov(self.hoy, 0, 0, 0, monto='4.00')
        self.mov(self.hoy, 23, 59, 59, monto='6.00')
        r = self.client.get(reverse('resumen_caja'), {'periodo': 'hoy'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_ingresos'], Decimal('10.00'))
        self.assertEqual(len(r.context['movimientos_detalle']), 2)

    def test_resumen_flujo_diario_agrupa_por_dia_local(self):
        self.mov(self.ayer, 22, 0, monto='5.00')   # UTC ya es hoy
        self.mov(self.hoy, 2, 0, monto='7.00')     # UTC aun es hoy
        self.mov(self.hoy, 22, 0, monto='1.00', tipo='egreso')
        r = self.client.get(reverse('resumen_caja'), {
            'periodo': 'custom', 'desde': self.ayer.isoformat(), 'hasta': self.hoy.isoformat()})
        flujo = {f['fecha']: f for f in r.context['flujo_diario']}
        self.assertEqual(flujo[self.ayer]['ingresos'], Decimal('5.00'))
        self.assertEqual(flujo[self.hoy]['ingresos'], Decimal('7.00'))
        self.assertEqual(flujo[self.hoy]['egresos'], Decimal('1.00'))

    def test_resumen_sesiones_periodo_por_fecha_apertura_local(self):
        from misastreria.models import CajaSesion
        CajaSesion.objects.filter(pk=self.sesion.pk).update(
            fecha_apertura=local(self.hoy.year, self.hoy.month, self.hoy.day, 23, 30))
        r = self.client.get(reverse('resumen_caja'), {'periodo': 'hoy'})
        self.assertEqual(len(r.context['sesiones_periodo']), 1)

    def test_reporte_transacciones_periodo_hoy(self):
        self.mov(self.ayer, 23, 59, 59)
        self.mov(self.hoy, 23, 59, 59)
        r = self.client.get(reverse('reporte_transacciones'), {'periodo': 'hoy'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['page_obj'].object_list), 1)

    def test_kardex_financiero_totales_y_grafico_diario(self):
        self.mov(self.ayer, 22, 0, monto='5.00')
        self.mov(self.hoy, 22, 0, monto='7.00')
        r = self.client.get(reverse('kardex_financiero'), {
            'desde': self.ayer.isoformat(), 'hasta': self.hoy.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_ingresos'], Decimal('12.00'))
        chart = r.context['chart_daily']
        chart = json.loads(chart) if isinstance(chart, str) else chart
        por_dia = {c['label']: c['ingresos'] for c in chart}
        self.assertEqual(por_dia[self.ayer.isoformat()], 5.0)
        self.assertEqual(por_dia[self.hoy.isoformat()], 7.0)

    def test_kardex_daily_chart_semanal_usa_semana_iso_local(self):
        from misastreria.models import CajaMovimiento
        desde = self.hoy - timedelta(days=90)
        self.mov(self.hoy, 22, 0, monto='3.00')
        chart = views._kardex_daily_chart(CajaMovimiento.objects.all(), desde, self.hoy)
        y, w, _ = self.hoy.isocalendar()
        valores = {c['label']: c['ingresos'] for c in chart}
        self.assertEqual(valores[f'{y}-W{w:02d}'], 3.0)


class ServiciosReportesTests(TestCase):
    """Reparacion.creado es DateTimeField: debe filtrarse por dia local."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.cliente = make_cliente(ci='900')
        from misastreria.models import Reparacion
        self.r_noche = make_reparacion(cliente=self.cliente, total=Decimal('30.00'))
        self.r_ayer = make_reparacion(cliente=self.cliente, total=Decimal('70.00'))
        Reparacion.objects.filter(pk=self.r_noche.pk).update(
            creado=local(self.hoy.year, self.hoy.month, self.hoy.day, 23, 59, 59))
        ayer = self.hoy - timedelta(days=1)
        Reparacion.objects.filter(pk=self.r_ayer.pk).update(
            creado=local(ayer.year, ayer.month, ayer.day, 23, 59, 59))

    def test_yoy_totals_reparaciones_solo_hoy(self):
        t = views._yoy_totals(self.hoy, self.hoy)
        self.assertEqual(t['reparaciones'], 30.0)

    def test_top_clients_reparaciones_solo_hoy(self):
        filas = views._top_clients(self.hoy, self.hoy)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['total_reparaciones'], 30.0)

    def test_kpis_operativas_reparaciones_del_dia(self):
        from misastreria.models import Reparacion
        Reparacion.objects.update(estado='entregado')
        k = views._kpis_operativas(self.hoy, self.hoy)
        self.assertEqual(k['reparacion_count'], 1)

    def test_top_empleados_reparaciones_del_dia(self):
        from .factories import make_empleado
        emp = make_empleado()
        from misastreria.models import Reparacion
        Reparacion.objects.update(empleado=emp)
        filas = views._top_empleados(self.hoy, self.hoy)
        self.assertEqual(len(filas), 1)

    def test_estacionalidad_reparaciones_por_mes_local(self):
        from misastreria.models import Reparacion
        # Ultima noche del mes local = primer dia del mes siguiente en UTC.
        ultimo = (self.hoy.replace(day=1) - timedelta(days=1))
        Reparacion.objects.filter(pk=self.r_ayer.pk).update(
            creado=local(ultimo.year, ultimo.month, ultimo.day, 23, 30))
        c = Client()
        c.force_login(make_user())
        r = c.get(reverse('analitica_estacionalidad'), {'año': ultimo.year})
        self.assertEqual(r.status_code, 200)
        fila_ultimo = r.context['tabla'][ultimo.month - 1]
        self.assertGreaterEqual(fila_ultimo['reparaciones'], 1)
