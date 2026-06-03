from decimal import Decimal
from itertools import zip_longest
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Count, Q, Avg, OuterRef, Subquery, Value, Exists
from django.db.models.functions import Coalesce, Greatest
from django.db import transaction, IntegrityError
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone as django_tz
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from .models import Empleado, TipoContrato, Cliente, Reparacion, ReparacionItem, TipoPrenda, TipoReparacion, Venta, VentaItem, Confeccion, ConfeccionItem, Alquiler, AlquilerItem, EstadoAlquiler, Transaccion, PrendaInventario, PrendaItem, UbicacionItem, Insumo, TipoMaterial, UnidadMedida, Permiso, Falta, OrdenProduccion, InsumoCortado, CajaSesion, CajaMovimiento, TipoGasto, Conjunto, ConjuntoSlot, PagoComisionEmpleado, ModeloConfeccion
from .forms import EmpleadoForm, ClienteForm, ReparacionForm, ReparacionItemForm, VentaForm, VentaItemForm, ConfeccionForm, ConfeccionItemFormSet, AlquilerForm, AlquilerItemForm, TransaccionForm, PrendaInventarioForm, InsumoForm, PermisoForm, FaltaForm, EmpleadoReporteForm, ClienteReporteForm, ReparacionReporteForm, OrdenProduccionForm, InsumoCortadoForm, CajaSesionAperturaForm, CajaSesionCierreForm, CajaMovimientoManualForm, TipoGastoForm, ConjuntoForm, ConjuntoSlotFormSet, PagoComisionEmpleadoForm
from django.core.paginator import Paginator
from datetime import date, datetime, timedelta
from dateutil import rrule
from dateutil.rrule import WEEKLY, MO, TU, WE, TH, FR
import calendar
import json
from django.http import HttpResponse, JsonResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from django.db.models import Q, ProtectedError
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics # Para registrar fuentes en ReportLab
from reportlab.pdfbase.ttfonts import TTFont # Para usar fuentes TrueType en ReportLab
from django.forms import ValidationError
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.utils import ImageReader
import csv
import os
import io
from django.conf import settings
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from io import BytesIO # Para manejar el archivo en memoria
from . import kardex_events
FONT_PATH = os.path.join(settings.BASE_DIR, 'misastreria', 'static', 'font', 'DejaVuSans.ttf')


# Esta es la línea que está causando el error
pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))

# ============================================================
# Analytics — module-level constants
# ============================================================

# Built from CajaMovimiento.CONCEPTO_CHOICES — single source of truth.
# Legacy keys (pre-refactor) added at the end to handle old data.
def _build_concepto_labels():
    from misastreria.models import CajaMovimiento as _CM
    labels = dict(_CM.CONCEPTO_CHOICES)
    labels.update({
        'confeccion_cobro': 'Cobro Confección',  # legacy
        'gasto':            'Gasto',              # legacy
    })
    return labels

CONCEPTO_LABELS = _build_concepto_labels()

CONCEPTOS_OPERATIVOS = [
    'apertura_caja', 'sobrante_caja', 'faltante_caja',
    'garantia_alquiler', 'garantia_devolucion',
]

FECHA_MIGRACION_CAJA = date(2026, 5, 8)

MESES_ES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
            'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

@login_required
def dashboard(request):
    prendas_alerta = PrendaInventario.objects.annotate(
        stock_total=Count('items', filter=~Q(items__estado='baja')),
    ).filter(
        estado='ACT', stock_minimo__isnull=False, stock_total__lte=F('stock_minimo')
    ).order_by('nombre')

    insumos_alerta = Insumo.objects.filter(
        estado='ACT', stock_minimo__isnull=False
    ).extra(where=['cantidad <= stock_minimo']).order_by('articulo')

    reparaciones_pendientes = Reparacion.objects.filter(estado='pendiente').count()
    alquileres_activos = Alquiler.objects.filter(estado='alquilado').count()
    reservas_activas = Alquiler.objects.filter(estado='reservado').count()
    ordenes_activas = OrdenProduccion.objects.exclude(estado='terminado').count()

    # Caja de hoy
    hoy = django_tz.now().date()
    caja_hoy_qs = CajaMovimiento.objects.filter(
        fecha__date__gte=hoy,
        fecha__date__lte=hoy,
        movimiento_reverso__isnull=True,
        via_caja=True,
    )
    ingresos_hoy = caja_hoy_qs.filter(tipo='ingreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    egresos_hoy = caja_hoy_qs.filter(tipo='egreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    sesion_activa = CajaSesion.objects.filter(estado='abierta').first()
    caja_hoy = {
        'ingresos': ingresos_hoy,
        'egresos': egresos_hoy,
        'saldo': ingresos_hoy - egresos_hoy,
        'sesion': sesion_activa,
    }

    # Analytics
    kpis = _dashboard_kpis(hoy)
    chart_trend = _dashboard_trend_chart(hoy)
    chart_donut = _dashboard_donut_chart(hoy)
    return render(request, 'misastreria/dashboard.html', {
        'prendas_alerta':          prendas_alerta,
        'insumos_alerta':          insumos_alerta,
        'reparaciones_pendientes': reparaciones_pendientes,
        'alquileres_activos':      alquileres_activos,
        'reservas_activas':        reservas_activas,
        'ordenes_activas':         ordenes_activas,
        'caja_hoy':                caja_hoy,
        'kpis':                    kpis,
        'chart_trend':             chart_trend,
        'chart_donut':             chart_donut,
    })

@login_required
def lista_empleados(request):
    empleado_id = request.GET.get('empleado_id', '').strip()
    activo = request.GET.get('activo', '')
    orden = request.GET.get('orden', 'desc')

    sort = '-codigo' if orden == 'desc' else 'codigo'
    empleados = Empleado.objects.order_by(sort)
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()

    selected_empleado = None
    if empleado_id:
        try:
            selected_empleado = Empleado.objects.get(id=empleado_id)
            empleados = empleados.filter(id=empleado_id)
        except Empleado.DoesNotExist:
            empleado_id = ''
    if activo in ('1', '0'):
        empleados = empleados.filter(activo=(activo == '1'))

    paginator = Paginator(empleados, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'misastreria/empleados/lista.html', {
        'page_obj': page_obj, 'empleado_id': empleado_id, 'activo': activo,
        'total': empleados.count(), 'orden': orden, 'orden_toggle_url': orden_toggle_url,
        'selected_empleado': selected_empleado,
    })

@login_required
def crear_empleado(request):
    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_empleados')
    else:
        form = EmpleadoForm()
    return render(request, 'misastreria/empleados/crear.html', {
        'form': form,
        'tipo_contrato_opts': list(TipoContrato.objects.values('id', 'nombre')),
    })

@login_required
def editar_empleado(request, id):
    empleado = get_object_or_404(Empleado, id=id)
    if request.method == 'POST':
        form = EmpleadoForm(request.POST, instance=empleado)
        if form.is_valid():
            form.save()
            return redirect('lista_empleados')
    else:
        form = EmpleadoForm(instance=empleado)
    return render(request, 'misastreria/empleados/editar.html', {
        'form': form,
        'empleado': empleado,
        'tipo_contrato_opts': list(TipoContrato.objects.values('id', 'nombre')),
    })

@login_required
def eliminar_empleado(request, id):
    empleado = get_object_or_404(Empleado, id=id)
    if request.method == 'POST':
        empleado.delete()
        return redirect('lista_empleados')
    return render(request, 'misastreria/empleados/eliminar.html', {'empleado': empleado})

def _calcular_saldo_comision_empleado(empleado):
    """Devengado (asignaciones en trabajos entregados con %) menos total pagado."""
    dev_rep = empleado.asignaciones_reparacion.filter(
        reparacion__estado='entregado'
    ).exclude(porcentaje_comision=0).aggregate(
        s=Sum(
            ExpressionWrapper(
                F('reparacion__total') * F('porcentaje_comision') / Decimal('100'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )['s'] or Decimal('0')

    dev_conf = empleado.asignaciones_confeccion.filter(
        confeccion__estado='entregado'
    ).exclude(porcentaje_comision=0).aggregate(
        s=Sum(
            ExpressionWrapper(
                F('confeccion__precio') * F('porcentaje_comision') / Decimal('100'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )['s'] or Decimal('0')

    dev_venta = empleado.arreglos_venta.filter(
        venta__estado='efectuada'
    ).exclude(porcentaje_comision__isnull=True).exclude(porcentaje_comision=0).aggregate(
        s=Sum(
            ExpressionWrapper(
                F('precio_reparacion') * F('porcentaje_comision') / Decimal('100'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )['s'] or Decimal('0')

    dev_alquiler = empleado.arreglos_alquiler.filter(
        alquiler__estado='devuelto'
    ).exclude(porcentaje_comision__isnull=True).exclude(porcentaje_comision=0).aggregate(
        s=Sum(
            ExpressionWrapper(
                F('precio_reparacion') * F('porcentaje_comision') / Decimal('100'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )['s'] or Decimal('0')

    pagado = empleado.pagos_comision.aggregate(s=Sum('monto'))['s'] or Decimal('0')
    return (dev_rep + dev_conf + dev_venta + dev_alquiler) - pagado


@login_required
def detalle_empleado(request, id):
    empleado = get_object_or_404(Empleado, id=id)
    permisos = empleado.permisos.order_by('-fecha_permiso')
    faltas = empleado.faltas.order_by('-fecha_falta')

    # Reparaciones entregadas con comision asignada (vía tabla de asignaciones)
    reparaciones_comision = empleado.asignaciones_reparacion.filter(
        reparacion__estado='entregado',
    ).exclude(porcentaje_comision=0).select_related('reparacion__cliente').annotate(
        monto_comision_calc=ExpressionWrapper(
            F('reparacion__total') * F('porcentaje_comision') / Decimal('100'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by('-reparacion__fecha_entrega', '-id')

    # Confecciones entregadas con comision asignada (vía tabla de asignaciones)
    confecciones_comision = empleado.asignaciones_confeccion.filter(
        confeccion__estado='entregado',
    ).exclude(porcentaje_comision=0).select_related('confeccion__cliente').annotate(
        monto_comision_calc=ExpressionWrapper(
            F('confeccion__precio') * F('porcentaje_comision') / Decimal('100'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by('-confeccion__fecha_entrega', '-id')

    # Arreglos de ventas efectuadas con comision asignada
    arreglos_venta_comision = empleado.arreglos_venta.filter(
        venta__estado='efectuada',
    ).exclude(porcentaje_comision__isnull=True).exclude(porcentaje_comision=0).select_related(
        'venta__cliente', 'prenda_item', 'tipo_reparacion',
    ).annotate(
        monto_comision_calc=ExpressionWrapper(
            F('precio_reparacion') * F('porcentaje_comision') / Decimal('100'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by('-venta__id', '-id')

    # Arreglos de alquileres devueltos con comision asignada
    arreglos_alquiler_comision = empleado.arreglos_alquiler.filter(
        alquiler__estado='devuelto',
    ).exclude(porcentaje_comision__isnull=True).exclude(porcentaje_comision=0).select_related(
        'alquiler__cliente', 'prenda_item', 'tipo_reparacion',
    ).annotate(
        monto_comision_calc=ExpressionWrapper(
            F('precio_reparacion') * F('porcentaje_comision') / Decimal('100'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    ).order_by('-alquiler__id', '-id')

    # Totales devengados
    total_devengado_rep = reparaciones_comision.aggregate(
        s=Sum('monto_comision_calc')
    )['s'] or Decimal('0')
    total_devengado_conf = confecciones_comision.aggregate(
        s=Sum('monto_comision_calc')
    )['s'] or Decimal('0')
    total_devengado_venta = arreglos_venta_comision.aggregate(
        s=Sum('monto_comision_calc')
    )['s'] or Decimal('0')
    total_devengado_alquiler = arreglos_alquiler_comision.aggregate(
        s=Sum('monto_comision_calc')
    )['s'] or Decimal('0')
    total_devengado = (
        total_devengado_rep + total_devengado_conf
        + total_devengado_venta + total_devengado_alquiler
    )

    # Pagos
    pagos_comision = empleado.pagos_comision.order_by('-fecha', '-id')
    total_pagado = pagos_comision.aggregate(s=Sum('monto'))['s'] or Decimal('0')

    saldo_comision = total_devengado - total_pagado

    return render(request, 'misastreria/empleados/detalle.html', {
        'empleado': empleado,
        'permisos': permisos,
        'faltas': faltas,
        'reparaciones_comision': reparaciones_comision,
        'confecciones_comision': confecciones_comision,
        'arreglos_venta_comision': arreglos_venta_comision,
        'arreglos_alquiler_comision': arreglos_alquiler_comision,
        'pagos_comision': pagos_comision,
        'total_devengado': total_devengado,
        'total_pagado': total_pagado,
        'saldo_comision': saldo_comision,
        'pago_form': PagoComisionEmpleadoForm(),
    })

@login_required
def crear_permiso(request, empleado_id):
    empleado = get_object_or_404(Empleado, id=empleado_id)
    if request.method == 'POST':
        form = PermisoForm(request.POST)
        if form.is_valid():
            permiso = form.save(commit=False)
            permiso.empleado = empleado
            permiso.save()
            return redirect('detalle_empleado', id=empleado_id)
    else:
        form = PermisoForm()
    return render(request, 'misastreria/empleados/crear_permiso.html', {'form': form, 'empleado': empleado})

@login_required
def crear_falta(request, empleado_id):
    empleado = get_object_or_404(Empleado, id=empleado_id)
    if request.method == 'POST':
        form = FaltaForm(request.POST)
        if form.is_valid():
            falta = form.save(commit=False)
            falta.empleado = empleado
            falta.save()
            return redirect('detalle_empleado', id=empleado_id)
    else:
        form = FaltaForm()
    return render(request, 'misastreria/empleados/crear_falta.html', {'form': form, 'empleado': empleado})

@login_required
def eliminar_permiso(request, id):
    permiso = get_object_or_404(Permiso, id=id)
    empleado_id = permiso.empleado.id
    if request.method == 'POST':
        permiso.delete()
    return redirect('detalle_empleado', id=empleado_id)

@login_required
def eliminar_falta(request, id):
    falta = get_object_or_404(Falta, id=id)
    empleado_id = falta.empleado.id
    if request.method == 'POST':
        falta.delete()
    return redirect('detalle_empleado', id=empleado_id)


@login_required
def pagar_comision_empleado(request, empleado_id):
    from django.http import HttpResponseNotAllowed
    from .caja_signals import registrar_pago_comision_empleado

    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    empleado = get_object_or_404(Empleado, id=empleado_id)
    form = PagoComisionEmpleadoForm(request.POST)

    if not form.is_valid():
        for err in form.errors.values():
            messages.error(request, err.as_text())
        return redirect('detalle_empleado', id=empleado_id)

    monto = form.cleaned_data['monto']

    saldo = _calcular_saldo_comision_empleado(empleado)
    if monto > saldo:
        messages.error(
            request,
            f"El pago de Bs {monto:.2f} excede el saldo de comisión pendiente (Bs {saldo:.2f})."
        )
        return redirect('detalle_empleado', id=empleado_id)

    registrar_pago_comision_empleado(
        empleado=empleado,
        monto=monto,
        forma_pago=form.cleaned_data['forma_pago'],
        via_caja=form.cleaned_data.get('via_caja', False),
        descripcion=form.cleaned_data.get('descripcion', ''),
        usuario=request.user,
    )
    via_label = "vía caja" if form.cleaned_data.get('via_caja') else "fuera de caja"
    messages.success(request, f"Comisión de Bs {monto:.2f} registrada ({via_label}).")
    return redirect('detalle_empleado', id=empleado_id)


@login_required
def reporte_dias_trabajados(request):
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    empleados = Empleado.objects.filter(activo=True)
    reportes = []

    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    # Calcular días laborables (lunes a sabado)
    workdays = 0
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() < 6:  # Lunes a sabado
            workdays += 1
        current_date += timedelta(days=1)

    for empleado in empleados:
        permisos = empleado.permisos.filter(fecha_permiso__range=(start_date, end_date)).count()
        faltas = empleado.faltas.filter(fecha_falta__range=(start_date, end_date)).count()
        dias_trabajados = workdays - permisos - faltas
        reportes.append({
            'empleado': empleado,
            'permisos': permisos,
            'faltas': faltas,
            'dias_trabajados': max(dias_trabajados, 0),
            'dias_laborables': workdays
        })

    # Listas para el formulario
    meses = [
        {'valor': 1, 'nombre': 'Enero'},
        {'valor': 2, 'nombre': 'Febrero'},
        {'valor': 3, 'nombre': 'Marzo'},
        {'valor': 4, 'nombre': 'Abril'},
        {'valor': 5, 'nombre': 'Mayo'},
        {'valor': 6, 'nombre': 'Junio'},
        {'valor': 7, 'nombre': 'Julio'},
        {'valor': 8, 'nombre': 'Agosto'},
        {'valor': 9, 'nombre': 'Septiembre'},
        {'valor': 10, 'nombre': 'Octubre'},
        {'valor': 11, 'nombre': 'Noviembre'},
        {'valor': 12, 'nombre': 'Diciembre'},
    ]
    anos = [2023, 2024, 2025, 2026]

    return render(request, 'misastreria/empleados/reporte_dias_trabajados.html', {
        'reportes': reportes,
        'year': year,
        'month': month,
        'meses': meses,
        'anos': anos
    })

@login_required
def lista_clientes(request):
    cliente_id = request.GET.get('cliente_id', '').strip()
    desde      = request.GET.get('desde', '')
    hasta      = request.GET.get('hasta', '')
    orden      = request.GET.get('orden', 'desc')

    sort = '-codigo' if orden == 'desc' else 'codigo'
    clientes = Cliente.objects.order_by(sort)
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()

    if cliente_id:
        clientes = clientes.filter(id=cliente_id)
    if desde:
        clientes = clientes.filter(fecha_registro__gte=desde)
    if hasta:
        clientes = clientes.filter(fecha_registro__lte=hasta)

    paginator = Paginator(clientes, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'misastreria/clientes/lista.html', {
        'page_obj': page_obj, 'cliente_id': cliente_id,
        'desde': desde, 'hasta': hasta,
        'total': clientes.count(), 'orden': orden, 'orden_toggle_url': orden_toggle_url,
    })

@login_required
def crear_cliente(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente creado exitosamente.')
            return redirect('lista_clientes')
    else:
        form = ClienteForm()
    return render(request, 'misastreria/clientes/form.html', {'form': form, 'titulo': 'Crear Cliente'})

@login_required
def editar_cliente(request, id):
    cliente = get_object_or_404(Cliente, id=id)
    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente actualizado exitosamente.')
            return redirect('lista_clientes')
    else:
        form = ClienteForm(instance=cliente)
    return render(request, 'misastreria/clientes/form.html', {'form': form, 'titulo': 'Editar Cliente'})

@login_required
def eliminar_cliente(request, id):
    cliente = get_object_or_404(Cliente, id=id)
    if request.method == 'POST':
        cliente.delete()
        messages.success(request, 'Cliente eliminado exitosamente.')
        return redirect('lista_clientes')
    return render(request, 'misastreria/clientes/eliminar.html', {'cliente': cliente})

def buscar_empleados(request):
    q = request.GET.get('q', '').strip()
    qs = Empleado.objects.filter(activo=True).filter(
        Q(nombres__icontains=q) | Q(apellido_paterno__icontains=q) |
        Q(apellido_materno__icontains=q) | Q(ci__icontains=q)
    ).order_by('nombres', 'apellido_paterno')
    if q:
        qs = qs[:10]
    data = [{'id': e.id, 'ci': e.ci or '', 'nombre': str(e)} for e in qs]
    return JsonResponse(data, safe=False)


def buscar_clientes(request):
    q = request.GET.get('q', '').strip()
    qs = Cliente.objects.filter(
        Q(nombres__icontains=q) | Q(apellido_paterno__icontains=q) |
        Q(apellido_materno__icontains=q) | Q(ci__icontains=q)
    ).order_by('nombres', 'apellido_paterno')
    if q:
        qs = qs[:10]
    data = [{'id': c.id, 'ci': c.ci or '', 'nombre': str(c)} for c in qs]
    return JsonResponse(data, safe=False)


def buscar_tipo_prenda(request):
    q = request.GET.get('q', '').strip()
    qs = TipoPrenda.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'id': t.id, 'nombre': t.nombre, 'plantilla': t.plantilla} for t in qs],
        safe=False,
    )


def crear_tipo_prenda(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    plantilla = request.POST.get('plantilla', '').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    tp = TipoPrenda.objects.create(nombre=nombre, plantilla=plantilla)
    return JsonResponse({'id': tp.id, 'nombre': tp.nombre, 'plantilla': tp.plantilla})


def buscar_tipo_reparacion(request):
    q = request.GET.get('q', '').strip()
    qs = TipoReparacion.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'id': t.id, 'nombre': t.nombre} for t in qs],
        safe=False,
    )


def crear_tipo_reparacion(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    tr = TipoReparacion.objects.create(nombre=nombre)
    return JsonResponse({'id': tr.id, 'nombre': tr.nombre})


def buscar_estado_alquiler(request):
    q = request.GET.get('q', '').strip()
    qs = EstadoAlquiler.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'nombre': e.nombre, 'display': e.nombre.replace('_', ' ').title(), 'color': e.color} for e in qs],
        safe=False,
    )


def crear_estado_alquiler(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip().lower().replace(' ', '_')
    color  = request.POST.get('color', 'warning').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    if color not in ('warning', 'danger'):
        color = 'warning'
    e, _ = EstadoAlquiler.objects.get_or_create(nombre=nombre, defaults={'color': color})
    return JsonResponse({'nombre': e.nombre, 'display': e.nombre.replace('_', ' ').title(), 'color': e.color})


def buscar_unidad_medida(request):
    q = request.GET.get('q', '').strip()
    qs = UnidadMedida.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'id': u.id, 'nombre': u.nombre} for u in qs],
        safe=False,
    )


def crear_unidad_medida(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    u, _ = UnidadMedida.objects.get_or_create(nombre=nombre)
    return JsonResponse({'id': u.id, 'nombre': u.nombre})


def buscar_tipo_contrato(request):
    q = request.GET.get('q', '').strip()
    qs = TipoContrato.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'id': t.id, 'nombre': t.nombre} for t in qs],
        safe=False,
    )


def crear_tipo_contrato(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    t, _ = TipoContrato.objects.get_or_create(nombre=nombre)
    return JsonResponse({'id': t.id, 'nombre': t.nombre})


def buscar_ubicacion_item(request):
    q = request.GET.get('q', '').strip()
    qs = UbicacionItem.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'id': u.id, 'nombre': u.nombre} for u in qs],
        safe=False,
    )


def crear_ubicacion_item(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    u, _ = UbicacionItem.objects.get_or_create(nombre=nombre)
    return JsonResponse({'id': u.id, 'nombre': u.nombre})


def buscar_tipo_material(request):
    q = request.GET.get('q', '').strip()
    qs = TipoMaterial.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:10]
    return JsonResponse(
        [{'id': t.id, 'nombre': t.nombre} for t in qs],
        safe=False,
    )


def crear_tipo_material(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'Nombre requerido'}, status=400)
    t, _ = TipoMaterial.objects.get_or_create(nombre=nombre)
    return JsonResponse({'id': t.id, 'nombre': t.nombre})


def buscar_modelo_confeccion(request):
    q = request.GET.get('q', '').strip()
    qs = ModeloConfeccion.objects.filter(nombre__icontains=q).order_by('nombre')
    if q:
        qs = qs[:15]
    return JsonResponse(
        [{'id': m.nombre, 'nombre': m.nombre} for m in qs],
        safe=False,
    )


def crear_modelo_confeccion(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'error': 'El nombre es requerido.'}, status=400)
    m, _ = ModeloConfeccion.objects.get_or_create(nombre=nombre)
    return JsonResponse({'id': m.nombre, 'nombre': m.nombre})


def buscar_prenda_inventario(request):
    q = request.GET.get('q', '').strip()
    qs = PrendaInventario.objects.filter(estado='ACT').order_by('nombre')
    if q:
        qs = qs.filter(
            Q(nombre__icontains=q) | Q(codigo__icontains=q) |
            Q(color__icontains=q) | Q(talla__icontains=q)
        )[:15]
    else:
        qs = qs[:200]
    data = [{'id': p.id, 'ci': p.codigo, 'nombre': str(p)} for p in qs]
    return JsonResponse(data, safe=False)


def buscar_confeccion(request):
    q = request.GET.get('q', '').strip()
    qs = Confeccion.objects.filter(estado__in=['pendiente', 'en_proceso']).select_related('cliente').order_by('-creado')
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) | Q(modelo__icontains=q) |
            Q(cliente__nombres__icontains=q) | Q(cliente__apellido_paterno__icontains=q)
        )[:15]
    else:
        qs = qs[:200]
    data = [{'id': c.id, 'ci': c.codigo, 'nombre': str(c)} for c in qs]
    return JsonResponse(data, safe=False)


@login_required
def historial_cliente(request, id):
    cliente      = get_object_or_404(Cliente, id=id)
    reparaciones = cliente.reparaciones.order_by('-creado')
    confecciones = cliente.confeccion_set.order_by('-creado')
    alquileres   = cliente.alquileres.prefetch_related('items__prenda_item__prenda').order_by('-fecha_alquiler')
    ventas       = cliente.ventas.prefetch_related('items__prenda_item__prenda').order_by('-fecha_venta')

    total_reparaciones = reparaciones.aggregate(t=Sum('total'))['t'] or 0
    total_confecciones = confecciones.aggregate(t=Sum('precio'))['t'] or 0
    total_alquileres   = alquileres.aggregate(t=Sum('total'))['t'] or 0
    total_ventas       = ventas.aggregate(t=Sum('total'))['t'] or 0
    total_general      = total_reparaciones + total_confecciones + total_alquileres + total_ventas

    return render(request, 'misastreria/clientes/historial.html', {
        'cliente':      cliente,
        'reparaciones': reparaciones,
        'confecciones': confecciones,
        'alquileres':   alquileres,
        'ventas':       ventas,
        'total_reparaciones': total_reparaciones,
        'total_confecciones': total_confecciones,
        'total_alquileres':   total_alquileres,
        'total_ventas':       total_ventas,
        'total_general':      total_general,
    })

@login_required
def lista_reparaciones(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    tipo_prenda = request.GET.get('tipo_prenda', '').strip()
    cliente_id = request.GET.get('cliente_id', '').strip()
    desde = request.GET.get('desde', '')
    hasta = request.GET.get('hasta', '')
    periodo = request.GET.get('periodo', '')
    orden = request.GET.get('orden', 'desc')

    hoy = django_tz.localdate()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = hoy.isoformat()
    elif periodo == 'mes':
        desde = (hoy - timedelta(days=30)).isoformat()
        hasta = hoy.isoformat()
    elif periodo == '3meses' or (not desde and not hasta and not q and not estado and not tipo_prenda and not cliente_id):
        desde = (hoy - timedelta(days=90)).isoformat()
        hasta = hoy.isoformat()

    sort = '-codigo' if orden == 'desc' else 'codigo'
    _dcf = DecimalField(max_digits=10, decimal_places=2)
    _rep_ingresos_q = (
        CajaMovimiento.objects
        .filter(referencia_reparacion=OuterRef('pk'), tipo='ingreso', movimiento_reverso__isnull=True)
        .values('referencia_reparacion').annotate(t=Sum('monto')).values('t')
    )
    _rep_egresos_q = (
        CajaMovimiento.objects
        .filter(referencia_reparacion=OuterRef('pk'), tipo='egreso', movimiento_reverso__isnull=True)
        .values('referencia_reparacion').annotate(t=Sum('monto')).values('t')
    )
    reparaciones = (
        Reparacion.objects
        .prefetch_related('asignaciones')
        .annotate(
            _ingresos_caja=Coalesce(Subquery(_rep_ingresos_q, output_field=_dcf), Value(Decimal('0')), output_field=_dcf),
            _egresos_caja=Coalesce(Subquery(_rep_egresos_q, output_field=_dcf), Value(Decimal('0')), output_field=_dcf),
        )
        .annotate(
            saldo_caja=Greatest(
                ExpressionWrapper(F('total') - F('_ingresos_caja') + F('_egresos_caja'), output_field=_dcf),
                Value(Decimal('0')), output_field=_dcf,
            )
        )
        .order_by(sort)
    )
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()

    if q:
        reparaciones = reparaciones.filter(
            Q(codigo__icontains=q) |
            Q(cliente__nombres__icontains=q) | Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        )
    if cliente_id:
        reparaciones = reparaciones.filter(cliente_id=cliente_id)
    if estado:
        reparaciones = reparaciones.filter(estado=estado)
    if tipo_prenda:
        reparaciones = reparaciones.filter(items__tipo_prenda_id=tipo_prenda).distinct()
    if desde:
        try:
            desde_dt = django_tz.make_aware(datetime.combine(date.fromisoformat(desde), datetime.min.time()))
            reparaciones = reparaciones.filter(creado__gte=desde_dt)
        except (ValueError, TypeError):
            desde = ''
    if hasta:
        try:
            hasta_dt = django_tz.make_aware(datetime.combine(date.fromisoformat(hasta) + timedelta(days=1), datetime.min.time()))
            reparaciones = reparaciones.filter(creado__lt=hasta_dt)
        except (ValueError, TypeError):
            hasta = ''

    paginator = Paginator(reparaciones, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/reparaciones/lista.html', {
        'page_obj': page_obj,
        'q': q, 'estado': estado, 'tipo_prenda': tipo_prenda,
        'cliente_id': cliente_id,
        'desde': desde, 'hasta': hasta, 'periodo': periodo,
        'total': reparaciones.count(), 'orden': orden, 'orden_toggle_url': orden_toggle_url,
        'tipo_prenda_opts': list(TipoPrenda.objects.values('id', 'nombre')),
        'estado_choices': Reparacion.ESTADO_CHOICES,
    })


def _parse_asignaciones(post):
    """Lee las filas de empleados asignados del POST.
    Retorna lista de (empleado_id, pct_Decimal) válidas, en orden, sin duplicados."""
    try:
        count = int(post.get('asignaciones_count', '0'))
    except ValueError:
        count = 0
    pares = []
    vistos = set()
    for i in range(count + 1):  # +1: 'count' es high-water de índices (puede haber huecos)
        emp = post.get(f'asignacion[{i}][empleado]', '').strip()
        pct = post.get(f'asignacion[{i}][pct]', '').strip()
        if not emp or emp in vistos:
            continue
        try:
            pct_dec = Decimal(pct) if pct else Decimal('0')
        except Exception:
            pct_dec = Decimal('0')
        vistos.add(emp)
        pares.append((emp, pct_dec))
    return pares


def _guardar_asignaciones(instance, post, modelo_asignacion, fk_name):
    """Borra y recrea las asignaciones de empleados de un servicio desde POST.
    Sincroniza el 'lead' (instance.empleado + porcentaje_comision) con la primera fila.
    Retorna lista de errores."""
    from .models import Empleado
    instance.asignaciones.all().delete()
    errores = []
    lead_emp = None
    lead_pct = None
    for emp_id, pct in _parse_asignaciones(post):
        try:
            emp = Empleado.objects.get(pk=emp_id)
        except Empleado.DoesNotExist:
            errores.append(f"Empleado {emp_id} no encontrado.")
            continue
        modelo_asignacion.objects.create(**{fk_name: instance, 'empleado': emp, 'porcentaje_comision': pct})
        if lead_emp is None:
            lead_emp = emp
            lead_pct = pct
    instance.empleado = lead_emp
    instance.porcentaje_comision = lead_pct
    instance.save(update_fields=['empleado', 'porcentaje_comision'])
    return errores


def _asignaciones_json(instance):
    """Serializa las asignaciones de un servicio para precargar el form de edición."""
    if not instance or not instance.pk:
        return '[]'
    return json.dumps([
        {'empleado_id': a.empleado_id, 'empleado_nombre': str(a.empleado),
         'porcentaje': str(a.porcentaje_comision)}
        for a in instance.asignaciones.select_related('empleado').all()
    ])


def _guardar_items_reparacion(reparacion, post):
    """Borra los items existentes y recrea desde POST. Retorna lista de errores."""
    reparacion.items.all().delete()
    errores = []
    count_str = post.get('items_count', '0')
    try:
        count = int(count_str)
    except ValueError:
        count = 0

    for i in range(count):
        tp_id = post.get(f'items[{i}][tipo_prenda]', '').strip()
        tr_id = post.get(f'items[{i}][tipo_reparacion]', '').strip()
        costo_str = post.get(f'items[{i}][costo]', '').strip()
        detalles = post.get(f'items[{i}][detalles]', '').strip()

        if not tp_id or not tr_id:
            errores.append(f"Fila {i+1}: prenda y tipo de reparación son requeridos.")
            continue
        try:
            from .models import TipoPrenda, TipoReparacion
            tp = TipoPrenda.objects.get(pk=tp_id)
            tr = TipoReparacion.objects.get(pk=tr_id)
        except (TipoPrenda.DoesNotExist, TipoReparacion.DoesNotExist):
            errores.append(f"Fila {i+1}: prenda o tipo de reparación no encontrado.")
            continue

        try:
            costo = Decimal(costo_str) if costo_str else None
        except Exception:
            costo = None

        ReparacionItem.objects.create(
            reparacion=reparacion,
            tipo_prenda=tp,
            tipo_reparacion=tr,
            costo=costo,
            detalles=detalles,
        )

    reparacion.recalcular_total()
    return errores


@login_required
def crear_reparacion(request):
    if request.method == 'POST':
        form = ReparacionForm(request.POST)
        if form.is_valid():
            from .models import ReparacionEmpleado
            reparacion = form.save()
            errores = _guardar_items_reparacion(reparacion, request.POST)
            errores += _guardar_asignaciones(reparacion, request.POST, ReparacionEmpleado, 'reparacion')
            if reparacion.estado == 'entregado':
                from .caja_signals import registrar_reparacion_en_caja
                registrar_reparacion_en_caja(reparacion)
            if errores:
                messages.warning(request, f"Reparación {reparacion.codigo} creada con advertencias: {'; '.join(errores)}")
            else:
                messages.success(request, f"Reparación {reparacion.codigo} creada con éxito.")
            return redirect('detalle_reparacion', id=reparacion.id)
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        form = ReparacionForm()
    return render(request, 'misastreria/reparaciones/crear.html', {
        'form': form,
        'asignaciones_json': '[]',
        'tipos_prenda_json': json.dumps([{'id': t.id, 'nombre': t.nombre} for t in TipoPrenda.objects.order_by('nombre')]),
        'tipos_reparacion_json': json.dumps([{'id': t.id, 'nombre': t.nombre} for t in TipoReparacion.objects.order_by('nombre')]),
    })

@login_required
def editar_reparacion(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    if request.method == 'POST':
        form = ReparacionForm(request.POST, instance=reparacion)
        if form.is_valid():
            from .models import ReparacionEmpleado
            old_total = reparacion.total
            reparacion = form.save()
            errores = _guardar_items_reparacion(reparacion, request.POST)
            errores += _guardar_asignaciones(reparacion, request.POST, ReparacionEmpleado, 'reparacion')
            from .caja_signals import _ajustar_total_en_caja
            _ajustar_total_en_caja(
                referencia_field='referencia_reparacion',
                instance=reparacion,
                concepto_cobro='reparacion_ajuste',
                nuevo_total=reparacion.total,
                old_total=old_total,
                forma_pago=getattr(reparacion, 'forma_pago', 'efectivo') or 'efectivo',
                cliente=getattr(reparacion, 'cliente', None),
            )
            if errores:
                messages.warning(request, f"Actualizado con advertencias: {'; '.join(errores)}")
            else:
                messages.success(request, "Reparación actualizada con éxito.")
            return redirect('lista_reparaciones')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        form = ReparacionForm(instance=reparacion)
    items_existentes = list(reparacion.items.select_related('tipo_prenda', 'tipo_reparacion').values(
        'tipo_prenda_id', 'tipo_prenda__nombre',
        'tipo_reparacion_id', 'tipo_reparacion__nombre',
        'costo', 'detalles',
    ))
    return render(request, 'misastreria/reparaciones/editar.html', {
        'form': form, 'reparacion': reparacion,
        'items_existentes_json': json.dumps(items_existentes, default=str),
        'asignaciones_json': _asignaciones_json(reparacion),
        'tipos_prenda_json': json.dumps([{'id': t.id, 'nombre': t.nombre} for t in TipoPrenda.objects.order_by('nombre')]),
        'tipos_reparacion_json': json.dumps([{'id': t.id, 'nombre': t.nombre} for t in TipoReparacion.objects.order_by('nombre')]),
    })

@login_required
def eliminar_reparacion(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    if request.method == 'POST':
        from .caja_signals import _reversar_movimientos_activos
        _reversar_movimientos_activos(referencia_field='referencia_reparacion', instance=reparacion, usuario=request.user)
        reparacion.delete()
        messages.success(request, "Reparación eliminada con éxito.")
        return redirect('lista_reparaciones')
    return render(request, 'misastreria/reparaciones/eliminar.html', {'reparacion': reparacion})

@login_required
@login_required
def detalle_reparacion(request, id):
    from .forms import PagoReparacionForm
    reparacion = get_object_or_404(Reparacion, id=id)
    items = reparacion.items.select_related('tipo_prenda', 'tipo_reparacion').all()
    pagos = reparacion.caja_movimientos.filter(
        movimiento_reverso__isnull=True,
        concepto__in=['reparacion_cobro', 'reparacion_pago', 'reparacion_saldo'],
    ).order_by('-fecha', '-id')
    return render(request, 'misastreria/reparaciones/detalle.html', {
        'reparacion': reparacion,
        'items': items,
        'pagos': pagos,
        'total': reparacion.total,
        'pagado': reparacion.total_pagado,
        'saldo': reparacion.saldo_pendiente,
        'form': PagoReparacionForm(),
    })


@login_required
def agregar_pago_reparacion(request, id):
    from .forms import PagoReparacionForm
    from .caja_signals import registrar_pago_reparacion
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    reparacion = get_object_or_404(Reparacion, id=id)
    form = PagoReparacionForm(request.POST)
    if form.is_valid():
        monto = form.cleaned_data['monto']
        saldo = reparacion.saldo_pendiente
        if monto > saldo:
            messages.error(request, f"El pago excede el saldo pendiente de Bs {saldo:.2f}.")
        else:
            registrar_pago_reparacion(
                reparacion,
                monto,
                form.cleaned_data['forma_pago'],
                form.cleaned_data.get('descripcion', ''),
                request.user,
                via_caja=form.cleaned_data.get('via_caja', True),
            )
            messages.success(request, f"Pago de Bs {monto:.2f} registrado.")
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())
    return redirect('detalle_reparacion', id=reparacion.id)


@login_required
def reparacion_en_proceso(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    if request.method == 'POST' and reparacion.estado == 'pendiente':
        reparacion.estado = 'en_proceso'
        reparacion.save()
        messages.success(request, f'Reparación {reparacion.codigo} marcada como En Proceso.')
    return redirect('detalle_reparacion', id=reparacion.id)


@login_required
def marcar_entregado(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    if request.method == 'POST':
        if reparacion.estado != 'entregado':
            reparacion.estado = 'entregado'
            reparacion.save()
            messages.success(request, f"La reparación {reparacion.codigo} ha sido marcada como entregada.")
        else:
            messages.warning(request, f"La reparación {reparacion.codigo} ya está entregada.")
        return redirect('detalle_reparacion', id=reparacion.id)
    return redirect('detalle_reparacion', id=reparacion.id)


# ─── PDF Elegante Premium — helpers compartidos ───────────────────────────────
_PDF_NAVY  = colors.HexColor('#0d1b2a')
_PDF_GOLD  = colors.HexColor('#c9a84c')
_PDF_LGRAY = colors.HexColor('#f7f7f7')
_LOGO_PDF    = os.path.join(os.path.dirname(__file__), 'static', 'images', 'fortium-tailor-logo.jpg')
_QR_WA_PDF   = os.path.join(os.path.dirname(__file__), 'static', 'images', 'qr_whatsapp.png')
_DEJAVU_PDF  = os.path.join(os.path.dirname(__file__), 'static', 'font', 'DejaVuSans.ttf')

_DEJAVU_REGISTERED = False
try:
    pdfmetrics.getFont('DejaVuSans')
    _DEJAVU_REGISTERED = True
except Exception:
    if os.path.exists(_DEJAVU_PDF):
        try:
            pdfmetrics.registerFont(TTFont('DejaVuSans', _DEJAVU_PDF))
            _DEJAVU_REGISTERED = True
        except Exception:
            pass

_QR_CONTACT_DATA = 'BEGIN:VCARD\nVERSION:3.0\nFN:Fortium Tailor\nTEL:+59174546175\nEMAIL:info@fortiumtailor.com\nEND:VCARD'


def _make_contact_qr():
    try:
        import qrcode as _qrcode
        qr = _qrcode.QRCode(version=2, error_correction=_qrcode.constants.ERROR_CORRECT_M,
                             box_size=8, border=2)
        qr.add_data(_QR_CONTACT_DATA)
        qr.make(fit=True)
        img = qr.make_image(fill_color='#0d1b2a', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception:
        return None


class _RoundedTable(Flowable):
    """Wraps a ReportLab Table with rounded-corner clipping and border."""
    def __init__(self, tbl, radius=5, border_color=None):
        Flowable.__init__(self)
        self._tbl = tbl
        self._r = radius
        self._bc = border_color or colors.HexColor('#cbd5e1')
        self._w = self._h = 0

    def wrap(self, aW, aH):
        self._w, self._h = self._tbl.wrap(aW, aH)
        self.width = self._w
        self.height = self._h
        return self._w, self._h

    def draw(self):
        c = self.canv
        w, h, r = self._w, self._h, self._r
        k = 0.5523 * r
        p = c.beginPath()
        p.moveTo(r, 0);       p.lineTo(w - r, 0)
        p.curveTo(w-r+k, 0,   w,     k,     w,     r)
        p.lineTo(w, h - r)
        p.curveTo(w,     h-r+k, w-r+k, h,     w-r,   h)
        p.lineTo(r, h)
        p.curveTo(r-k,   h,     0,     h-r+k, 0,     h-r)
        p.lineTo(0, r)
        p.curveTo(0,     r-k,   r-k,   0,     r,     0)
        p.close()
        c.saveState()
        c.clipPath(p, fill=0, stroke=0)
        self._tbl.drawOn(c, 0, 0)
        c.restoreState()
        c.saveState()
        c.setStrokeColor(self._bc)
        c.setLineWidth(0.6)
        c.roundRect(0, 0, w, h, r, fill=0, stroke=1)
        c.restoreState()


def _pdf_page(c, doc, tipo_doc, codigo, fecha_str, hora_str, estado_str):
    c.saveState()
    W, H = A4
    HEADER_H = 4.0 * cm
    c.setFillColor(_PDF_NAVY)
    c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)
    if os.path.exists(_LOGO_PDF):
        c.drawImage(_LOGO_PDF, 0.5*cm, H - HEADER_H + 0.3*cm,
                    width=4.2*cm, height=3.5*cm,
                    preserveAspectRatio=True, mask='auto')
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 15)
    c.drawCentredString(W / 2, H - 1.55*cm, 'COMPROBANTE')
    c.setFont('Helvetica', 10)
    c.drawCentredString(W / 2, H - 2.2*cm, tipo_doc)
    c.setStrokeColor(_PDF_GOLD)
    c.setLineWidth(1.5)
    c.line(W/2 - 3.2*cm, H - 2.55*cm, W/2 + 3.2*cm, H - 2.55*cm)
    lbls = ['Código:', 'Fecha:', 'Hora:', 'Estado:'] if hora_str else ['Código:', 'Fecha:', 'Estado:']
    vals = [codigo, fecha_str, hora_str, estado_str] if hora_str else [codigo, fecha_str, estado_str]
    for i, (lbl, val) in enumerate(zip(lbls, vals)):
        yi = H - 1.4*cm - i * 0.65*cm
        c.setFillColor(_PDF_GOLD)
        c.setFont('Helvetica-Bold', 7.5)
        c.drawString(W - 5.8*cm, yi, lbl)
        c.setFillColor(colors.white)
        c.setFont('Helvetica', 7.5)
        c.drawString(W - 4.3*cm, yi, str(val))
    c.setFillColor(_PDF_GOLD)
    c.setFont('Helvetica-Oblique', 8)
    c.drawCentredString(W / 2, H - HEADER_H - 0.5*cm, 'El arte de vestir a tu forma y medida')
    c.setFillColor(_PDF_NAVY)
    c.rect(0, 0, W, 1.3*cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont('Helvetica', 7.5)
    c.drawString(0.8*cm, 0.47*cm, 'Calle Méndez #549 · Comercial MÉNDEZ, piso 1 loc. 1-2, Tarija')
    c.drawCentredString(W / 2, 0.47*cm, '+591 74546175')
    c.drawRightString(W - 0.8*cm, 0.47*cm, 'info@fortiumtailor.com')
    c.restoreState()


def _pdf_page_reparacion(c, doc, tipo_doc, codigo, fecha_str, hora_str, estado_str):
    """Header blanco: logo izq, COMPROBANTE centro, QR esquina sup-der. Footer navy con dirección."""
    c.saveState()
    W, H = A4
    HEADER_H = 4.0 * cm
    STRIP_H  = 0.48 * cm   # franja inferior del header para metadata
    MAIN_H   = HEADER_H - STRIP_H
    FOOTER_H = 2.0 * cm

    # ── Header: fondo blanco ───────────────────────────────────────────────────
    c.setFillColor(colors.white)
    c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)

    # Franja de metadata (parte inferior del header)
    c.setFillColor(colors.HexColor('#eef2ff'))
    c.rect(0, H - HEADER_H, W, STRIP_H, fill=1, stroke=0)

    # Borde inferior del header
    c.setStrokeColor(colors.HexColor('#dde3f0'))
    c.setLineWidth(0.6)
    c.line(0, H - HEADER_H, W, H - HEADER_H)

    # Logo (izquierda, en zona principal)
    logo_y = H - HEADER_H + STRIP_H + 0.1 * cm
    if os.path.exists(_LOGO_PDF):
        c.drawImage(_LOGO_PDF, 0.4*cm, logo_y,
                    width=3.9*cm, height=MAIN_H - 0.2*cm,
                    preserveAspectRatio=True, mask='auto')

    # QR (esquina superior derecha, dentro de la zona principal)
    QR_SIZE = MAIN_H - 0.3 * cm
    qr_x = W - QR_SIZE - 0.25*cm
    qr_y = H - HEADER_H + STRIP_H + 0.15*cm
    if os.path.exists(_QR_WA_PDF):
        c.drawImage(_QR_WA_PDF, qr_x, qr_y, width=QR_SIZE, height=QR_SIZE)
    else:
        qr_buf = _make_contact_qr()
        if qr_buf:
            c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=QR_SIZE, height=QR_SIZE)

    # COMPROBANTE + tipo centrado entre logo y QR
    text_cx = (4.5*cm + qr_x) / 2
    c.setFillColor(_PDF_NAVY)
    c.setFont('Helvetica-Bold', 15)
    c.drawCentredString(text_cx, H - 1.4*cm, 'COMPROBANTE')
    c.setFont('Helvetica', 10)
    c.drawCentredString(text_cx, H - 2.05*cm, tipo_doc)
    c.setStrokeColor(_PDF_GOLD)
    c.setLineWidth(1.5)
    c.line(text_cx - 3.0*cm, H - 2.4*cm, text_cx + 3.0*cm, H - 2.4*cm)

    # Metadata en la franja inferior: Código | Fecha | [Hora |] Estado
    meta = [('Código', codigo), ('Fecha', fecha_str)]
    if hora_str:
        meta.append(('Hora', hora_str))
    meta.append(('Estado', estado_str))
    strip_cy = H - HEADER_H + STRIP_H / 2 - 0.05*cm
    col_w = W / len(meta)
    for i, (lbl, val) in enumerate(meta):
        cx = col_w * i + col_w / 2
        c.setFillColor(colors.HexColor('#4a5568'))
        c.setFont('Helvetica-Bold', 6.5)
        c.drawString(cx - 0.4*cm, strip_cy, f'{lbl}:')
        c.setFont('Helvetica', 6.5)
        c.drawString(cx + 0.7*cm, strip_cy, str(val))

    # ── Footer navy ────────────────────────────────────────────────────────────
    c.setFillColor(_PDF_NAVY)
    c.rect(0, 0, W, FOOTER_H, fill=1, stroke=0)

    icon_font = 'DejaVuSans' if _DEJAVU_REGISTERED else 'Helvetica'
    c.setFillColor(colors.white)
    c.setFont(icon_font, 7)
    line1_y = FOOTER_H * 0.67
    line2_y = FOOTER_H * 0.27
    if _DEJAVU_REGISTERED:
        c.drawString(0.8*cm, line1_y,
                     '◆  Calle Méndez #549 entre 15 de Abril y Madrid · Comercial MÉNDEZ, primer piso locales 1 y 2, Tarija')
        c.drawString(0.8*cm, line2_y,
                     '☎  +591 74546175        ✉  info@fortiumtailor.com')
    else:
        c.drawString(0.8*cm, line1_y,
                     'Calle Méndez #549 entre 15 de Abril y Madrid · Comercial MÉNDEZ, primer piso locales 1 y 2, Tarija')
        c.drawString(0.8*cm, line2_y, '+591 74546175   info@fortiumtailor.com')

    c.restoreState()


def _pdf_st():
    return {
        'sec': ParagraphStyle('_PSec', fontName='Helvetica-Bold', fontSize=9,
                              textColor=colors.white, leading=14),
        'kl':  ParagraphStyle('_PKl',  fontName='Helvetica-Bold', fontSize=8.5, leading=12),
        'kv':  ParagraphStyle('_PKv',  fontName='Helvetica',      fontSize=8.5, leading=12),
        'sig': ParagraphStyle('_PSig', fontName='Helvetica',      fontSize=8.5,
                              alignment=TA_CENTER),
        'ch':  ParagraphStyle('_PCH',  fontName='Helvetica-Bold', fontSize=9,
                              textColor=_PDF_NAVY, spaceAfter=2),
        'ci':  ParagraphStyle('_PCI',  fontName='Helvetica',      fontSize=8,
                              leading=11, spaceAfter=2),
    }


def _pdf_left_tbl(rows, lw):
    t = Table(rows, colWidths=[2.2*cm, lw - 2.2*cm])
    t.setStyle(TableStyle([
        ('SPAN',          (0, 0), (1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), _PDF_NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTSIZE',      (0, 0), (-1, -1), 8.5),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, _PDF_LGRAY]),
        ('GRID',          (0, 1), (-1, -1), 0.25, colors.HexColor('#e0e0e0')),
    ]))
    return t


def _pdf_items_tbl(rows, col_widths, n_right_cols):
    t = Table(rows, colWidths=col_widths)
    cmds = [
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), _PDF_NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#1e3a5c')),
        ('TEXTCOLOR',     (0, 1), (-1, 1), colors.white),
        ('FONTNAME',      (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTNAME',      (0, -1),(-1, -1),'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ALIGN',         (-n_right_cols, 2), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS',(0, 2), (-1, -2), [colors.white, _PDF_LGRAY]),
        ('GRID',          (0, 1), (-1, -2), 0.25, colors.HexColor('#e0e0e0')),
        ('LINEABOVE',     (0, -1),(-1, -1), 0.5, _PDF_NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(cmds))
    return t


def _pdf_body(left_tbl, right_tbl, lw, rw):
    t = Table([[left_tbl, right_tbl]], colWidths=[lw, rw])
    t.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (0, -1),  6),
    ]))
    return t


def _pdf_total_tbl(label, amount_str, page_w):
    t = Table([[label, amount_str]], colWidths=[page_w * 0.55, page_w * 0.45])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), _PDF_LGRAY),
        ('FONTNAME',      (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (0, 0), 11),
        ('FONTNAME',      (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (1, 0), (1, 0), 14),
        ('TEXTCOLOR',     (1, 0), (1, 0), _PDF_NAVY),
        ('ALIGN',         (0, 0), (0, 0), 'LEFT'),
        ('ALIGN',         (1, 0), (1, 0), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('BOX',           (0, 0), (-1, -1), 1, _PDF_GOLD),
    ]))
    return t


def _pdf_sig_tbl(st, page_w):
    t = Table(
        [
            [Paragraph('Firma del cliente', st['sig']),
             Paragraph('Firma del encargado', st['sig'])],
            [Paragraph('CI: _______________', st['sig']), Paragraph('', st['sig'])],
        ],
        colWidths=[page_w / 2, page_w / 2],
    )
    t.setStyle(TableStyle([
        ('LINEABOVE',     (0, 0), (0, 0), 0.5, colors.black),
        ('LINEABOVE',     (1, 0), (1, 0), 0.5, colors.black),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


@login_required
def exportar_recibo_reparacion_pdf(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    items = list(reparacion.items.select_related('tipo_prenda', 'tipo_reparacion'))

    if not reparacion.cliente:
        messages.error(request, "No se puede generar el recibo: falta el cliente.")
        return redirect('lista_reparaciones')
    if not items:
        messages.error(request, "No se puede generar el recibo: la reparación no tiene items.")
        return redirect('lista_reparaciones')

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_reparacion_{reparacion.codigo}.pdf"'

    st = _pdf_st()
    W_PAGE, L_W, R_W = 18*cm, 6.5*cm, 11.5*cm

    cliente  = reparacion.cliente
    cli_str  = f"{cliente.nombres} {cliente.apellido_paterno}" if cliente else '—'
    tel_str  = getattr(cliente, 'celular', '—') or '—'
    emp_str  = str(reparacion.empleado) if reparacion.empleado else '—'
    fe_str   = reparacion.fecha_entrega.strftime('%d/%m/%Y') if reparacion.fecha_entrega else '—'
    est_str  = reparacion.get_estado_display()
    cod_str  = reparacion.codigo
    fec_str  = reparacion.creado.strftime('%d/%m/%Y')

    left_data = [
        [Paragraph('DATOS DEL CLIENTE', st['sec']), ''],
        [Paragraph('<b>Cliente:</b>',       st['kl']), Paragraph(cli_str, st['kv'])],
        [Paragraph('<b>Teléfono:</b>',       st['kl']), Paragraph(tel_str, st['kv'])],
        [Paragraph('<b>Empleado:</b>',       st['kl']), Paragraph(emp_str, st['kv'])],
        [Paragraph('<b>Fecha entrega:</b>',  st['kl']), Paragraph(fe_str,  st['kv'])],
        [Paragraph('<b>Estado:</b>',         st['kl']), Paragraph(est_str, st['kv'])],
    ]
    left_tbl = _pdf_left_tbl(left_data, L_W)

    det_st = ParagraphStyle('_Det', fontName='Helvetica', fontSize=7.5, leading=10)
    items_rows = [
        [Paragraph('DETALLE DE REPARACIÓN', st['sec']), '', '', '', ''],
        ['N°', 'Prenda', 'Tipo Reparación', 'Costo', 'Detalles'],
    ]
    for i, item in enumerate(items, 1):
        items_rows.append([
            str(i),
            str(item.tipo_prenda) if item.tipo_prenda else '—',
            str(item.tipo_reparacion) if item.tipo_reparacion else '—',
            f"Bs {item.costo:.2f}" if item.costo else '—',
            Paragraph(item.detalles or '—', det_st),
        ])
    items_rows.append(['', '', '', 'TOTAL:', f"Bs {reparacion.total:.2f}"])

    col_widths = [0.5*cm, 2.5*cm, 3.4*cm, 1.9*cm, 3.2*cm]
    n_right = 2
    right_inner = Table(items_rows, colWidths=col_widths)
    right_inner.setStyle(TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), _PDF_NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR',     (0, 1), (-1, 1), _PDF_NAVY),
        ('FONTNAME',      (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTNAME',      (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ALIGN',         (-n_right, 2), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 2), (-1, -2), [colors.white, _PDF_LGRAY]),
        ('GRID',          (0, 1), (-1, -2), 0.25, colors.HexColor('#e0e0e0')),
        ('LINEABOVE',     (0, -1), (-1, -1), 0.5, _PDF_NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))

    left_tbl  = _RoundedTable(_pdf_left_tbl(left_data, L_W))
    right_tbl = _RoundedTable(right_inner)

    def on_page(c, doc):
        _pdf_page_reparacion(c, doc, 'DE REPARACIÓN', cod_str, fec_str, '', est_str)

    doc = SimpleDocTemplate(response, pagesize=A4,
                            topMargin=4.4*cm, bottomMargin=2.4*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    doc.build(
        [
            _pdf_body(left_tbl, right_tbl, L_W, R_W),
            Spacer(1, 0.5*cm),
            _pdf_total_tbl('TOTAL A PAGAR', f"Bs.  {reparacion.total:.2f}", W_PAGE),
            Spacer(1, 0.8*cm),
            _pdf_sig_tbl(st, W_PAGE),
        ],
        onFirstPage=on_page, onLaterPages=on_page,
    )
    return response

@login_required
def lista_ventas(request):
    q           = request.GET.get('q', '').strip()
    cliente_id  = request.GET.get('cliente_id', '').strip()
    empleado_id = request.GET.get('empleado_id', '').strip()
    desde       = request.GET.get('desde', '').strip()
    hasta       = request.GET.get('hasta', '').strip()
    periodo     = request.GET.get('periodo', '').strip()
    orden       = request.GET.get('orden', 'desc')
    estado      = request.GET.get('estado', '').strip()

    hoy = django_tz.localdate()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    sort = '-codigo' if orden == 'desc' else 'codigo'
    ventas = Venta.objects.all().order_by(sort)
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()
    if q:
        ventas = ventas.filter(
            Q(codigo__icontains=q) |
            Q(items__prenda_item__prenda__nombre__icontains=q) |
            Q(cliente__nombres__icontains=q) |
            Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        ).distinct()
    if cliente_id:
        ventas = ventas.filter(cliente_id=cliente_id)
    if empleado_id:
        ventas = ventas.filter(empleado_id=empleado_id)
    if estado:
        ventas = ventas.filter(estado=estado)
    if desde:
        try:
            date.fromisoformat(desde)
            ventas = ventas.filter(fecha_venta__gte=desde)
        except (ValueError, TypeError):
            desde = ''
    if hasta:
        try:
            date.fromisoformat(hasta)
            ventas = ventas.filter(fecha_venta__lte=hasta)
        except (ValueError, TypeError):
            hasta = ''

    total = ventas.count()
    paginator = Paginator(ventas, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/ventas/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'cliente_id': cliente_id, 'empleado_id': empleado_id,
        'desde': desde, 'hasta': hasta, 'periodo': periodo,
        'orden': orden, 'orden_toggle_url': orden_toggle_url,
        'estado': estado,
    })


def _guardar_items_venta(venta, post_data, estado_items='baja'):
    """Guarda los ítems de la venta y gestiona el estado de cada PrendaItem."""
    for item in venta.items.select_related('prenda_item'):
        pi = item.prenda_item
        pi.estado = 'disponible'
        pi.save(update_fields=['estado'])
    kardex_events.delete_eventos_venta(venta)
    venta.items.all().delete()

    prenda_item_ids       = post_data.getlist('item_prenda_item')
    precios               = post_data.getlist('item_precio')
    grupos                = post_data.getlist('item_grupo_conjunto')
    tipo_reparacion_ids   = post_data.getlist('item_tipo_reparacion')
    precios_reparacion    = post_data.getlist('item_precio_reparacion')
    empleado_ids          = post_data.getlist('item_empleado')
    porcentajes_comision  = post_data.getlist('item_porcentaje_comision')
    errores               = []
    seen                  = set()

    for i, (pi_id, precio_str, grupo_str, tr_id, prec_rep_str, emp_id, pct_str) in enumerate(
        zip_longest(
            prenda_item_ids, precios, grupos, tipo_reparacion_ids, precios_reparacion,
            empleado_ids, porcentajes_comision, fillvalue=''
        ), 1
    ):
        if not pi_id:
            continue
        if pi_id in seen:
            errores.append(f"Fila {i}: item duplicado.")
            continue
        seen.add(pi_id)
        try:
            pi = PrendaItem.objects.select_related('prenda').get(pk=pi_id)
        except PrendaItem.DoesNotExist:
            errores.append(f"Fila {i}: item inexistente.")
            continue
        if pi.estado != 'disponible':
            errores.append(f"Fila {i}: {pi.codigo_item} no disponible.")
            continue

        try:
            precio = Decimal(precio_str)
        except Exception:
            precio = pi.prenda.precio
        try:
            grupo = int(grupo_str) or None
        except (TypeError, ValueError):
            grupo = None
        try:
            precio_reparacion = Decimal(prec_rep_str) if prec_rep_str else Decimal('0')
        except Exception:
            precio_reparacion = Decimal('0')
        tipo_reparacion = None
        if tr_id:
            tipo_reparacion = TipoReparacion.objects.filter(pk=tr_id).first()
        empleado_arreglo = Empleado.objects.filter(pk=emp_id).first() if emp_id else None
        try:
            pct_comision = Decimal(pct_str) if (pct_str and empleado_arreglo) else None
        except Exception:
            pct_comision = None
        vi = VentaItem.objects.create(
            venta=venta,
            prenda_item=pi,
            precio_unitario=precio,
            tipo_reparacion=tipo_reparacion,
            precio_reparacion=precio_reparacion,
            empleado=empleado_arreglo,
            porcentaje_comision=pct_comision,
            grupo_conjunto=grupo,
        )
        kardex_events.emit_venta(vi.prenda_item, venta, vi.precio_unitario)
        pi.estado = estado_items
        pi.save(update_fields=['estado'])

    venta.recalcular_totales()
    return errores


def _empleados_arreglo_json():
    """Lista de empleados activos para los selects de comisión de arreglo en los items."""
    return json.dumps([
        {'id': e.id, 'nombre': str(e)}
        for e in Empleado.objects.filter(activo=True).order_by('nombres', 'apellido_paterno')
    ])


def _prendas_venta_json():
    return _prenda_items_json('venta')


@login_required
def crear_venta(request):
    if request.method == 'POST':
        form = VentaForm(request.POST)
        if form.is_valid():
            venta = form.save()
            estado = venta.estado
            estado_items = 'reservado' if estado == 'en_proceso' else 'baja'
            errores = _guardar_items_venta(venta, request.POST, estado_items=estado_items)
            if estado == 'efectuada':
                from .caja_signals import registrar_venta_en_caja
                registrar_venta_en_caja(venta)
            if errores:
                messages.warning(request, 'Venta creada con advertencias: ' + '; '.join(errores))
            else:
                messages.success(request, f"Venta {venta.codigo} creada exitosamente.")
            return redirect('detalle_venta', id=venta.id)
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = VentaForm()
    items_preload = []
    item_id = request.GET.get('item')
    if item_id:
        try:
            pi = PrendaItem.objects.select_related('prenda').get(id=item_id, tipo='venta', estado='disponible', conjunto_slots__isnull=True)
            items_preload = [{'prenda_item_id': pi.id, 'precio_unitario': float(pi.prenda.precio), 'grupo_conjunto': None}]
        except PrendaItem.DoesNotExist:
            pass
    return render(request, 'misastreria/ventas/form.html', {
        'form': form,
        'titulo': 'Nueva Venta',
        'prendas_json': _prendas_venta_json(),
        'conjuntos_json': _conjuntos_json('venta'),
        'items_existentes': json.dumps(items_preload),
        'tipos_reparacion_json': json.dumps(list(TipoReparacion.objects.values('id', 'nombre').order_by('nombre'))),
        'empleados_json': _empleados_arreglo_json(),
    })


@login_required
def editar_venta(request, id):
    venta = get_object_or_404(Venta, id=id)
    if request.method == 'POST':
        form = VentaForm(request.POST, instance=venta)
        if form.is_valid():
            old_total = venta.total
            venta = form.save()
            estado_items = 'reservado' if venta.estado == 'en_proceso' else 'baja'
            errores = _guardar_items_venta(venta, request.POST, estado_items=estado_items)
            from .caja_signals import _ajustar_total_en_caja
            _ajustar_total_en_caja(
                referencia_field='referencia_venta',
                instance=venta,
                concepto_cobro='venta_ajuste',
                nuevo_total=venta.total,
                old_total=old_total,
                forma_pago=getattr(venta, 'forma_pago', 'efectivo') or 'efectivo',
                cliente=getattr(venta, 'cliente', None),
            )
            if errores:
                messages.warning(request, 'Actualizado con advertencias: ' + '; '.join(errores))
            else:
                messages.success(request, 'Venta actualizada correctamente.')
            return redirect('detalle_venta', id=venta.id)
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = VentaForm(instance=venta)
    prendas_json = _prendas_venta_json()
    items_propios_ids = list(venta.items.values_list('prenda_item_id', flat=True))
    if items_propios_ids:
        prendas_base = json.loads(prendas_json)
        ids_en_json = {p['prenda_item_id'] for p in prendas_base}
        for pi in PrendaItem.objects.filter(pk__in=items_propios_ids).select_related('prenda'):
            if pi.id not in ids_en_json:
                p = pi.prenda
                ubic = f" [{pi.ubicacion}]" if pi.ubicacion else ""
                label = (
                    f"{pi.codigo_item} — {p.nombre}"
                    f"{f' T{p.talla}' if p.talla else ''}"
                    f"{f' {p.color}' if p.color else ''}"
                    f" ({pi.get_condicion_display()}){ubic}"
                )
                prendas_base.append({
                    'prenda_item_id': pi.id,
                    'codigo_item':    pi.codigo_item,
                    'sku_codigo':     p.codigo,
                    'sku_nombre':     p.nombre,
                    'talla':          p.talla,
                    'color':          p.color,
                    'condicion':      pi.condicion,
                    'condicion_label': pi.get_condicion_display(),
                    'ubicacion':      str(pi.ubicacion) if pi.ubicacion else '',
                    'precio':         float(p.precio),
                    'label':          label,
                    'tipo_prenda_id': p.tipo_prenda_id,
                })
        prendas_json = json.dumps(prendas_base)

    items_existentes = [
        {
            'prenda_item_id': item.prenda_item_id,
            'precio_unitario': float(item.precio_unitario),
            'grupo_conjunto': item.grupo_conjunto,
            'tipo_reparacion_id': item.tipo_reparacion_id,
            'precio_reparacion': float(item.precio_reparacion or 0),
            'empleado_id': item.empleado_id,
            'porcentaje_comision': float(item.porcentaje_comision) if item.porcentaje_comision is not None else None,
        }
        for item in venta.items.all()
    ]
    return render(request, 'misastreria/ventas/form.html', {
        'form':    form,
        'titulo':  'Editar Venta',
        'venta':   venta,
        'items_existentes': json.dumps(items_existentes),
        'prendas_json': prendas_json,
        'conjuntos_json': _conjuntos_json('venta'),
        'tipos_reparacion_json': json.dumps(list(TipoReparacion.objects.values('id', 'nombre').order_by('nombre'))),
        'empleados_json': _empleados_arreglo_json(),
    })


@login_required
def eliminar_venta(request, id):
    venta = get_object_or_404(Venta, id=id)
    if request.method == 'POST':
        from .caja_signals import _reversar_movimientos_activos
        for item in venta.items.select_related('prenda_item'):
            pi = item.prenda_item
            pi.estado = 'disponible'
            pi.save(update_fields=['estado'])
        _reversar_movimientos_activos(referencia_field='referencia_venta', instance=venta, usuario=request.user)
        venta.delete()
        messages.success(request, 'Venta eliminada correctamente.')
        return redirect('lista_ventas')
    return render(request, 'misastreria/ventas/eliminar.html', {'venta': venta})


@login_required
def detalle_venta(request, id):
    from .forms import PagoVentaForm
    venta = get_object_or_404(Venta, id=id)
    items = venta.items.select_related('prenda_item__prenda', 'tipo_reparacion').all()
    pagos = venta.caja_movimientos.filter(
        movimiento_reverso__isnull=True,
        concepto__in=['venta_cobro', 'venta_adelanto', 'venta_pago', 'venta_saldo'],
    ).order_by('-fecha', '-id')
    return render(request, 'misastreria/ventas/detalle.html', {
        'venta': venta,
        'items': items,
        'pagos': pagos,
        'total': venta.total,
        'pagado': venta.total_pagado,
        'saldo': venta.saldo_pendiente,
        'form': PagoVentaForm(),
    })


@login_required
def agregar_pago_venta(request, id):
    from .forms import PagoVentaForm
    from .caja_signals import registrar_pago_venta
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    venta = get_object_or_404(Venta, id=id)
    if venta.estado == 'efectuada':
        messages.warning(request, "La venta ya está efectuada.")
        return redirect('detalle_venta', id=venta.id)
    form = PagoVentaForm(request.POST)
    if form.is_valid():
        monto = form.cleaned_data['monto']
        saldo = venta.saldo_pendiente
        if monto > saldo:
            messages.error(request, f"El pago excede el saldo pendiente de Bs {saldo:.2f}.")
        else:
            registrar_pago_venta(
                venta,
                monto,
                form.cleaned_data['forma_pago'],
                form.cleaned_data.get('descripcion', ''),
                request.user,
                via_caja=form.cleaned_data.get('via_caja', True),
            )
            messages.success(request, f"Pago de Bs {monto:.2f} registrado.")
    else:
        for err in form.errors.values():
            messages.error(request, err.as_text())
    return redirect('detalle_venta', id=venta.id)


@login_required
def exportar_recibo_pdf(request, id):
    venta = get_object_or_404(Venta, id=id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_venta_{venta.codigo}.pdf"'

    st = _pdf_st()
    W_PAGE, L_W, R_W = 18*cm, 6.5*cm, 11.5*cm

    cliente = venta.cliente
    cli_str = f"{cliente.nombres} {cliente.apellido_paterno}" if cliente else '—'
    tel_str = getattr(cliente, 'celular', '—') or '—'
    emp_str = str(venta.empleado) if venta.empleado else '—'
    fec_str = venta.fecha_venta.strftime('%d/%m/%Y')
    cod_str = venta.codigo

    left_data = [
        [Paragraph('DATOS DEL CLIENTE', st['sec']), ''],
        [Paragraph('<b>Cliente:</b>',    st['kl']), Paragraph(cli_str, st['kv'])],
        [Paragraph('<b>Teléfono:</b>',   st['kl']), Paragraph(tel_str, st['kv'])],
        [Paragraph('<b>Empleado:</b>',   st['kl']), Paragraph(emp_str, st['kv'])],
        [Paragraph('<b>Fecha venta:</b>',st['kl']), Paragraph(fec_str, st['kv'])],
    ]
    venta_items = list(venta.items.select_related('prenda_item__prenda').all())
    items_rows = [
        [Paragraph('DETALLE DE VENTA', st['sec']), '', '', '', '', ''],
        ['N°', 'Prenda', 'Color', 'Talla', 'P. Unit.', 'Subtotal'],
    ]
    for i, item in enumerate(venta_items, 1):
        prenda = item.prenda_item.prenda if item.prenda_item else None
        items_rows.append([
            str(i),
            prenda.nombre if prenda else '—',
            (prenda.color or '—') if prenda else '—',
            (prenda.talla or '—') if prenda else '—',
            f"Bs {item.precio_unitario:.2f}",
            f"Bs {item.subtotal:.2f}",
        ])
    items_rows.append(['', '', '', '', 'Subtotal:', f"Bs {venta.subtotal:.2f}"])
    if venta.descuento:
        items_rows.append(['', '', '', '', f'Desc. {venta.descuento}%:',
                           f"-Bs {(venta.subtotal - venta.total):.2f}"])
    items_rows.append(['', '', '', '', 'TOTAL:', f"Bs {venta.total:.2f}"])

    _vcw = [0.5*cm, 3.6*cm, 1.8*cm, 1.2*cm, 2.2*cm, 2.2*cm]
    right_inner = Table(items_rows, colWidths=_vcw)
    right_inner.setStyle(TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), _PDF_NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR',     (0, 1), (-1, 1), _PDF_NAVY),
        ('FONTNAME',      (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTNAME',      (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ALIGN',         (-2, 2), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 2), (-1, -2), [colors.white, _PDF_LGRAY]),
        ('GRID',          (0, 1), (-1, -2), 0.25, colors.HexColor('#e0e0e0')),
        ('LINEABOVE',     (0, -1), (-1, -1), 0.5, _PDF_NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    left_tbl  = _RoundedTable(_pdf_left_tbl(left_data, L_W))
    right_tbl = _RoundedTable(right_inner)

    def on_page(c, doc):
        _pdf_page_reparacion(c, doc, 'DE VENTA', cod_str, fec_str, '', 'Completado')

    doc = SimpleDocTemplate(response, pagesize=A4,
                            topMargin=4.4*cm, bottomMargin=2.4*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    doc.build(
        [
            _pdf_body(left_tbl, right_tbl, L_W, R_W),
            Spacer(1, 0.5*cm),
            _pdf_total_tbl('TOTAL A PAGAR', f"Bs.  {venta.total:.2f}", W_PAGE),
            Spacer(1, 0.8*cm),
            _pdf_sig_tbl(st, W_PAGE),
        ],
        onFirstPage=on_page, onLaterPages=on_page,
    )
    return response

@login_required
def get_precio_articulo(request):
    articulo_id = request.GET.get('articulo_id')
    try:
        articulo = PrendaInventario.objects.get(id=articulo_id)
        return JsonResponse({'precio': float(articulo.precio)})
    except PrendaInventario.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)

@login_required
def lista_confecciones(request):
    q           = request.GET.get('q', '').strip()
    tipo_prenda = request.GET.get('tipo_prenda', '').strip()
    estado      = request.GET.get('estado', '').strip()
    cliente_id  = request.GET.get('cliente_id', '').strip()
    empleado_id = request.GET.get('empleado_id', '').strip()
    desde       = request.GET.get('desde', '').strip()
    hasta       = request.GET.get('hasta', '').strip()
    periodo     = request.GET.get('periodo', '').strip()
    orden       = request.GET.get('orden', 'desc')

    hoy = django_tz.localdate()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    sort = '-codigo' if orden == 'desc' else 'codigo'
    _dcf = DecimalField(max_digits=10, decimal_places=2)
    _ingresos_q = (
        CajaMovimiento.objects
        .filter(referencia_confeccion=OuterRef('pk'), tipo='ingreso', movimiento_reverso__isnull=True)
        .values('referencia_confeccion')
        .annotate(t=Sum('monto'))
        .values('t')
    )
    _egresos_q = (
        CajaMovimiento.objects
        .filter(referencia_confeccion=OuterRef('pk'), tipo='egreso', movimiento_reverso__isnull=True)
        .values('referencia_confeccion')
        .annotate(t=Sum('monto'))
        .values('t')
    )
    confecciones = (
        Confeccion.objects
        .prefetch_related('asignaciones')
        .annotate(
            _ingresos_caja=Coalesce(Subquery(_ingresos_q, output_field=_dcf), Value(Decimal('0')), output_field=_dcf),
            _egresos_caja=Coalesce(Subquery(_egresos_q, output_field=_dcf), Value(Decimal('0')), output_field=_dcf),
        )
        .annotate(
            saldo_caja=Greatest(
                ExpressionWrapper(F('precio') - F('_ingresos_caja') + F('_egresos_caja'), output_field=_dcf),
                Value(Decimal('0')),
                output_field=_dcf,
            )
        )
        .order_by(sort)
    )
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()
    if q:
        confecciones = confecciones.filter(
            Q(codigo__icontains=q) |
            Q(cliente__nombres__icontains=q) |
            Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        )
    if cliente_id:
        confecciones = confecciones.filter(cliente_id=cliente_id)
    if empleado_id:
        confecciones = confecciones.filter(empleado_id=empleado_id)
    if tipo_prenda:
        confecciones = confecciones.filter(items__tipo_prenda_id=tipo_prenda).distinct()
    if estado:
        confecciones = confecciones.filter(estado=estado)
    if desde:
        try:
            date.fromisoformat(desde)
            confecciones = confecciones.filter(fecha_inicio__gte=desde)
        except (ValueError, TypeError):
            desde = ''
    if hasta:
        try:
            date.fromisoformat(hasta)
            confecciones = confecciones.filter(fecha_inicio__lte=hasta)
        except (ValueError, TypeError):
            hasta = ''

    total = confecciones.count()
    paginator = Paginator(confecciones, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/confecciones/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'tipo_prenda': tipo_prenda,
        'estado': estado,
        'cliente_id': cliente_id, 'empleado_id': empleado_id,
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'orden': orden, 'orden_toggle_url': orden_toggle_url,
        'tipo_prenda_opts': list(TipoPrenda.objects.values('id', 'nombre')),
        'estado_choices': Confeccion.ESTADO_CHOICES,
    })


def _parsear_lineas_pago(post):
    """Lee líneas de pago divididas del POST: pago[i][monto] / pago[i][forma_pago].
    Si no hay líneas, cae al envío simple (monto / forma_pago). Devuelve
    (lineas, errores) donde lineas = [(Decimal monto, str forma_pago), ...]."""
    import re
    from decimal import Decimal, InvalidOperation
    lineas, errores = [], []
    indices = sorted({
        int(m.group(1)) for k in post.keys()
        for m in [re.match(r'^pago\[(\d+)\]\[monto\]$', k)] if m
    })
    for i in indices:
        monto_str = (post.get(f'pago[{i}][monto]') or '').strip()
        forma = (post.get(f'pago[{i}][forma_pago]') or 'efectivo').strip()
        if not monto_str:
            continue
        try:
            monto = Decimal(monto_str)
        except (InvalidOperation, ValueError):
            errores.append(f"Monto inválido: {monto_str}")
            continue
        if monto > 0:
            lineas.append((monto, forma))
    if not lineas:  # fallback: envío simple (ej. modal "Completar pago")
        monto_str = (post.get('monto') or '').strip()
        if monto_str:
            try:
                monto = Decimal(monto_str)
                if monto > 0:
                    lineas.append((monto, (post.get('forma_pago') or 'efectivo').strip()))
            except (InvalidOperation, ValueError):
                errores.append(f"Monto inválido: {monto_str}")
    return lineas, errores


def _registrar_pagos_confeccion(confeccion, post, usuario, descripcion_default, saldo_max):
    """Registra pagos divididos de una confección (cada línea → confeccion_pago).
    Valida que el total no exceda saldo_max. Devuelve (total_registrado, errores)."""
    from decimal import Decimal
    from .caja_signals import registrar_pago_confeccion
    lineas, errores = _parsear_lineas_pago(post)
    if errores:
        return Decimal('0'), errores
    total = sum((m for m, _ in lineas), Decimal('0'))
    if total <= 0:
        return Decimal('0'), []
    if saldo_max is not None and total > saldo_max:
        return Decimal('0'), [f"El pago (Bs {total:.2f}) excede el saldo pendiente de Bs {saldo_max:.2f}."]
    via_caja = bool(post.get('via_caja'))
    descripcion = (post.get('descripcion') or '').strip() or descripcion_default
    for monto, forma in lineas:
        registrar_pago_confeccion(confeccion, monto, forma, descripcion, usuario, via_caja=via_caja)
    return total, []


@login_required
def crear_confeccion(request):
    if request.method == 'POST':
        form = ConfeccionForm(request.POST)
        formset = ConfeccionItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            from .models import ConfeccionEmpleado
            confeccion = form.save(commit=False)
            confeccion.tipo = 'confeccion'
            confeccion.save()
            formset.instance = confeccion
            formset.save()
            confeccion.recalcular_precio()  # precio = suma de costos por prenda
            _guardar_asignaciones(confeccion, request.POST, ConfeccionEmpleado, 'confeccion')
            # Adelanto inicial: una o varias formas de pago (pagos divididos)
            _total, pago_errores = _registrar_pagos_confeccion(
                confeccion, request.POST, request.user,
                f"Adelanto confección {confeccion.codigo}", saldo_max=confeccion.precio,
            )
            if pago_errores:
                messages.warning(request, f"Confección {confeccion.codigo} creada, pero el adelanto no se registró: {'; '.join(pago_errores)}")
            else:
                messages.success(request, f"Confección {confeccion.codigo} creada exitosamente.")
            return redirect('detalle_confeccion', id=confeccion.id)
        else:
            messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        initial = {}
        desde_alquiler_id = request.GET.get('desde_alquiler')
        if desde_alquiler_id:
            try:
                alquiler = Alquiler.objects.select_related('cliente').prefetch_related('items__prenda_item__prenda').get(pk=desde_alquiler_id)
                initial['cliente'] = alquiler.cliente_id
                primer_item = alquiler.items.select_related('prenda_item__prenda').first()
                if primer_item and primer_item.prenda_item:
                    initial['color'] = primer_item.prenda_item.prenda.color
                    initial['modelo'] = primer_item.prenda_item.prenda.modelo
                initial['observaciones'] = f"Basado en alquiler {alquiler.codigo}"
            except Alquiler.DoesNotExist:
                pass
        form = ConfeccionForm(initial=initial)
        formset = ConfeccionItemFormSet(prefix='items')
    tipos_prenda = list(TipoPrenda.objects.values('id', 'nombre', 'plantilla'))
    modelo_opts = list(ModeloConfeccion.objects.values_list('nombre', flat=True))
    return render(request, 'misastreria/confecciones/form.html', {
        'form': form,
        'formset': formset,
        'titulo': 'Crear Confección',
        'asignaciones_json': '[]',
        'tipos_prenda_json': json.dumps(tipos_prenda),
        'modelo_opts_json': json.dumps(modelo_opts),
    })

@login_required
def editar_confeccion(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if request.method == 'POST':
        form = ConfeccionForm(request.POST, instance=confeccion)
        formset = ConfeccionItemFormSet(request.POST, instance=confeccion, prefix='items')
        if form.is_valid() and formset.is_valid():
            from .models import ConfeccionEmpleado
            form.save()
            formset.save()
            confeccion.recalcular_precio()  # precio = suma de costos por prenda
            _guardar_asignaciones(confeccion, request.POST, ConfeccionEmpleado, 'confeccion')
            messages.success(request, 'Confección actualizada exitosamente.')
            return redirect('detalle_confeccion', id=confeccion.id)
        else:
            messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        form = ConfeccionForm(instance=confeccion)
        formset = ConfeccionItemFormSet(instance=confeccion, prefix='items')
    tipos_prenda = list(TipoPrenda.objects.values('id', 'nombre', 'plantilla'))
    modelo_opts = list(ModeloConfeccion.objects.values_list('nombre', flat=True))
    return render(request, 'misastreria/confecciones/form.html', {
        'form': form,
        'formset': formset,
        'titulo': 'Editar Confección',
        'confeccion': confeccion,
        'asignaciones_json': _asignaciones_json(confeccion),
        'tipos_prenda_json': json.dumps(tipos_prenda),
        'modelo_opts_json': json.dumps(modelo_opts),
    })

@login_required
def detalle_confeccion(request, id):
    from .forms import PagoConfeccionForm
    confeccion = get_object_or_404(Confeccion, id=id)
    items = confeccion.items.select_related('tipo_prenda').all()
    pagos = confeccion.caja_movimientos.filter(
        movimiento_reverso__isnull=True,
        concepto__in=['confeccion_adelanto', 'confeccion_pago', 'confeccion_saldo'],
    ).order_by('-fecha', '-id')
    return render(request, 'misastreria/confecciones/detalle.html', {
        'confeccion': confeccion,
        'items': items,
        'pagos': pagos,
        'precio': confeccion.precio,
        'pagado': confeccion.total_pagado,
        'saldo': confeccion.saldo_pendiente,
        'form': PagoConfeccionForm(),
    })


@login_required
def agregar_pago_confeccion(request, id):
    from .forms import PagoConfeccionForm
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    confeccion = get_object_or_404(Confeccion, id=id)
    # Soporta una o varias formas de pago (pagos divididos) en un mismo cobro.
    total, errores = _registrar_pagos_confeccion(
        confeccion, request.POST, request.user,
        f"Pago confección {confeccion.codigo}", saldo_max=confeccion.saldo_pendiente,
    )
    if total > 0 and not errores:
        messages.success(request, f"Pago de Bs {total:.2f} registrado correctamente.")
        return redirect('detalle_confeccion', id=id)
    for err in errores:
        messages.error(request, err)
    if not errores and total <= 0:
        messages.error(request, "Ingresá al menos un monto de pago.")
    items = confeccion.items.select_related('tipo_prenda').all()
    pagos = confeccion.caja_movimientos.filter(
        movimiento_reverso__isnull=True,
        concepto__in=['confeccion_adelanto', 'confeccion_pago', 'confeccion_saldo'],
    ).order_by('-fecha', '-id')
    return render(request, 'misastreria/confecciones/detalle.html', {
        'confeccion': confeccion,
        'items': items,
        'pagos': pagos,
        'precio': confeccion.precio,
        'pagado': confeccion.total_pagado,
        'saldo': confeccion.saldo_pendiente,
        'form': PagoConfeccionForm(),
    })


@login_required
def eliminar_confeccion(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if request.method == 'POST':
        try:
            from .caja_signals import _reversar_movimientos_activos
            with transaction.atomic():
                _reversar_movimientos_activos(referencia_field='referencia_confeccion', instance=confeccion, usuario=request.user)
                confeccion.delete()
            messages.success(request, 'Confección eliminada exitosamente.')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar la confección porque está asociada a otros registros.')
        return redirect('lista_confecciones')
    return render(request, 'misastreria/confecciones/eliminar.html', {'confeccion': confeccion})

@login_required
def confeccion_en_proceso(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if request.method == 'POST' and confeccion.estado == 'pendiente':
        confeccion.estado = 'en_proceso'
        confeccion.save()
        messages.success(request, f'Confección {confeccion.codigo} marcada como En Proceso.')
    return redirect('detalle_confeccion', id=confeccion.id)

@login_required
def entregar_confeccion(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if confeccion.estado == 'entregado':
        messages.error(request, 'La confección ya está marcada como entregada.')
        return redirect('lista_confecciones')
    if request.method == 'POST':
        from dateutil.relativedelta import relativedelta
        from datetime import date
        forma_pago = request.POST.get('forma_pago', 'efectivo')
        from .models import FORMA_PAGO_CHOICES as _FPC
        valid = [k for k, _ in _FPC]
        confeccion.forma_pago = forma_pago if forma_pago in valid else 'efectivo'
        confeccion.estado = 'entregado'
        confeccion.saldo = 0
        if not confeccion.fecha_entrega:
            confeccion.fecha_entrega = date.today()
        if confeccion.garantia_meses and not confeccion.garantia_hasta:
            confeccion.garantia_hasta = confeccion.fecha_entrega + relativedelta(months=confeccion.garantia_meses)
        confeccion.save()
        messages.success(request, f'Confección {confeccion.codigo} marcada como entregada.')
        return redirect('lista_confecciones')
    from .models import FORMA_PAGO_CHOICES
    return render(request, 'misastreria/confecciones/entregar.html', {
        'confeccion': confeccion,
        'forma_pago_choices': FORMA_PAGO_CHOICES,
        'saldo_pendiente': confeccion.saldo_pendiente,
    })

@login_required
def exportar_recibo_confeccion_pdf(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_confeccion_{confeccion.codigo}.pdf"'

    st = _pdf_st()
    W_PAGE, L_W, R_W = 18*cm, 6.5*cm, 11.5*cm

    def fmt_d(d):
        return d.strftime('%d/%m/%Y') if d else '—'

    cliente  = confeccion.cliente
    cli_str  = f"{cliente.nombres} {cliente.apellido_paterno}" if cliente else '—'
    tel_str  = getattr(cliente, 'celular', '—') or '—'
    emp_str  = str(confeccion.empleado) if confeccion.empleado else '—'
    cod_str  = confeccion.codigo
    fec_str  = fmt_d(confeccion.fecha_inicio)
    est_str  = confeccion.get_estado_display()

    left_data = [
        [Paragraph('DATOS DEL ENCARGO', st['sec']), ''],
        [Paragraph('<b>Cliente:</b>',        st['kl']), Paragraph(cli_str, st['kv'])],
        [Paragraph('<b>Teléfono:</b>',        st['kl']), Paragraph(tel_str, st['kv'])],
        [Paragraph('<b>Empleado:</b>',        st['kl']), Paragraph(emp_str, st['kv'])],
        [Paragraph('<b>Color:</b>',           st['kl']), Paragraph(confeccion.color or '—', st['kv'])],
        [Paragraph('<b>Modelo:</b>',          st['kl']), Paragraph(confeccion.modelo or '—', st['kv'])],
        [Paragraph('<b>Fecha inicio:</b>',    st['kl']), Paragraph(fec_str, st['kv'])],
        [Paragraph('<b>Fecha prueba:</b>',    st['kl']), Paragraph(fmt_d(confeccion.fecha_prueba), st['kv'])],
        [Paragraph('<b>Fecha entrega:</b>',   st['kl']), Paragraph(fmt_d(confeccion.fecha_entrega), st['kv'])],
        [Paragraph('<b>Estado:</b>',          st['kl']), Paragraph(est_str, st['kv'])],
    ]
    if confeccion.observaciones:
        left_data.append(
            [Paragraph('<b>Observaciones:</b>', st['kl']),
             Paragraph(confeccion.observaciones[:80], st['kv'])]
        )
    conf_items = list(confeccion.items.select_related('tipo_prenda').all())
    items_rows = [
        [Paragraph('PRENDAS A CONFECCIONAR', st['sec']), '', ''],
        ['N°', 'Tipo de Prenda', 'Talla'],
    ]
    for i, item in enumerate(conf_items, 1):
        items_rows.append([
            str(i),
            str(item.tipo_prenda) if item.tipo_prenda else '—',
            item.talla or '—',
        ])
    if not conf_items:
        items_rows.append(['—', '—', '—'])

    _ccw = [0.7*cm, 7.8*cm, 3.0*cm]
    right_inner = Table(items_rows, colWidths=_ccw)
    right_inner.setStyle(TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), _PDF_NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR',     (0, 1), (-1, 1), _PDF_NAVY),
        ('FONTNAME',      (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ALIGN',         (-1, 2), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, _PDF_LGRAY]),
        ('GRID',          (0, 1), (-1, -1), 0.25, colors.HexColor('#e0e0e0')),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    left_tbl  = _RoundedTable(_pdf_left_tbl(left_data, L_W))
    right_tbl = _RoundedTable(right_inner)

    # Financial summary table (replaces single total)
    fin_data = [
        ['Precio total', f"Bs.  {confeccion.precio:.2f}"],
        ['Pagado',       f"Bs.  {confeccion.total_pagado:.2f}"],
        ['Saldo pendiente', f"Bs.  {confeccion.saldo_pendiente:.2f}"],
    ]
    fin_tbl = Table(fin_data, colWidths=[W_PAGE * 0.55, W_PAGE * 0.45])
    fin_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), _PDF_LGRAY),
        ('BACKGROUND',    (0, 2), (-1, 2), colors.HexColor('#eef3ff')),
        ('FONTNAME',      (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME',      (1, 0), (1, -1), 'Helvetica'),
        ('FONTNAME',      (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 10),
        ('FONTSIZE',      (1, 2), (1, 2), 13),
        ('TEXTCOLOR',     (1, 2), (1, 2), _PDF_NAVY),
        ('ALIGN',         (0, 0), (0, -1), 'LEFT'),
        ('ALIGN',         (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('BOX',           (0, 0), (-1, -1), 1, _PDF_GOLD),
        ('LINEBELOW',     (0, 1), (-1, 1), 0.5, colors.HexColor('#cccccc')),
    ]))

    def on_page(c, doc):
        _pdf_page_reparacion(c, doc, 'DE CONFECCIÓN', cod_str, fec_str, '', est_str)

    doc = SimpleDocTemplate(response, pagesize=A4,
                            topMargin=4.4*cm, bottomMargin=2.4*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    doc.build(
        [
            _pdf_body(left_tbl, right_tbl, L_W, R_W),
            Spacer(1, 0.5*cm),
            fin_tbl,
            Spacer(1, 0.8*cm),
            _pdf_sig_tbl(st, W_PAGE),
        ],
        onFirstPage=on_page, onLaterPages=on_page,
    )
    return response

@login_required
def lista_alquileres(request):
    q          = request.GET.get('q', '').strip()
    estado     = request.GET.get('estado', '').strip()
    prenda     = request.GET.get('prenda', '').strip()
    cliente_id = request.GET.get('cliente_id', '').strip()
    desde      = request.GET.get('desde', '').strip()
    hasta      = request.GET.get('hasta', '').strip()
    periodo    = request.GET.get('periodo', '').strip()
    orden      = request.GET.get('orden', 'desc')

    hoy = django_tz.localdate()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat(); hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat(); hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    sort = '-codigo' if orden == 'desc' else 'codigo'
    alquileres = Alquiler.objects.all().order_by(sort)
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()

    if q:
        alquileres = alquileres.filter(
            Q(codigo__icontains=q) |
            Q(cliente__nombres__icontains=q) |
            Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q) |
            Q(items__prenda_item__prenda__nombre__icontains=q)
        ).distinct()
    if cliente_id:
        alquileres = alquileres.filter(cliente_id=cliente_id)
    if prenda:
        alquileres = alquileres.filter(items__prenda_item__prenda__nombre__icontains=prenda).distinct()
    if estado:
        alquileres = alquileres.filter(estado=estado)
    if desde:
        alquileres = alquileres.filter(fecha_alquiler__gte=desde)
    if hasta:
        alquileres = alquileres.filter(fecha_alquiler__lte=hasta)

    total = alquileres.count()
    paginator = Paginator(alquileres, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/alquileres/lista.html', {
        'page_obj': page_obj,
        'total':    total,
        'q':        q,
        'prenda':   prenda,
        'cliente_id': cliente_id,
        'estado':   estado,
        'desde':    desde,
        'hasta':    hasta,
        'periodo':  periodo,
        'orden':    orden,
        'orden_toggle_url': orden_toggle_url,
        'estado_choices': [(n, n) for n in EstadoAlquiler.objects.values_list('nombre', flat=True)],
        'estado_mapa':    {e.nombre: e.color for e in EstadoAlquiler.objects.all()},
    })


def _guardar_items_alquiler(alquiler, post_data, estado_anterior=None):
    """Guarda los ítems del alquiler y gestiona el estado de cada PrendaItem."""
    ESTADOS_QUE_BLOQUEAN = {'alquilado', 'reservado'}
    ESTADOS_NORMALES = {'alquilado', 'devuelto', 'reservado'}
    if estado_anterior in ESTADOS_QUE_BLOQUEAN:
        nuevo = alquiler.estado
        if nuevo not in ESTADOS_NORMALES:
            disposition = post_data.get('items_disposition', 'disponible')
            if disposition == 'baja':
                target = 'baja'
            elif disposition == 'mantener':
                target = None  # no tocar
            else:
                target = 'disponible'
        else:
            target = 'disponible'

        if target is not None:
            for item in alquiler.items.select_related('prenda_item'):
                pi = item.prenda_item
                pi.estado = target
                pi.save(update_fields=['estado'])
    kardex_events.delete_eventos_alquiler(alquiler)
    alquiler.items.all().delete()

    prenda_item_ids       = post_data.getlist('item_prenda_item')
    precios               = post_data.getlist('item_precio')
    grupos                = post_data.getlist('item_grupo_conjunto')
    tipo_reparacion_ids   = post_data.getlist('item_tipo_reparacion')
    precios_reparacion    = post_data.getlist('item_precio_reparacion')
    empleado_ids          = post_data.getlist('item_empleado')
    porcentajes_comision  = post_data.getlist('item_porcentaje_comision')
    errores               = []
    seen                  = set()

    for i, (pi_id, precio_str, grupo_str, tr_id, prec_rep_str, emp_id, pct_str) in enumerate(
        zip_longest(
            prenda_item_ids, precios, grupos, tipo_reparacion_ids, precios_reparacion,
            empleado_ids, porcentajes_comision, fillvalue=''
        ), 1
    ):
        if not pi_id:
            continue
        if pi_id in seen:
            errores.append(f"Fila {i}: el item ya fue seleccionado en otra fila.")
            continue
        seen.add(pi_id)
        try:
            pi = PrendaItem.objects.select_related('prenda').get(pk=pi_id)
        except PrendaItem.DoesNotExist:
            errores.append(f"Fila {i}: item inexistente.")
            continue

        if alquiler.estado in ESTADOS_QUE_BLOQUEAN and pi.estado != 'disponible':
            errores.append(
                f"Fila {i}: el item {pi.codigo_item} no está disponible "
                f"(estado: {pi.get_estado_display()})."
            )
            continue

        try:
            precio = Decimal(precio_str)
        except Exception:
            precio = pi.prenda.precio
        try:
            grupo = int(grupo_str) or None
        except (TypeError, ValueError):
            grupo = None
        try:
            precio_reparacion = Decimal(prec_rep_str) if prec_rep_str else Decimal('0')
        except Exception:
            precio_reparacion = Decimal('0')
        tipo_reparacion = None
        if tr_id:
            tipo_reparacion = TipoReparacion.objects.filter(pk=tr_id).first()
        empleado_arreglo = Empleado.objects.filter(pk=emp_id).first() if emp_id else None
        try:
            pct_comision = Decimal(pct_str) if (pct_str and empleado_arreglo) else None
        except Exception:
            pct_comision = None
        ai = AlquilerItem.objects.create(
            alquiler=alquiler,
            prenda_item=pi,
            precio_unitario=precio,
            tipo_reparacion=tipo_reparacion,
            precio_reparacion=precio_reparacion,
            empleado=empleado_arreglo,
            porcentaje_comision=pct_comision,
            grupo_conjunto=grupo,
        )
        if alquiler.estado in ESTADOS_QUE_BLOQUEAN:
            if alquiler.estado == 'alquilado':
                kardex_events.emit_alquiler(ai.prenda_item, alquiler, ai.precio_unitario)
            pi.estado = alquiler.estado
            pi.save(update_fields=['estado'])

    alquiler.recalcular_totales()
    return errores


@login_required
def crear_alquiler(request):
    if request.method == 'POST':
        form = AlquilerForm(request.POST)
        if form.is_valid():
            alquiler = form.save()
            errores = _guardar_items_alquiler(alquiler, request.POST)
            from decimal import Decimal
            from .caja_signals import registrar_alquiler_en_caja, registrar_garantia_alquiler_en_caja, registrar_pago_alquiler
            adelanto = form.cleaned_data.get('adelanto') or Decimal('0')
            if adelanto > (alquiler.total or Decimal('0')):
                adelanto = alquiler.total or Decimal('0')
            forma = form.cleaned_data.get('forma_pago') or 'efectivo'
            registrar_alquiler_en_caja(alquiler, adelanto=adelanto, forma_pago=forma)
            registrar_garantia_alquiler_en_caja(alquiler)
            if errores:
                messages.warning(request, 'Alquiler creado con advertencias: ' + '; '.join(errores))
            else:
                messages.success(request, f"Alquiler {alquiler.codigo} creado exitosamente.")
            return redirect('detalle_alquiler', id=alquiler.id)
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = AlquilerForm()
    items_preload = []
    item_id = request.GET.get('item')
    if item_id:
        try:
            pi = PrendaItem.objects.select_related('prenda').get(id=item_id, tipo='alquiler', estado='disponible', conjunto_slots__isnull=True)
            items_preload = [{'prenda_item_id': pi.id, 'precio_unitario': float(pi.prenda.precio), 'grupo_conjunto': None}]
        except PrendaItem.DoesNotExist:
            pass
    return render(request, 'misastreria/alquileres/form.html', {
        'form': form,
        'titulo': 'Nuevo Alquiler',
        'prendas_json': _prendas_alquiler_json(),
        'conjuntos_json': _conjuntos_json('alquiler'),
        'estado_alquiler_opts': list(EstadoAlquiler.objects.values('nombre', 'color')),
        'items_existentes': json.dumps(items_preload),
        'tipos_reparacion_json': json.dumps(list(TipoReparacion.objects.values('id', 'nombre').order_by('nombre'))),
        'empleados_json': _empleados_arreglo_json(),
    })


@login_required
def editar_alquiler(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if request.method == 'POST':
        estado_anterior = alquiler.estado
        form = AlquilerForm(request.POST, instance=alquiler)
        if form.is_valid():
            old_total = alquiler.total
            alquiler = form.save()
            errores = _guardar_items_alquiler(alquiler, request.POST, estado_anterior=estado_anterior)
            from .caja_signals import _ajustar_total_en_caja, _ajustar_garantia_alquiler_en_caja
            _ajustar_total_en_caja(
                referencia_field='referencia_alquiler',
                instance=alquiler,
                concepto_cobro='alquiler_ajuste',
                nuevo_total=alquiler.total,
                old_total=old_total,
                forma_pago=getattr(alquiler, 'forma_pago', 'efectivo') or 'efectivo',
                cliente=getattr(alquiler, 'cliente', None),
            )
            _ajustar_garantia_alquiler_en_caja(alquiler)
            if errores:
                messages.warning(request, 'Actualizado con advertencias: ' + '; '.join(errores))
            else:
                messages.success(request, 'Alquiler actualizado correctamente.')
            return redirect('lista_alquileres')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = AlquilerForm(instance=alquiler)
    prendas_json = _prendas_alquiler_json()

    # Inyectar items propios del alquiler (aunque estén en estado 'alquilado' o 'reservado')
    if alquiler.estado in ('alquilado', 'reservado'):
        items_propios_ids = list(alquiler.items.values_list('prenda_item_id', flat=True))
        prendas_base = json.loads(prendas_json)
        ids_en_json = {p['prenda_item_id'] for p in prendas_base}
        for pi in PrendaItem.objects.filter(pk__in=items_propios_ids).select_related('prenda'):
            if pi.id not in ids_en_json:
                p = pi.prenda
                ubic = f" [{pi.ubicacion}]" if pi.ubicacion else ""
                label = (
                    f"{pi.codigo_item} — {p.nombre}"
                    f"{f' T{p.talla}' if p.talla else ''}"
                    f"{f' {p.color}' if p.color else ''}"
                    f" ({pi.get_condicion_display()}){ubic}"
                )
                prendas_base.append({
                    'prenda_item_id': pi.id,
                    'codigo_item': pi.codigo_item,
                    'sku_codigo': p.codigo,
                    'sku_nombre': p.nombre,
                    'talla': p.talla,
                    'color': p.color,
                    'condicion': pi.condicion,
                    'condicion_label': pi.get_condicion_display(),
                    'ubicacion': str(pi.ubicacion) if pi.ubicacion else '',
                    'precio': float(p.precio),
                    'label': label,
                    'tipo_prenda_id': p.tipo_prenda_id,
                })
        prendas_json = json.dumps(prendas_base)

    # Construir ITEMS_INICIALES para el template
    items_iniciales = [
        {
            'prenda_item_id': item.prenda_item_id,
            'precio_unitario': float(item.precio_unitario),
            'grupo_conjunto': item.grupo_conjunto,
            'tipo_reparacion_id': item.tipo_reparacion_id,
            'precio_reparacion': float(item.precio_reparacion or 0),
            'empleado_id': item.empleado_id,
            'porcentaje_comision': float(item.porcentaje_comision) if item.porcentaje_comision is not None else None,
        }
        for item in alquiler.items.all()
    ]
    items_iniciales_json = json.dumps(items_iniciales)

    return render(request, 'misastreria/alquileres/form.html', {
        'form':    form,
        'titulo':  'Editar Alquiler',
        'alquiler': alquiler,
        'items_existentes': items_iniciales_json,
        'prendas_json': prendas_json,
        'conjuntos_json': _conjuntos_json('alquiler'),
        'estado_alquiler_opts': list(EstadoAlquiler.objects.values('nombre', 'color')),
        'tipos_reparacion_json': json.dumps(list(TipoReparacion.objects.values('id', 'nombre').order_by('nombre'))),
        'empleados_json': _empleados_arreglo_json(),
    })


def _build_prenda_item_opts(tipo=None):
    qs = (
        PrendaItem.objects
        .filter(estado='disponible', prenda__estado='ACT')
        .exclude(conjunto_slots__isnull=False)
        .select_related('prenda')
        .order_by('codigo_item')
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    result = []
    for pi in qs:
        nombre_prenda = pi.prenda.nombre
        if pi.prenda.talla:
            nombre_prenda += f' T{pi.prenda.talla}'
        result.append({
            'id': pi.id,
            'nombre': f'{pi.codigo_item} — {nombre_prenda}',
            'info': pi.get_estado_display(),
        })
    return result


def _conjuntos_json(tipo=None):
    qs = (
        Conjunto.objects.filter(activo=True)
        .prefetch_related('slots__prenda_item__prenda')
        .order_by('nombre')
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    data = []
    for c in qs:
        slots_out = []
        requeridos_total = 0
        requeridos_disponible = 0
        for s in c.slots.all():
            pi = s.prenda_item
            if pi:
                nombre = pi.prenda.nombre
                if pi.prenda.talla:
                    nombre += f' T{pi.prenda.talla}'
                disponible = pi.estado == 'disponible'
            else:
                nombre = 'Sin asignar'
                disponible = False
            if not s.opcional:
                requeridos_total += 1
                if disponible:
                    requeridos_disponible += 1
            precio_base = float(pi.prenda.precio_alquiler_base) if (pi and pi.prenda.precio_alquiler_base) else None
            slots_out.append({
                'id': s.id,
                'prenda_item_id': s.prenda_item_id,
                'prenda_item_codigo': pi.codigo_item if pi else None,
                'prenda_item_nombre': nombre,
                'disponible': disponible,
                'opcional': s.opcional,
                'orden': s.orden,
                'precio_alquiler_base': precio_base,
            })

        if requeridos_total == 0:
            disponibilidad = 'no_disponible'
        elif requeridos_disponible == requeridos_total:
            disponibilidad = 'completo'
        elif requeridos_disponible > 0:
            disponibilidad = 'parcial'
        else:
            disponibilidad = 'no_disponible'

        data.append({
            'id': c.id,
            'nombre': c.nombre,
            'descripcion': c.descripcion,
            'precio_sugerido': float(c.precio_sugerido),
            'disponibilidad': disponibilidad,
            'slots': slots_out,
        })
    return json.dumps(data)


def _prenda_items_json(tipo):
    qs = (
        PrendaItem.objects
        .select_related('prenda')
        .filter(
            tipo=tipo,
            prenda__estado='ACT',
            estado='disponible',
        )
        .exclude(conjunto_slots__isnull=False)
        .order_by('prenda__codigo', 'codigo_item')
    )
    data = []
    for pi in qs:
        p = pi.prenda
        ubic = f" [{pi.ubicacion}]" if pi.ubicacion else ""
        label = (
            f"{pi.codigo_item} — {p.nombre}"
            f"{f' T{p.talla}' if p.talla else ''}"
            f"{f' {p.color}' if p.color else ''}"
            f" ({pi.get_condicion_display()}){ubic}"
        )
        data.append({
            'prenda_item_id': pi.id,
            'codigo_item':    pi.codigo_item,
            'sku_codigo':     p.codigo,
            'sku_nombre':     p.nombre,
            'talla':          p.talla,
            'color':          p.color,
            'condicion':      pi.condicion,
            'condicion_label': pi.get_condicion_display(),
            'ubicacion':      str(pi.ubicacion) if pi.ubicacion else '',
            'precio':         float(p.precio),
            'precio_alquiler_base': float(p.precio_alquiler_base) if p.precio_alquiler_base else None,
            'label':          label,
            'tipo_prenda_id': p.tipo_prenda_id,
            'prenda_inventario_id': pi.prenda_id,
        })
    return json.dumps(data)


def _prendas_alquiler_json():
    return _prenda_items_json('alquiler')


@login_required
def eliminar_alquiler(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if request.method == 'POST':
        from .caja_signals import _reversar_movimientos_activos
        if alquiler.estado in ('alquilado', 'reservado'):
            for item in alquiler.items.select_related('prenda_item'):
                pi = item.prenda_item
                pi.estado = 'disponible'
                pi.save(update_fields=['estado'])
        _reversar_movimientos_activos(referencia_field='referencia_alquiler', instance=alquiler, usuario=request.user)
        alquiler.delete()
        messages.success(request, 'Alquiler eliminado correctamente.')
        return redirect('lista_alquileres')
    return render(request, 'misastreria/alquileres/eliminar.html', {'alquiler': alquiler})


@login_required
def devolver_alquiler(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if alquiler.estado == 'reservado':
        return redirect('confirmar_reserva', id=alquiler.id)
    if alquiler.estado == 'devuelto':
        messages.error(request, 'El alquiler ya está marcado como devuelto.')
        return redirect('lista_alquileres')

    _TIPOS_MONETARIOS = ('efectivo', 'qr', 'transferencia')
    tiene_garantia_monetaria = (
        alquiler.garantia_tipo in _TIPOS_MONETARIOS
        and alquiler.garantia_monto
        and alquiler.garantia_monto > 0
    )

    if request.method == 'POST':
        for item in alquiler.items.select_related('prenda_item'):
            pi = item.prenda_item
            pi.veces_alquilado = (pi.veces_alquilado or 0) + 1
            pi.condicion = 'usada'
            pi.estado = 'disponible'
            pi.save(update_fields=['veces_alquilado', 'condicion', 'estado'])
        alquiler.estado = 'devuelto'
        alquiler.save()
        for ai in alquiler.items.select_related('prenda_item').all():
            kardex_events.emit_devolucion(ai.prenda_item, alquiler)

        if tiene_garantia_monetaria:
            raw = request.POST.get('garantia_devolver', '').strip()
            try:
                monto_devuelto = Decimal(raw) if raw else Decimal('0')
            except Exception:
                monto_devuelto = Decimal('0')
            if monto_devuelto > 0:
                from .caja_signals import registrar_devolucion_garantia_alquiler
                registrar_devolucion_garantia_alquiler(alquiler, monto_devuelto, request.user)

        messages.success(request, f'Alquiler {alquiler.codigo} devuelto. Items restaurados a disponible.')
        return redirect('lista_alquileres')

    return render(request, 'misastreria/alquileres/devolver.html', {
        'alquiler': alquiler,
        'tiene_garantia_monetaria': tiene_garantia_monetaria,
    })


@login_required
def confirmar_reserva(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if alquiler.estado != 'reservado':
        messages.error(request, 'Solo se pueden confirmar alquileres en estado reservado.')
        return redirect('detalle_alquiler', id=alquiler.id)
    if request.method == 'POST':
        for ai in alquiler.items.select_related('prenda_item'):
            kardex_events.emit_alquiler(ai.prenda_item, alquiler, ai.precio_unitario)
            ai.prenda_item.estado = 'alquilado'
            ai.prenda_item.save(update_fields=['estado'])
        alquiler.estado = 'alquilado'
        alquiler.save()
        messages.success(request, f'Reserva {alquiler.codigo} confirmada como alquiler.')
        return redirect('detalle_alquiler', id=alquiler.id)
    return render(request, 'misastreria/alquileres/confirmar.html', {'alquiler': alquiler})


@login_required
def exportar_comprobante_alquiler_pdf(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="comprobante_alquiler_{alquiler.codigo}.pdf"'

    st = _pdf_st()
    W_PAGE, L_W, R_W = 18*cm, 6.5*cm, 11.5*cm

    cliente  = alquiler.cliente
    cli_str  = f"{cliente.nombres} {cliente.apellido_paterno}" if cliente else '—'
    tel_str  = getattr(cliente, 'celular', '—') or '—'
    emp_str  = str(alquiler.empleado) if alquiler.empleado else '—'
    garantia = alquiler.garantia or 'Cubre pérdida y daño de las prendas alquiladas.'
    fec_str  = alquiler.fecha_alquiler.strftime('%d/%m/%Y')
    fdev_str = alquiler.fecha_devolucion.strftime('%d/%m/%Y')
    if alquiler.hora_devolucion:
        fdev_str += f" a las {alquiler.hora_devolucion.strftime('%H:%M')}"
    hora_hdr = alquiler.hora_devolucion.strftime('%H:%M') if alquiler.hora_devolucion else ''
    est_str  = alquiler.estado_display
    cod_str  = alquiler.codigo

    left_data = [
        [Paragraph('DATOS DEL CLIENTE', st['sec']), ''],
        [Paragraph('<b>Cliente:</b>',         st['kl']), Paragraph(cli_str, st['kv'])],
        [Paragraph('<b>Empleado:</b>',         st['kl']), Paragraph(emp_str, st['kv'])],
        [Paragraph('<b>Teléfono:</b>',         st['kl']), Paragraph(tel_str, st['kv'])],
        [Paragraph('<b>Garantía:</b>',         st['kl']), Paragraph(garantia[:60], st['kv'])],
        [Paragraph('<b>Fecha alquiler:</b>',   st['kl']), Paragraph(fec_str, st['kv'])],
        [Paragraph('<b>Fecha devolución:</b>', st['kl']), Paragraph(fdev_str, st['kv'])],
        [Paragraph('<b>Aviso:</b>',            st['kl']),
         Paragraph('En caso de no devolver en la fecha acordada, se aplicará un recargo por día de retraso.',
                   st['kv'])],
    ]
    alq_items = list(alquiler.items.select_related('prenda_item__prenda'))
    items_rows = [
        [Paragraph('DETALLE DE PRENDAS', st['sec']), '', '', '', '', '', ''],
        ['N°', 'Prenda', 'Color', 'Talla', 'Cant.', 'P. Unit.', 'Subtotal'],
    ]
    for i, item in enumerate(alq_items, 1):
        prenda = item.prenda_item.prenda if item.prenda_item else None
        items_rows.append([
            str(i),
            prenda.nombre if prenda else '—',
            (prenda.color or '—') if prenda else '—',
            (prenda.talla or '—') if prenda else '—',
            '1',
            f"Bs {item.precio_unitario:.2f}",
            f"Bs {item.subtotal:.2f}",
        ])
    items_rows.append(['', '', '', '', '', 'Subtotal:', f"Bs {alquiler.subtotal:.2f}"])
    if alquiler.descuento:
        items_rows.append(['', '', '', '', '', f'Desc. {alquiler.descuento}%:',
                           f"-Bs {(alquiler.subtotal - alquiler.total):.2f}"])
    items_rows.append(['', '', '', '', '', 'TOTAL:', f"Bs {alquiler.total:.2f}"])

    _acw = [0.5*cm, 3.0*cm, 1.5*cm, 1.2*cm, 0.8*cm, 2.0*cm, 2.5*cm]
    right_inner = Table(items_rows, colWidths=_acw)
    right_inner.setStyle(TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), _PDF_NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR',     (0, 1), (-1, 1), _PDF_NAVY),
        ('FONTNAME',      (0, 0), (-1, 1), 'Helvetica-Bold'),
        ('FONTNAME',      (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('ALIGN',         (-2, 2), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 2), (-1, -2), [colors.white, _PDF_LGRAY]),
        ('GRID',          (0, 1), (-1, -2), 0.25, colors.HexColor('#e0e0e0')),
        ('LINEABOVE',     (0, -1), (-1, -1), 0.5, _PDF_NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    left_tbl  = _RoundedTable(_pdf_left_tbl(left_data, L_W))
    right_tbl = _RoundedTable(right_inner)

    # Condiciones
    cond_rows = [
        [Paragraph('CONDICIONES DEL ALQUILER', st['ch'])],
        [Paragraph('&bull; El cliente es responsable del cuidado de las prendas.', st['ci'])],
        [Paragraph('&bull; En caso de daño o pérdida, se aplicará el monto correspondiente.', st['ci'])],
        [Paragraph('&bull; Recargo por retraso: 20% por día de la prenda alquilada.', st['ci'])],
        [Paragraph('&bull; No se devuelve la garantía por pérdida o daño total.', st['ci'])],
    ]
    cond_tbl = Table(cond_rows, colWidths=[W_PAGE])
    cond_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), _PDF_LGRAY),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('BOX',           (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))

    def on_page(c, doc):
        _pdf_page_reparacion(c, doc, 'DE ALQUILER DE PRENDAS', cod_str, fec_str, hora_hdr, est_str)

    doc = SimpleDocTemplate(response, pagesize=A4,
                            topMargin=4.4*cm, bottomMargin=2.4*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    doc.build(
        [
            _pdf_body(left_tbl, right_tbl, L_W, R_W),
            Spacer(1, 0.4*cm),
            _pdf_total_tbl('TOTAL A PAGAR', f"Bs.  {alquiler.total:.2f}", W_PAGE),
            Spacer(1, 0.4*cm),
            cond_tbl,
            Spacer(1, 0.6*cm),
            _pdf_sig_tbl(st, W_PAGE),
        ],
        onFirstPage=on_page, onLaterPages=on_page,
    )
    return response


@login_required
def detalle_alquiler(request, id):
    from .forms import PagoAlquilerForm
    alquiler = get_object_or_404(Alquiler, id=id)
    items = alquiler.items.select_related('prenda_item__prenda').all()
    pagos = alquiler.caja_movimientos.filter(
        movimiento_reverso__isnull=True,
        concepto__in=['alquiler_cobro', 'alquiler_pago'],
    ).order_by('-fecha', '-id')
    total = alquiler.total
    pagado = alquiler.total_pagado
    saldo = alquiler.saldo_pendiente
    form = PagoAlquilerForm()
    return render(request, 'misastreria/alquileres/detalle.html', {
        'alquiler': alquiler,
        'items': items,
        'pagos': pagos,
        'total': total,
        'pagado': pagado,
        'saldo': saldo,
        'form': form,
    })


@login_required
def agregar_pago_alquiler(request, id):
    from .forms import PagoAlquilerForm
    from .caja_signals import registrar_pago_alquiler
    from django.http import HttpResponseNotAllowed
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    alquiler = get_object_or_404(Alquiler, id=id)
    form = PagoAlquilerForm(request.POST)
    if form.is_valid():
        monto = form.cleaned_data['monto']
        saldo = alquiler.saldo_pendiente
        if monto > saldo:
            form.add_error('monto', f"El pago excede el saldo pendiente de Bs {saldo:.2f}.")
        else:
            registrar_pago_alquiler(
                alquiler,
                monto,
                form.cleaned_data['forma_pago'],
                form.cleaned_data.get('descripcion', ''),
                request.user,
                via_caja=form.cleaned_data.get('via_caja', True),
            )
            messages.success(request, f"Pago de Bs {monto:.2f} registrado correctamente.")
            return redirect('detalle_alquiler', id=id)
    items = alquiler.items.select_related('prenda_item__prenda').all()
    pagos = alquiler.caja_movimientos.filter(
        movimiento_reverso__isnull=True,
        concepto__in=['alquiler_cobro', 'alquiler_pago'],
    ).order_by('-fecha', '-id')
    return render(request, 'misastreria/alquileres/detalle.html', {
        'alquiler': alquiler,
        'items': items,
        'pagos': pagos,
        'total': alquiler.total,
        'pagado': alquiler.total_pagado,
        'saldo': alquiler.saldo_pendiente,
        'form': form,
    })


@login_required
def lista_transacciones(request):
    q = request.GET.get('q', '').strip()
    tipo_transaccion = request.GET.get('tipo_transaccion', '').strip()
    tipo_servicio = request.GET.get('tipo_servicio', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()
    orden = request.GET.get('orden', 'desc')

    hoy = django_tz.localdate()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    sort = '-codigo' if orden == 'desc' else 'codigo'
    transacciones = Transaccion.objects.all().order_by(sort)
    _p = request.GET.copy(); _p['orden'] = 'asc' if orden == 'desc' else 'desc'; _p.pop('page', None)
    orden_toggle_url = '?' + _p.urlencode()
    if q:
        transacciones = transacciones.filter(
            Q(codigo__icontains=q) |
            Q(descripcion__icontains=q)
        )
    if tipo_transaccion:
        transacciones = transacciones.filter(tipo_transaccion=tipo_transaccion)
    if tipo_servicio:
        transacciones = transacciones.filter(tipo_servicio=tipo_servicio)
    if desde:
        transacciones = transacciones.filter(fecha__gte=desde)
    if hasta:
        transacciones = transacciones.filter(fecha__lte=hasta)

    total = transacciones.count()
    paginator = Paginator(transacciones, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/transacciones/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'tipo_transaccion': tipo_transaccion,
        'tipo_servicio': tipo_servicio,
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'orden': orden, 'orden_toggle_url': orden_toggle_url,
        'tipo_transaccion_choices': Transaccion.TIPO_TRANSACCION_CHOICES,
        'tipo_servicio_choices': Transaccion.TIPO_SERVICIO_CHOICES,
    })


@login_required
def crear_transaccion(request):
    if request.method == 'POST':
        form = TransaccionForm(request.POST)
        if form.is_valid():
            transaccion = form.save()
            messages.success(request, f"Transacción {transaccion.codigo} creada exitosamente.")
            return redirect('lista_transacciones')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = TransaccionForm()
    return render(request, 'misastreria/transacciones/form.html', {
        'form': form,
        'titulo': 'Crear Transacción'
    })

@login_required
def editar_transaccion(request, id):
    transaccion = get_object_or_404(Transaccion, id=id)
    if request.method == 'POST':
        form = TransaccionForm(request.POST, instance=transaccion)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transacción actualizada exitosamente.')
            return redirect('lista_transacciones')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = TransaccionForm(instance=transaccion)
    return render(request, 'misastreria/transacciones/form.html', {
        'form': form,
        'titulo': 'Editar Transacción',
        'transaccion': transaccion
    })

@login_required
def eliminar_transaccion(request, id):
    transaccion = get_object_or_404(Transaccion, id=id)
    if request.method == 'POST':
        transaccion.delete()
        messages.success(request, 'Transacción eliminada exitosamente.')
        return redirect('lista_transacciones')
    return render(request, 'misastreria/transacciones/eliminar.html', {'transaccion': transaccion})

@login_required
def lista_prendas(request):
    q      = request.GET.get('q', '').strip()
    tipo   = request.GET.get('tipo', '').strip()
    estado = request.GET.get('estado', 'ACT').strip()

    qs = (
        PrendaInventario.objects
        .annotate(
            stock_total=Count('items', filter=~Q(items__estado='baja')),
            _stock_disponible=Count('items', filter=Q(items__estado='disponible')),
            items_alquiler=Count('items', filter=Q(items__tipo='alquiler') & ~Q(items__estado='baja')),
            items_venta=Count('items', filter=Q(items__tipo='venta') & ~Q(items__estado='baja')),
        )
        .prefetch_related('items')
        .order_by('-creado')
    )
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) | Q(nombre__icontains=q) |
            Q(color__icontains=q)  | Q(talla__icontains=q)  |
            Q(codigo_referencia__icontains=q)
        )
    if tipo:
        qs = qs.filter(items__tipo=tipo).distinct()
    if estado:
        qs = qs.filter(estado=estado)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    # Annotate each page object with alert counts using Python (prefetch_related avoids N+1)
    for prenda in page_obj:
        alerta_items = [
            i for i in prenda.items.all()
            if i.estado != 'baja' and i.estado_vida_util in ('advertencia', 'critico')
        ]
        prenda.items_proximos_baja_count = len(alerta_items)
        prenda.tiene_critico = any(i.estado_vida_util == 'critico' for i in alerta_items)

    return render(request, 'misastreria/prendas/lista.html', {
        'page_obj': page_obj,
        'total':    total,
        'q':        q,
        'tipo':     tipo,
        'estado':   estado,
        'tipo_choices':   PrendaItem.TIPO_CHOICES,
        'estado_choices': PrendaInventario.ESTADO_OPCIONES,
    })


@login_required
def crear_prenda(request):
    if request.method == 'POST':
        form = PrendaInventarioForm(request.POST)
        if form.is_valid():
            prenda = form.save()
            messages.success(request, f'Prenda creada con código {prenda.codigo}.')
            return redirect('lista_prendas')
    else:
        form = PrendaInventarioForm()
    return render(request, 'misastreria/prendas/form.html', {
        'form':   form,
        'titulo': 'Nueva Prenda',
    })


@login_required
def editar_prenda(request, id):
    prenda = get_object_or_404(PrendaInventario, id=id)
    if request.method == 'POST':
        form = PrendaInventarioForm(request.POST, instance=prenda)
        if form.is_valid():
            form.save()
            messages.success(request, 'Prenda actualizada correctamente.')
            return redirect('lista_prendas')
    else:
        form = PrendaInventarioForm(instance=prenda)
    return render(request, 'misastreria/prendas/form.html', {
        'form':   form,
        'titulo': 'Editar Prenda',
        'prenda': prenda,
    })


@login_required
def eliminar_prenda(request, id):
    prenda = get_object_or_404(PrendaInventario, id=id)
    if request.method == 'POST':
        try:
            prenda.delete()
            messages.success(request, 'Prenda eliminada correctamente.')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar la prenda porque tiene ventas o alquileres asociados.')
        return redirect('lista_prendas')
    return render(request, 'misastreria/prendas/eliminar.html', {'prenda': prenda})


@login_required
def detalle_prenda(request, id):
    from django.db.models import Count, Q as Qfilter
    prenda = get_object_or_404(
        PrendaInventario.objects.annotate(
            stock_total=Count('items', filter=~Qfilter(items__estado='baja')),
            _stock_disponible=Count('items', filter=Qfilter(items__estado='disponible')),
        ),
        id=id,
    )
    items = prenda.items.all().order_by('codigo_item')
    resumen = {
        'disponible': items.filter(estado='disponible').count(),
        'alquilado':  items.filter(estado='alquilado').count(),
        'baja':       items.filter(estado='baja').count(),
        'total':      items.count(),
    }
    return render(request, 'misastreria/prendas/detalle.html', {
        'prenda':  prenda,
        'items':   items,
        'resumen': resumen,
        'ubicacion_opts': list(UbicacionItem.objects.values('id', 'nombre')),
    })


@login_required
def editar_prenda_item(request, id):
    item = get_object_or_404(PrendaItem, id=id)
    if request.method == 'POST':
        ubicacion_id = request.POST.get('ubicacion', '').strip()
        if ubicacion_id:
            try:
                item.ubicacion = UbicacionItem.objects.get(id=int(ubicacion_id))
            except (ValueError, UbicacionItem.DoesNotExist):
                item.ubicacion = None
        else:
            item.ubicacion = None
        item.condicion = request.POST.get('condicion', item.condicion)
        item.tipo      = request.POST.get('tipo', item.tipo)
        item.notas     = request.POST.get('notas', '').strip()
        max_usos_raw = request.POST.get('max_usos', '').strip()
        if max_usos_raw == '':
            item.max_usos = None
        else:
            try:
                val = int(max_usos_raw)
                if val > 0:
                    item.max_usos = val
            except (TypeError, ValueError):
                pass  # silently keep current value on invalid input
        if item.max_usos and item.max_usos <= item.veces_alquilado:
            messages.warning(request, f'El máx. de usos ({item.max_usos}) es menor o igual a los usos actuales ({item.veces_alquilado}).')
        item.save(update_fields=['ubicacion', 'condicion', 'tipo', 'notas', 'max_usos', 'actualizado'])
        messages.success(request, f'Item {item.codigo_item} actualizado.')
        return redirect('detalle_prenda', id=item.prenda_id)
    return redirect('detalle_prenda', id=item.prenda_id)


@login_required
def baja_prenda_item(request, id):
    item = get_object_or_404(PrendaItem, id=id)
    if request.method == 'POST':
        if item.estado in ('alquilado', 'reservado'):
            messages.error(request, f'El item {item.codigo_item} está {item.get_estado_display().lower()} y no puede darse de baja.')
            return redirect('detalle_prenda', id=item.prenda_id)
        item.estado = 'baja'
        item.fecha_baja = date.today()
        item.save(update_fields=['estado', 'fecha_baja', 'actualizado'])
        kardex_events.emit_baja(item)
        messages.success(request, f'Item {item.codigo_item} dado de baja.')
        return redirect('detalle_prenda', id=item.prenda_id)
    return redirect('detalle_prenda', id=item.prenda_id)


@login_required
def items_proximos_baja(request):
    estado_filter = request.GET.get('estado', 'todos').strip()

    items = PrendaItem.objects.exclude(estado='baja').select_related('prenda').order_by('prenda__nombre')
    items_con_vida_util = [i for i in items if i.max_usos_efectivo is not None]

    if estado_filter == 'advertencia':
        items_filtrados = [i for i in items_con_vida_util if i.estado_vida_util == 'advertencia']
    elif estado_filter == 'critico':
        items_filtrados = [i for i in items_con_vida_util if i.estado_vida_util == 'critico']
    else:
        estado_filter = 'todos'
        items_filtrados = [i for i in items_con_vida_util if i.estado_vida_util in ('advertencia', 'critico')]

    items_filtrados.sort(key=lambda i: i.porcentaje_vida_util or 0, reverse=True)

    total = len(items_filtrados)
    paginator = Paginator(items_filtrados, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/prendas/proximos_baja.html', {
        'page_obj':      page_obj,
        'total':         total,
        'estado_filter': estado_filter,
    })


@login_required
def agregar_items_prenda(request, id):
    prenda = get_object_or_404(PrendaInventario, id=id)
    if request.method != 'POST':
        return redirect('detalle_prenda', id=prenda.id)
    try:
        cantidad = int(request.POST.get('cantidad', 1))
    except (TypeError, ValueError):
        cantidad = 1
    cantidad = min(50, max(1, cantidad))
    tipo      = request.POST.get('tipo', 'alquiler')
    condicion = request.POST.get('condicion', 'nueva')
    notas     = request.POST.get('notas', '').strip()
    ubicacion_id = request.POST.get('ubicacion', '').strip()
    ubicacion_obj = None
    if ubicacion_id:
        try:
            ubicacion_obj = UbicacionItem.objects.get(id=int(ubicacion_id))
        except (ValueError, UbicacionItem.DoesNotExist):
            pass
    for _ in range(cantidad):
        pi = PrendaItem.objects.create(
            prenda=prenda,
            tipo=tipo,
            condicion=condicion,
            ubicacion=ubicacion_obj,
            notas=notas,
        )
        kardex_events.emit_ingreso(pi)
    messages.success(request, f"Se agregaron {cantidad} item{'s' if cantidad != 1 else ''} a {prenda.codigo}.")
    return redirect('detalle_prenda', id=prenda.id)


@login_required
def lista_insumos(request):
    q            = request.GET.get('q', '').strip()
    tipo_material= request.GET.get('tipo_material', '').strip()
    estado       = request.GET.get('estado', 'ACT').strip()

    qs = Insumo.objects.all().select_related('tipo_material', 'unidad_medida').order_by('-creado')
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q)    | Q(articulo__icontains=q) |
            Q(coleccion__icontains=q) | Q(color__icontains=q)    |
            Q(codigo_referencia__icontains=q)
        )
    if tipo_material:
        qs = qs.filter(tipo_material_id=tipo_material)
    if estado:
        qs = qs.filter(estado=estado)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/insumos/lista.html', {
        'page_obj':     page_obj,
        'total':        total,
        'q':            q,
        'tipo_material':tipo_material,
        'estado':       estado,
        'tipo_material_opts': list(TipoMaterial.objects.values('id', 'nombre')),
        'estado_choices':     Insumo.ESTADO_OPCIONES,
    })


@login_required
def crear_insumo(request):
    if request.method == 'POST':
        form = InsumoForm(request.POST)
        if form.is_valid():
            insumo = form.save()
            messages.success(request, f'Insumo creado con código {insumo.codigo}.')
            return redirect('lista_insumos')
    else:
        form = InsumoForm()
    return render(request, 'misastreria/insumos/form.html', {
        'form':   form,
        'titulo': 'Nuevo Insumo',
        'unidad_medida_opts':  list(UnidadMedida.objects.values('id', 'nombre')),
        'tipo_material_opts':  list(TipoMaterial.objects.values('id', 'nombre')),
    })


@login_required
def editar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        form = InsumoForm(request.POST, instance=insumo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Insumo actualizado correctamente.')
            return redirect('lista_insumos')
    else:
        form = InsumoForm(instance=insumo)
    return render(request, 'misastreria/insumos/form.html', {
        'form':   form,
        'titulo': 'Editar Insumo',
        'insumo': insumo,
        'unidad_medida_opts':  list(UnidadMedida.objects.values('id', 'nombre')),
        'tipo_material_opts':  list(TipoMaterial.objects.values('id', 'nombre')),
    })


@login_required
def eliminar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        insumo.delete()
        messages.success(request, 'Insumo eliminado correctamente.')
        return redirect('lista_insumos')
    return render(request, 'misastreria/insumos/eliminar.html', {'insumo': insumo})

@login_required
def reporte_empleados(request):
    form = EmpleadoReporteForm(request.GET or None)
    
    # Inicia con un QuerySet base de Empleados
    empleados_qs = Empleado.objects.all()
    
    if form.is_valid():
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        tipo_contrato = form.cleaned_data.get('tipo_contrato')

        # Aplica filtros si los campos están presentes en el formulario
        if fecha_inicio and fecha_fin:
            # Filtra empleados por fecha de ingreso dentro del rango
            empleados_qs = empleados_qs.filter(fecha_ingreso__range=(fecha_inicio, fecha_fin))
        
        if tipo_contrato:
            # Filtra empleados por tipo de contrato
            empleados_qs = empleados_qs.filter(tipo_contrato=tipo_contrato)

    # Utiliza annotate para agregar el conteo de faltas y permisos directamente al QuerySet
    # 'faltas' y 'permisos' son los related_name definidos en tus modelos Falta y Permiso
    empleados_con_counts = empleados_qs.annotate(
        faltas_count=Count('faltas'),
        permisos_count=Count('permisos')
    )

    # Prepara los datos para el template
    datos = []
    for emp in empleados_con_counts:
        datos.append({
            'empleado': emp,
            'faltas': emp.faltas_count,   # Accede al conteo anotado
            'permisos': emp.permisos_count, # Accede al conteo anotado
        })

    return render(request, 'misastreria/reportes/empleados.html', {
        'form': form,
        'datos': datos
    })



@login_required
def exportar_empleados_pdf(request):
    form = EmpleadoReporteForm(request.GET or None)
    empleados = Empleado.objects.all()

    if form.is_valid():
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        tipo_contrato = form.cleaned_data.get('tipo_contrato')

        if fecha_inicio and fecha_fin:
            empleados = empleados.filter(fecha_ingreso__range=(fecha_inicio, fecha_fin))
        if tipo_contrato:
            empleados = empleados.filter(tipo_contrato=tipo_contrato)

    data = [['Empleado', 'Tipo Contrato', 'Fecha Ingreso', 'Faltas', 'Permisos']]
    for e in empleados:
        data.append([
            str(e),
            str(e.tipo_contrato) if e.tipo_contrato else '-',
            e.fecha_ingreso.strftime('%d/%m/%Y'),
            e.faltas.count(),
            e.permisos.count()
        ])

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_empleados.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Titulo', fontSize=16, alignment=1, spaceAfter=20, fontName='Helvetica-Bold'))

    elements = [
        Paragraph("SASTRERÍA CONFORT Y MÁS", styles['Titulo']),
        Paragraph("Reporte de Empleados", styles['Heading2']),
        Spacer(1, 12),
        Table(data, style=[
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10)
        ])
    ]
    doc.build(elements)
    return response

@login_required
def exportar_empleados_excel(request):
    # **Optimización:** Usar annotate para contar faltas y permisos en una sola consulta
    empleados_qs = Empleado.objects.all().annotate(
        faltas_count=Count('faltas'),
        permisos_count=Count('permisos')
    )

    form = EmpleadoReporteForm(request.GET or None)

    if form.is_valid():
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        tipo_contrato = form.cleaned_data.get('tipo_contrato')

        if fecha_inicio and fecha_fin:
            empleados_qs = empleados_qs.filter(fecha_ingreso__range=(fecha_inicio, fecha_fin))
        if tipo_contrato:
            empleados_qs = empleados_qs.filter(tipo_contrato=tipo_contrato)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Empleados"

    # Encabezado principal
    ws.merge_cells('A1:E1')
    ws['A1'] = "SASTRERÍA CONFORT Y MÁS - Reporte de Empleados"
    ws['A1'].font = Font(size=14, bold=True)
    ws['A1'].alignment = Alignment(horizontal='center')

    # Encabezados de la tabla de datos
    headers = ['Empleado', 'Tipo Contrato', 'Fecha Ingreso', 'Faltas', 'Permisos']
    ws.append(headers)

    # Estilo para los encabezados de la tabla (fila 2)
    for col_num, header_text in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col_num)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    # Llenar la hoja con los datos de los empleados
    for e in empleados_qs: # Usamos empleados_qs (con los counts ya hechos)
        ws.append([
            str(e),
            str(e.tipo_contrato) if e.tipo_contrato else '-',
            e.fecha_ingreso.strftime('%d/%m/%Y'),
            e.faltas_count,   # <-- ¡Usamos el count ya calculado!
            e.permisos_count  # <-- ¡Usamos el count ya calculado!
        ])

    # Ajustar el ancho de las columnas
    for col in range(1, 6): # Asumiendo 5 columnas de datos
        ws.column_dimensions[get_column_letter(col)].width = 20

    # -------------------------------------------------------------------
    # ¡¡¡ESTAS LINEAS SON LAS QUE FALTABAN PARA DEVOLVER EL ARCHIVO!!!
    # -------------------------------------------------------------------
    output = BytesIO()
    wb.save(output)
    output.seek(0) # Volver al inicio del flujo de datos

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="reporte_empleados.xlsx"'
    
    return response # <-- ¡Asegúrate de que esta línea esté presente!


# --- INICIO de funciones de Reporte de CLIENTES (ACTUALIZADO) ---

@login_required
def reporte_clientes(request):
    form = ClienteReporteForm(request.GET or None)
    
    # Inicia con todos los clientes
    clientes_filtrados = Cliente.objects.all()
    
    fecha_inicio = None
    fecha_fin = None
    tipo_operacion = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        tipo_operacion = form.cleaned_data.get('tipo_operacion')

        if fecha_inicio and fecha_fin:
            clientes_filtrados = clientes_filtrados.filter(fecha_registro__range=[fecha_inicio, fecha_fin])
        
        # Si hay un tipo de operación seleccionado, filtra los clientes que tienen al menos 1 de esa operación
        # Esto se hace después de obtener los registros para cada cliente
        
    datos = []
    for cliente in clientes_filtrados:
        registros = {
            'ventas': cliente.ventas.count(),
            'reparaciones': cliente.reparaciones.count(),
            'confecciones': cliente.confeccion_set.count(),
            'alquileres': cliente.alquileres.count(),
        }

        # Aplica el filtro por tipo de operación aquí, después de contar
        if tipo_operacion and registros.get(tipo_operacion, 0) == 0:
            continue # Salta este cliente si no tiene operaciones del tipo seleccionado

        datos.append({
            'cliente': cliente,
            'operaciones': registros
        })

    # Exportación
    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_clientes_pdf(request, datos, form.cleaned_data if form.is_valid() else {})
    elif export_format == 'excel':
        return exportar_clientes_excel(request, datos, form.cleaned_data if form.is_valid() else {})

    return render(request, 'misastreria/reportes/clientes.html', {
        'form': form,
        'datos': datos,
        'selected_fecha_inicio': fecha_inicio,
        'selected_fecha_fin': fecha_fin,
        'selected_tipo_operacion': tipo_operacion,
    })

@login_required
def exportar_clientes_pdf(request, datos, filtros_aplicados):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    # Estilos personalizados (asegúrate de que DejaVuSans esté registrado)
    styles.add(ParagraphStyle(name='CompanyTitle',
                              fontSize=20, leading=24, alignment=TA_CENTER, fontName='DejaVuSans', textColor=colors.HexColor('#1e3a8a')))
    styles.add(ParagraphStyle(name='ReportTitle',
                              fontSize=16, leading=20, alignment=TA_CENTER, fontName='DejaVuSans', textColor=colors.HexColor('#2563eb')))
    styles.add(ParagraphStyle(name='SubTitle',
                              fontSize=10, leading=12, alignment=TA_CENTER, fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='TableHeader',
                              fontSize=9, fontName='DejaVuSans', alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='TableContent',
                              fontSize=7, fontName='DejaVuSans', alignment=TA_CENTER)) # Alineación central para los datos de la tabla

    elements = []

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(Paragraph("REPORTE DE CLIENTES", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    # Filtros aplicados en el PDF
    filter_text_lines = []
    if filtros_aplicados.get('fecha_inicio') and filtros_aplicados.get('fecha_fin'):
        filter_text_lines.append(f"Fecha de Registro: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')} al {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}.")
    elif filtros_aplicados.get('fecha_inicio'):
        filter_text_lines.append(f"Fecha de Registro Desde: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')}.")
    elif filtros_aplicados.get('fecha_fin'):
        filter_text_lines.append(f"Fecha de Registro Hasta: {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}.")
    
    tipo_operacion_display = dict(ClienteReporteForm.TIPO_OPERACION_CHOICES).get(filtros_aplicados.get('tipo_operacion', ''), "Todas las Operaciones")
    filter_text_lines.append(f"Tipo de Operación: {tipo_operacion_display}.")

    if filter_text_lines:
        for line in filter_text_lines:
            elements.append(Paragraph(line, styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))


    # Datos de la tabla
    table_data = [[
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Fecha Registro', styles['TableHeader']),
        Paragraph('Ventas', styles['TableHeader']),
        Paragraph('Reparaciones', styles['TableHeader']),
        Paragraph('Confecciones', styles['TableHeader']),
        Paragraph('Alquileres', styles['TableHeader'])
    ]]

    for item in datos:
        table_data.append([
            Paragraph(str(item['cliente']), styles['TableContent']),
            Paragraph(item['cliente'].fecha_registro.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(str(item['operaciones']['ventas']), styles['TableContent']),
            Paragraph(str(item['operaciones']['reparaciones']), styles['TableContent']),
            Paragraph(str(item['operaciones']['confecciones']), styles['TableContent']),
            Paragraph(str(item['operaciones']['alquileres']), styles['TableContent']),
        ])

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ])

    table = Table(table_data, colWidths=[
        2.0*inch, # Cliente
        1.0*inch, # Fecha Registro
        0.8*inch, # Ventas
        1.0*inch, # Reparaciones
        1.0*inch, # Confecciones
        0.8*inch  # Alquileres
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_clientes.pdf"'
    return response

@login_required
def exportar_clientes_excel(request, datos, filtros_aplicados):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Clientes"

    # Estilos de Excel
    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    
    content_font = Font(name='Calibri', size=10)
    
    # Títulos principales
    ws.merge_cells('A1:F1') # 6 columnas
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:F2') # 6 columnas
    ws['A2'] = "REPORTE DE CLIENTES"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")

    # Filtros aplicados
    filter_row_start = 4
    filter_col_span = 6
    filter_text_lines = []
    if filtros_aplicados.get('fecha_inicio') and filtros_aplicados.get('fecha_fin'):
        filter_text_lines.append(f"Fecha de Registro: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')} al {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}.")
    elif filtros_aplicados.get('fecha_inicio'):
        filter_text_lines.append(f"Fecha de Registro Desde: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')}.")
    elif filtros_aplicados.get('fecha_fin'):
        filter_text_lines.append(f"Fecha de Registro Hasta: {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}.")
    
    tipo_operacion_display = dict(ClienteReporteForm.TIPO_OPERACION_CHOICES).get(filtros_aplicados.get('tipo_operacion', ''), "Todas las Operaciones")
    filter_text_lines.append(f"Tipo de Operación: {tipo_operacion_display}.")

    for i, line in enumerate(filter_text_lines):
        ws.merge_cells(start_row=filter_row_start + i, start_column=1, end_row=filter_row_start + i, end_column=filter_col_span)
        ws[f'A{filter_row_start + i}'] = line
        ws[f'A{filter_row_start + i}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row_start + i}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    header_row = filter_row_start + len(filter_text_lines) + 1


    # Cabecera de la tabla principal
    headers = ['Cliente', 'Fecha Registro', 'Ventas', 'Reparaciones', 'Confecciones', 'Alquileres']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    # Datos de la tabla principal
    for item in datos:
        row_data = [
            str(item['cliente']),
            item['cliente'].fecha_registro.strftime('%d/%m/%Y'),
            item['operaciones']['ventas'],
            item['operaciones']['reparaciones'],
            item['operaciones']['confecciones'],
            item['operaciones']['alquileres'],
        ]
        ws.append(row_data)
        for col_num, cell in enumerate(ws[ws.max_row]):
            cell.font = content_font
            cell.border = full_border
            if col_num in [2, 3, 4, 5]: # Columnas de conteo
                cell.number_format = '#,##0'
            else:
                cell.alignment = Alignment(horizontal="center")

    # Autoajustar ancho de columnas
    for col_idx in range(1, ws.max_column + 1):
        max_length = 0
        column = get_column_letter(col_idx)
        for cell in ws[column]:
            try:
                if cell.value is not None:
                    cell_len = len(str(cell.value))
                    if cell_len > max_length:
                        max_length = cell_len
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        if adjusted_width > 50: adjusted_width = 50
        ws.column_dimensions[column].width = adjusted_width


    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_clientes.xlsx"'
    wb.save(response)
    return response
# --- FIN de funciones de Reporte de CLIENTES ---

# ⚠️ Importante: Registra una fuente Unicode para ReportLab para que pueda mostrar caracteres especiales (ñ, tildes, etc.)
# Asegúrate de tener el archivo 'DejaVuSans.ttf' en alguna ruta accesible (ej. en tu carpeta de static files o en la raíz de tu app)
pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))


@login_required
def reporte_reparaciones(request):
    form = ReparacionReporteForm(request.GET or None)
    
    reparaciones_filtradas = Reparacion.objects.all().select_related('cliente', 'empleado').order_by('-fecha_entrega')
    
    selected_fecha_inicio = None
    selected_fecha_fin = None
    selected_cliente = None
    selected_empleado = None
    selected_tipo_prenda = None
    selected_estado = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        cliente = form.cleaned_data.get('cliente')
        empleado = form.cleaned_data.get('empleado')
        tipo_prenda = form.cleaned_data.get('tipo_prenda')
        estado = form.cleaned_data.get('estado')

        if fecha_inicio:
            reparaciones_filtradas = reparaciones_filtradas.filter(fecha_entrega__gte=fecha_inicio)
            selected_fecha_inicio = fecha_inicio
        if fecha_fin:
            reparaciones_filtradas = reparaciones_filtradas.filter(fecha_entrega__lte=fecha_fin)
            selected_fecha_fin = fecha_fin
        if cliente:
            reparaciones_filtradas = reparaciones_filtradas.filter(cliente=cliente)
            selected_cliente = cliente
        if empleado:
            reparaciones_filtradas = reparaciones_filtradas.filter(empleado=empleado)
            selected_empleado = empleado
        if tipo_prenda:
            reparaciones_filtradas = reparaciones_filtradas.filter(tipo_prenda=tipo_prenda)
            selected_tipo_prenda = tipo_prenda
        if estado:
            reparaciones_filtradas = reparaciones_filtradas.filter(estado=estado)
            selected_estado = estado
    
    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reparaciones_pdf(request, reparaciones_filtradas, form.cleaned_data if form.is_valid() else {})
    elif export_format == 'excel':
        return exportar_reparaciones_excel(request, reparaciones_filtradas, form.cleaned_data if form.is_valid() else {})

    kpis = _kpis_reparaciones(reparaciones_filtradas)

    context = {
        'form': form,
        'reparaciones': reparaciones_filtradas,
        'selected_fecha_inicio': selected_fecha_inicio,
        'selected_fecha_fin': selected_fecha_fin,
        'selected_cliente': selected_cliente,
        'selected_empleado': selected_empleado,
        'selected_tipo_prenda': selected_tipo_prenda,
        'selected_estado': selected_estado,
        'kpis': kpis,
    }
    return render(request, 'misastreria/reportes/reparaciones.html', context)


@login_required
def exportar_reparaciones_pdf(request, reparaciones_data, filtros_aplicados):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    # Estilos personalizados (todos usando 'DejaVuSans' normal)
    styles.add(ParagraphStyle(name='CompanyTitle',
                              fontSize=20, leading=24, alignment=TA_CENTER, fontName='DejaVuSans', textColor=colors.HexColor('#1e3a8a'))) # Ahora usa DejaVuSans
    styles.add(ParagraphStyle(name='ReportTitle',
                              fontSize=16, leading=20, alignment=TA_CENTER, fontName='DejaVuSans', textColor=colors.HexColor('#2563eb'))) # Ahora usa DejaVuSans
    styles.add(ParagraphStyle(name='SubTitle',
                              fontSize=10, leading=12, alignment=TA_CENTER, fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='TableHeader',
                              fontSize=9, fontName='DejaVuSans', alignment=TA_CENTER)) # Ahora usa DejaVuSans
    styles.add(ParagraphStyle(name='TableContent',
                              fontSize=8, fontName='DejaVuSans', alignment=TA_CENTER))

    elements = []

    # Títulos del reporte
    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("REPORTE DE REPARACIONES", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    # Información de filtros aplicados
    filter_text_lines = []
    if filtros_aplicados:
        if filtros_aplicados.get('fecha_inicio') and filtros_aplicados.get('fecha_fin'):
            filter_text_lines.append(f"Fecha de Entrega: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')} al {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}.")
        elif filtros_aplicados.get('fecha_inicio'):
            filter_text_lines.append(f"Fecha de Entrega Desde: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')}.")
        elif filtros_aplicados.get('fecha_fin'):
            filter_text_lines.append(f"Fecha de Entrega Hasta: {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}.")
        
        if filtros_aplicados.get('cliente'):
            filter_text_lines.append(f"Cliente: {filtros_aplicados['cliente'].__str__()}." )
        if filtros_aplicados.get('empleado'):
            filter_text_lines.append(f"Empleado: {filtros_aplicados['empleado'].__str__()}." )
        if filtros_aplicados.get('tipo_prenda'):
            filter_text_lines.append(f"Tipo de Prenda: {filtros_aplicados['tipo_prenda']}.")
        if filtros_aplicados.get('estado'):
            estado_display = dict(Reparacion.ESTADO_CHOICES).get(filtros_aplicados['estado'], filtros_aplicados['estado'])
            filter_text_lines.append(f"Estado: {estado_display}.")

    if filter_text_lines:
        for line in filter_text_lines:
            elements.append(Paragraph(line, styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    # Datos de la tabla
    table_data = [[
        Paragraph('Código', styles['TableHeader']),
        Paragraph('Fecha Entrega', styles['TableHeader']),
        Paragraph('Prendas', styles['TableHeader']),
        Paragraph('Total (BOB)', styles['TableHeader']),
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Empleado', styles['TableHeader']),
        Paragraph('Estado', styles['TableHeader'])
    ]]

    for rep in reparaciones_data:
        prendas_txt = ', '.join(str(it.tipo_prenda) for it in rep.items.all()) or '-'
        table_data.append([
            Paragraph(str(rep.codigo), styles['TableContent']),
            Paragraph(rep.fecha_entrega.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(prendas_txt, styles['TableContent']),
            Paragraph(f"{rep.total:.2f}", styles['TableContent']),
            Paragraph(rep.cliente.__str__() if rep.cliente else "N/A", styles['TableContent']),
            Paragraph(rep.empleado.__str__() if rep.empleado else "N/A", styles['TableContent']),
            Paragraph(rep.get_estado_display(), styles['TableContent']),
        ])

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'), # Asegura que la cabecera de tabla use DejaVuSans
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ])

    col_widths = [0.8*inch, 1*inch, 1.8*inch, 0.9*inch, 1.5*inch, 1.5*inch, 0.8*inch]
    table = Table(table_data, colWidths=col_widths)
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_reparaciones.pdf"'
    return response


@login_required
def exportar_reparaciones_excel(request, reparaciones_data, filtros_aplicados):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Reparaciones"

    # Estilos de Excel (estos estilos son para Excel y no están afectados por la fuente de ReportLab)
    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    
    content_font = Font(name='Calibri', size=10)
    
    # Títulos principales
    ws.merge_cells('A1:H1')
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:H2')
    ws['A2'] = "REPORTE DE REPARACIONES"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")

    # Filtros aplicados
    filter_row_start = 4
    filter_col_span = 8
    current_filter_row = filter_row_start
    
    if filtros_aplicados:
        if filtros_aplicados.get('fecha_inicio') and filtros_aplicados.get('fecha_fin'):
            filter_text = f"Fecha de Entrega: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')} al {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1
        elif filtros_aplicados.get('fecha_inicio'):
            filter_text = f"Fecha de Entrega Desde: {filtros_aplicados['fecha_inicio'].strftime('%d/%m/%Y')}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1
        elif filtros_aplicados.get('fecha_fin'):
            filter_text = f"Fecha de Entrega Hasta: {filtros_aplicados['fecha_fin'].strftime('%d/%m/%Y')}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1
        
        if filtros_aplicados.get('cliente'):
            filter_text = f"Cliente: {filtros_aplicados['cliente'].__str__()}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1
        if filtros_aplicados.get('empleado'):
            filter_text = f"Empleado: {filtros_aplicados['empleado'].__str__()}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1
        if filtros_aplicados.get('tipo_prenda'):
            filter_text = f"Tipo de Prenda: {filtros_aplicados['tipo_prenda']}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1
        if filtros_aplicados.get('estado'):
            estado_display = dict(Reparacion.ESTADO_CHOICES).get(filtros_aplicados['estado'], filtros_aplicados['estado'])
            filter_text = f"Estado: {estado_display}."
            ws.merge_cells(start_row=current_filter_row, start_column=1, end_row=current_filter_row, end_column=filter_col_span)
            ws[f'A{current_filter_row}'] = filter_text
            ws[f'A{current_filter_row}'].font = Font(name='Calibri', size=10)
            ws[f'A{current_filter_row}'].alignment = Alignment(horizontal="center")
            current_filter_row += 1

    header_row = current_filter_row + 1

    # Cabecera de la tabla principal
    headers = ['Código', 'Fecha Entrega', 'Prendas', 'Total (BOB)', 'Cliente', 'Empleado', 'Estado']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    # Datos de la tabla principal
    for rep in reparaciones_data:
        prendas_txt = ', '.join(str(it.tipo_prenda) for it in rep.items.all()) or '-'
        row_data = [
            str(rep.codigo),
            rep.fecha_entrega.strftime('%d/%m/%Y'),
            prendas_txt,
            float(rep.total),
            rep.cliente.__str__() if rep.cliente else "N/A",
            rep.empleado.__str__() if rep.empleado else "N/A",
            rep.get_estado_display(),
        ]
        ws.append(row_data)
        for col_num, cell in enumerate(ws[ws.max_row]):
            cell.font = content_font
            cell.border = full_border
            if col_num == 4:
                cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal="center")

    # Autoajustar ancho de columnas
    for col_idx in range(1, ws.max_column + 1):
        max_length = 0
        column = get_column_letter(col_idx)
        for cell in ws[column]:
            try:
                if cell.value is not None:
                    cell_len = len(str(cell.value))
                    if cell_len > max_length:
                        max_length = cell_len
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        if adjusted_width > 50: adjusted_width = 50
        ws.column_dimensions[column].width = adjusted_width

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_reparaciones.xlsx"'
    wb.save(response)
    return response
@login_required
def reporte_ventas(request):
    ventas = Venta.objects.prefetch_related('items__prenda_item__prenda').all()
    clientes = Cliente.objects.all()
    empleados = Empleado.objects.all()

    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_id = request.GET.get('cliente')
    empleado_id = request.GET.get('empleado')

    if fecha_desde:
        ventas = ventas.filter(fecha_venta__gte=fecha_desde)
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        ventas = ventas.filter(fecha_venta__lt=fecha_hasta_dt)
    if cliente_id and cliente_id != '':
        ventas = ventas.filter(cliente__id=cliente_id)
    if empleado_id and empleado_id != '':
        ventas = ventas.filter(empleado__id=empleado_id)

    ventas = ventas.order_by('fecha_venta')

    total_ventas = ventas.aggregate(Sum('total'))['total__sum'] or 0.00

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_ventas_pdf(request, ventas, fecha_desde, fecha_hasta, total_ventas)
    elif export_format == 'excel':
        return exportar_reporte_ventas_excel(request, ventas, fecha_desde, fecha_hasta, total_ventas)

    kpis = _kpis_ventas(ventas)

    context = {
        'ventas': ventas,
        'clientes': clientes,
        'empleados': empleados,
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_cliente': cliente_id,
        'selected_empleado': empleado_id,
        'total_ventas': total_ventas,
        'kpis': kpis,
    }
    return render(request, 'misastreria/reportes/reporte_ventas.html', context)


def exportar_reporte_ventas_pdf(request, ventas, fecha_desde, fecha_hasta, total_ventas):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    # Definir estilos personalizados para el PDF
    styles.add(ParagraphStyle(name='CompanyTitle',
                              fontSize=20,
                              leading=24,
                              alignment=1, # TA_CENTER
                              fontName='DejaVuSans', # <-- CAMBIADO a 'DejaVuSans'
                              textColor=colors.HexColor('#1e3a8a')))

    styles.add(ParagraphStyle(name='ReportTitle',
                              fontSize=16,
                              leading=20,
                              alignment=1, # TA_CENTER
                              fontName='DejaVuSans', # <-- CAMBIADO a 'DejaVuSans'
                              textColor=colors.HexColor('#2563eb')))

    styles.add(ParagraphStyle(name='SubTitle',
                              fontSize=10,
                              leading=12,
                              alignment=1, # TA_CENTER
                              fontName='DejaVuSans')) # <-- Ya era 'DejaVuSans'
    styles.add(ParagraphStyle(name='TableHeader',
                              fontSize=9,
                              fontName='DejaVuSans', # <-- CAMBIADO a 'DejaVuSans'
                              alignment=1))
    styles.add(ParagraphStyle(name='TableContent',
                              fontSize=7,
                              fontName='DejaVuSans',
                              alignment=0)) # <-- Ya era 'DejaVuSans'
    styles.add(ParagraphStyle(name='TotalStyle',
                              fontSize=10,
                              fontName='DejaVuSans', # <-- CAMBIADO a 'DejaVuSans'
                              alignment=2))

    elements = []

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(Paragraph("REPORTE DE VENTAS", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    
    if request.GET.get('cliente') and request.GET.get('cliente') != '':
        try:
            cliente_obj = Cliente.objects.get(id=request.GET.get('cliente'))
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno} {cliente_obj.apellido_materno}. "
        except ObjectDoesNotExist:
            filter_text += f"Cliente (ID {request.GET.get('cliente')}) no encontrado. "
    
    if request.GET.get('empleado') and request.GET.get('empleado') != '':
        try:
            empleado_obj = Empleado.objects.get(id=request.GET.get('empleado'))
            filter_text += f"Vendedor: {empleado_obj.nombres} {empleado_obj.apellido_paterno}. "
        except ObjectDoesNotExist:
            filter_text += f"Vendedor (ID {request.GET.get('empleado')}) no encontrado. "
    
    if filter_text:
        elements.append(Paragraph(filter_text.strip(), styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    data = [[
        Paragraph('Código', styles['TableHeader']),
        Paragraph('Fecha', styles['TableHeader']),
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Vendedor', styles['TableHeader']),
        Paragraph('Prenda', styles['TableHeader']),
        Paragraph('Cant.', styles['TableHeader']),
        Paragraph('P. Unit (Bs.)', styles['TableHeader']),
        Paragraph('Total (Bs.)', styles['TableHeader'])
    ]]

    for venta in ventas:
        cliente_full_name = f"{venta.cliente.nombres} {venta.cliente.apellido_paterno}".strip() if venta.cliente else "N/A"
        empleado_full_name = f"{venta.empleado.nombres} {venta.empleado.apellido_paterno}".strip() if venta.empleado else "N/A"
        items = list(venta.items.select_related('prenda_item__prenda').all())
        if items:
            for idx, item in enumerate(items):
                data.append([
                    Paragraph(venta.codigo if idx == 0 else '', styles['TableContent']),
                    Paragraph(venta.fecha_venta.strftime('%d/%m/%Y') if idx == 0 else '', styles['TableContent']),
                    Paragraph(cliente_full_name if idx == 0 else '', styles['TableContent']),
                    Paragraph(empleado_full_name if idx == 0 else '', styles['TableContent']),
                    Paragraph(str(item.prenda_item.prenda) if item.prenda_item else '—', styles['TableContent']),
                    Paragraph('1', styles['TableContent']),
                    Paragraph(f"{item.precio_unitario:.2f}", styles['TableContent']),
                    Paragraph(f"{item.subtotal:.2f}" if idx == len(items) - 1 else '', styles['TableContent']),
                ])
        else:
            data.append([
                Paragraph(venta.codigo, styles['TableContent']),
                Paragraph(venta.fecha_venta.strftime('%d/%m/%Y'), styles['TableContent']),
                Paragraph(cliente_full_name, styles['TableContent']),
                Paragraph(empleado_full_name, styles['TableContent']),
                Paragraph('—', styles['TableContent']),
                Paragraph('', styles['TableContent']),
                Paragraph('', styles['TableContent']),
                Paragraph(f"{venta.total:.2f}", styles['TableContent']),
            ])

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'), # <-- CAMBIADO a 'DejaVuSans' para el encabezado de la tabla
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ])

    table = Table(data, colWidths=[
        0.8*inch, # Código Venta
        0.8*inch, # Fecha
        1.2*inch, # Cliente
        1.2*inch, # Vendedor
        1.6*inch, # Nombre del Artículo
        0.5*inch, # Cant.
        0.9*inch, # P. Unit
        0.9*inch  # Total
    ])
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph(f"Total de Ventas Filtradas: Bs. {total_ventas:.2f}", styles['TotalStyle']))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_ventas.pdf"'
    return response


def exportar_reporte_ventas_excel(request, ventas, fecha_desde, fecha_hasta, total_ventas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Ventas"

    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    
    content_font = Font(name='Calibri', size=10)
    total_font = Font(name='Calibri', bold=True, size=12)
    total_alignment = Alignment(horizontal="right")

    ws.merge_cells('A1:H1')
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:H2')
    ws['A2'] = "REPORTE DE VENTAS"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")


    filter_row = 4
    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    
    if request.GET.get('cliente') and request.GET.get('cliente') != '':
        try:
            cliente_obj = Cliente.objects.get(id=request.GET.get('cliente'))
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno} {cliente_obj.apellido_materno}. "
        except ObjectDoesNotExist:
            filter_text += f"Cliente (ID {request.GET.get('cliente')}) no encontrado. "
    
    if request.GET.get('empleado') and request.GET.get('empleado') != '':
        try:
            empleado_obj = Empleado.objects.get(id=request.GET.get('empleado'))
            filter_text += f"Vendedor: {empleado_obj.nombres} {empleado_obj.apellido_paterno}. "
        except ObjectDoesNotExist:
            filter_text += f"Vendedor (ID {request.GET.get('empleado')}) no encontrado. "
    
    if filter_text:
        ws.merge_cells(f'A{filter_row}:H{filter_row}')
        ws[f'A{filter_row}'] = filter_text.strip()
        ws[f'A{filter_row}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        filter_row += 1

    header_row = filter_row + 1

    headers = ['Código', 'Fecha', 'Cliente', 'Vendedor', 'Prenda', 'Cantidad', 'P. Unitario (Bs.)', 'Total (Bs.)']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    for venta in ventas:
        cliente_full_name = f"{venta.cliente.nombres} {venta.cliente.apellido_paterno}".strip() if venta.cliente else "N/A"
        empleado_full_name = f"{venta.empleado.nombres} {venta.empleado.apellido_paterno}".strip() if venta.empleado else "N/A"
        items = list(venta.items.select_related('prenda_item__prenda').all())
        rows_to_write = items if items else [None]
        for idx, item in enumerate(rows_to_write):
            row_data = [
                venta.codigo if idx == 0 else '',
                venta.fecha_venta.strftime('%d/%m/%Y') if idx == 0 else '',
                cliente_full_name if idx == 0 else '',
                empleado_full_name if idx == 0 else '',
                str(item.prenda_item.prenda) if item and item.prenda_item else '—',
                1 if item else '',
                float(item.precio_unitario) if item else '',
                float(item.subtotal) if item else float(venta.total),
            ]
            ws.append(row_data)
            for col_num, cell in enumerate(ws[ws.max_row]):
                cell.font = content_font
                cell.border = full_border
                if col_num in [6, 7]:
                    cell.number_format = '#,##0.00'
                else:
                    cell.alignment = Alignment(horizontal="center")


    last_data_row = ws.max_row
    ws.merge_cells(start_row=last_data_row + 2, start_column=1, end_row=last_data_row + 2, end_column=7)
    total_label_cell = ws.cell(row=last_data_row + 2, column=1)
    total_label_cell.value = "Total de Ventas Filtradas: Bs."
    total_label_cell.font = total_font
    total_label_cell.alignment = total_alignment

    total_value_cell = ws.cell(row=last_data_row + 2, column=8)
    total_value_cell.value = total_ventas
    total_value_cell.font = total_font
    total_value_cell.alignment = Alignment(horizontal="right")
    total_value_cell.number_format = '#,##0.00'

    for col in ws.columns:
        max_length = 0
        for cell in col[header_row-1:]:
            try:
                if cell.value is not None:
                    cell_len = len(str(cell.value))
                    if cell_len > max_length:
                        max_length = cell_len
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        if adjusted_width > 50: adjusted_width = 50
        ws.column_dimensions[get_column_letter(col[0].column)].width = adjusted_width


    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_ventas.xlsx"'
    wb.save(response)
    return response

@login_required
def reporte_articulos(request):
    # Obtén todos los artículos o aplica filtros si los tienes
    articulos = PrendaInventario.objects.all().order_by('nombre')

    context = {
        'articulos': articulos,
    }
    return render(request, 'misastreria/reportes/articulos.html', context)

@login_required
def reporte_confecciones(request):
    confecciones = Confeccion.objects.all()
    clientes = Cliente.objects.all()
    empleados = Empleado.objects.all()
    tipo_prenda_opts = list(TipoPrenda.objects.values('id', 'nombre'))
    estado_choices = Confeccion.ESTADO_CHOICES

    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_id = request.GET.get('cliente')
    empleado_id = request.GET.get('empleado')
    selected_tipo_prenda = request.GET.get('tipo_prenda') # Cambiado de 'articulo' a 'tipo_prenda'
    selected_estado = request.GET.get('estado') # Nuevo filtro de estado

    # Aplicar filtros
    if fecha_desde:
        confecciones = confecciones.filter(fecha_inicio__gte=fecha_desde) 
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        confecciones = confecciones.filter(fecha_inicio__lt=fecha_hasta_dt)
    if cliente_id and cliente_id != '':
        confecciones = confecciones.filter(cliente__id=cliente_id)
    if empleado_id and empleado_id != '':
        confecciones = confecciones.filter(empleado__id=empleado_id)
    
    if selected_tipo_prenda and selected_tipo_prenda != '':
        confecciones = confecciones.filter(items__tipo_prenda_id=selected_tipo_prenda).distinct()
    
    if selected_estado and selected_estado != '':
        confecciones = confecciones.filter(estado=selected_estado)

    confecciones = confecciones.order_by('fecha_inicio') 

    total_confecciones = confecciones.aggregate(Sum('precio'))['precio__sum'] or 0.00 # Suma 'precio' en lugar de 'precio_total'

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_confecciones_pdf(request, confecciones, fecha_desde, fecha_hasta, total_confecciones)
    elif export_format == 'excel':
        return exportar_reporte_confecciones_excel(request, confecciones, fecha_desde, fecha_hasta, total_confecciones)

    kpis = _kpis_confecciones(confecciones)

    context = {
        'confecciones': confecciones,
        'clientes': clientes,
        'empleados': empleados,
        'tipo_prenda_opts': tipo_prenda_opts,
        'estado_choices': estado_choices, # Pasa las opciones de estado
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_cliente': cliente_id,
        'selected_empleado': empleado_id,
        'selected_tipo_prenda': selected_tipo_prenda, # Cambiado a tipo_prenda
        'selected_estado': selected_estado, # Nuevo para el estado
        'total_confecciones': total_confecciones,
        'kpis': kpis,
    }
    return render(request, 'misastreria/reportes/reporte_confecciones.html', context)


def exportar_reporte_confecciones_pdf(request, confecciones, fecha_desde, fecha_hasta, total_confecciones):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name='CompanyTitle',
                              fontSize=20,
                              leading=24,
                              alignment=1,
                              fontName='DejaVuSans',
                              textColor=colors.HexColor('#1e3a8a')))

    styles.add(ParagraphStyle(name='ReportTitle',
                              fontSize=16,
                              leading=20,
                              alignment=1,
                              fontName='DejaVuSans',
                              textColor=colors.HexColor('#2563eb')))

    styles.add(ParagraphStyle(name='SubTitle',
                              fontSize=10,
                              leading=12,
                              alignment=1,
                              fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='TableHeader',
                              fontSize=9,
                              fontName='DejaVuSans',
                              alignment=1))
    styles.add(ParagraphStyle(name='TableContent',
                              fontSize=7,
                              fontName='DejaVuSans',
                              alignment=0))
    styles.add(ParagraphStyle(name='TotalStyle',
                              fontSize=10,
                              fontName='DejaVuSans',
                              alignment=2))

    elements = []

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(Paragraph("REPORTE DE CONFECCIONES", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    
    if request.GET.get('cliente') and request.GET.get('cliente') != '':
        try:
            cliente_obj = Cliente.objects.get(id=request.GET.get('cliente'))
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno} {cliente_obj.apellido_materno}. "
        except ObjectDoesNotExist:
            filter_text += f"Cliente (ID {request.GET.get('cliente')}) no encontrado. "
    
    if request.GET.get('empleado') and request.GET.get('empleado') != '':
        try:
            empleado_obj = Empleado.objects.get(id=request.GET.get('empleado'))
            filter_text += f"Encargado: {empleado_obj.nombres} {empleado_obj.apellido_paterno}. "
        except ObjectDoesNotExist:
            filter_text += f"Encargado (ID {request.GET.get('empleado')}) no encontrado. "
    
    selected_tipo_prenda = request.GET.get('tipo_prenda')
    if selected_tipo_prenda and selected_tipo_prenda != '':
        tp_obj = TipoPrenda.objects.filter(pk=selected_tipo_prenda).first()
        filter_text += f"Tipo de Prenda: {tp_obj.nombre if tp_obj else selected_tipo_prenda}. "
    else:
        filter_text += "Tipo de Prenda: Todas las Prendas. "

    selected_estado = request.GET.get('estado') # Nuevo filtro de estado
    if selected_estado and selected_estado != '':
        estado_display = dict(Confeccion.ESTADO_CHOICES).get(selected_estado, selected_estado)
        filter_text += f"Estado: {estado_display}. "
    else:
        filter_text += "Estado: Todos los Estados. "


    if filter_text:
        elements.append(Paragraph(filter_text.strip(), styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    data = [[
        Paragraph('Código Conf.', styles['TableHeader']),
        Paragraph('Fecha Inicio', styles['TableHeader']), # Cambiado a Fecha Inicio
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Encargado', styles['TableHeader']),
        Paragraph('Tipo de Prenda', styles['TableHeader']), # Cambiado a Tipo de Prenda
        Paragraph('Estado', styles['TableHeader']), # Nuevo encabezado
        Paragraph('Total (Bs.)', styles['TableHeader']) 
    ]]

    for confeccion in confecciones:
        cliente_full_name = f"{confeccion.cliente.nombres} {confeccion.cliente.apellido_paterno} {confeccion.cliente.apellido_materno}".strip() if confeccion.cliente else "N/A"
        empleado_full_name = f"{confeccion.empleado.nombres} {confeccion.empleado.apellido_paterno}".strip() if hasattr(confeccion, 'empleado') and confeccion.empleado else "N/A"
        
        row_data = [
            Paragraph(confeccion.codigo, styles['TableContent']),
            Paragraph(confeccion.fecha_inicio.strftime('%d/%m/%Y'), styles['TableContent']), # Usar fecha_inicio
            Paragraph(cliente_full_name, styles['TableContent']),
            Paragraph(empleado_full_name, styles['TableContent']),
            Paragraph(confeccion.tipos_prenda_display or '—', styles['TableContent']),
            Paragraph(confeccion.get_estado_display(), styles['TableContent']),
            Paragraph(f"{confeccion.precio:.2f}", styles['TableContent']) # Usar precio
        ]
        
        data.append(row_data)

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ])

    table = Table(data, colWidths=[
        0.8*inch, # Código Conf.
        0.9*inch, # Fecha Inicio
        1.2*inch, # Cliente
        1.2*inch, # Encargado
        1.2*inch, # Tipo de Prenda
        0.8*inch, # Estado
        0.8*inch  # Total
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph(f"Total de Confecciones Filtradas: Bs. {total_confecciones:.2f}", styles['TotalStyle']))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_confecciones.pdf"'
    return response


def exportar_reporte_confecciones_excel(request, confecciones, fecha_desde, fecha_hasta, total_confecciones):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Confecciones"

    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    
    content_font = Font(name='Calibri', size=10)
    total_font = Font(name='Calibri', bold=True, size=12)
    total_alignment = Alignment(horizontal="right")

    ws.merge_cells('A1:G1') # Ajusta el rango por el número de columnas (7 columnas)
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:G2') # Ajusta el rango por el número de columnas (7 columnas)
    ws['A2'] = "REPORTE DE CONFECCIONES"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")


    filter_row = 4
    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    
    if request.GET.get('cliente') and request.GET.get('cliente') != '':
        try:
            cliente_obj = Cliente.objects.get(id=request.GET.get('cliente'))
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno} {cliente_obj.apellido_materno}. "
        except ObjectDoesNotExist:
            filter_text += f"Cliente (ID {request.GET.get('cliente')}) no encontrado. "
    
    if request.GET.get('empleado') and request.GET.get('empleado') != '':
        try:
            empleado_obj = Empleado.objects.get(id=request.GET.get('empleado'))
            filter_text += f"Encargado: {empleado_obj.nombres} {empleado_obj.apellido_paterno}. "
        except ObjectDoesNotExist:
            filter_text += f"Encargado (ID {request.GET.get('empleado')}) no encontrado. "
    
    selected_tipo_prenda = request.GET.get('tipo_prenda')
    if selected_tipo_prenda and selected_tipo_prenda != '':
        tp_obj = TipoPrenda.objects.filter(pk=selected_tipo_prenda).first()
        filter_text += f"Tipo de Prenda: {tp_obj.nombre if tp_obj else selected_tipo_prenda}. "
    else:
        filter_text += "Tipo de Prenda: Todas las Prendas. "

    selected_estado = request.GET.get('estado')
    if selected_estado and selected_estado != '':
        estado_display = dict(Confeccion.ESTADO_CHOICES).get(selected_estado, selected_estado)
        filter_text += f"Estado: {estado_display}. "
    else:
        filter_text += "Estado: Todos los Estados. "


    if filter_text:
        ws.merge_cells(f'A{filter_row}:G{filter_row}') # Ajusta el rango por el número de columnas (7 columnas)
        ws[f'A{filter_row}'] = filter_text.strip()
        ws[f'A{filter_row}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        filter_row += 1
    
    header_row = filter_row + 1

    headers = ['Código Conf.', 'Fecha Inicio', 'Cliente', 'Encargado', 'Tipo de Prenda', 'Estado', 'Total (Bs.)'] # Nuevos encabezados
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    for confeccion in confecciones:
        cliente_full_name = f"{confeccion.cliente.nombres} {confeccion.cliente.apellido_paterno} {confeccion.cliente.apellido_materno}".strip() if confeccion.cliente else "N/A"
        empleado_full_name = f"{confeccion.empleado.nombres} {confeccion.empleado.apellido_paterno}".strip() if hasattr(confeccion, 'empleado') and confeccion.empleado else "N/A"

        row_data = [
            confeccion.codigo,
            confeccion.fecha_inicio.strftime('%d/%m/%Y'), # Usar fecha_inicio
            cliente_full_name,
            empleado_full_name,
            confeccion.tipos_prenda_display or '—',
            confeccion.get_estado_display(),
            confeccion.precio # Usar precio
        ]
        
        ws.append(row_data)
        for col_num, cell in enumerate(ws[ws.max_row]):
            cell.font = content_font
            cell.border = full_border
            if col_num == 6: # El Total (Bs.) ahora está en la columna 6 (índice base 0)
                cell.number_format = '#,##0.00'
            else:
                cell.alignment = Alignment(horizontal="center")


    last_data_row = ws.max_row
    ws.merge_cells(start_row=last_data_row + 2, start_column=1, end_row=last_data_row + 2, end_column=6) # Ajusta el colspan (hasta la columna 6, dejando la 7 para el total)
    total_label_cell = ws.cell(row=last_data_row + 2, column=1)
    total_label_cell.value = "Total de Confecciones Filtradas: Bs."
    total_label_cell.font = total_font
    total_label_cell.alignment = total_alignment

    total_value_cell = ws.cell(row=last_data_row + 2, column=7) # El Total (Bs.) ahora está en la columna 7
    total_value_cell.value = total_confecciones
    total_value_cell.font = total_font
    total_value_cell.alignment = Alignment(horizontal="right")
    total_value_cell.number_format = '#,##0.00'

    for col in ws.columns:
        max_length = 0
        for cell in col[header_row-1:]:
            try:
                if cell.value is not None:
                    cell_len = len(str(cell.value))
                    if cell_len > max_length:
                        max_length = cell_len
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        if adjusted_width > 50: adjusted_width = 50
        ws.column_dimensions[get_column_letter(col[0].column)].width = adjusted_width


    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_confecciones.xlsx"'
    wb.save(response)
    return response

# --- FIN de funciones de Reporte de Confecciones ---

# --- INICIO de funciones de Reporte de ALQUILERES (NUEVO) ---

@login_required
def reporte_alquileres(request):
    alquileres = Alquiler.objects.prefetch_related('items__prenda_item__prenda').all()
    clientes = Cliente.objects.all()
    articulos_inventario = PrendaInventario.objects.filter(items__tipo='alquiler').distinct().order_by('nombre')
    estado_alquiler_choices = [(n, n) for n in EstadoAlquiler.objects.values_list('nombre', flat=True)]

    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_id = request.GET.get('cliente')
    selected_articulo_id = request.GET.get('articulo')
    selected_estado = request.GET.get('estado')

    if fecha_desde:
        alquileres = alquileres.filter(fecha_alquiler__gte=fecha_desde)
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        alquileres = alquileres.filter(fecha_alquiler__lt=fecha_hasta_dt)
    if cliente_id and cliente_id != '':
        alquileres = alquileres.filter(cliente__id=cliente_id)
    if selected_articulo_id and selected_articulo_id != '':
        alquileres = alquileres.filter(items__prenda_item__prenda__id=selected_articulo_id).distinct()
    if selected_estado and selected_estado != '':
        alquileres = alquileres.filter(estado=selected_estado)

    alquileres = alquileres.order_by('fecha_alquiler')

    total_alquileres = alquileres.aggregate(Sum('total'))['total__sum'] or 0.00

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_alquileres_pdf(request, alquileres, fecha_desde, fecha_hasta, total_alquileres)
    elif export_format == 'excel':
        return exportar_reporte_alquileres_excel(request, alquileres, fecha_desde, fecha_hasta, total_alquileres)

    kpis = _kpis_alquileres(alquileres)

    context = {
        'alquileres': alquileres,
        'clientes': clientes,
        'articulos_inventario': articulos_inventario,
        'estado_alquiler_choices': estado_alquiler_choices,
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_cliente': cliente_id,
        'selected_articulo': selected_articulo_id,
        'selected_estado': selected_estado,
        'total_alquileres': total_alquileres,
        'kpis': kpis,
    }
    return render(request, 'misastreria/reportes/reporte_alquileres.html', context)


def exportar_reporte_alquileres_pdf(request, alquileres, fecha_desde, fecha_hasta, total_alquileres):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name='CompanyTitle', fontSize=20, leading=24, alignment=1,
                              fontName='DejaVuSans', textColor=colors.HexColor('#1e3a8a')))
    styles.add(ParagraphStyle(name='ReportTitle', fontSize=16, leading=20, alignment=1,
                              fontName='DejaVuSans', textColor=colors.HexColor('#2563eb')))
    styles.add(ParagraphStyle(name='SubTitle', fontSize=10, leading=12, alignment=1,
                              fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='TableHeader', fontSize=9, fontName='DejaVuSans', alignment=1))
    styles.add(ParagraphStyle(name='TableContent', fontSize=7, fontName='DejaVuSans', alignment=0))
    styles.add(ParagraphStyle(name='TotalStyle', fontSize=10, fontName='DejaVuSans', alignment=2))

    elements = []
    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("REPORTE DE ALQUILERES", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    if request.GET.get('cliente') and request.GET.get('cliente') != '':
        try:
            cliente_obj = Cliente.objects.get(id=request.GET.get('cliente'))
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno}. "
        except ObjectDoesNotExist:
            pass
    selected_articulo_id = request.GET.get('articulo')
    if selected_articulo_id and selected_articulo_id != '':
        try:
            articulo_obj = PrendaInventario.objects.get(id=selected_articulo_id)
            filter_text += f"Artículo: {articulo_obj.nombre}. "
        except ObjectDoesNotExist:
            pass
    selected_estado = request.GET.get('estado')
    if selected_estado and selected_estado != '':
        filter_text += f"Estado: {selected_estado.replace('_', ' ').title()}. "
    if filter_text:
        elements.append(Paragraph(filter_text.strip(), styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    data = [[
        Paragraph('Código', styles['TableHeader']),
        Paragraph('Fecha Alq.', styles['TableHeader']),
        Paragraph('F. Dev.', styles['TableHeader']),
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Estado', styles['TableHeader']),
        Paragraph('Prenda', styles['TableHeader']),
        Paragraph('Cant.', styles['TableHeader']),
        Paragraph('P.Unit.', styles['TableHeader']),
        Paragraph('Total (Bs.)', styles['TableHeader']),
    ]]

    for alquiler in alquileres:
        cliente_str = f"{alquiler.cliente.nombres} {alquiler.cliente.apellido_paterno}".strip() if alquiler.cliente else "N/A"
        items = list(alquiler.items.select_related('prenda_item__prenda').all())
        if items:
            for idx, item in enumerate(items):
                data.append([
                    Paragraph(alquiler.codigo if idx == 0 else '', styles['TableContent']),
                    Paragraph(alquiler.fecha_alquiler.strftime('%d/%m/%Y') if idx == 0 else '', styles['TableContent']),
                    Paragraph(alquiler.fecha_devolucion.strftime('%d/%m/%Y') if idx == 0 else '', styles['TableContent']),
                    Paragraph(cliente_str if idx == 0 else '', styles['TableContent']),
                    Paragraph(alquiler.estado_display if idx == 0 else '', styles['TableContent']),
                    Paragraph(str(item.prenda_item.prenda) if item.prenda_item else '—', styles['TableContent']),
                    Paragraph('1', styles['TableContent']),
                    Paragraph(f"{item.precio_unitario:.2f}", styles['TableContent']),
                    Paragraph(f"{alquiler.total:.2f}" if idx == len(items) - 1 else '', styles['TableContent']),
                ])
        else:
            data.append([
                Paragraph(alquiler.codigo, styles['TableContent']),
                Paragraph(alquiler.fecha_alquiler.strftime('%d/%m/%Y'), styles['TableContent']),
                Paragraph(alquiler.fecha_devolucion.strftime('%d/%m/%Y'), styles['TableContent']),
                Paragraph(cliente_str, styles['TableContent']),
                Paragraph(alquiler.estado_display, styles['TableContent']),
                Paragraph('—', styles['TableContent']),
                Paragraph('', styles['TableContent']),
                Paragraph('', styles['TableContent']),
                Paragraph(f"{alquiler.total:.2f}", styles['TableContent']),
            ])

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ])
    table = Table(data, colWidths=[
        0.7*inch,  # Código
        0.8*inch,  # Fecha Alq.
        0.8*inch,  # F. Dev.
        1.3*inch,  # Cliente
        0.7*inch,  # Estado
        1.5*inch,  # Prenda
        0.4*inch,  # Cant.
        0.7*inch,  # P.Unit.
        0.7*inch,  # Total
    ])
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph(f"Total de Alquileres Filtrados: Bs. {total_alquileres:.2f}", styles['TotalStyle']))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_alquileres.pdf"'
    return response


def exportar_reporte_alquileres_excel(request, alquileres, fecha_desde, fecha_hasta, total_alquileres):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Alquileres"

    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    content_font = Font(name='Calibri', size=10)
    total_font = Font(name='Calibri', bold=True, size=12)

    num_cols = 9
    col_letter = get_column_letter(num_cols)
    ws.merge_cells(f'A1:{col_letter}1')
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells(f'A2:{col_letter}2')
    ws['A2'] = "REPORTE DE ALQUILERES"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")

    filter_row = 4
    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    if request.GET.get('cliente') and request.GET.get('cliente') != '':
        try:
            cliente_obj = Cliente.objects.get(id=request.GET.get('cliente'))
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno}. "
        except ObjectDoesNotExist:
            pass
    selected_articulo_id = request.GET.get('articulo')
    if selected_articulo_id and selected_articulo_id != '':
        try:
            articulo_obj = PrendaInventario.objects.get(id=selected_articulo_id)
            filter_text += f"Artículo: {articulo_obj.nombre}. "
        except ObjectDoesNotExist:
            pass
    selected_estado = request.GET.get('estado')
    if selected_estado and selected_estado != '':
        filter_text += f"Estado: {selected_estado.replace('_', ' ').title()}. "
    if filter_text:
        ws.merge_cells(f'A{filter_row}:{col_letter}{filter_row}')
        ws[f'A{filter_row}'] = filter_text.strip()
        ws[f'A{filter_row}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        filter_row += 1

    header_row = filter_row + 1
    headers = ['Código', 'Fecha Alq.', 'F. Devolución', 'Cliente', 'Estado', 'Prenda', 'Cantidad', 'P. Unitario (Bs.)', 'Subtotal (Bs.)']
    ws.append(headers)
    for cell in ws[header_row]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    for alquiler in alquileres:
        cliente_str = f"{alquiler.cliente.nombres} {alquiler.cliente.apellido_paterno}".strip() if alquiler.cliente else "N/A"
        items = list(alquiler.items.select_related('prenda_item__prenda').all())
        rows = items if items else [None]
        for idx, item in enumerate(rows):
            row_data = [
                alquiler.codigo if idx == 0 else '',
                alquiler.fecha_alquiler.strftime('%d/%m/%Y') if idx == 0 else '',
                alquiler.fecha_devolucion.strftime('%d/%m/%Y') if idx == 0 else '',
                cliente_str if idx == 0 else '',
                alquiler.estado_display if idx == 0 else '',
                str(item.prenda_item.prenda) if item and item.prenda_item else '—',
                1 if item else '',
                float(item.precio_unitario) if item else '',
                float(item.subtotal) if item else float(alquiler.total),
            ]
            ws.append(row_data)
            for col_num, cell in enumerate(ws[ws.max_row]):
                cell.font = content_font
                cell.border = full_border
                if col_num in [7, 8]:
                    cell.number_format = '#,##0.00'
                else:
                    cell.alignment = Alignment(horizontal="center")

    last_data_row = ws.max_row
    ws.merge_cells(start_row=last_data_row + 2, start_column=1, end_row=last_data_row + 2, end_column=num_cols - 1)
    total_label_cell = ws.cell(row=last_data_row + 2, column=1)
    total_label_cell.value = "Total de Alquileres Filtrados: Bs."
    total_label_cell.font = total_font
    total_label_cell.alignment = Alignment(horizontal="right")
    total_value_cell = ws.cell(row=last_data_row + 2, column=num_cols)
    total_value_cell.value = total_alquileres
    total_value_cell.font = total_font
    total_value_cell.alignment = Alignment(horizontal="right")
    total_value_cell.number_format = '#,##0.00'

    for col in ws.columns:
        max_length = 0
        for cell in col[header_row - 1:]:
            try:
                if cell.value is not None:
                    cell_len = len(str(cell.value))
                    if cell_len > max_length:
                        max_length = cell_len
            except Exception:
                pass
        adjusted_width = min((max_length + 2) * 1.2, 50)
        ws.column_dimensions[get_column_letter(col[0].column)].width = adjusted_width

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_alquileres.xlsx"'
    wb.save(response)
    return response

# --- FIN de funciones de Reporte de Alquileres ---

@login_required
def reporte_transacciones(request):
    periodo = request.GET.get('periodo', '').strip() or 'mes'
    hoy_txn = django_tz.localdate()

    # Compute date range; default to current month when no periodo param given
    if periodo == 'hoy':
        desde = hasta = hoy_txn
    elif periodo == 'semana':
        desde = hoy_txn - timedelta(days=6)
        hasta = hoy_txn
    elif periodo == 'custom':
        try:
            desde = date.fromisoformat(request.GET.get('desde', str(hoy_txn)))
            hasta = date.fromisoformat(request.GET.get('hasta', str(hoy_txn)))
        except (ValueError, TypeError):
            desde = hasta = hoy_txn
    else:  # 'mes' and any unrecognized value
        desde = hoy_txn.replace(day=1)
        hasta = hoy_txn

    tipo_filter = request.GET.get('tipo', '').strip()
    concepto_filter = request.GET.get('concepto', '').strip()

    qs = CajaMovimiento.objects.filter(
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
        movimiento_reverso__isnull=True,
        via_caja=True,
    ).exclude(
        concepto__in=['apertura_caja', 'sobrante_caja', 'faltante_caja']
    ).order_by('-fecha')

    if tipo_filter:
        qs = qs.filter(tipo=tipo_filter)
    if concepto_filter:
        qs = qs.filter(concepto=concepto_filter)

    total_ingresos = qs.filter(tipo='ingreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_egresos = qs.filter(tipo='egreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    saldo = total_ingresos - total_egresos

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    mostrar_banner = isinstance(desde, date) and desde < FECHA_MIGRACION_CAJA

    return render(request, 'misastreria/reportes/reporte_transacciones.html', {
        'page_obj': page_obj,
        'total': qs.count(),
        'desde': desde.isoformat() if hasattr(desde, 'isoformat') else desde,
        'hasta': hasta.isoformat() if hasattr(hasta, 'isoformat') else hasta,
        'periodo': periodo,
        'tipo_filter': tipo_filter,
        'concepto_filter': concepto_filter,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'saldo': saldo,
        'concepto_choices': list(CONCEPTO_LABELS.items()),
        'fecha_migracion': FECHA_MIGRACION_CAJA,
        'mostrar_banner': mostrar_banner,
    })


def exportar_reporte_transacciones_pdf(request, transacciones, fecha_desde, fecha_hasta, total_ingresos, total_gastos, saldo_neto):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name='CompanyTitle',
                              fontSize=20,
                              leading=24,
                              alignment=1,
                              fontName='DejaVuSans',
                              textColor=colors.HexColor('#1e3a8a')))

    styles.add(ParagraphStyle(name='ReportTitle',
                              fontSize=16,
                              leading=20,
                              alignment=1,
                              fontName='DejaVuSans',
                              textColor=colors.HexColor('#2563eb')))

    styles.add(ParagraphStyle(name='SubTitle',
                              fontSize=10,
                              leading=12,
                              alignment=1,
                              fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='TableHeader',
                              fontSize=9,
                              fontName='DejaVuSans',
                              alignment=1))
    styles.add(ParagraphStyle(name='TableContent',
                              fontSize=7,
                              fontName='DejaVuSans',
                              alignment=0))
    styles.add(ParagraphStyle(name='TotalStyle',
                              fontSize=10,
                              fontName='DejaVuSans',
                              alignment=2))
    styles.add(ParagraphStyle(name='TotalNetoStyle',
                              fontSize=12,
                              fontName='DejaVuSans',
                              alignment=2,
                              textColor=colors.HexColor('#059669') if saldo_neto >= 0 else colors.HexColor('#dc2626')))

    elements = []

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(Paragraph("REPORTE DE TRANSACCIONES", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    
    selected_tipo_transaccion = request.GET.get('tipo_transaccion')
    if selected_tipo_transaccion and selected_tipo_transaccion != '':
        tipo_transaccion_display = dict(Transaccion.TIPO_TRANSACCION_CHOICES).get(selected_tipo_transaccion, selected_tipo_transaccion)
        filter_text += f"Tipo de Transacción: {tipo_transaccion_display}. "
    else:
        filter_text += "Tipo de Transacción: Todas. "

    selected_tipo_servicio = request.GET.get('tipo_servicio')
    if selected_tipo_servicio and selected_tipo_servicio != '':
        tipo_servicio_display = dict(Transaccion.TIPO_SERVICIO_CHOICES).get(selected_tipo_servicio, selected_tipo_servicio)
        filter_text += f"Tipo de Servicio: {tipo_servicio_display}. "
    else:
        filter_text += "Tipo de Servicio: Todos. "

    descripcion_filtro = request.GET.get('descripcion')
    if descripcion_filtro:
        filter_text += f"Descripción contiene: '{descripcion_filtro}'. "
    else:
        filter_text += "Descripción: Todas. "

    if filter_text:
        elements.append(Paragraph(filter_text.strip(), styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    data = [[
        Paragraph('Código', styles['TableHeader']),
        Paragraph('Tipo Transacción', styles['TableHeader']),
        Paragraph('Descripción', styles['TableHeader']),
        Paragraph('Tipo Servicio', styles['TableHeader']),
        Paragraph('Fecha', styles['TableHeader']),
        Paragraph('Cant.', styles['TableHeader']),
        Paragraph('Monto (Bs.)', styles['TableHeader'])
    ]]

    for transaccion in transacciones:
        row_data = [
            Paragraph(transaccion.codigo, styles['TableContent']),
            Paragraph(transaccion.get_tipo_transaccion_display(), styles['TableContent']),
            Paragraph(transaccion.descripcion, styles['TableContent']),
            Paragraph(transaccion.get_tipo_servicio_display(), styles['TableContent']),
            Paragraph(transaccion.fecha.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(str(transaccion.cantidad), styles['TableContent']),
            Paragraph(f"{transaccion.monto:.2f}", styles['TableContent'])
        ]
        
        data.append(row_data)

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a8a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f8f8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ])

    table = Table(data, colWidths=[
        0.8*inch,  # Código
        1.1*inch,  # Tipo Transacción
        2.5*inch,  # Descripción
        1.1*inch,  # Tipo Servicio
        0.8*inch,  # Fecha
        0.5*inch,  # Cant.
        0.9*inch   # Monto
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph(f"Total Ingresos: Bs. {total_ingresos:.2f}", styles['TotalStyle']))
    elements.append(Paragraph(f"Total Gastos: Bs. {total_gastos:.2f}", styles['TotalStyle']))
    elements.append(Paragraph(f"Saldo Neto: Bs. {saldo_neto:.2f}", styles['TotalNetoStyle']))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_transacciones.pdf"'
    return response


def exportar_reporte_transacciones_excel(request, transacciones, fecha_desde, fecha_hasta, total_ingresos, total_gastos, saldo_neto):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Transacciones"

    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    
    content_font = Font(name='Calibri', size=10)
    total_font = Font(name='Calibri', bold=True, size=12)
    total_alignment = Alignment(horizontal="right")
    
    # Colores para saldo neto
    ingresos_color = "059669" # Verde
    gastos_color = "DC2626" # Rojo
    saldo_positivo_color = "059669" # Verde
    saldo_negativo_color = "DC2626" # Rojo

    ws.merge_cells('A1:G1') # 7 columnas
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:G2') # 7 columnas
    ws['A2'] = "REPORTE DE TRANSACCIONES"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")


    filter_row = 4
    filter_text = ""
    if fecha_desde and fecha_hasta:
        filter_text += f"Periodo: {fecha_desde} al {fecha_hasta}. "
    elif fecha_desde:
        filter_text += f"Desde: {fecha_desde}. "
    elif fecha_hasta:
        filter_text += f"Hasta: {fecha_hasta}. "
    
    selected_tipo_transaccion = request.GET.get('tipo_transaccion')
    if selected_tipo_transaccion and selected_tipo_transaccion != '':
        tipo_transaccion_display = dict(Transaccion.TIPO_TRANSACCION_CHOICES).get(selected_tipo_transaccion, selected_tipo_transaccion)
        filter_text += f"Tipo de Transacción: {tipo_transaccion_display}. "
    else:
        filter_text += "Tipo de Transacción: Todas. "

    selected_tipo_servicio = request.GET.get('tipo_servicio')
    if selected_tipo_servicio and selected_tipo_servicio != '':
        tipo_servicio_display = dict(Transaccion.TIPO_SERVICIO_CHOICES).get(selected_tipo_servicio, selected_tipo_servicio)
        filter_text += f"Tipo de Servicio: {tipo_servicio_display}. "
    else:
        filter_text += "Tipo de Servicio: Todos. "

    descripcion_filtro = request.GET.get('descripcion')
    if descripcion_filtro:
        filter_text += f"Descripción contiene: '{descripcion_filtro}'. "
    else:
        filter_text += "Descripción: Todas. "


    if filter_text:
        ws.merge_cells(f'A{filter_row}:G{filter_row}') # 7 columnas
        ws[f'A{filter_row}'] = filter_text.strip()
        ws[f'A{filter_row}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        filter_row += 1
    
    header_row = filter_row + 1

    headers = ['Código', 'Tipo Transacción', 'Descripción', 'Tipo Servicio', 'Fecha', 'Cantidad', 'Monto (Bs.)']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    for transaccion in transacciones:
        row_data = [
            transaccion.codigo,
            transaccion.get_tipo_transaccion_display(),
            transaccion.descripcion,
            transaccion.get_tipo_servicio_display(),
            transaccion.fecha.strftime('%d/%m/%Y'),
            transaccion.cantidad,
            transaccion.monto
        ]
        
        ws.append(row_data)
        for col_num, cell in enumerate(ws[ws.max_row]):
            cell.font = content_font
            cell.border = full_border
            if col_num == 6: # Monto (Bs.) es la columna 6 (índice 0)
                cell.number_format = '#,##0.00'
            else:
                cell.alignment = Alignment(horizontal="center")


    last_data_row = ws.max_row
    
    # Totales
    total_label_ingresos = ws.cell(row=last_data_row + 2, column=1)
    total_label_ingresos.value = "Total Ingresos:"
    total_label_ingresos.font = total_font
    total_label_ingresos.alignment = total_alignment
    ws.merge_cells(start_row=last_data_row + 2, start_column=1, end_row=last_data_row + 2, end_column=6) # Ajusta el colspan
    
    total_value_ingresos = ws.cell(row=last_data_row + 2, column=7)
    total_value_ingresos.value = total_ingresos
    total_value_ingresos.font = Font(name='Calibri', bold=True, size=12, color=ingresos_color)
    total_value_ingresos.alignment = Alignment(horizontal="right")
    total_value_ingresos.number_format = '#,##0.00'

    total_label_gastos = ws.cell(row=last_data_row + 3, column=1)
    total_label_gastos.value = "Total Gastos:"
    total_label_gastos.font = total_font
    total_label_gastos.alignment = total_alignment
    ws.merge_cells(start_row=last_data_row + 3, start_column=1, end_row=last_data_row + 3, end_column=6) # Ajusta el colspan
    
    total_value_gastos = ws.cell(row=last_data_row + 3, column=7)
    total_value_gastos.value = total_gastos
    total_value_gastos.font = Font(name='Calibri', bold=True, size=12, color=gastos_color)
    total_value_gastos.alignment = Alignment(horizontal="right")
    total_value_gastos.number_format = '#,##0.00'

    total_label_neto = ws.cell(row=last_data_row + 4, column=1)
    total_label_neto.value = "Saldo Neto:"
    total_label_neto.font = total_font
    total_label_neto.alignment = total_alignment
    ws.merge_cells(start_row=last_data_row + 4, start_column=1, end_row=last_data_row + 4, end_column=6) # Ajusta el colspan
    
    total_value_neto = ws.cell(row=last_data_row + 4, column=7)
    total_value_neto.value = saldo_neto
    total_value_neto.font = Font(name='Calibri', bold=True, size=12, color=saldo_positivo_color if saldo_neto >= 0 else saldo_negativo_color)
    total_value_neto.alignment = Alignment(horizontal="right")
    total_value_neto.number_format = '#,##0.00'


    for col in ws.columns:
        max_length = 0
        column = col[header_row-1] # Get the column letter (e.g., 'A')
        for cell in col[header_row-1:]:
            try:
                if cell.value is not None:
                    cell_len = len(str(cell.value))
                    if cell_len > max_length:
                        max_length = cell_len
            except:
                pass
        adjusted_width = (max_length + 2) * 1.2
        if adjusted_width > 50: adjusted_width = 50
        ws.column_dimensions[get_column_letter(column.column)].width = adjusted_width


    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_transacciones.xlsx"'
    wb.save(response)
    return response

# --- FIN de funciones de Reporte de Transacciones ---

@login_required
def reporte_inventario(request):
    q      = request.GET.get('q', '').strip()
    tipo   = request.GET.get('tipo', '').strip()
    estado = request.GET.get('estado', 'ACT').strip()

    qs = PrendaInventario.objects.annotate(
        items_alquiler=Count('items', filter=Q(items__tipo='alquiler') & ~Q(items__estado='baja')),
        items_venta=Count('items', filter=Q(items__tipo='venta') & ~Q(items__estado='baja')),
    ).order_by('nombre', 'talla')
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) | Q(nombre__icontains=q) |
            Q(color__icontains=q)  | Q(talla__icontains=q)
        )
    if tipo:
        qs = qs.filter(items__tipo=tipo).distinct()
    if estado:
        qs = qs.filter(estado=estado)

    valor_total = PrendaInventario.objects.filter(estado='ACT').annotate(
        count_active=Count('items', filter=~Q(items__estado='baja')),
    ).aggregate(
        total=Sum(ExpressionWrapper(F('count_active') * F('precio'), output_field=DecimalField()))
    )['total'] or 0

    total = qs.count()
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/reportes/reporte_inventario.html', {
        'page_obj':     page_obj,
        'total':        total,
        'q':            q,
        'tipo':         tipo,
        'estado':       estado,
        'valor_total':  valor_total,
        'tipo_choices':   PrendaItem.TIPO_CHOICES,
        'estado_choices': PrendaInventario.ESTADO_OPCIONES,
    })


@login_required
def reporte_stock(request):
    prendas = PrendaInventario.objects.filter(estado='ACT').annotate(
        items_alquiler=Count('items', filter=Q(items__tipo='alquiler') & ~Q(items__estado='baja')),
        items_venta=Count('items', filter=Q(items__tipo='venta') & ~Q(items__estado='baja')),
    ).order_by('nombre')
    return render(request, 'misastreria/reportes/stock.html', {'prendas': prendas})

@login_required
def reporte_ingresos(request):
    return redirect('kardex_financiero', permanent=True)


# ── Producción ─────────────────────────────────────────────────────────────

def _guardar_insumos_orden(orden, post_data):
    """Restaura stock de los insumos viejos, elimina los registros y crea los nuevos."""
    for ins in orden.insumos.select_related('insumo').all():
        ins.insumo.cantidad += ins.cantidad
        ins.insumo.save()
    orden.insumos.all().delete()

    insumo_ids  = post_data.getlist('item_insumo')
    cantidades  = post_data.getlist('item_cantidad')

    errores = []
    for i, (ins_id, cant_str) in enumerate(zip(insumo_ids, cantidades), 1):
        if not ins_id:
            continue
        try:
            insumo   = Insumo.objects.get(pk=ins_id)
            cantidad = Decimal(cant_str or '0')
            if cantidad <= 0:
                errores.append(f"Fila {i}: la cantidad debe ser mayor que cero.")
                continue
            if insumo.cantidad < cantidad:
                errores.append(f"Fila {i}: stock insuficiente de {insumo} (disponible: {insumo.cantidad}).")
                continue
            InsumoCortado.objects.create(orden=orden, insumo=insumo, cantidad=cantidad)
            insumo.cantidad -= cantidad
            insumo.save()
        except (Insumo.DoesNotExist, Exception):
            errores.append(f"Fila {i}: datos inválidos.")
    return errores


def _insumos_json():
    import json
    insumos = list(
        Insumo.objects.filter(estado='ACT').select_related('unidad_medida')
        .values('id', 'articulo', 'unidad_medida__nombre', 'cantidad')
    )
    for ins in insumos:
        ins['cantidad'] = float(ins['cantidad'])
        unidad = ins.pop('unidad_medida__nombre') or ''
        ins['label'] = f"{ins['articulo']} ({unidad}) — stock: {ins['cantidad']}"
    return json.dumps(insumos)


@login_required
def lista_ordenes(request):
    q       = request.GET.get('q', '').strip()
    estado  = request.GET.get('estado', '').strip()
    desde   = request.GET.get('desde', '').strip()
    hasta   = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()

    hoy = django_tz.localdate()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat(); hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat(); hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    qs = OrdenProduccion.objects.select_related('empleado', 'confeccion').order_by('-creado')
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(empleado__nombres__icontains=q)
        )
    if estado:
        qs = qs.filter(estado=estado)
    if desde:
        qs = qs.filter(fecha_inicio__gte=desde)
    if hasta:
        qs = qs.filter(fecha_inicio__lte=hasta)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/produccion/lista.html', {
        'page_obj':      page_obj,
        'total':         total,
        'q':             q,
        'estado':        estado,
        'desde':         desde,
        'hasta':         hasta,
        'periodo':       periodo,
        'estado_choices': OrdenProduccion.ESTADO_CHOICES,
    })


@login_required
def crear_orden(request):
    if request.method == 'POST':
        form = OrdenProduccionForm(request.POST)
        if form.is_valid():
            orden = form.save()
            errores = _guardar_insumos_orden(orden, request.POST)
            if errores:
                messages.warning(request, 'Orden creada con advertencias: ' + '; '.join(errores))
            else:
                messages.success(request, f"Orden {orden.codigo} creada exitosamente.")
            return redirect('lista_ordenes')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = OrdenProduccionForm()
    return render(request, 'misastreria/produccion/form.html', {
        'form':        form,
        'titulo':      'Nueva Orden de Producción',
        'insumos_json': _insumos_json(),
    })


@login_required
def editar_orden(request, id):
    orden = get_object_or_404(OrdenProduccion, id=id)
    if request.method == 'POST':
        form = OrdenProduccionForm(request.POST, instance=orden)
        if form.is_valid():
            orden = form.save()
            errores = _guardar_insumos_orden(orden, request.POST)
            if errores:
                messages.warning(request, 'Actualizado con advertencias: ' + '; '.join(errores))
            else:
                messages.success(request, 'Orden actualizada correctamente.')
            return redirect('lista_ordenes')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = OrdenProduccionForm(instance=orden)
    items_existentes = list(orden.insumos.select_related('insumo').values('insumo_id', 'cantidad'))
    return render(request, 'misastreria/produccion/form.html', {
        'form':             form,
        'titulo':           'Editar Orden de Producción',
        'orden':            orden,
        'items_existentes': items_existentes,
        'insumos_json':     _insumos_json(),
    })


@login_required
def eliminar_orden(request, id):
    orden = get_object_or_404(OrdenProduccion, id=id)
    if request.method == 'POST':
        for ins in orden.insumos.select_related('insumo').all():
            ins.insumo.cantidad += ins.cantidad
            ins.insumo.save()
        orden.delete()
        messages.success(request, 'Orden eliminada correctamente.')
        return redirect('lista_ordenes')
    return render(request, 'misastreria/produccion/eliminar.html', {'orden': orden})


def _crear_items_desde_orden(orden):
    """
    Crea N PrendaItem para una OrdenProduccion de tipo 'stock' que acaba
    de transicionar a 'terminado'. Emite un KardexEvento de ingreso por cada item
    con descripcion trazable a la orden.

    Precondiciones (caller responsibility):
    - orden.tipo == 'stock'
    - orden.prenda_inventario is not None
    - orden.cantidad >= 1
    - Llamada DENTRO de transaction.atomic()

    Returns: int — numero de items creados (== orden.cantidad).
    """
    descripcion = f'Producción — {orden.codigo}'
    for _ in range(orden.cantidad):
        pi = PrendaItem.objects.create(
            prenda=orden.prenda_inventario,
            tipo='alquiler',
            condicion='nueva',
        )
        kardex_events.emit_ingreso(pi, descripcion=descripcion)
    return orden.cantidad


@login_required
def avanzar_estado_orden(request, id):
    orden = get_object_or_404(OrdenProduccion, id=id)

    # Idempotencia explícita: si ya terminó, redirigir sin acción
    if orden.estado == 'terminado':
        messages.info(request, f"La orden {orden.codigo} ya está terminada.")
        return redirect('lista_ordenes')

    siguiente = OrdenProduccion.ESTADO_SIGUIENTE.get(orden.estado)
    if not siguiente:
        messages.warning(request, 'Esta orden ya está en estado Terminado.')
        return redirect('lista_ordenes')

    if request.method == 'POST':
        items_creados = 0
        with transaction.atomic():
            orden.estado = siguiente
            orden.save()
            if siguiente == 'terminado' and orden.tipo == 'stock':
                items_creados = _crear_items_desde_orden(orden)

        if items_creados:
            messages.success(
                request,
                f"Orden {orden.codigo} terminada. Se ingresaron {items_creados} "
                f"prenda{'s' if items_creados != 1 else ''} al inventario "
                f"de {orden.prenda_inventario.nombre}.",
            )
        else:
            messages.success(request, f"Orden {orden.codigo} avanzó a: {orden.get_estado_display()}.")

    return redirect('lista_ordenes')


# === Kardex ===

@login_required
def kardex_item(request, codigo_item):
    item = get_object_or_404(
        PrendaItem.objects.select_related('prenda'),
        codigo_item=codigo_item,
    )

    eventos = item.kardex_eventos.select_related(
        'alquiler', 'venta', 'cliente'
    ).order_by('timestamp')

    metricas = {
        'total_alquileres': item.alquiler_items.count(),
        'total_ventas': item.venta_items.count(),
        'ingreso_acumulado': (
            sum((ai.precio_unitario for ai in item.alquiler_items.all()), Decimal('0')) +
            sum((vi.precio_unitario for vi in item.venta_items.all()), Decimal('0'))
        ),
    }

    return render(request, 'misastreria/kardex/item.html', {
        'item': item,
        'prenda': item.prenda,
        'eventos': eventos,
        'metricas': metricas,
    })


@login_required
def kardex_inventario(request, prenda_id):
    prenda = get_object_or_404(
        PrendaInventario.objects.annotate(
            count_disponible=Count('items', filter=Q(items__estado='disponible')),
            count_alquilado=Count('items', filter=Q(items__estado='alquilado')),
            count_reservado=Count('items', filter=Q(items__estado='reservado')),
            count_baja=Count('items', filter=Q(items__estado='baja')),
        ),
        id=prenda_id,
    )

    items_qs = (
        prenda.items
              .select_related('prenda')
              .prefetch_related('venta_items', 'alquiler_items')
              .order_by('codigo_item')
    )

    items_vendidos_ids = set(
        prenda.items
              .filter(venta_items__isnull=False)
              .values_list('id', flat=True)
              .distinct()
    )

    resumen = {
        'disponible': prenda.count_disponible,
        'alquilado':  prenda.count_alquilado,
        'reservado':  prenda.count_reservado,
        'baja':       prenda.count_baja,
        'vendido':    len(items_vendidos_ids),
        'total':      prenda.count_disponible + prenda.count_alquilado + prenda.count_reservado + prenda.count_baja,
    }

    items_view = []
    for it in items_qs:
        items_view.append({
            'obj': it,
            'is_vendido': it.id in items_vendidos_ids,
            'count_alquileres': it.alquiler_items.count(),
            'count_ventas': it.venta_items.count(),
        })

    return render(request, 'misastreria/kardex/inventario.html', {
        'prenda': prenda,
        'resumen': resumen,
        'items': items_view,
    })


@login_required
def kardex_financiero(request):
    hoy = django_tz.localdate()
    desde_default = hoy.replace(day=1).isoformat()
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    hasta_default = hoy.replace(day=ultimo_dia).isoformat()

    desde = request.GET.get('desde', desde_default).strip() or desde_default
    hasta = request.GET.get('hasta', hasta_default).strip() or hasta_default

    # Read totals from CajaMovimiento ledger (KARDEX-01)
    movimientos_qs = CajaMovimiento.objects.filter(
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
        movimiento_reverso__isnull=True,
        via_caja=True,
    ).exclude(concepto__in=['apertura_caja', 'sobrante_caja', 'faltante_caja'])

    total_ingresos = movimientos_qs.filter(tipo='ingreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_egresos = movimientos_qs.filter(tipo='egreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    saldo = total_ingresos - total_egresos

    breakdown = (
        movimientos_qs
        .values('concepto', 'tipo')
        .annotate(total=Sum('monto'))
        .order_by('tipo', 'concepto')
    )

    # Display-only querysets for service reference (not summed — totals come from ledger)
    alquileres = Alquiler.objects.filter(
        fecha_alquiler__range=[desde, hasta]
    ).select_related('cliente').order_by('-fecha_alquiler')
    ventas = Venta.objects.filter(
        fecha_venta__range=[desde, hasta]
    ).select_related('cliente').order_by('-fecha_venta')
    transacciones = Transaccion.objects.filter(
        fecha__range=[desde, hasta]
    ).order_by('-fecha')

    # Analytics charts
    chart_daily = _kardex_daily_chart(movimientos_qs, desde, hasta)
    chart_donut_kardex = _kardex_donut_chart(movimientos_qs)

    breakdown_list = [
        {
            'concepto': row['concepto'],
            'label': CONCEPTO_LABELS.get(row['concepto'], row['concepto'].replace('_', ' ').title()),
            'tipo': row['tipo'],
            'total': row['total'],
        }
        for row in breakdown
    ]

    return render(request, 'misastreria/kardex/financiero.html', {
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'saldo': saldo,
        'breakdown': breakdown_list,
        'alquileres': alquileres,
        'ventas': ventas,
        'transacciones': transacciones,
        'desde': desde,
        'hasta': hasta,
        'fecha_migracion': FECHA_MIGRACION_CAJA,
        'chart_daily': chart_daily,
        'chart_donut_kardex': chart_donut_kardex,
    })


# ============================================================
# CAJA — Private helpers
# ============================================================

def _get_periodo_range(request):
    """Returns (date_desde, date_hasta) for the requested period."""
    periodo = request.GET.get('periodo', 'hoy')
    hoy = django_tz.localdate()
    if periodo == 'semana':
        return hoy - timedelta(days=6), hoy
    elif periodo == 'mes':
        return hoy.replace(day=1), hoy
    elif periodo == 'custom':
        desde_str = request.GET.get('desde', str(hoy))
        hasta_str = request.GET.get('hasta', str(hoy))
        try:
            return date.fromisoformat(desde_str), date.fromisoformat(hasta_str)
        except (ValueError, TypeError):
            return hoy, hoy
    else:  # 'hoy' and default
        return hoy, hoy


def _calcular_arqueo(sesion):
    """Returns dict keyed by forma_pago with {ingresos, egresos, neto} for a session. Excluye garantías."""
    from collections import defaultdict
    arqueo = defaultdict(lambda: {'ingresos': Decimal('0'), 'egresos': Decimal('0'), 'neto': Decimal('0')})

    movs = CajaMovimiento.objects.filter(
        sesion=sesion,
        movimiento_reverso__isnull=True,
        via_caja=True,
    ).exclude(
        concepto__in=('garantia_alquiler', 'garantia_devolucion', 'apertura_caja', 'sobrante_caja', 'faltante_caja')
    ).values('forma_pago', 'tipo').annotate(total=Sum('monto'))

    for row in movs:
        fp = row['forma_pago']
        if row['tipo'] == 'ingreso':
            arqueo[fp]['ingresos'] += row['total']
        else:
            arqueo[fp]['egresos'] += row['total']

    for fp, vals in arqueo.items():
        vals['neto'] = vals['ingresos'] - vals['egresos']

    return dict(arqueo)


def _build_resumen_context(request):
    """Builds aggregated context shared by HTML/PDF/Excel resumen views."""
    desde, hasta = _get_periodo_range(request)
    periodo = request.GET.get('periodo', 'hoy')

    base_qs = CajaMovimiento.objects.filter(
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
        movimiento_reverso__isnull=True,
        via_caja=True,
    ).exclude(concepto__in=['apertura_caja', 'sobrante_caja', 'faltante_caja', 'garantia_alquiler', 'garantia_devolucion'])

    total_ingresos = base_qs.filter(tipo='ingreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_egresos = base_qs.filter(tipo='egreso').aggregate(t=Sum('monto'))['t'] or Decimal('0')
    saldo = total_ingresos - total_egresos

    breakdown_concepto = (
        base_qs
        .values('concepto', 'tipo')
        .annotate(total=Sum('monto'))
        .order_by('tipo', 'concepto')
    )

    breakdown_forma_pago = (
        base_qs
        .values('forma_pago', 'tipo')
        .annotate(total=Sum('monto'))
        .order_by('forma_pago', 'tipo')
    )

    # Daily flow: list of {'fecha': date, 'ingresos': Decimal, 'egresos': Decimal}
    flujo_por_dia_ingresos = (
        base_qs.filter(tipo='ingreso')
        .values('fecha__date')
        .annotate(total=Sum('monto'))
    )
    flujo_por_dia_egresos = (
        base_qs.filter(tipo='egreso')
        .values('fecha__date')
        .annotate(total=Sum('monto'))
    )

    flujo_map = {}
    for row in flujo_por_dia_ingresos:
        d = row['fecha__date']
        flujo_map.setdefault(d, {'fecha': d, 'ingresos': Decimal('0'), 'egresos': Decimal('0')})
        flujo_map[d]['ingresos'] += row['total']
    for row in flujo_por_dia_egresos:
        d = row['fecha__date']
        flujo_map.setdefault(d, {'fecha': d, 'ingresos': Decimal('0'), 'egresos': Decimal('0')})
        flujo_map[d]['egresos'] += row['total']

    flujo_diario = sorted(flujo_map.values(), key=lambda x: x['fecha'])

    sesiones_periodo = CajaSesion.objects.filter(
        fecha_apertura__date__gte=desde,
        fecha_apertura__date__lte=hasta,
    ).order_by('-fecha_apertura')

    movimientos_detalle = CajaMovimiento.objects.filter(
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
        via_caja=True,
    ).select_related('sesion', 'cliente', 'tipo_gasto').order_by('-fecha')

    return {
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'saldo': saldo,
        'breakdown_concepto': [
            {**row, 'label': CONCEPTO_LABELS.get(row['concepto'], row['concepto'].replace('_', ' ').title())}
            for row in breakdown_concepto
        ],
        'breakdown_forma_pago': list(breakdown_forma_pago),
        'flujo_diario': flujo_diario,
        'sesiones_periodo': sesiones_periodo,
        'movimientos_detalle': movimientos_detalle,
    }


# ============================================================
# Analytics — Dashboard helpers
# ============================================================

def _dashboard_kpis(hoy):
    """Returns KPI dict for the dashboard analytics section."""
    from collections import defaultdict
    mes_inicio = hoy.replace(day=1)

    # Current month ingresos (excluding operational concepts)
    ingresos_qs = CajaMovimiento.objects.filter(
        fecha__date__gte=mes_inicio,
        fecha__date__lte=hoy,
        movimiento_reverso__isnull=True,
        via_caja=True,
        tipo='ingreso',
    ).exclude(concepto__in=CONCEPTOS_OPERATIVOS)
    ingresos_actual = ingresos_qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')

    egresos_qs = CajaMovimiento.objects.filter(
        fecha__date__gte=mes_inicio,
        fecha__date__lte=hoy,
        movimiento_reverso__isnull=True,
        via_caja=True,
        tipo='egreso',
    ).exclude(concepto__in=CONCEPTOS_OPERATIVOS)
    egresos_actual = egresos_qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')

    # Previous month ingresos
    mes_anterior_fin = mes_inicio - timedelta(days=1)
    mes_anterior_inicio = mes_anterior_fin.replace(day=1)
    ingresos_anterior = CajaMovimiento.objects.filter(
        fecha__date__gte=mes_anterior_inicio,
        fecha__date__lte=mes_anterior_fin,
        movimiento_reverso__isnull=True,
        via_caja=True,
        tipo='ingreso',
    ).exclude(concepto__in=CONCEPTOS_OPERATIVOS).aggregate(t=Sum('monto'))['t'] or Decimal('0')

    # Delta percentage
    if ingresos_anterior == 0:
        delta_pct = None
    else:
        delta_pct = round(float(ingresos_actual - ingresos_anterior) / float(ingresos_anterior) * 100, 1)

    # Servicios activos
    servicios_activos = (
        Alquiler.objects.filter(estado='alquilado').count()
        + Reparacion.objects.filter(estado__in=['pendiente', 'en_proceso']).count()
        + Confeccion.objects.filter(estado__in=['pendiente', 'en_proceso']).count()
    )

    # Nuevos clientes del mes
    clientes_nuevos = Cliente.objects.filter(
        creado__date__gte=mes_inicio,
        creado__date__lte=hoy,
    ).count()

    return {
        'ingresos_mes': ingresos_actual,
        'egresos_mes': egresos_actual,
        'ingresos_anterior': ingresos_anterior,
        'delta_pct': delta_pct,
        'servicios_activos': servicios_activos,
        'clientes_nuevos': clientes_nuevos,
    }


def _dashboard_trend_chart(hoy):
    """Returns JSON string of weekly ingresos/egresos from FECHA_MIGRACION_CAJA to today (max 12 weeks)."""
    from collections import defaultdict

    # Only show weeks with real data (from migration date onwards, max 12 weeks back)
    fecha_inicio_trend = max(hoy - timedelta(weeks=12), FECHA_MIGRACION_CAJA)

    base_qs = (
        CajaMovimiento.objects
        .filter(
            fecha__date__gte=fecha_inicio_trend,
            fecha__date__lte=hoy,
            movimiento_reverso__isnull=True,
            via_caja=True,
        )
        .exclude(concepto__in=CONCEPTOS_OPERATIVOS)
    )

    ingresos_rows = base_qs.filter(tipo='ingreso').values('fecha__date').annotate(total=Sum('monto'))
    egresos_rows  = base_qs.filter(tipo='egreso').values('fecha__date').annotate(total=Sum('monto'))

    week_data = defaultdict(lambda: {'ingresos': 0.0, 'egresos': 0.0, 'start': None})
    for row in ingresos_rows:
        d = row['fecha__date']
        key = d - timedelta(days=d.weekday())  # Monday of that week
        week_data[key]['ingresos'] += float(row['total'])
        if week_data[key]['start'] is None:
            week_data[key]['start'] = key
    for row in egresos_rows:
        d = row['fecha__date']
        key = d - timedelta(days=d.weekday())
        week_data[key]['egresos'] += float(row['total'])
        if week_data[key]['start'] is None:
            week_data[key]['start'] = key

    result = []
    for week_start in sorted(week_data):
        data = week_data[week_start]
        label = week_start.strftime('%-d/%-m')
        result.append({
            'label': label,
            'ingresos': data['ingresos'],
            'egresos': data['egresos'],
        })

    return result


def _dashboard_donut_chart(hoy):
    """Returns JSON string of current-month revenue grouped by service type."""
    mes_inicio = max(hoy.replace(day=1), FECHA_MIGRACION_CAJA)

    SERVICE_GROUPS = [
        ('Alquiler',   ['alquiler_cobro']),
        ('Venta',      ['venta_cobro']),
        ('Confección', ['confeccion_cobro', 'confeccion_adelanto', 'confeccion_saldo']),
        ('Reparación', ['reparacion_cobro']),
    ]
    all_conceptos = [c for _, cs in SERVICE_GROUPS for c in cs]

    rows = (
        CajaMovimiento.objects
        .filter(
            fecha__date__gte=mes_inicio,
            fecha__date__lte=hoy,
            tipo='ingreso',
            concepto__in=all_conceptos,
            movimiento_reverso__isnull=True,
        )
        .values('concepto')
        .annotate(total=Sum('monto'))
    )

    # Aggregate per-concepto totals into service groups
    totals_by_concepto = {row['concepto']: float(row['total']) for row in rows}
    result = []
    for label, conceptos in SERVICE_GROUPS:
        total = sum(totals_by_concepto.get(c, 0.0) for c in conceptos)
        if total > 0:
            result.append({'label': label, 'value': total})

    return result


# ============================================================
# Analytics — Fase 2 helpers
# ============================================================

# --- Batch 1: KPI helpers for existing report views ---

def _kpis_ventas(qs):
    """Compute KPI summary for a filtered Venta queryset."""
    # NOTE: Do NOT use 'total' as an aggregate alias — Venta has a field also
    # named 'total', causing FieldError("Cannot compute Sum('total'): 'total'
    # is an aggregate"). Use 'count_ventas' instead.
    agg = qs.aggregate(
        count_ventas=Count('id'),
        ingreso_total=Sum('total'),
        ticket_promedio=Avg('total'),
    )
    items_vendidos = VentaItem.objects.filter(venta__in=qs).aggregate(n=Count('id'))['n'] or 0
    return {
        'total': agg['count_ventas'] or 0,
        'ingreso_total': agg['ingreso_total'] or 0,
        'ticket_promedio': agg['ticket_promedio'] or 0,
        'items_vendidos': items_vendidos,
    }


def _kpis_alquileres(qs):
    """Compute KPI summary for a filtered Alquiler queryset."""
    # NOTE: Do NOT use 'total' as an aggregate alias — Alquiler has a field also
    # named 'total', causing FieldError("Cannot compute Sum('total'): 'total'
    # is an aggregate"). Use 'count_alquileres' instead.
    # NOTE: fecha_devolucion is a required field (never null), so we use estado
    # to distinguish devueltos from pendientes/activos.
    agg = qs.aggregate(
        count_alquileres=Count('id'),
        ingreso_total=Sum('total'),
        ticket_promedio=Avg('total'),
    )
    return {
        'total': agg['count_alquileres'] or 0,
        'ingreso_total': agg['ingreso_total'] or 0,
        'ticket_promedio': agg['ticket_promedio'] or 0,
        'devueltos': qs.filter(estado='devuelto').count(),
        'pendientes': qs.exclude(estado='devuelto').count(),
    }


def _kpis_confecciones(qs):
    """Compute KPI summary for a filtered Confeccion queryset. Uses precio field (nullable)."""
    agg = qs.aggregate(
        total=Count('id'),
        ingreso_total=Sum('precio'),
        ticket_promedio=Avg('precio'),
    )
    return {
        'total': agg['total'] or 0,
        'ingreso_total': agg['ingreso_total'] or 0,
        'ticket_promedio': agg['ticket_promedio'] or 0,
        'entregadas': qs.filter(fecha_entrega__isnull=False).count(),
        'pendientes': qs.filter(fecha_entrega__isnull=True).count(),
    }


def _kpis_reparaciones(qs):
    # NOTE: Do NOT use 'total' as an aggregate alias here — Reparacion has a
    # field also named 'total', causing FieldError("Cannot compute Sum('total'):
    # 'total' is an aggregate"). Use 'count_reparaciones' instead.
    agg = qs.aggregate(
        count_reparaciones=Count('id'),
        ingreso_total=Sum('total'),
        ticket_promedio=Avg('total'),
    )
    return {
        'total': agg['count_reparaciones'] or 0,
        'ingreso_total': agg['ingreso_total'] or 0,
        'ticket_promedio': agg['ticket_promedio'] or 0,
        'entregadas': qs.filter(estado='entregado').count(),
        'pendientes': qs.filter(estado='pendiente').count(),
    }


# --- Batch 2: Analytics helpers ---

def _top_clients(fecha_inicio, fecha_fin, limit=10):
    """
    Generalized cross-service LTV helper.
    Returns list of dicts sorted by total_global DESC, truncated to limit.
    fecha_inicio and fecha_fin are date instances.
    Uses __date__gte / __date__lte filters on each service queryset.
    Guards Confeccion.precio with or 0.
    """
    from collections import defaultdict
    totals = defaultdict(lambda: {
        'total_ventas': 0.0, 'total_alquileres': 0.0,
        'total_confecciones': 0.0, 'total_reparaciones': 0.0,
        'num_transacciones': 0,
    })

    # Ventas
    for row in Venta.objects.filter(
        fecha_venta__gte=fecha_inicio,
        fecha_venta__lte=fecha_fin,
        cliente__isnull=False,
    ).values('cliente_id').annotate(subtotal=Sum('total'), num=Count('id')):
        totals[row['cliente_id']]['total_ventas'] += float(row['subtotal'] or 0)
        totals[row['cliente_id']]['num_transacciones'] += row['num'] or 0

    # Alquileres
    for row in Alquiler.objects.filter(
        fecha_alquiler__gte=fecha_inicio,
        fecha_alquiler__lte=fecha_fin,
        cliente__isnull=False,
    ).values('cliente_id').annotate(subtotal=Sum('total'), num=Count('id')):
        totals[row['cliente_id']]['total_alquileres'] += float(row['subtotal'] or 0)
        totals[row['cliente_id']]['num_transacciones'] += row['num'] or 0

    # Confecciones (precio nullable)
    for row in Confeccion.objects.filter(
        fecha_inicio__gte=fecha_inicio,
        fecha_inicio__lte=fecha_fin,
        cliente__isnull=False,
    ).values('cliente_id').annotate(subtotal=Sum('precio'), num=Count('id')):
        totals[row['cliente_id']]['total_confecciones'] += float(row['subtotal'] or 0)
        totals[row['cliente_id']]['num_transacciones'] += row['num'] or 0

    # Reparaciones (costo nullable)
    for row in Reparacion.objects.filter(
        creado__date__gte=fecha_inicio,
        creado__date__lte=fecha_fin,
        cliente__isnull=False,
    ).values('cliente_id').annotate(subtotal=Sum('total'), num=Count('id')):
        totals[row['cliente_id']]['total_reparaciones'] += float(row['subtotal'] or 0)
        totals[row['cliente_id']]['num_transacciones'] += row['num'] or 0

    if not totals:
        return []

    for cid, data in totals.items():
        data['total_global'] = (
            data['total_ventas'] + data['total_alquileres'] +
            data['total_confecciones'] + data['total_reparaciones']
        )

    sorted_ids = sorted(totals.keys(), key=lambda cid: totals[cid]['total_global'], reverse=True)[:limit]
    clientes_map = {c.pk: c for c in Cliente.objects.filter(pk__in=sorted_ids)}

    result = []
    for cid in sorted_ids:
        c = clientes_map.get(cid)
        if c:
            data = totals[cid]
            result.append({
                'cliente_id': cid,
                'cliente_nombre': f'{c.nombres} {c.apellido_paterno}'.strip(),
                'total_ventas': data['total_ventas'],
                'total_alquileres': data['total_alquileres'],
                'total_confecciones': data['total_confecciones'],
                'total_reparaciones': data['total_reparaciones'],
                'total_global': data['total_global'],
                'num_transacciones': data['num_transacciones'],
            })
    return result


def _top_items(fecha_inicio, fecha_fin, servicio='ambos', sort_by='ingreso', limit=200):
    """
    Aggregates VentaItem and/or AlquilerItem by prenda_item__prenda__nombre.
    Returns list of dicts merged in Python, sorted DESC by chosen metric.
    Product path: prenda_item__prenda__nombre (2-hop, never prenda__nombre).
    """
    merged = {}  # keyed on prenda_nombre

    if servicio in ('venta', 'ambos'):
        rows = VentaItem.objects.filter(
            venta__fecha_venta__gte=fecha_inicio,
            venta__fecha_venta__lte=fecha_fin,
        ).values('prenda_item__prenda__nombre').annotate(
            cant=Count('id'),
            ingreso=Sum('subtotal'),
        )
        for row in rows:
            nombre = row['prenda_item__prenda__nombre'] or 'Sin nombre'
            entry = merged.setdefault(nombre, {
                'prenda_nombre': nombre,
                'cantidad_venta': 0, 'ingreso_venta': 0,
                'cantidad_alquiler': 0, 'ingreso_alquiler': 0,
            })
            entry['cantidad_venta'] += row['cant'] or 0
            entry['ingreso_venta'] += float(row['ingreso'] or 0)

    if servicio in ('alquiler', 'ambos'):
        rows = AlquilerItem.objects.filter(
            alquiler__fecha_alquiler__gte=fecha_inicio,
            alquiler__fecha_alquiler__lte=fecha_fin,
        ).values('prenda_item__prenda__nombre').annotate(
            cant=Count('id'),
            ingreso=Sum('subtotal'),
        )
        for row in rows:
            nombre = row['prenda_item__prenda__nombre'] or 'Sin nombre'
            entry = merged.setdefault(nombre, {
                'prenda_nombre': nombre,
                'cantidad_venta': 0, 'ingreso_venta': 0,
                'cantidad_alquiler': 0, 'ingreso_alquiler': 0,
            })
            entry['cantidad_alquiler'] += row['cant'] or 0
            entry['ingreso_alquiler'] += float(row['ingreso'] or 0)

    result = []
    for entry in merged.values():
        entry['cantidad_total'] = entry['cantidad_venta'] + entry['cantidad_alquiler']
        entry['ingreso_total'] = entry['ingreso_venta'] + entry['ingreso_alquiler']
        entry['tiene_venta'] = entry['cantidad_venta'] > 0
        entry['tiene_alquiler'] = entry['cantidad_alquiler'] > 0
        result.append(entry)

    sort_key = 'ingreso_total' if sort_by == 'ingreso' else 'cantidad_total'
    result.sort(key=lambda x: x[sort_key], reverse=True)
    return result[:limit]


def _empty_empleado_row():
    return {
        'empleado_id': None, 'empleado_nombre': '',
        'num_ventas': 0, 'ingreso_ventas': 0,
        'num_alquileres': 0, 'ingreso_alquileres': 0,
        'num_confecciones': 0, 'ingreso_confecciones': 0,
        'num_reparaciones': 0, 'ingreso_reparaciones': 0,
        'num_total': 0, 'ingreso_total': 0,
    }


def _top_empleados(fecha_inicio, fecha_fin, limit=200):
    """
    Four per-service aggregations keyed by empleado_id, merged in Python.
    Returns list of dicts sorted DESC by ingreso_total.
    """
    merged = {}

    # Ventas
    for row in Venta.objects.filter(
        empleado__isnull=False,
        fecha_venta__gte=fecha_inicio,
        fecha_venta__lte=fecha_fin,
    ).values('empleado_id').annotate(num=Count('id'), ingreso=Sum('total')):
        eid = row['empleado_id']
        merged.setdefault(eid, _empty_empleado_row())
        merged[eid]['num_ventas'] = row['num'] or 0
        merged[eid]['ingreso_ventas'] = float(row['ingreso'] or 0)

    # Alquileres
    for row in Alquiler.objects.filter(
        empleado__isnull=False,
        fecha_alquiler__gte=fecha_inicio,
        fecha_alquiler__lte=fecha_fin,
    ).values('empleado_id').annotate(num=Count('id'), ingreso=Sum('total')):
        eid = row['empleado_id']
        merged.setdefault(eid, _empty_empleado_row())
        merged[eid]['num_alquileres'] = row['num'] or 0
        merged[eid]['ingreso_alquileres'] = float(row['ingreso'] or 0)

    # Confecciones (precio, nullable)
    for row in Confeccion.objects.filter(
        empleado__isnull=False,
        fecha_inicio__gte=fecha_inicio,
        fecha_inicio__lte=fecha_fin,
    ).values('empleado_id').annotate(num=Count('id'), ingreso=Sum('precio')):
        eid = row['empleado_id']
        merged.setdefault(eid, _empty_empleado_row())
        merged[eid]['num_confecciones'] = row['num'] or 0
        merged[eid]['ingreso_confecciones'] = float(row['ingreso'] or 0)

    # Reparaciones (costo, nullable)
    for row in Reparacion.objects.filter(
        empleado__isnull=False,
        creado__date__gte=fecha_inicio,
        creado__date__lte=fecha_fin,
    ).values('empleado_id').annotate(num=Count('id'), ingreso=Sum('total')):
        eid = row['empleado_id']
        merged.setdefault(eid, _empty_empleado_row())
        merged[eid]['num_reparaciones'] = row['num'] or 0
        merged[eid]['ingreso_reparaciones'] = float(row['ingreso'] or 0)

    # Get names from Empleado model
    emp_ids = list(merged.keys())
    for emp in Empleado.objects.filter(id__in=emp_ids):
        parts = [emp.nombres or '', emp.apellido_paterno or '', emp.apellido_materno or '']
        merged[emp.id]['empleado_nombre'] = ' '.join(p for p in parts if p).strip()
        merged[emp.id]['empleado_id'] = emp.id

    result = []
    for eid, row in merged.items():
        row['num_total'] = row['num_ventas'] + row['num_alquileres'] + row['num_confecciones'] + row['num_reparaciones']
        row['ingreso_total'] = row['ingreso_ventas'] + row['ingreso_alquileres'] + row['ingreso_confecciones'] + row['ingreso_reparaciones']
        result.append(row)

    result.sort(key=lambda x: x['ingreso_total'], reverse=True)
    return result[:limit]


def _kpis_operativas(fecha_inicio, fecha_fin):
    """
    Computes operational KPIs at Python level (no DurationField per D1).
    Returns scalar dict with avg/min/max durations (days) and inventory occupation.
    """
    # Alquiler durations — only devueltos (fecha_devolucion is required/always set,
    # so isnull=False was always True and selected everything; use estado instead)
    pares = list(Alquiler.objects.filter(
        fecha_alquiler__gte=fecha_inicio,
        fecha_alquiler__lte=fecha_fin,
        estado='devuelto',
    ).values_list('fecha_alquiler', 'fecha_devolucion'))
    dur_alq = [(b - a).days for a, b in pares if b is not None]

    # Confeccion delivery
    pares_conf = list(Confeccion.objects.filter(
        fecha_inicio__gte=fecha_inicio,
        fecha_inicio__lte=fecha_fin,
        fecha_entrega__isnull=False,
    ).values_list('fecha_inicio', 'fecha_entrega'))
    dur_conf = [(b - a).days for a, b in pares_conf if a and b]

    # Reparacion turnaround (creado is DateTimeField, fecha_entrega is DateField)
    # fecha_entrega is required/never null — filter by estado='entregado' for actual turnarounds
    pares_rep = list(Reparacion.objects.filter(
        creado__date__gte=fecha_inicio,
        creado__date__lte=fecha_fin,
        estado='entregado',
    ).values_list('creado', 'fecha_entrega'))
    dur_rep = [(b - a.date()).days for a, b in pares_rep if a and b]

    # Inventario occupation — fecha_devolucion is required (never null), use estado instead
    total_items = PrendaItem.objects.count()
    ocupados = PrendaItem.objects.filter(
        alquiler_items__alquiler__estado='alquilado'
    ).distinct().count()
    tasa = (ocupados / total_items) if total_items else 0

    def safe_avg(lst): return round(sum(lst) / len(lst), 1) if lst else None
    def safe_min(lst): return min(lst) if lst else None
    def safe_max(lst): return max(lst) if lst else None

    return {
        'alquiler_duracion_avg': safe_avg(dur_alq),
        'alquiler_duracion_min': safe_min(dur_alq),
        'alquiler_duracion_max': safe_max(dur_alq),
        'alquiler_count': len(dur_alq),
        'confeccion_entrega_avg': safe_avg(dur_conf),
        'confeccion_entrega_min': safe_min(dur_conf),
        'confeccion_entrega_max': safe_max(dur_conf),
        'confeccion_count': len(dur_conf),
        'reparacion_turnaround_avg': safe_avg(dur_rep),
        'reparacion_turnaround_min': safe_min(dur_rep),
        'reparacion_turnaround_max': safe_max(dur_rep),
        'reparacion_count': len(dur_rep),
        'inventario_ocupados': ocupados,
        'inventario_total': total_items,
        'inventario_tasa_ocupacion': round(tasa * 100, 1),
    }


# --- Batch 3: YoY helpers ---

def _yoy_totals(fecha_inicio, fecha_fin):
    """
    Computes service-model totals for a single period.
    Uses __date__gte / __date__lte. Does NOT touch CajaMovimiento (per D2).
    Guards Confeccion.precio with or 0.
    """
    v = Venta.objects.filter(
        fecha_venta__gte=fecha_inicio,
        fecha_venta__lte=fecha_fin,
    ).aggregate(total=Sum('total'), count=Count('id'))
    a = Alquiler.objects.filter(
        fecha_alquiler__gte=fecha_inicio,
        fecha_alquiler__lte=fecha_fin,
    ).aggregate(total=Sum('total'), count=Count('id'))
    c = Confeccion.objects.filter(
        fecha_inicio__gte=fecha_inicio,
        fecha_inicio__lte=fecha_fin,
    ).aggregate(total=Sum('precio'), count=Count('id'))
    r = Reparacion.objects.filter(
        creado__date__gte=fecha_inicio,
        creado__date__lte=fecha_fin,
    ).aggregate(total=Sum('total'), count=Count('id'))
    ventas = float(v['total'] or 0)
    alquileres = float(a['total'] or 0)
    confecciones = float(c['total'] or 0)
    reparaciones = float(r['total'] or 0)
    return {
        'ventas': ventas,
        'alquileres': alquileres,
        'confecciones': confecciones,
        'reparaciones': reparaciones,
        'total': ventas + alquileres + confecciones + reparaciones,
        'count_ventas': v['count'] or 0,
        'count_alquileres': a['count'] or 0,
        'count_confecciones': c['count'] or 0,
        'count_reparaciones': r['count'] or 0,
        'count_total': (v['count'] or 0) + (a['count'] or 0) + (c['count'] or 0) + (r['count'] or 0),
    }


def _yoy_comparativa(fecha_inicio, fecha_fin):
    """
    Calls _yoy_totals twice (current + prior-year periods).
    Computes deltas absolute and percentage; guards division by zero.
    Returns nested dict.
    """
    try:
        from dateutil.relativedelta import relativedelta
        fi_ant = fecha_inicio - relativedelta(years=1)
        ff_ant = fecha_fin - relativedelta(years=1)
    except ImportError:
        fi_ant = fecha_inicio.replace(year=fecha_inicio.year - 1)
        ff_ant = fecha_fin.replace(year=fecha_fin.year - 1)

    actual = _yoy_totals(fecha_inicio, fecha_fin)
    anterior = _yoy_totals(fi_ant, ff_ant)

    def pct(a, b):
        if b == 0:
            return None
        return round((a - b) / b * 100, 1)

    metricas = ['ventas', 'alquileres', 'confecciones', 'reparaciones', 'total']
    deltas = {}
    for m in metricas:
        deltas[f'{m}_abs'] = actual[m] - anterior[m]
        deltas[f'{m}_pct'] = pct(actual[m], anterior[m])

    return {
        'periodo_actual': {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, **actual},
        'periodo_anterior': {'fecha_inicio': fi_ant, 'fecha_fin': ff_ant, **anterior},
        'deltas': deltas,
    }


# ============================================================
# Analytics — New Analytics Views (Fase 2)
# ============================================================

@login_required
def analitica_items(request):
    today = date.today()
    fecha_fin_default = today
    fecha_inicio_default = today - timedelta(days=30)

    fecha_inicio_str = request.GET.get('fecha_inicio', fecha_inicio_default.strftime('%Y-%m-%d'))
    fecha_fin_str = request.GET.get('fecha_fin', fecha_fin_default.strftime('%Y-%m-%d'))
    servicio = request.GET.get('servicio', 'ambos')
    sort_by = request.GET.get('sort', 'ingreso')
    export_format = request.GET.get('export_format', '')

    try:
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin = date.fromisoformat(fecha_fin_str)
    except (ValueError, TypeError):
        fecha_inicio = fecha_inicio_default
        fecha_fin = fecha_fin_default

    if servicio not in ('venta', 'alquiler', 'ambos'):
        servicio = 'ambos'
    if sort_by not in ('ingreso', 'cantidad'):
        sort_by = 'ingreso'

    rows = _top_items(fecha_inicio, fecha_fin, servicio=servicio, sort_by=sort_by)
    filtros = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, 'servicio': servicio, 'sort': sort_by}

    if export_format == 'pdf':
        return exportar_analitica_items_pdf(request, rows, filtros)
    elif export_format == 'excel':
        return exportar_analitica_items_excel(request, rows, filtros)

    paginator = Paginator(rows, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'misastreria/analitica/analitica_items.html', {
        'page_obj': page_obj,
        'filtros': filtros,
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str,
        'servicio': servicio,
        'sort': sort_by,
        'total_items': len(rows),
    })


@login_required
def analitica_empleados(request):
    today = date.today()
    fecha_fin_default = today
    fecha_inicio_default = today - timedelta(days=30)

    fecha_inicio_str = request.GET.get('fecha_inicio', fecha_inicio_default.strftime('%Y-%m-%d'))
    fecha_fin_str = request.GET.get('fecha_fin', fecha_fin_default.strftime('%Y-%m-%d'))
    export_format = request.GET.get('export_format', '')

    try:
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin = date.fromisoformat(fecha_fin_str)
    except (ValueError, TypeError):
        fecha_inicio = fecha_inicio_default
        fecha_fin = fecha_fin_default

    rows = _top_empleados(fecha_inicio, fecha_fin)
    filtros = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin}

    if export_format == 'pdf':
        return exportar_analitica_empleados_pdf(request, rows, filtros)
    elif export_format == 'excel':
        return exportar_analitica_empleados_excel(request, rows, filtros)

    return render(request, 'misastreria/analitica/analitica_empleados.html', {
        'empleados': rows,
        'filtros': filtros,
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str,
        'total_empleados': len(rows),
    })


@login_required
def analitica_clientes_ltv(request):
    today = date.today()
    fecha_fin_default = today
    fecha_inicio_default = today - timedelta(days=30)

    fecha_inicio_str = request.GET.get('fecha_inicio', fecha_inicio_default.strftime('%Y-%m-%d'))
    fecha_fin_str = request.GET.get('fecha_fin', fecha_fin_default.strftime('%Y-%m-%d'))
    export_format = request.GET.get('export_format', '')

    try:
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin = date.fromisoformat(fecha_fin_str)
    except (ValueError, TypeError):
        fecha_inicio = fecha_inicio_default
        fecha_fin = fecha_fin_default

    try:
        limit = min(int(request.GET.get('limit', 50)), 200)
    except (ValueError, TypeError):
        limit = 50

    rows = _top_clients(fecha_inicio, fecha_fin, limit=limit)
    filtros = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, 'limit': limit}

    if export_format == 'pdf':
        return exportar_analitica_clientes_ltv_pdf(request, rows, filtros)
    elif export_format == 'excel':
        return exportar_analitica_clientes_ltv_excel(request, rows, filtros)

    paginator = Paginator(rows, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'misastreria/analitica/analitica_clientes_ltv.html', {
        'page_obj': page_obj,
        'filtros': filtros,
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str,
        'limit': limit,
        'total_clientes': len(rows),
    })


@login_required
def analitica_operativas(request):
    today = date.today()
    fecha_fin_default = today
    fecha_inicio_default = today - timedelta(days=30)

    fecha_inicio_str = request.GET.get('fecha_inicio', fecha_inicio_default.strftime('%Y-%m-%d'))
    fecha_fin_str = request.GET.get('fecha_fin', fecha_fin_default.strftime('%Y-%m-%d'))
    export_format = request.GET.get('export_format', '')

    try:
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin = date.fromisoformat(fecha_fin_str)
    except (ValueError, TypeError):
        fecha_inicio = fecha_inicio_default
        fecha_fin = fecha_fin_default

    kpis = _kpis_operativas(fecha_inicio, fecha_fin)
    filtros = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin}

    if export_format == 'pdf':
        return exportar_analitica_operativas_pdf(request, kpis, filtros)
    elif export_format == 'excel':
        return exportar_analitica_operativas_excel(request, kpis, filtros)

    return render(request, 'misastreria/analitica/analitica_operativas.html', {
        'kpis': kpis,
        'filtros': filtros,
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str,
    })


@login_required
def analitica_comparativas(request):
    today = date.today()
    periodo = request.GET.get('periodo', 'this_month')
    export_format = request.GET.get('export_format', '')

    # Compute fecha_inicio / fecha_fin from preset or explicit GET params
    if periodo == 'last_month':
        if today.month == 1:
            fi = today.replace(year=today.year - 1, month=12, day=1)
        else:
            fi = today.replace(month=today.month - 1, day=1)
        try:
            import calendar as _cal
            last_day = _cal.monthrange(fi.year, fi.month)[1]
        except Exception:
            last_day = 28
        ff = fi.replace(day=last_day)
    elif periodo == 'this_quarter':
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        fi = today.replace(month=quarter_month, day=1)
        ff = today
    elif periodo == 'this_year':
        fi = today.replace(month=1, day=1)
        ff = today
    else:
        # Default: this_month
        periodo = 'this_month'
        fi = today.replace(day=1)
        ff = today

    # Allow explicit override
    fecha_inicio_str = request.GET.get('fecha_inicio', fi.strftime('%Y-%m-%d'))
    fecha_fin_str = request.GET.get('fecha_fin', ff.strftime('%Y-%m-%d'))
    try:
        fecha_inicio = date.fromisoformat(fecha_inicio_str)
        fecha_fin = date.fromisoformat(fecha_fin_str)
    except (ValueError, TypeError):
        fecha_inicio = fi
        fecha_fin = ff

    comparativa = _yoy_comparativa(fecha_inicio, fecha_fin)
    filtros = {'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin, 'periodo': periodo}

    if export_format == 'pdf':
        return exportar_analitica_comparativas_pdf(request, comparativa, filtros)
    elif export_format == 'excel':
        return exportar_analitica_comparativas_excel(request, comparativa, filtros)

    return render(request, 'misastreria/analitica/analitica_comparativas.html', {
        'comparativa': comparativa,
        'filtros': filtros,
        'fecha_inicio': fecha_inicio_str,
        'fecha_fin': fecha_fin_str,
        'periodo': periodo,
    })


@login_required
def estacionalidad(request):
    hoy = date.today()

    # Available years: from earliest record up to current year
    años_candidatos = [
        Alquiler.objects.order_by('fecha_alquiler').values_list('fecha_alquiler__year', flat=True).first(),
        Venta.objects.order_by('fecha_venta').values_list('fecha_venta__year', flat=True).first(),
        Confeccion.objects.order_by('fecha_inicio').values_list('fecha_inicio__year', flat=True).first(),
        Reparacion.objects.order_by('creado').values_list('creado__year', flat=True).first(),
    ]
    año_min = min((y for y in años_candidatos if y), default=hoy.year)
    años_disponibles = list(range(año_min, hoy.year + 1))

    try:
        año = int(request.GET.get('año', hoy.year))
    except (ValueError, TypeError):
        año = hoy.year
    if año not in años_disponibles:
        año = hoy.year

    def _por_mes(qs, campo_mes):
        rows = qs.values(campo_mes).annotate(n=Count('id'))
        return {row[campo_mes]: row['n'] for row in rows}

    alq  = _por_mes(Alquiler.objects.filter(fecha_alquiler__year=año),   'fecha_alquiler__month')
    ven  = _por_mes(Venta.objects.filter(fecha_venta__year=año),          'fecha_venta__month')
    conf = _por_mes(Confeccion.objects.filter(fecha_inicio__year=año),    'fecha_inicio__month')
    rep  = _por_mes(Reparacion.objects.filter(creado__year=año),          'creado__month')

    def _arr(d):
        return [d.get(m, 0) for m in range(1, 13)]

    series = {
        'alquileres':   _arr(alq),
        'ventas':       _arr(ven),
        'confecciones': _arr(conf),
        'reparaciones': _arr(rep),
    }

    tabla = []
    for i, mes in enumerate(MESES_ES):
        fila = {k: series[k][i] for k in series}
        fila['mes'] = mes
        fila['total'] = sum(series[k][i] for k in series)
        tabla.append(fila)

    return render(request, 'misastreria/analitica/estacionalidad.html', {
        'año': año,
        'años_disponibles': años_disponibles,
        'data_json': json.dumps({**series, 'meses': MESES_ES}),
        'tabla': tabla,
        'total_año': sum(f['total'] for f in tabla),
    })


@login_required
def prendas_temporada(request):
    hoy = date.today()

    try:
        año = int(request.GET.get('año', hoy.year))
    except (ValueError, TypeError):
        año = hoy.year
    servicio = request.GET.get('servicio', 'alquiler')
    try:
        top = min(int(request.GET.get('top', 20)), 50)
    except (ValueError, TypeError):
        top = 20

    # Build cross-tab {prenda_nombre: {mes: count}}
    if servicio == 'venta':
        qs = (VentaItem.objects
              .filter(venta__fecha_venta__year=año)
              .values(nombre=F('prenda_item__prenda__nombre'),
                      mes=F('venta__fecha_venta__month'))
              .annotate(n=Count('id')))
    else:  # alquiler (default)
        qs = (AlquilerItem.objects
              .filter(alquiler__fecha_alquiler__year=año)
              .values(nombre=F('prenda_item__prenda__nombre'),
                      mes=F('alquiler__fecha_alquiler__month'))
              .annotate(n=Count('id')))

    cross = {}
    for row in qs:
        nombre = row['nombre'] or 'Sin nombre'
        cross.setdefault(nombre, {})
        cross[nombre][row['mes']] = row['n']

    filas = []
    for nombre, meses_dict in cross.items():
        meses_vals = [meses_dict.get(m, 0) for m in range(1, 13)]
        filas.append({
            'nombre': nombre,
            'meses': meses_vals,
            'total': sum(meses_vals),
            'pico': MESES_ES[meses_vals.index(max(meses_vals))] if any(meses_vals) else '—',
        })

    filas.sort(key=lambda x: x['total'], reverse=True)
    filas = filas[:top]

    max_val = max((v for f in filas for v in f['meses']), default=1) or 1

    def _alpha(v):
        if not v:
            return '0'
        return f'{0.15 + (v / max_val) * 0.85:.2f}'

    for fila in filas:
        fila['meses_data'] = [
            {'val': v, 'alpha': _alpha(v), 'light': v < max_val * 0.55}
            for v in fila['meses']
        ]

    # Year range from earliest AlquilerItem
    primer_alq = AlquilerItem.objects.order_by('alquiler__fecha_alquiler').values_list('alquiler__fecha_alquiler__year', flat=True).first()
    primer_ven = VentaItem.objects.order_by('venta__fecha_venta').values_list('venta__fecha_venta__year', flat=True).first()
    año_min = min(y for y in [primer_alq, primer_ven, hoy.year] if y)
    años_disponibles = list(range(año_min, hoy.year + 1))

    return render(request, 'misastreria/analitica/prendas_temporada.html', {
        'año': año,
        'años_disponibles': años_disponibles,
        'servicio': servicio,
        'top': top,
        'filas': filas,
        'meses': MESES_ES,
        'max_val': max_val,
    })


# ============================================================
# Analytics — Fase 2 PDF/Excel Exporters
# ============================================================

def _pdf_styles():
    """Returns a getSampleStyleSheet with project-standard named styles added."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CompanyTitle', fontSize=14, leading=18,
                              alignment=TA_CENTER, fontName='DejaVuSans',
                              textColor=colors.HexColor('#1e3a8a')))
    styles.add(ParagraphStyle(name='ReportTitle', fontSize=12, leading=16,
                              alignment=TA_CENTER, fontName='DejaVuSans',
                              textColor=colors.HexColor('#2563eb')))
    styles.add(ParagraphStyle(name='SubTitle', fontSize=9, leading=12,
                              alignment=TA_CENTER, fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='InfoBanner', fontSize=8, leading=11,
                              alignment=TA_LEFT, fontName='DejaVuSans',
                              textColor=colors.HexColor('#374151')))
    return styles


def _pdf_table_style(header_rows=1):
    """Returns a TableStyle with project-standard header/row formatting."""
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, header_rows - 1), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), colors.white),
        ('FONTNAME', (0, 0), (-1, header_rows - 1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, header_rows - 1), 8),
        ('ALIGN', (0, 0), (-1, header_rows - 1), 'CENTER'),
        ('FONTNAME', (0, header_rows), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, header_rows), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, header_rows), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])


def exportar_analitica_items_pdf(request, rows, filtros):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch / 2, leftMargin=inch / 2,
                            topMargin=inch / 2, bottomMargin=inch / 2)
    styles = _pdf_styles()
    elements = []

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')
    servicio = filtros.get('servicio', 'ambos')

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("ANÁLISIS DE ITEMS", styles['ReportTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(f"Período: {fi} al {ff} | Servicio: {servicio}", styles['SubTitle']))
    elements.append(Spacer(1, 0.15 * inch))

    header = ['Prenda', 'Cant.Venta', 'Ing.Venta (S/)', 'Cant.Alq', 'Ing.Alq (S/)', 'Cant.Total', 'Ing.Total (S/)']
    data = [header]
    for row in rows:
        data.append([
            row['prenda_nombre'],
            str(row['cantidad_venta']),
            f"{row['ingreso_venta']:,.2f}",
            str(row['cantidad_alquiler']),
            f"{row['ingreso_alquiler']:,.2f}",
            str(row['cantidad_total']),
            f"{row['ingreso_total']:,.2f}",
        ])

    if len(data) > 1:
        col_widths = [2.5 * inch, 0.8 * inch, 1.2 * inch, 0.8 * inch, 1.2 * inch, 0.8 * inch, 1.2 * inch]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(_pdf_table_style())
        elements.append(table)
    else:
        elements.append(Paragraph("Sin datos para los filtros seleccionados.", styles['SubTitle']))

    doc.build(elements)
    filename = f"analitica_items_{fi}_{ff}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_items_excel(request, rows, filtros):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Items'

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')
    servicio = filtros.get('servicio', 'ambos')

    header_fill = PatternFill('solid', fgColor='1F2937')
    header_font = Font(bold=True, color='FFFFFF', name='Calibri')
    bold_font = Font(bold=True, name='Calibri')

    ws.merge_cells('A1:G1')
    ws['A1'] = 'Análisis de Items — Fortium Tailor'
    ws['A1'].font = Font(bold=True, size=14, name='Calibri')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:G2')
    ws['A2'] = f'Período: {fi} al {ff} | Servicio: {servicio}'
    ws['A2'].font = Font(italic=True, name='Calibri')

    headers = ['Prenda', 'Cant. Venta', 'Ing. Venta (S/)', 'Cant. Alquiler', 'Ing. Alquiler (S/)', 'Cant. Total', 'Ing. Total (S/)']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    for r, row in enumerate(rows, 5):
        ws.cell(row=r, column=1, value=row['prenda_nombre'])
        ws.cell(row=r, column=2, value=row['cantidad_venta']).number_format = '#,##0'
        c = ws.cell(row=r, column=3, value=row['ingreso_venta'])
        c.number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=4, value=row['cantidad_alquiler']).number_format = '#,##0'
        c = ws.cell(row=r, column=5, value=row['ingreso_alquiler'])
        c.number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=6, value=row['cantidad_total']).number_format = '#,##0'
        c = ws.cell(row=r, column=7, value=row['ingreso_total'])
        c.number_format = '"S/ "#,##0.00'

    for col, width in zip('ABCDEFG', [35, 12, 16, 14, 16, 12, 16]):
        ws.column_dimensions[col].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    filename = f"analitica_items_{fi}_{ff}.xlsx"
    response = HttpResponse(buffer.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_empleados_pdf(request, rows, filtros):
    from reportlab.lib.pagesizes import landscape
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                            rightMargin=inch / 2, leftMargin=inch / 2,
                            topMargin=inch / 2, bottomMargin=inch / 2)
    styles = _pdf_styles()
    elements = []

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("PERFORMANCE POR EMPLEADO", styles['ReportTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(f"Período: {fi} al {ff}", styles['SubTitle']))
    elements.append(Spacer(1, 0.15 * inch))

    header = ['Empleado', 'Ventas (n)', 'Ventas (S/)', 'Alq (n)', 'Alq (S/)', 'Conf (n)', 'Conf (S/)', 'Rep (n)', 'Rep (S/)', 'Total (n)', 'Total (S/)']
    data = [header]
    for row in rows:
        data.append([
            row['empleado_nombre'],
            str(row['num_ventas']),
            f"{row['ingreso_ventas']:,.2f}",
            str(row['num_alquileres']),
            f"{row['ingreso_alquileres']:,.2f}",
            str(row['num_confecciones']),
            f"{row['ingreso_confecciones']:,.2f}",
            str(row['num_reparaciones']),
            f"{row['ingreso_reparaciones']:,.2f}",
            str(row['num_total']),
            f"{row['ingreso_total']:,.2f}",
        ])

    if len(data) > 1:
        col_widths = [2.0 * inch, 0.65 * inch, 0.9 * inch, 0.65 * inch, 0.9 * inch, 0.65 * inch, 0.9 * inch, 0.65 * inch, 0.9 * inch, 0.65 * inch, 0.9 * inch]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(_pdf_table_style())
        elements.append(table)
    else:
        elements.append(Paragraph("Sin datos para los filtros seleccionados.", styles['SubTitle']))

    doc.build(elements)
    filename = f"analitica_empleados_{fi}_{ff}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_empleados_excel(request, rows, filtros):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Empleados'

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')

    header_fill = PatternFill('solid', fgColor='1F2937')
    header_font = Font(bold=True, color='FFFFFF', name='Calibri')

    ws.merge_cells('A1:K1')
    ws['A1'] = 'Performance por Empleado — Fortium Tailor'
    ws['A1'].font = Font(bold=True, size=14, name='Calibri')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:K2')
    ws['A2'] = f'Período: {fi} al {ff}'
    ws['A2'].font = Font(italic=True, name='Calibri')

    headers = ['Empleado', 'Ventas (n)', 'Ventas (S/)', 'Alq (n)', 'Alq (S/)', 'Conf (n)', 'Conf (S/)', 'Rep (n)', 'Rep (S/)', 'Total (n)', 'Total (S/)']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    for r, row in enumerate(rows, 5):
        ws.cell(row=r, column=1, value=row['empleado_nombre'])
        ws.cell(row=r, column=2, value=row['num_ventas']).number_format = '#,##0'
        ws.cell(row=r, column=3, value=row['ingreso_ventas']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=4, value=row['num_alquileres']).number_format = '#,##0'
        ws.cell(row=r, column=5, value=row['ingreso_alquileres']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=6, value=row['num_confecciones']).number_format = '#,##0'
        ws.cell(row=r, column=7, value=row['ingreso_confecciones']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=8, value=row['num_reparaciones']).number_format = '#,##0'
        ws.cell(row=r, column=9, value=row['ingreso_reparaciones']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=10, value=row['num_total']).number_format = '#,##0'
        ws.cell(row=r, column=11, value=row['ingreso_total']).number_format = '"S/ "#,##0.00'

    for col, width in zip('ABCDEFGHIJK', [28, 10, 14, 10, 14, 10, 14, 10, 14, 10, 14]):
        ws.column_dimensions[col].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    filename = f"analitica_empleados_{fi}_{ff}.xlsx"
    response = HttpResponse(buffer.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_clientes_ltv_pdf(request, rows, filtros):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch / 2, leftMargin=inch / 2,
                            topMargin=inch / 2, bottomMargin=inch / 2)
    styles = _pdf_styles()
    elements = []

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')
    limit = filtros.get('limit', 50)

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("LIFETIME VALUE DE CLIENTES", styles['ReportTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(f"Período: {fi} al {ff} | Top {limit} clientes", styles['SubTitle']))
    elements.append(Spacer(1, 0.15 * inch))

    header = ['Cliente', 'Ventas (S/)', 'Alquil. (S/)', 'Conf. (S/)', 'Rep. (S/)', 'LTV (S/)', '# Tx']
    data = [header]
    for row in rows:
        data.append([
            row['cliente_nombre'],
            f"{row['total_ventas']:,.2f}",
            f"{row['total_alquileres']:,.2f}",
            f"{row['total_confecciones']:,.2f}",
            f"{row['total_reparaciones']:,.2f}",
            f"{row['total_global']:,.2f}",
            str(row['num_transacciones']),
        ])

    if len(data) > 1:
        col_widths = [2.3 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 0.7 * inch]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(_pdf_table_style())
        elements.append(table)
    else:
        elements.append(Paragraph("Sin datos para los filtros seleccionados.", styles['SubTitle']))

    doc.build(elements)
    filename = f"analitica_clientes_ltv_{fi}_{ff}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_clientes_ltv_excel(request, rows, filtros):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Clientes LTV'

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')
    limit = filtros.get('limit', 50)

    header_fill = PatternFill('solid', fgColor='1F2937')
    header_font = Font(bold=True, color='FFFFFF', name='Calibri')

    ws.merge_cells('A1:G1')
    ws['A1'] = 'Lifetime Value de Clientes — Fortium Tailor'
    ws['A1'].font = Font(bold=True, size=14, name='Calibri')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:G2')
    ws['A2'] = f'Período: {fi} al {ff} | Top {limit} clientes'
    ws['A2'].font = Font(italic=True, name='Calibri')

    headers = ['Cliente', 'Ventas (S/)', 'Alquileres (S/)', 'Confecciones (S/)', 'Reparaciones (S/)', 'LTV Total (S/)', '# Transacciones']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    for r, row in enumerate(rows, 5):
        ws.cell(row=r, column=1, value=row['cliente_nombre'])
        ws.cell(row=r, column=2, value=row['total_ventas']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=3, value=row['total_alquileres']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=4, value=row['total_confecciones']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=5, value=row['total_reparaciones']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=6, value=row['total_global']).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=7, value=row['num_transacciones']).number_format = '#,##0'

    for col, width in zip('ABCDEFG', [30, 14, 16, 18, 18, 16, 16]):
        ws.column_dimensions[col].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    filename = f"analitica_clientes_ltv_{fi}_{ff}.xlsx"
    response = HttpResponse(buffer.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_operativas_pdf(request, kpis, filtros):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch / 2, bottomMargin=inch / 2)
    styles = _pdf_styles()
    elements = []

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("MÉTRICAS OPERATIVAS", styles['ReportTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(f"Período: {fi} al {ff}", styles['SubTitle']))
    elements.append(Spacer(1, 0.15 * inch))

    def fmt_days(val): return f"{val} días" if val is not None else "N/A"

    rows = [
        ['Métrica', 'Valor'],
        ['--- Alquileres ---', ''],
        ['Duración promedio', fmt_days(kpis['alquiler_duracion_avg'])],
        ['Duración mínima', fmt_days(kpis['alquiler_duracion_min'])],
        ['Duración máxima', fmt_days(kpis['alquiler_duracion_max'])],
        ['Alquileres con devolución', str(kpis['alquiler_count'])],
        ['--- Confecciones ---', ''],
        ['Entrega promedio', fmt_days(kpis['confeccion_entrega_avg'])],
        ['Entrega mínima', fmt_days(kpis['confeccion_entrega_min'])],
        ['Entrega máxima', fmt_days(kpis['confeccion_entrega_max'])],
        ['Confecciones entregadas', str(kpis['confeccion_count'])],
        ['--- Reparaciones ---', ''],
        ['Turnaround promedio', fmt_days(kpis['reparacion_turnaround_avg'])],
        ['Turnaround mínimo', fmt_days(kpis['reparacion_turnaround_min'])],
        ['Turnaround máximo', fmt_days(kpis['reparacion_turnaround_max'])],
        ['Reparaciones entregadas', str(kpis['reparacion_count'])],
        ['--- Inventario ---', ''],
        ['Items ocupados (alquiler activo)', str(kpis['inventario_ocupados'])],
        ['Items totales', str(kpis['inventario_total'])],
        ['Tasa de ocupación', f"{kpis['inventario_tasa_ocupacion']}%"],
    ]

    table = Table(rows, colWidths=[4 * inch, 2 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('FONTNAME', (0, 1), (-1, -1), 'DejaVuSans'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)

    doc.build(elements)
    filename = f"analitica_operativas_{fi}_{ff}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_operativas_excel(request, kpis, filtros):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Operativas'

    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')

    header_fill = PatternFill('solid', fgColor='1F2937')
    header_font = Font(bold=True, color='FFFFFF', name='Calibri')

    ws.merge_cells('A1:B1')
    ws['A1'] = 'Métricas Operativas — Fortium Tailor'
    ws['A1'].font = Font(bold=True, size=14, name='Calibri')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:B2')
    ws['A2'] = f'Período: {fi} al {ff}'
    ws['A2'].font = Font(italic=True, name='Calibri')

    for col, h in enumerate(['Métrica', 'Valor'], 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font

    def fmt_days(val): return f"{val} días" if val is not None else "N/A"

    rows = [
        ('Duración promedio alquiler', fmt_days(kpis['alquiler_duracion_avg'])),
        ('Duración mínima alquiler', fmt_days(kpis['alquiler_duracion_min'])),
        ('Duración máxima alquiler', fmt_days(kpis['alquiler_duracion_max'])),
        ('Alquileres con devolución', kpis['alquiler_count']),
        ('Entrega promedio confección', fmt_days(kpis['confeccion_entrega_avg'])),
        ('Entrega mínima confección', fmt_days(kpis['confeccion_entrega_min'])),
        ('Entrega máxima confección', fmt_days(kpis['confeccion_entrega_max'])),
        ('Confecciones entregadas', kpis['confeccion_count']),
        ('Turnaround promedio reparación', fmt_days(kpis['reparacion_turnaround_avg'])),
        ('Turnaround mínimo reparación', fmt_days(kpis['reparacion_turnaround_min'])),
        ('Turnaround máximo reparación', fmt_days(kpis['reparacion_turnaround_max'])),
        ('Reparaciones entregadas', kpis['reparacion_count']),
        ('Items ocupados (alquiler activo)', kpis['inventario_ocupados']),
        ('Items totales en inventario', kpis['inventario_total']),
        ('Tasa de ocupación', f"{kpis['inventario_tasa_ocupacion']}%"),
    ]
    for r, (key, val) in enumerate(rows, 5):
        ws.cell(row=r, column=1, value=key)
        ws.cell(row=r, column=2, value=val)

    ws.column_dimensions['A'].width = 38
    ws.column_dimensions['B'].width = 18

    buffer = io.BytesIO()
    wb.save(buffer)
    filename = f"analitica_operativas_{fi}_{ff}.xlsx"
    response = HttpResponse(buffer.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_comparativas_pdf(request, comparativa, filtros):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch / 2, leftMargin=inch / 2,
                            topMargin=inch / 2, bottomMargin=inch / 2)
    styles = _pdf_styles()
    elements = []

    pa = comparativa['periodo_actual']
    pant = comparativa['periodo_anterior']
    deltas = comparativa['deltas']

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph("COMPARATIVA AÑO VS AÑO", styles['ReportTitle']))
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(
        "Comparativa basada en datos históricos de servicios (no ajustados por reversiones de caja).",
        styles['InfoBanner']
    ))
    elements.append(Spacer(1, 0.15 * inch))

    def fmt_currency(v): return f"S/ {v:,.2f}"
    def fmt_pct(v): return f"{v:+.1f}%" if v is not None else "N/A"

    header = ['Métrica', f"Actual\n{pa['fecha_inicio']} – {pa['fecha_fin']}", f"Anterior\n{pant['fecha_inicio']} – {pant['fecha_fin']}", 'Δ Abs', 'Δ %']
    data = [header]

    for metrica, key in [('Ventas', 'ventas'), ('Alquileres', 'alquileres'), ('Confecciones', 'confecciones'), ('Reparaciones', 'reparaciones'), ('Total', 'total')]:
        data.append([
            metrica,
            fmt_currency(pa[key]),
            fmt_currency(pant[key]),
            fmt_currency(deltas[f'{key}_abs']),
            fmt_pct(deltas[f'{key}_pct']),
        ])

    col_widths = [1.5 * inch, 1.8 * inch, 1.8 * inch, 1.5 * inch, 1.0 * inch]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(_pdf_table_style())
    elements.append(table)

    doc.build(elements)
    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')
    filename = f"analitica_comparativas_{fi}_{ff}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def exportar_analitica_comparativas_excel(request, comparativa, filtros):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Comparativas YoY'

    pa = comparativa['periodo_actual']
    pant = comparativa['periodo_anterior']
    deltas = comparativa['deltas']
    fi = filtros.get('fecha_inicio', '')
    ff = filtros.get('fecha_fin', '')

    header_fill = PatternFill('solid', fgColor='1F2937')
    header_font = Font(bold=True, color='FFFFFF', name='Calibri')

    ws.merge_cells('A1:E1')
    ws['A1'] = 'Comparativa Año vs Año — Fortium Tailor'
    ws['A1'].font = Font(bold=True, size=14, name='Calibri')
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:E2')
    ws['A2'] = 'Comparativa basada en datos históricos de servicios (no ajustados por reversiones de caja).'
    ws['A2'].font = Font(italic=True, name='Calibri')

    ws.merge_cells('A3:E3')
    ws['A3'] = f'Período actual: {pa["fecha_inicio"]} al {pa["fecha_fin"]} | Período anterior: {pant["fecha_inicio"]} al {pant["fecha_fin"]}'
    ws['A3'].font = Font(italic=True, name='Calibri')

    headers = ['Métrica', f'Actual ({pa["fecha_inicio"]})', f'Anterior ({pant["fecha_inicio"]})', 'Δ Absoluto (S/)', 'Δ %']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    for r, (metrica, key) in enumerate([('Ventas', 'ventas'), ('Alquileres', 'alquileres'), ('Confecciones', 'confecciones'), ('Reparaciones', 'reparaciones'), ('Total', 'total')], 6):
        ws.cell(row=r, column=1, value=metrica)
        ws.cell(row=r, column=2, value=pa[key]).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=3, value=pant[key]).number_format = '"S/ "#,##0.00'
        ws.cell(row=r, column=4, value=deltas[f'{key}_abs']).number_format = '"S/ "#,##0.00'
        pct_val = deltas[f'{key}_pct']
        ws.cell(row=r, column=5, value=pct_val if pct_val is not None else 'N/A')

    for col, width in zip('ABCDE', [18, 20, 20, 20, 12]):
        ws.column_dimensions[col].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    filename = f"analitica_comparativas_{fi}_{ff}.xlsx"
    response = HttpResponse(buffer.getvalue(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ============================================================
# Analytics — Kardex helpers
# ============================================================

def _kardex_daily_chart(movimientos_qs, desde, hasta):
    """Returns JSON string of daily or weekly ingresos/egresos for the kardex view."""
    from collections import defaultdict

    # Normalize desde/hasta to date objects
    if isinstance(desde, str):
        desde = date.fromisoformat(desde)
    if isinstance(hasta, str):
        hasta = date.fromisoformat(hasta)

    delta_days = (hasta - desde).days
    use_weekly = delta_days > 60

    base_qs = movimientos_qs.exclude(concepto__in=CONCEPTOS_OPERATIVOS)

    # Use two separate queries (combining fecha__date transform + tipo in values() is broken in Django 5.2)
    ingresos_rows = base_qs.filter(tipo='ingreso').values('fecha__date').annotate(total=Sum('monto'))
    egresos_rows = base_qs.filter(tipo='egreso').values('fecha__date').annotate(total=Sum('monto'))

    if use_weekly:
        # ISO week bucketing
        week_data = defaultdict(lambda: {'ingresos': 0.0, 'egresos': 0.0})
        seen_weeks = []
        for row in ingresos_rows:
            d = row['fecha__date']
            year, week, _ = d.isocalendar()
            key = (year, week)
            if key not in week_data:
                seen_weeks.append(key)
            week_data[key]['ingresos'] += float(row['total'])
        for row in egresos_rows:
            d = row['fecha__date']
            year, week, _ = d.isocalendar()
            key = (year, week)
            if key not in week_data:
                seen_weeks.append(key)
            week_data[key]['egresos'] += float(row['total'])

        result = [
            {
                'label': f'{y}-W{w:02d}',
                'ingresos': week_data[(y, w)]['ingresos'],
                'egresos': week_data[(y, w)]['egresos'],
            }
            for y, w in sorted(set(seen_weeks))
        ]
    else:
        # Daily bucketing with zero-fill for every day in range
        day_data = {}
        current = desde
        while current <= hasta:
            day_data[str(current)] = {'ingresos': 0.0, 'egresos': 0.0}
            current += timedelta(days=1)
        for row in ingresos_rows:
            key = str(row['fecha__date'])
            if key in day_data:
                day_data[key]['ingresos'] += float(row['total'])
        for row in egresos_rows:
            key = str(row['fecha__date'])
            if key in day_data:
                day_data[key]['egresos'] += float(row['total'])

        result = [
            {'label': d, 'ingresos': v['ingresos'], 'egresos': v['egresos']}
            for d, v in sorted(day_data.items())
        ]

    return result


def _kardex_donut_chart(movimientos_qs):
    """Returns JSON string of income breakdown by concepto for the kardex view."""
    rows = (
        movimientos_qs
        .filter(tipo='ingreso')
        .exclude(concepto__in=CONCEPTOS_OPERATIVOS)
        .values('concepto')
        .annotate(total=Sum('monto'))
    )

    result = [
        {'label': CONCEPTO_LABELS.get(row['concepto'], row['concepto']), 'value': float(row['total'])}
        for row in rows
        if row['total']
    ]
    return result


# ============================================================
# CAJA — Movimientos views
# ============================================================

@login_required
def lista_movimientos_caja(request):
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    concepto = request.GET.get('concepto', '').strip()
    forma_pago = request.GET.get('forma_pago', '').strip()
    origen = request.GET.get('origen', '').strip()
    sesion_id = request.GET.get('sesion', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()

    hoy = django_tz.localdate()
    if periodo == 'hoy':
        desde = hoy.isoformat()
        hasta = hoy.isoformat()
    elif periodo == 'semana':
        desde = (hoy - timedelta(days=6)).isoformat()
        hasta = hoy.isoformat()
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = hoy.isoformat()

    qs = CajaMovimiento.objects.filter(via_caja=True).select_related(
        'sesion', 'cliente', 'tipo_gasto'
    ).annotate(
        tiene_reverso=Exists(
            CajaMovimiento.objects.filter(movimiento_reverso_id=OuterRef('pk'))
        )
    ).order_by('-fecha', '-id')

    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) |
            Q(descripcion__icontains=q) |
            Q(cliente__nombres__icontains=q)
        )
    if tipo:
        qs = qs.filter(tipo=tipo)
    if concepto:
        qs = qs.filter(concepto=concepto)
    if forma_pago:
        qs = qs.filter(forma_pago=forma_pago)
    if origen:
        qs = qs.filter(origen=origen)
    if sesion_id:
        qs = qs.filter(sesion_id=sesion_id)
    if desde:
        qs = qs.filter(fecha__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha__date__lte=hasta)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/caja/lista_movimientos.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'tipo': tipo,
        'concepto': concepto,
        'forma_pago': forma_pago,
        'origen': origen,
        'sesion_id': sesion_id,
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'tipo_choices': CajaMovimiento.TIPO_CHOICES,
        'concepto_choices': CajaMovimiento.CONCEPTO_CHOICES,
        'forma_pago_choices': CajaMovimiento.FORMA_PAGO_MOV_CHOICES,
        'origen_choices': CajaMovimiento.ORIGEN_CHOICES,
        'sesiones': CajaSesion.objects.order_by('-fecha_apertura')[:30],
    })


@login_required
def crear_movimiento_caja(request):
    sesion_activa = CajaSesion.objects.filter(estado='abierta').first()
    next_sesion = request.GET.get('sesion', '') or request.POST.get('next_sesion', '')

    if request.method == 'POST':
        form = CajaMovimientoManualForm(request.POST)
        if form.is_valid():
            movimiento = form.save(commit=False)
            movimiento.origen = 'manual'
            movimiento.sesion = sesion_activa
            movimiento.usuario = request.user
            movimiento.tipo = CajaMovimiento.concepto_tipo(movimiento.concepto)
            movimiento.save()
            messages.success(request, f"Movimiento {movimiento.codigo} creado exitosamente.")
            if next_sesion:
                return redirect('detalle_sesion_caja', pk=next_sesion)
            return redirect('detalle_movimiento_caja', pk=movimiento.pk)
        else:
            messages.error(request, "Por favor corrige los errores del formulario.")
    else:
        form = CajaMovimientoManualForm()

    return render(request, 'misastreria/caja/form_movimiento.html', {
        'form': form,
        'titulo': 'Crear Movimiento Manual',
        'sesion_activa': sesion_activa,
        'requiere_tipo_gasto': CajaMovimiento.REQUIERE_TIPO_GASTO,
        'next_sesion': next_sesion,
    })


@login_required
def detalle_movimiento_caja(request, pk):
    movimiento = get_object_or_404(
        CajaMovimiento.objects.select_related(
            'sesion', 'cliente', 'tipo_gasto', 'usuario',
            'referencia_alquiler', 'referencia_venta',
            'referencia_confeccion', 'referencia_reparacion',
        ),
        pk=pk,
    )
    puede_reversar = (
        not movimiento.fue_reversado and
        movimiento.movimiento_reverso is None and
        movimiento.origen == 'manual'
    )
    return render(request, 'misastreria/caja/detalle_movimiento.html', {
        'movimiento': movimiento,
        'puede_reversar': puede_reversar,
    })


@login_required
@require_POST
def revertir_movimiento_caja(request, pk):
    movimiento = get_object_or_404(CajaMovimiento, pk=pk)

    if movimiento.origen != 'manual':
        messages.error(request, "Solo se pueden anular movimientos manuales.")
        return redirect('detalle_movimiento_caja', pk=pk)

    # Block reversal of a reversal (movement already has a reverso_de)
    if movimiento.fue_reversado:
        messages.error(request, "Este movimiento ya fue reversado.")
        return redirect('detalle_movimiento_caja', pk=pk)

    # Block if this movement IS itself a reversal (has movimiento_reverso set)
    if movimiento.movimiento_reverso is not None:
        messages.error(request, "No se puede reversar un movimiento que ya es un reverso.")
        return redirect('detalle_movimiento_caja', pk=pk)

    # Determine reversal concepto
    if movimiento.tipo == 'ingreso':
        concepto_reverso = 'anulacion_cobro'
    else:
        concepto_reverso = 'ingreso_manual'

    tipo_reverso = 'egreso' if movimiento.tipo == 'ingreso' else 'ingreso'

    sesion_activa = CajaSesion.objects.filter(estado='abierta').first()

    with transaction.atomic():
        reverso = CajaMovimiento.objects.create(
            sesion=sesion_activa,
            tipo=tipo_reverso,
            concepto=concepto_reverso,
            origen='manual',
            forma_pago=movimiento.forma_pago,
            monto=movimiento.monto,
            cliente=movimiento.cliente,
            descripcion=f"Reverso de {movimiento.codigo}",
            usuario=request.user,
        )
        movimiento.movimiento_reverso = reverso
        movimiento.save(update_fields=['movimiento_reverso'])

    messages.success(request, f"Movimiento {movimiento.codigo} reversado. Se creó {reverso.codigo}.")
    return redirect('detalle_movimiento_caja', pk=movimiento.pk)


# ============================================================
# CAJA — Sesiones views
# ============================================================

@login_required
def lista_sesiones_caja(request):
    qs = CajaSesion.objects.order_by('-fecha_apertura')
    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'misastreria/caja/lista_sesiones.html', {
        'page_obj': page_obj,
        'total': total,
    })


@login_required
def abrir_sesion_caja(request):
    sesion_existente = CajaSesion.objects.filter(estado='abierta').first()

    if request.method == 'POST':
        form = CajaSesionAperturaForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    sesion = form.save(commit=False)
                    sesion.usuario_apertura = request.user
                    sesion.estado = 'abierta'
                    sesion.save()
                    CajaMovimiento.objects.create(
                        sesion=sesion,
                        tipo='ingreso',
                        concepto='apertura_caja',
                        origen='automatico',
                        forma_pago='efectivo',
                        monto=sesion.monto_apertura,
                        descripcion=f"Apertura de caja sesión #{sesion.pk}",
                        usuario=request.user,
                    )
                messages.success(request, f"Sesión de caja #{sesion.pk} abierta exitosamente.")
                return redirect('detalle_sesion_caja', pk=sesion.pk)
            except IntegrityError:
                form.add_error(None, "Ya existe una sesión de caja abierta. Ciérrala antes de abrir una nueva.")
    else:
        form = CajaSesionAperturaForm()

    return render(request, 'misastreria/caja/abrir_caja.html', {
        'form': form,
        'sesion_existente': sesion_existente,
    })


@login_required
def detalle_sesion_caja(request, pk):
    sesion = get_object_or_404(CajaSesion.objects.select_related('usuario_apertura', 'usuario_cierre'), pk=pk)
    movimientos = CajaMovimiento.objects.filter(sesion=sesion, via_caja=True).select_related('cliente', 'tipo_gasto').annotate(
        tiene_reverso=Exists(CajaMovimiento.objects.filter(movimiento_reverso_id=OuterRef('pk')))
    ).order_by('fecha', 'id')
    movimientos_garantia = movimientos.filter(concepto__in=('garantia_alquiler', 'garantia_devolucion'))
    arqueo = _calcular_arqueo(sesion)
    return render(request, 'misastreria/caja/detalle_sesion.html', {
        'sesion': sesion,
        'movimientos': movimientos,
        'movimientos_garantia': movimientos_garantia,
        'arqueo': arqueo,
    })


@login_required
def export_detalle_sesion_excel(request, pk):
    from decimal import Decimal
    sesion = get_object_or_404(CajaSesion.objects.select_related('usuario_apertura', 'usuario_cierre'), pk=pk)
    movimientos = CajaMovimiento.objects.filter(sesion=sesion, via_caja=True).select_related(
        'cliente', 'tipo_gasto', 'usuario',
        'referencia_alquiler', 'referencia_venta',
        'referencia_reparacion', 'referencia_confeccion',
    ).order_by('fecha', 'id')
    arqueo = _calcular_arqueo(sesion)

    # ── Paleta ──────────────────────────────────────────────────────────────
    C_BLUE       = '2563EB'   # encabezados principales
    C_BLUE_MID   = '3B82F6'   # encabezados secundarios / arqueo
    C_BLUE_LIGHT = 'DBEAFE'   # fila alterna clara
    C_GREEN      = '10B981'   # ingreso
    C_RED        = 'EF4444'   # egreso / negativo
    C_GOLD       = 'F59E0B'   # totales
    C_DARK       = '1E293B'   # texto oscuro
    C_MUTED      = '64748B'   # texto secundario
    C_WHITE      = 'FFFFFF'

    # ── Estilos reutilizables ────────────────────────────────────────────────
    def _fill(hex_color):
        return PatternFill(start_color=hex_color, end_color=hex_color, fill_type='solid')

    def _border(style='thin'):
        s = Side(style=style, color='D1D5DB')
        return Border(left=s, right=s, top=s, bottom=s)

    def _border_medium():
        sm = Side(style='medium', color='9CA3AF')
        st = Side(style='thin', color='D1D5DB')
        return Border(left=sm, right=sm, top=st, bottom=st)

    FONT_TITLE   = Font(name='Calibri', bold=True, size=14, color=C_DARK)
    FONT_SUBTITLE= Font(name='Calibri', size=10, color=C_MUTED)
    FONT_HEADER  = Font(name='Calibri', bold=True, size=10, color=C_WHITE)
    FONT_HEADER2 = Font(name='Calibri', bold=True, size=10, color=C_WHITE)
    FONT_BODY    = Font(name='Calibri', size=10, color=C_DARK)
    FONT_BODY_M  = Font(name='Calibri', size=10, color=C_MUTED)
    FONT_TOTAL   = Font(name='Calibri', bold=True, size=10, color=C_DARK)
    FONT_LABEL   = Font(name='Calibri', bold=True, size=10, color=C_DARK)

    ALIGN_LEFT   = Alignment(horizontal='left',   vertical='center', wrap_text=False)
    ALIGN_RIGHT  = Alignment(horizontal='right',  vertical='center')
    ALIGN_CENTER = Alignment(horizontal='center', vertical='center')
    ALIGN_WRAP   = Alignment(horizontal='left',   vertical='center', wrap_text=True)

    NUM_BS   = '#,##0.00'
    NUM_DATE = '@'

    def _style_header_cells(cells):
        for cell in cells:
            cell.font  = FONT_HEADER
            cell.fill  = _fill(C_BLUE)
            cell.border = _border()
            cell.alignment = ALIGN_CENTER

    def _style_header2_cells(cells):
        for cell in cells:
            cell.font  = FONT_HEADER2
            cell.fill  = _fill(C_BLUE_MID)
            cell.border = _border()
            cell.alignment = ALIGN_CENTER

    def _apply_body_row(ws, row_num, alt=False):
        fill = _fill(C_BLUE_LIGHT) if alt else _fill(C_WHITE)
        for cell in ws[row_num]:
            if cell.fill.fgColor.rgb in (C_BLUE, C_BLUE_MID, C_GOLD, '00000000', '000000'):
                continue
            cell.fill   = fill
            cell.border = _border()
            cell.alignment = ALIGN_LEFT
            if cell.font.bold:
                continue
            cell.font = FONT_BODY

    def _set_col_width(ws, col_letter, width):
        ws.column_dimensions[col_letter].width = width

    # ════════════════════════════════════════════════════════════════════════
    # Hoja 1 — Resumen
    # ════════════════════════════════════════════════════════════════════════
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Resumen'
    ws.sheet_view.showGridLines = False

    # Fila 1: título grande (merge A1:D1)
    ws.append(['Fortium Tailor  —  Detalle de Sesión de Caja', '', '', ''])
    ws.merge_cells('A1:D1')
    c = ws['A1']
    c.font      = FONT_TITLE
    c.fill      = _fill(C_BLUE)
    c.alignment = Alignment(horizontal='left', vertical='center')
    c.font      = Font(name='Calibri', bold=True, size=14, color=C_WHITE)
    ws.row_dimensions[1].height = 28

    # Fila 2: subtítulo
    ws.append([f'Sesión #{sesion.pk}  ·  generado {date.today().strftime("%d/%m/%Y")}', '', '', ''])
    ws.merge_cells('A2:D2')
    c = ws['A2']
    c.font      = FONT_SUBTITLE
    c.fill      = _fill('EFF6FF')
    c.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[2].height = 18

    ws.append([])  # fila 3 vacía

    # Encabezado sección info
    ws.append(['Campo', 'Valor', '', ''])
    _style_header_cells([ws['A4'], ws['B4']])
    ws.row_dimensions[4].height = 20

    info_rows = [
        ('Estado',              sesion.get_estado_display()),
        ('Fecha apertura',      sesion.fecha_apertura.strftime('%d/%m/%Y %H:%M') if sesion.fecha_apertura else ''),
        ('Fecha cierre',        sesion.fecha_cierre.strftime('%d/%m/%Y %H:%M') if sesion.fecha_cierre else '—'),
        ('Monto apertura (Bs)', float(sesion.monto_apertura or 0)),
        ('Total ingresos (Bs)', float(sesion.total_ingresos or 0)),
        ('Total egresos (Bs)',  float(sesion.total_egresos or 0)),
        ('Saldo sistema (Bs)',  float(sesion.saldo_sistema or 0)),
    ]
    if sesion.diferencia is not None:
        info_rows.append(('Diferencia (Bs)', float(sesion.diferencia)))
    if sesion.saldo_garantias:
        info_rows.append(('Garantías (Bs)', float(sesion.saldo_garantias)))
    info_rows.append(('Abrió', str(sesion.usuario_apertura)))
    if sesion.usuario_cierre:
        info_rows.append(('Cerró', str(sesion.usuario_cierre)))
    if sesion.observaciones:
        info_rows.append(('Observaciones', sesion.observaciones))

    for i, (label, val) in enumerate(info_rows):
        ws.append([label, val, '', ''])
        rn = ws.max_row
        alt = (i % 2 == 0)
        row_fill = _fill(C_BLUE_LIGHT if alt else C_WHITE)
        la = ws.cell(rn, 1); lb = ws.cell(rn, 2)
        la.font = FONT_LABEL; la.fill = row_fill; la.border = _border(); la.alignment = ALIGN_LEFT
        lb.font = FONT_BODY;  lb.fill = row_fill; lb.border = _border(); lb.alignment = ALIGN_LEFT
        if isinstance(val, float):
            lb.number_format = NUM_BS
            lb.alignment = ALIGN_RIGHT
        ws.row_dimensions[rn].height = 18

    ws.append([])  # separador

    # Sección arqueo
    ws.append(['Arqueo por forma de pago', '', '', ''])
    rn = ws.max_row
    ws.merge_cells(f'A{rn}:D{rn}')
    c = ws.cell(rn, 1)
    c.font      = Font(name='Calibri', bold=True, size=11, color=C_WHITE)
    c.fill      = _fill(C_BLUE_MID)
    c.alignment = ALIGN_LEFT
    ws.row_dimensions[rn].height = 22

    ws.append(['Forma de pago', 'Ingresos (Bs)', 'Egresos (Bs)', 'Neto (Bs)'])
    _style_header2_cells(list(ws[ws.max_row]))
    ws.row_dimensions[ws.max_row].height = 20

    for i, (fp, vals) in enumerate(arqueo.items()):
        ingresos = float(vals['ingresos']); egresos = float(vals['egresos']); neto = float(vals['neto'])
        ws.append([fp, ingresos, egresos, neto])
        rn = ws.max_row
        alt = (i % 2 == 0)
        row_fill = _fill(C_BLUE_LIGHT if alt else C_WHITE)
        neto_color = C_GREEN if neto >= 0 else C_RED
        for col in range(1, 5):
            c = ws.cell(rn, col)
            c.fill   = row_fill
            c.border = _border()
            c.font   = Font(name='Calibri', size=10, color=C_DARK if col == 1 else (C_GREEN if col == 2 else (C_RED if col == 3 else neto_color)), bold=(col == 4))
            c.alignment = ALIGN_RIGHT if col > 1 else ALIGN_LEFT
            if col > 1:
                c.number_format = NUM_BS
        ws.row_dimensions[rn].height = 18

    # Anchos columna A=30, B=20, C=20, D=20
    for ltr, w in [('A', 32), ('B', 20), ('C', 20), ('D', 20)]:
        _set_col_width(ws, ltr, w)

    ws.freeze_panes = 'A4'

    # ════════════════════════════════════════════════════════════════════════
    # Hoja 2 — Movimientos
    # ════════════════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet('Movimientos')
    ws2.sheet_view.showGridLines = False

    # Título
    COLS_MOV = 12
    ws2.append(['Movimientos de caja'] + [''] * (COLS_MOV - 1))
    ws2.merge_cells(f'A1:{get_column_letter(COLS_MOV)}1')
    c = ws2['A1']
    c.font      = Font(name='Calibri', bold=True, size=13, color=C_WHITE)
    c.fill      = _fill(C_BLUE)
    c.alignment = Alignment(horizontal='left', vertical='center')
    ws2.row_dimensions[1].height = 26

    HDR = ['Código', 'Fecha', 'Tipo', 'Concepto', 'Monto (Bs)', 'Forma Pago',
           'Cliente', 'Tipo Gasto', 'Referencia', 'Origen', 'Usuario', 'Descripción']
    ws2.append(HDR)
    _style_header_cells(list(ws2[2]))
    ws2.row_dimensions[2].height = 22

    mov_list = list(movimientos.exclude(concepto__in=('garantia_alquiler', 'garantia_devolucion')))
    total_ingresos_mov = Decimal(0)
    total_egresos_mov  = Decimal(0)

    for i, m in enumerate(mov_list):
        ref = (
            (m.referencia_alquiler.codigo if m.referencia_alquiler_id else None) or
            (m.referencia_venta.codigo if m.referencia_venta_id else None) or
            (m.referencia_reparacion.codigo if m.referencia_reparacion_id else None) or
            (m.referencia_confeccion.codigo if m.referencia_confeccion_id else None) or ''
        )
        monto = float(m.monto)
        ws2.append([
            m.codigo,
            m.fecha.strftime('%d/%m/%Y %H:%M') if m.fecha else '',
            m.get_tipo_display(),
            m.get_concepto_display(),
            monto,
            m.get_forma_pago_display(),
            str(m.cliente) if m.cliente_id else '',
            str(m.tipo_gasto) if m.tipo_gasto_id else '',
            ref,
            m.get_origen_display(),
            str(m.usuario) if m.usuario_id else '',
            m.descripcion or '',
        ])
        rn = ws2.max_row
        alt = (i % 2 == 0)
        row_fill = _fill(C_BLUE_LIGHT if alt else C_WHITE)
        is_ing = (m.tipo == 'ingreso')
        if is_ing:
            total_ingresos_mov += m.monto
        else:
            total_egresos_mov += m.monto

        for col in range(1, COLS_MOV + 1):
            c = ws2.cell(rn, col)
            c.fill   = row_fill
            c.border = _border()
            if col == 5:  # monto
                c.font          = Font(name='Calibri', bold=True, size=10,
                                       color=C_GREEN if is_ing else C_RED)
                c.number_format = NUM_BS
                c.alignment     = ALIGN_RIGHT
            elif col == 12:  # descripción
                c.font      = FONT_BODY_M
                c.alignment = ALIGN_WRAP
            else:
                c.font      = FONT_BODY
                c.alignment = ALIGN_LEFT
        ws2.row_dimensions[rn].height = 18

    # Fila de totales
    ws2.append(['TOTALES', '', '', '',
                float(total_ingresos_mov), '',
                '', '', '', '', '', ''])
    rn_total = ws2.max_row
    ws2.merge_cells(f'A{rn_total}:D{rn_total}')
    for col in range(1, COLS_MOV + 1):
        c = ws2.cell(rn_total, col)
        c.fill      = _fill('FEF3C7')  # amarillo suave
        c.border    = _border_medium()
        c.font      = FONT_TOTAL
        c.alignment = ALIGN_RIGHT if col >= 4 else ALIGN_LEFT
    ws2.cell(rn_total, 1).alignment = ALIGN_CENTER
    ws2.cell(rn_total, 5).number_format = NUM_BS
    ws2.cell(rn_total, 5).font = Font(name='Calibri', bold=True, size=10, color=C_GREEN)
    ws2.row_dimensions[rn_total].height = 22

    # Anchos movimientos
    MOV_WIDTHS = [14, 17, 11, 22, 14, 16, 24, 18, 14, 12, 16, 32]
    for idx, w in enumerate(MOV_WIDTHS, 1):
        _set_col_width(ws2, get_column_letter(idx), w)

    ws2.freeze_panes = 'A3'

    # ════════════════════════════════════════════════════════════════════════
    # Hoja 3 — Garantías (si hay)
    # ════════════════════════════════════════════════════════════════════════
    garantias = movimientos.filter(concepto__in=('garantia_alquiler', 'garantia_devolucion'))
    if garantias.exists():
        ws3 = wb.create_sheet('Garantías')
        ws3.sheet_view.showGridLines = False

        COLS_GAR = 5
        ws3.append(['Garantías'] + [''] * (COLS_GAR - 1))
        ws3.merge_cells(f'A1:{get_column_letter(COLS_GAR)}1')
        c = ws3['A1']
        c.font      = Font(name='Calibri', bold=True, size=13, color=C_WHITE)
        c.fill      = _fill(C_BLUE)
        c.alignment = Alignment(horizontal='left', vertical='center')
        ws3.row_dimensions[1].height = 26

        ws3.append(['Código', 'Fecha', 'Concepto', 'Monto (Bs)', 'Forma Pago'])
        _style_header_cells(list(ws3[2]))
        ws3.row_dimensions[2].height = 22

        for i, m in enumerate(garantias):
            monto = float(m.monto)
            is_ing = (m.tipo == 'ingreso')
            ws3.append([
                m.codigo,
                m.fecha.strftime('%d/%m/%Y %H:%M') if m.fecha else '',
                m.get_concepto_display(),
                monto,
                m.get_forma_pago_display(),
            ])
            rn = ws3.max_row
            alt = (i % 2 == 0)
            row_fill = _fill(C_BLUE_LIGHT if alt else C_WHITE)
            for col in range(1, COLS_GAR + 1):
                c = ws3.cell(rn, col)
                c.fill   = row_fill
                c.border = _border()
                if col == 4:
                    c.font          = Font(name='Calibri', bold=True, size=10,
                                           color=C_GREEN if is_ing else C_RED)
                    c.number_format = NUM_BS
                    c.alignment     = ALIGN_RIGHT
                else:
                    c.font      = FONT_BODY
                    c.alignment = ALIGN_LEFT
            ws3.row_dimensions[rn].height = 18

        for ltr, w in [('A', 14), ('B', 17), ('C', 24), ('D', 14), ('E', 16)]:
            _set_col_width(ws3, ltr, w)
        ws3.freeze_panes = 'A3'

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"sesion_caja_{sesion.pk}_{sesion.fecha_apertura.strftime('%Y%m%d') if sesion.fecha_apertura else 'sin_fecha'}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def cerrar_sesion_caja(request, pk):
    sesion = get_object_or_404(CajaSesion, pk=pk, estado='abierta')

    if request.method == 'POST':
        form = CajaSesionCierreForm(request.POST)
        if form.is_valid():
            monto_declarado = form.cleaned_data['monto_cierre_declarado']
            observaciones = form.cleaned_data.get('observaciones', '')
            saldo_sistema = sesion.saldo_efectivo_sistema
            diferencia = monto_declarado - saldo_sistema

            # Require observaciones when there is a difference
            if diferencia != Decimal('0') and not observaciones:
                form.add_error('observaciones', 'Las observaciones son requeridas cuando hay diferencia.')
            else:
                with transaction.atomic():
                    sesion_locked = CajaSesion.objects.select_for_update().get(pk=sesion.pk)

                    if diferencia > Decimal('0'):
                        CajaMovimiento.objects.create(
                            sesion=sesion_locked,
                            tipo='ingreso',
                            concepto='sobrante_caja',
                            origen='automatico',
                            forma_pago='efectivo',
                            monto=abs(diferencia),
                            descripcion=f"Sobrante al cerrar sesión #{sesion.pk}",
                            usuario=request.user,
                        )
                    elif diferencia < Decimal('0'):
                        CajaMovimiento.objects.create(
                            sesion=sesion_locked,
                            tipo='egreso',
                            concepto='faltante_caja',
                            origen='automatico',
                            forma_pago='efectivo',
                            monto=abs(diferencia),
                            descripcion=f"Faltante al cerrar sesión #{sesion.pk}",
                            usuario=request.user,
                        )

                    sesion_locked.monto_cierre_sistema = saldo_sistema
                    sesion_locked.monto_cierre_declarado = monto_declarado
                    sesion_locked.diferencia = diferencia
                    sesion_locked.estado = 'cerrada'
                    sesion_locked.fecha_cierre = django_tz.now()
                    sesion_locked.usuario_cierre = request.user
                    sesion_locked.observaciones = observaciones
                    sesion_locked.save()

                messages.success(request, f"Sesión #{sesion.pk} cerrada. Diferencia: Bs {diferencia:+.2f}.")
                return redirect('detalle_sesion_caja', pk=sesion.pk)
    else:
        form = CajaSesionCierreForm()

    saldo_sistema = sesion.saldo_efectivo_sistema
    arqueo = _calcular_arqueo(sesion)

    return render(request, 'misastreria/caja/cerrar_caja.html', {
        'form': form,
        'sesion': sesion,
        'saldo_sistema': saldo_sistema,
        'arqueo': arqueo,
    })


# ============================================================
# CAJA — Resumen y Exports
# ============================================================

@login_required
def resumen_caja(request):
    ctx = _build_resumen_context(request)
    return render(request, 'misastreria/caja/resumen_caja.html', ctx)


@login_required
def export_resumen_caja_pdf(request):
    ctx = _build_resumen_context(request)
    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontName='DejaVuSans',
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Heading2'],
        fontName='DejaVuSans',
        fontSize=12,
        spaceAfter=6,
    )
    normal_style = ParagraphStyle(
        'NormalStyle',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=9,
    )

    elements.append(Paragraph("Fortium Tailor — Resumen de Caja", title_style))
    elements.append(Paragraph(
        f"Período: {ctx['desde']} al {ctx['hasta']}",
        normal_style,
    ))
    elements.append(Spacer(1, 0.2 * inch))

    # Totals section
    elements.append(Paragraph("Totales del Período", header_style))
    totals_data = [
        ['Concepto', 'Monto (Bs)'],
        ['Total Ingresos', f"{ctx['total_ingresos']:.2f}"],
        ['Total Egresos', f"{ctx['total_egresos']:.2f}"],
        ['Saldo Neto', f"{ctx['saldo']:.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[3 * inch, 2 * inch])
    totals_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Breakdown by concepto
    elements.append(Paragraph("Desglose por Concepto", header_style))
    concepto_data = [['Concepto', 'Tipo', 'Total (Bs)']]
    for row in ctx['breakdown_concepto']:
        concepto_data.append([row['concepto'], row['tipo'], f"{row['total']:.2f}"])
    if len(concepto_data) > 1:
        c_table = Table(concepto_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch])
        c_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ]))
        elements.append(c_table)
    else:
        elements.append(Paragraph("Sin movimientos en el período.", normal_style))

    elements.append(Spacer(1, 0.2 * inch))

    # Breakdown by forma de pago
    elements.append(Paragraph("Desglose por Forma de Pago", header_style))
    fp_data = [['Forma de Pago', 'Tipo', 'Total (Bs)']]
    for row in ctx['breakdown_forma_pago']:
        fp_data.append([row['forma_pago'], row['tipo'], f"{row['total']:.2f}"])
    if len(fp_data) > 1:
        fp_table = Table(fp_data, colWidths=[2.5 * inch, 1.5 * inch, 1.5 * inch])
        fp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dbeafe')),
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ]))
        elements.append(fp_table)

    doc.build(elements)
    buffer.seek(0)
    filename = f"resumen_caja_{ctx['desde']}_{ctx['hasta']}.pdf"
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_resumen_caja_excel(request):
    ctx = _build_resumen_context(request)

    wb = openpyxl.Workbook()

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
    center_align = Alignment(horizontal='center')

    def _style_header_row(ws, row_num=1):
        for cell in ws[row_num]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align

    def _auto_width(ws):
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[get_column_letter(col[0].column)].width = max_len + 4

    # Sheet 1: Resumen
    ws_resumen = wb.active
    ws_resumen.title = 'Resumen'
    ws_resumen.append(['Fortium Tailor — Resumen de Caja'])
    ws_resumen.append([f"Período: {ctx['desde']} al {ctx['hasta']}"])
    ws_resumen.append([])
    ws_resumen.append(['Concepto', 'Monto (Bs)'])
    _style_header_row(ws_resumen, 4)
    ws_resumen.append(['Total Ingresos', float(ctx['total_ingresos'])])
    ws_resumen.append(['Total Egresos', float(ctx['total_egresos'])])
    ws_resumen.append(['Saldo Neto', float(ctx['saldo'])])
    _auto_width(ws_resumen)

    # Sheet 2: Detalle
    ws_detalle = wb.create_sheet('Detalle')
    ws_detalle.append(['Código', 'Fecha', 'Tipo', 'Concepto', 'Forma Pago', 'Monto (Bs)', 'Sesión', 'Descripción'])
    _style_header_row(ws_detalle)
    for mov in ctx['movimientos_detalle']:
        ws_detalle.append([
            mov.codigo,
            mov.creado.strftime('%Y-%m-%d %H:%M'),
            mov.get_tipo_display(),
            mov.get_concepto_display(),
            mov.get_forma_pago_display(),
            float(mov.monto),
            str(mov.sesion) if mov.sesion else 'Sin sesión',
            mov.descripcion,
        ])
    _auto_width(ws_detalle)

    # Sheet 3: Por Concepto
    ws_concepto = wb.create_sheet('Por Concepto')
    ws_concepto.append(['Concepto', 'Tipo', 'Total (Bs)'])
    _style_header_row(ws_concepto)
    for row in ctx['breakdown_concepto']:
        ws_concepto.append([row['concepto'], row['tipo'], float(row['total'])])
    _auto_width(ws_concepto)

    # Sheet 4: Por Forma de Pago
    ws_fp = wb.create_sheet('Por Forma de Pago')
    ws_fp.append(['Forma de Pago', 'Tipo', 'Total (Bs)'])
    _style_header_row(ws_fp)
    for row in ctx['breakdown_forma_pago']:
        ws_fp.append([row['forma_pago'], row['tipo'], float(row['total'])])
    _auto_width(ws_fp)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"resumen_caja_{ctx['desde']}_{ctx['hasta']}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ============================================================
# CAJA — Conceptos de gasto (TipoGasto CRUD)
# ============================================================

@login_required
def lista_tipo_gasto(request):
    q = request.GET.get('q', '').strip()
    activo = request.GET.get('activo', '').strip()

    qs = TipoGasto.objects.all()
    if q:
        qs = qs.filter(nombre__icontains=q)
    if activo == '1':
        qs = qs.filter(activo=True)
    elif activo == '0':
        qs = qs.filter(activo=False)

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/caja/lista_tipo_gasto.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'activo': activo,
    })


@login_required
def crear_tipo_gasto(request):
    if request.method == 'POST':
        form = TipoGastoForm(request.POST)
        if form.is_valid():
            tipo = form.save()
            messages.success(request, f'Concepto "{tipo.nombre}" creado.')
            return redirect('lista_tipo_gasto')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = TipoGastoForm()

    return render(request, 'misastreria/caja/form_tipo_gasto.html', {
        'form': form,
        'titulo': 'Nuevo Concepto de Gasto',
    })


@login_required
def editar_tipo_gasto(request, pk):
    tipo = get_object_or_404(TipoGasto, pk=pk)
    if request.method == 'POST':
        form = TipoGastoForm(request.POST, instance=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, f'Concepto "{tipo.nombre}" actualizado.')
            return redirect('lista_tipo_gasto')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        form = TipoGastoForm(instance=tipo)

    return render(request, 'misastreria/caja/form_tipo_gasto.html', {
        'form': form,
        'titulo': f'Editar: {tipo.nombre}',
        'objeto': tipo,
    })


@login_required
@require_POST
def eliminar_tipo_gasto(request, pk):
    tipo = get_object_or_404(TipoGasto, pk=pk)
    nombre = tipo.nombre
    try:
        tipo.delete()
        messages.success(request, f'Concepto "{nombre}" eliminado.')
    except ProtectedError:
        messages.error(request, f'No se puede eliminar "{nombre}" — tiene movimientos asociados.')
    return redirect('lista_tipo_gasto')


# ============================================================
# MÓDULO DE CONJUNTOS
# ============================================================

@login_required
def lista_conjuntos(request):
    q = request.GET.get('q', '').strip()
    activo = request.GET.get('activo', '').strip()

    qs = Conjunto.objects.all().order_by('nombre')
    if q:
        qs = qs.filter(nombre__icontains=q)
    if activo in ('True', 'False'):
        qs = qs.filter(activo=(activo == 'True'))

    total = qs.count()
    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/conjuntos/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'activo': activo,
    })


@login_required
def crear_conjunto(request):
    if request.method == 'POST':
        form = ConjuntoForm(request.POST)
        tipo = request.POST.get('tipo', 'alquiler')
        formset = ConjuntoSlotFormSet(request.POST, form_kwargs={'tipo': tipo})
        if form.is_valid() and formset.is_valid():
            conjunto = form.save()
            formset.instance = conjunto
            formset.save()
            messages.success(request, f'Conjunto "{conjunto.nombre}" creado exitosamente.')
            return redirect('lista_conjuntos')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        tipo = 'alquiler'
        form = ConjuntoForm()
        formset = ConjuntoSlotFormSet(form_kwargs={'tipo': tipo})
    prenda_item_opts = _build_prenda_item_opts(tipo)
    return render(request, 'misastreria/conjuntos/form.html', {
        'form': form,
        'formset': formset,
        'titulo': 'Nuevo Conjunto',
        'prenda_item_opts': json.dumps(prenda_item_opts),
    })


@login_required
def editar_conjunto(request, pk):
    conjunto = get_object_or_404(Conjunto, pk=pk)
    if request.method == 'POST':
        form = ConjuntoForm(request.POST, instance=conjunto)
        tipo = request.POST.get('tipo', conjunto.tipo)
        formset = ConjuntoSlotFormSet(request.POST, instance=conjunto, form_kwargs={'tipo': tipo})
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Conjunto "{conjunto.nombre}" actualizado.')
            return redirect('lista_conjuntos')
        else:
            messages.error(request, 'Por favor corrige los errores del formulario.')
    else:
        tipo = conjunto.tipo
        form = ConjuntoForm(instance=conjunto)
        formset = ConjuntoSlotFormSet(instance=conjunto, form_kwargs={'tipo': tipo})
    prenda_item_opts = _build_prenda_item_opts(tipo)
    return render(request, 'misastreria/conjuntos/form.html', {
        'form': form,
        'formset': formset,
        'titulo': 'Editar Conjunto',
        'conjunto': conjunto,
        'prenda_item_opts': json.dumps(prenda_item_opts),
    })


@login_required
def eliminar_conjunto(request, pk):
    conjunto = get_object_or_404(Conjunto, pk=pk)
    if request.method == 'POST':
        conjunto.activo = False
        conjunto.save(update_fields=['activo'])
        messages.success(request, f'Conjunto "{conjunto.nombre}" desactivado.')
        return redirect('lista_conjuntos')
    return render(request, 'misastreria/conjuntos/confirmar_eliminar.html', {
        'conjunto': conjunto,
    })


def buscar_prenda_items(request):
    q = request.GET.get('q', '').strip()
    qs = PrendaItem.objects.exclude(estado='baja').select_related('prenda').order_by('codigo_item')
    if q:
        qs = qs.filter(
            Q(codigo_item__icontains=q) | Q(prenda__nombre__icontains=q)
        )
    results = []
    for pi in qs[:15]:
        nombre = pi.prenda.nombre
        if pi.prenda.talla:
            nombre += f' T{pi.prenda.talla}'
        results.append({
            'id': pi.id,
            'codigo_item': pi.codigo_item,
            'nombre': nombre,
            'estado': pi.estado,
        })
    return JsonResponse(results, safe=False)