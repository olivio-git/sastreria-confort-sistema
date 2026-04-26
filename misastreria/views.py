from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import login_required
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from .models import Empleado, Cliente, Reparacion, Venta, Confeccion, Alquiler, Transaccion, Inventario, Permiso, Falta, Categoria
from .forms import EmpleadoForm, ClienteForm, ReparacionForm, VentaForm, ConfeccionForm, AlquilerForm, TransaccionForm, InventarioForm, PermisoForm, FaltaForm, BajaInventarioForm, EmpleadoReporteForm, ClienteReporteForm, ReparacionReporteForm
from django.core.paginator import Paginator
from datetime import date, datetime, timedelta
from dateutil import rrule
from dateutil.rrule import WEEKLY, MO, TU, WE, TH, FR
import calendar
from django.http import HttpResponse, JsonResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from django.db.models import Q, ProtectedError
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics # Para registrar fuentes en ReportLab
from reportlab.pdfbase.ttfonts import TTFont # Para usar fuentes TrueType en ReportLab
from django.forms import ValidationError
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import csv
import os
import io
from django.conf import settings
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from io import BytesIO # Para manejar el archivo en memoria
from django.db.models import Count
FONT_PATH = os.path.join(settings.BASE_DIR, 'misastreria', 'static', 'font', 'DejaVuSans.ttf')


# Esta es la línea que está causando el error
pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))

@login_required
def dashboard(request):
    modulos = [
        {'nombre': 'Empleados', 'url': 'lista_empleados', 'icono': 'bi bi-people-fill', 'descripcion': 'Gestiona la información de los empleados.'},
        {'nombre': 'Clientes', 'url': 'lista_clientes', 'icono': 'bi bi-person-lines-fill', 'descripcion': 'Administra los datos de los clientes.'},
        {'nombre': 'Reparaciones', 'url': 'lista_reparaciones', 'icono': 'bi bi-tools', 'descripcion': 'Registra y gestiona reparaciones de prendas.'},
        {'nombre': 'Ventas', 'url': 'lista_ventas', 'icono': 'bi bi-cart-fill', 'descripcion': 'Registra las ventas realizadas.'},
        {'nombre': 'Confecciones', 'url': 'lista_confecciones', 'icono': 'bi bi-scissors', 'descripcion': 'Gestiona las confecciones de trajes.'},
        {'nombre': 'Alquileres', 'url': 'lista_alquileres', 'icono': 'bi bi-bag-fill', 'descripcion': 'Administra los alquileres de prendas.'},
        {'nombre': 'Transacciones', 'url': 'lista_transacciones', 'icono': 'bi bi-currency-dollar', 'descripcion': 'Registra las transacciones del negocio.'},
        {'nombre': 'Inventario', 'url': 'lista_inventario', 'icono': 'bi bi-box-seam', 'descripcion': 'Controla el inventario de artículos.'},
        {'nombre': 'Reportes', 'url': 'reporte_empleados', 'icono': 'bi bi-bar-chart-fill', 'descripcion': 'Consulta reportes de empleados, clientes, artículos, stock e ingresos.'},
    ]
    return render(request, 'misastreria/dashboard.html', {'modulos': modulos})

@login_required
def lista_empleados(request):
    q = request.GET.get('q', '').strip()
    activo = request.GET.get('activo', '')

    empleados = Empleado.objects.order_by('-creado')

    if q:
        empleados = empleados.filter(
            Q(nombres__icontains=q) | Q(apellido_paterno__icontains=q) |
            Q(apellido_materno__icontains=q) | Q(ci__icontains=q) | Q(codigo__icontains=q)
        )
    if activo in ('1', '0'):
        empleados = empleados.filter(activo=(activo == '1'))

    paginator = Paginator(empleados, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'misastreria/empleados/lista.html', {
        'page_obj': page_obj, 'q': q, 'activo': activo,
        'total': empleados.count(),
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
    return render(request, 'misastreria/empleados/crear.html', {'form': form})

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
    return render(request, 'misastreria/empleados/editar.html', {'form': form, 'empleado': empleado})

@login_required
def eliminar_empleado(request, id):
    empleado = get_object_or_404(Empleado, id=id)
    if request.method == 'POST':
        empleado.delete()
        return redirect('lista_empleados')
    return render(request, 'misastreria/empleados/eliminar.html', {'empleado': empleado})

@login_required
def crear_permiso(request, empleado_id):
    empleado = get_object_or_404(Empleado, id=empleado_id)
    if request.method == 'POST':
        form = PermisoForm(request.POST)
        if form.is_valid():
            permiso = form.save(commit=False)
            permiso.empleado = empleado
            permiso.save()
            return redirect('lista_empleados')
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
            return redirect('lista_empleados')
    else:
        form = FaltaForm()
    return render(request, 'misastreria/empleados/crear_falta.html', {'form': form, 'empleado': empleado})

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
    q = request.GET.get('q', '').strip()
    desde = request.GET.get('desde', '')
    hasta = request.GET.get('hasta', '')

    clientes = Cliente.objects.order_by('-id')

    if q:
        clientes = clientes.filter(
            Q(nombres__icontains=q) | Q(apellido_paterno__icontains=q) |
            Q(apellido_materno__icontains=q) | Q(ci__icontains=q) | Q(celular__icontains=q)
        )
    if desde:
        clientes = clientes.filter(fecha_registro__gte=desde)
    if hasta:
        clientes = clientes.filter(fecha_registro__lte=hasta)

    paginator = Paginator(clientes, 15)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'misastreria/clientes/lista.html', {
        'page_obj': page_obj, 'q': q, 'desde': desde, 'hasta': hasta,
        'total': clientes.count(),
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

def buscar_clientes(request):
    q = request.GET.get('q', '').strip()
    clientes = Cliente.objects.filter(
        Q(nombres__icontains=q) | Q(apellido_paterno__icontains=q) |
        Q(apellido_materno__icontains=q) | Q(ci__icontains=q)
    ).order_by('nombres', 'apellido_paterno')[:10]
    data = [{'id': c.id, 'ci': c.ci or '', 'nombre': str(c)} for c in clientes]
    return JsonResponse(data, safe=False)

@login_required
def historial_cliente(request, id):
    cliente = get_object_or_404(Cliente, id=id)
    reparaciones = cliente.reparaciones.order_by('-creado')
    confecciones = cliente.confeccion_set.order_by('-fecha_inicio')
    alquileres = cliente.alquileres.order_by('-fecha_alquiler')
    ventas = cliente.ventas.order_by('-fecha_venta')
    return render(request, 'misastreria/clientes/historial.html', {
        'cliente': cliente,
        'reparaciones': reparaciones,
        'confecciones': confecciones,
        'alquileres': alquileres,
        'ventas': ventas,
    })

@login_required
def lista_reparaciones(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    tipo_prenda = request.GET.get('tipo_prenda', '').strip()
    desde = request.GET.get('desde', '')
    hasta = request.GET.get('hasta', '')
    periodo = request.GET.get('periodo', '')

    hoy = date.today()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = hoy.isoformat()
    elif periodo == 'mes':
        desde = (hoy - timedelta(days=30)).isoformat()
        hasta = hoy.isoformat()
    elif periodo == '3meses' or (not desde and not hasta and not q and not estado and not tipo_prenda):
        desde = (hoy - timedelta(days=90)).isoformat()
        hasta = hoy.isoformat()

    reparaciones = Reparacion.objects.order_by('-creado')

    if q:
        reparaciones = reparaciones.filter(
            Q(codigo__icontains=q) |
            Q(cliente__nombres__icontains=q) | Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        )
    if estado:
        reparaciones = reparaciones.filter(estado=estado)
    if tipo_prenda:
        reparaciones = reparaciones.filter(tipo_prenda=tipo_prenda)
    if desde:
        reparaciones = reparaciones.filter(creado__date__gte=desde)
    if hasta:
        reparaciones = reparaciones.filter(creado__date__lte=hasta)

    paginator = Paginator(reparaciones, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/reparaciones/lista.html', {
        'page_obj': page_obj,
        'q': q, 'estado': estado, 'tipo_prenda': tipo_prenda,
        'desde': desde, 'hasta': hasta, 'periodo': periodo,
        'total': reparaciones.count(),
        'tipo_prenda_choices': Reparacion.TIPO_PRENDA_CHOICES,
        'estado_choices': Reparacion.ESTADO_CHOICES,
    })

@login_required
def crear_reparacion(request):
    if request.method == 'POST':
        form = ReparacionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Reparación creada con éxito.")
            return redirect('lista_reparaciones')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        form = ReparacionForm()
    return render(request, 'misastreria/reparaciones/crear.html', {'form': form})

@login_required
def editar_reparacion(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    if request.method == 'POST':
        form = ReparacionForm(request.POST, instance=reparacion)
        if form.is_valid():
            form.save()
            messages.success(request, "Reparación actualizada con éxito.")
            return redirect('lista_reparaciones')
        else:
            messages.error(request, "Por favor corrige los errores en el formulario.")
    else:
        form = ReparacionForm(instance=reparacion)
    return render(request, 'misastreria/reparaciones/editar.html', {'form': form, 'reparacion': reparacion})

@login_required
def eliminar_reparacion(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    if request.method == 'POST':
        reparacion.delete()
        messages.success(request, "Reparación eliminada con éxito.")
        return redirect('lista_reparaciones')
    return render(request, 'misastreria/reparaciones/eliminar.html', {'reparacion': reparacion})

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
        return redirect('lista_reparaciones')
    return redirect('lista_reparaciones')

@login_required
def exportar_recibo_reparacion_pdf(request, id):
    reparacion = get_object_or_404(Reparacion, id=id)
    
    missing_fields = []
    if not reparacion.costo:
        missing_fields.append("costo")
    if not reparacion.cliente:
        missing_fields.append("cliente")
    if not reparacion.fecha_entrega:
        missing_fields.append("fecha de entrega")
    
    if missing_fields:
        messages.error(request, f"No se puede generar el recibo: faltan {', '.join(missing_fields)}.")
        return redirect('lista_reparaciones')
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_reparacion_{reparacion.codigo}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch/2)
    elements = []
    styles = getSampleStyleSheet()
    
    try:
        styles.add(ParagraphStyle(name='Centered', alignment=1, fontSize=16, spaceAfter=20))
        styles.add(ParagraphStyle(name='NormalBold', fontName='Helvetica-Bold', fontSize=12, spaceAfter=10))
    except Exception as e:
        messages.error(request, f"Error al generar el PDF: {str(e)}")
        return redirect('lista_reparaciones')
    
    elements.append(Paragraph("Recibo de Reparación - Sastrería", styles['Centered']))
    elements.append(Paragraph(f"Código: {reparacion.codigo}", styles['NormalBold']))
    elements.append(Paragraph(f"Fecha: {reparacion.creado.strftime('%d/%m/%Y')}", styles['Normal']))
    
    data = [
        ['Cliente', str(reparacion.cliente) if reparacion.cliente else '-'],
        ['Tipo de Prenda', reparacion.otro_prenda if reparacion.tipo_prenda == 'otro' and reparacion.otro_prenda else reparacion.get_tipo_prenda_display() or reparacion.tipo_prenda],
        ['Tipo de Reparación', reparacion.otro_reparacion if reparacion.tipo_reparacion == 'otro' and reparacion.otro_reparacion else reparacion.get_tipo_reparacion_display() or reparacion.tipo_reparacion],
        ['Costo', f"${reparacion.costo:.2f}" if reparacion.costo else '-'],
        ['Fecha de Entrega', str(reparacion.fecha_entrega)],
        ['Estado', reparacion.get_estado_display()],
        ['Detalles', reparacion.detalles or '-'],
        ['Asignado a', str(reparacion.empleado) if reparacion.empleado else '-'],
    ]
    
    table = Table(data, colWidths=[150, 300])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response

@login_required
def lista_ventas(request):
    q = request.GET.get('q', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()

    hoy = date.today()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    ventas = Venta.objects.all().order_by('-fecha_venta')
    if q:
        ventas = ventas.filter(
            Q(codigo__icontains=q) |
            Q(articulo__articulo__icontains=q) |
            Q(cliente__nombres__icontains=q) |
            Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        )
    if desde:
        ventas = ventas.filter(fecha_venta__gte=desde)
    if hasta:
        ventas = ventas.filter(fecha_venta__lte=hasta)

    total = ventas.count()
    paginator = Paginator(ventas, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/ventas/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
    })


@login_required
def crear_venta(request):
    if request.method == 'POST':
        form = VentaForm(request.POST)
        if form.is_valid():
            venta = form.save(commit=False)
            venta.save()  # El modelo calcula precio_unitario y precio_total
            messages.success(request, 'Venta creada exitosamente.')
            return redirect('lista_ventas')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = VentaForm()
    return render(request, 'misastreria/ventas/form.html', {
        'form': form,
        'titulo': 'Crear Venta'
    })

@login_required
def editar_venta(request, id):
    venta = get_object_or_404(Venta, id=id)
    if request.method == 'POST':
        form = VentaForm(request.POST, instance=venta)
        if form.is_valid():
            venta = form.save(commit=False)
            venta.save()  # El modelo calcula precio_unitario y precio_total
            messages.success(request, 'Venta actualizada exitosamente.')
            return redirect('lista_ventas')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = VentaForm(instance=venta)
    return render(request, 'misastreria/ventas/form.html', {
        'form': form,
        'titulo': 'Editar Venta',
        'venta': venta
    })

@login_required
def eliminar_venta(request, id):
    venta = get_object_or_404(Venta, id=id)
    if request.method == 'POST':
        venta.articulo.cantidad += venta.cantidad
        venta.articulo.save()
        venta.delete()
        messages.success(request, 'Venta eliminada exitosamente.')
        return redirect('lista_ventas')
    return render(request, 'misastreria/ventas/eliminar.html', {'venta': venta})

@login_required
def exportar_recibo_pdf(request, id):
    venta = get_object_or_404(Venta, id=id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_venta_{venta.codigo}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Recibo de Venta", styles['Heading1']))
    elements.append(Paragraph(f"Código: {venta.codigo}", styles['Normal']))

    data = [
        ['Campo', 'Valor'],
        ['Cliente', str(venta.cliente) if venta.cliente else '-'],
        ['Artículo', str(venta.articulo)],
        ['Cantidad', venta.cantidad],
        ['Precio Unitario', f"${venta.precio_unitario:.2f}"],
        ['Precio Total', f"${venta.precio_total:.2f}"],
        ['Fecha de Venta', venta.fecha_venta.strftime('%d/%m/%Y')],
    ]

    table = Table(data, colWidths=[150, 350])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response

@login_required
def get_precio_articulo(request):
    articulo_id = request.GET.get('articulo_id')
    try:
        articulo = Inventario.objects.get(id=articulo_id)
        return JsonResponse({'precio': float(articulo.precio)})
    except Inventario.DoesNotExist:
        return JsonResponse({'error': 'Artículo no encontrado'}, status=404)

@login_required
def lista_confecciones(request):
    q = request.GET.get('q', '').strip()
    tipo_prenda = request.GET.get('tipo_prenda', '').strip()
    estado = request.GET.get('estado', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()

    hoy = date.today()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    confecciones = Confeccion.objects.all().order_by('-fecha_inicio')
    if q:
        confecciones = confecciones.filter(
            Q(codigo__icontains=q) |
            Q(cliente__nombres__icontains=q) |
            Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        )
    if tipo_prenda:
        confecciones = confecciones.filter(tipo_prenda=tipo_prenda)
    if estado:
        confecciones = confecciones.filter(estado=estado)
    if desde:
        confecciones = confecciones.filter(fecha_inicio__gte=desde)
    if hasta:
        confecciones = confecciones.filter(fecha_inicio__lte=hasta)

    total = confecciones.count()
    paginator = Paginator(confecciones, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/confecciones/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'tipo_prenda': tipo_prenda,
        'estado': estado,
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'tipo_prenda_choices': Confeccion.TIPO_PRENDA_CHOICES,
        'estado_choices': Confeccion.ESTADO_CHOICES,
    })


@login_required
def crear_confeccion(request):
    if request.method == 'POST':
        form = ConfeccionForm(request.POST)
        if form.is_valid():
            confeccion = form.save(commit=False)
            confeccion.tipo = 'confeccion'
            confeccion.save()
            messages.success(request, 'Confección creada exitosamente.')
            return redirect('lista_confecciones')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = ConfeccionForm()
    return render(request, 'misastreria/confecciones/form.html', {
        'form': form,
        'titulo': 'Crear Confección'
    })

@login_required
def editar_confeccion(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if request.method == 'POST':
        form = ConfeccionForm(request.POST, instance=confeccion)
        if form.is_valid():
            form.save()
            messages.success(request, 'Confección actualizada exitosamente.')
            return redirect('lista_confecciones')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = ConfeccionForm(instance=confeccion)
    return render(request, 'misastreria/confecciones/form.html', {
        'form': form,
        'titulo': 'Editar Confección',
        'confeccion': confeccion
    })

@login_required
def eliminar_confeccion(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if request.method == 'POST':
        try:
            confeccion.delete()
            messages.success(request, 'Confección eliminada exitosamente.')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar la confección porque está asociada a otros registros.')
        return redirect('lista_confecciones')
    return render(request, 'misastreria/confecciones/eliminar.html', {'confeccion': confeccion})

@login_required
def entregar_confeccion(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    if confeccion.estado == 'entregado':
        messages.error(request, 'La confección ya está marcada como entregada.')
        return redirect('lista_confecciones')
    if request.method == 'POST':
        confeccion.estado = 'entregado'
        confeccion.saldo = 0
        confeccion.save()
        messages.success(request, f'Confección {confeccion.codigo} marcada como entregada.')
        return redirect('lista_confecciones')
    return render(request, 'misastreria/confecciones/entregar.html', {'confeccion': confeccion})

@login_required
def exportar_recibo_confeccion_pdf(request, id):
    confeccion = get_object_or_404(Confeccion, id=id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="recibo_confeccion_{confeccion.codigo}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Recibo de Confección", styles['Heading1']))
    elements.append(Paragraph(f"Código: {confeccion.codigo}", styles['Normal']))

    data = [
        ['Campo', 'Valor'],
        ['Fecha Inicio', confeccion.fecha_inicio.strftime('%d/%m/%Y')],
        ['Tipo de Prenda', confeccion.get_tipo_prenda_display()],
        ['Color', confeccion.color],
        ['Modelo', confeccion.modelo],
        ['Cliente', str(confeccion.cliente)],
        ['Precio', f"${confeccion.precio:.2f}"],
        ['Fecha de Prueba', confeccion.fecha_prueba.strftime('%d/%m/%Y')],
        ['Fecha de Entrega', confeccion.fecha_entrega.strftime('%d/%m/%Y')],
        ['Adelanto', f"${confeccion.adelanto:.2f}"],
        ['Saldo', f"${confeccion.saldo:.2f}"],
    ]

    table = Table(data, colWidths=[150, 350])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response

@login_required
def lista_alquileres(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()

    hoy = date.today()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    alquileres = Alquiler.objects.all().order_by('-fecha_alquiler')
    if q:
        alquileres = alquileres.filter(
            Q(codigo__icontains=q) |
            Q(articulo__articulo__icontains=q) |
            Q(cliente__nombres__icontains=q) |
            Q(cliente__apellido_paterno__icontains=q) |
            Q(cliente__ci__icontains=q)
        )
    if estado:
        alquileres = alquileres.filter(estado=estado)
    if desde:
        alquileres = alquileres.filter(fecha_alquiler__gte=desde)
    if hasta:
        alquileres = alquileres.filter(fecha_alquiler__lte=hasta)

    total = alquileres.count()
    paginator = Paginator(alquileres, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/alquileres/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'estado': estado,
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'estado_choices': Alquiler.ESTADO_OPCIONES,
    })


@login_required
def crear_alquiler(request):
    if request.method == 'POST':
        form = AlquilerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Alquiler creado exitosamente.')
            return redirect('lista_alquileres')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = AlquilerForm()
    return render(request, 'misastreria/alquileres/form.html', {
        'form': form,
        'titulo': 'Crear Alquiler'
    })

@login_required
def editar_alquiler(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if request.method == 'POST':
        form = AlquilerForm(request.POST, instance=alquiler)
        if form.is_valid():
            form.save()
            messages.success(request, 'Alquiler actualizado exitosamente.')
            return redirect('lista_alquileres')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = AlquilerForm(instance=alquiler)
    return render(request, 'misastreria/alquileres/form.html', {
        'form': form,
        'titulo': 'Editar Alquiler',
        'alquiler': alquiler
    })

@login_required
def eliminar_alquiler(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if request.method == 'POST':
        if alquiler.estado == 'alquilado':
            alquiler.articulo.cantidad += alquiler.cantidad
            alquiler.articulo.save()
        alquiler.delete()
        messages.success(request, 'Alquiler eliminado exitosamente.')
        return redirect('lista_alquileres')
    return render(request, 'misastreria/alquileres/eliminar.html', {'alquiler': alquiler})

@login_required
def devolver_alquiler(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    if alquiler.estado == 'devuelto':
        messages.error(request, 'El alquiler ya está marcado como devuelto.')
        return redirect('lista_alquileres')
    if request.method == 'POST':
        alquiler.estado = 'devuelto'
        alquiler.save()  # Esto restaura el stock vía Alquiler.save()
        messages.success(request, f'Alquiler {alquiler.codigo} marcado como devuelto. Stock restaurado.')
        return redirect('lista_alquileres')
    return render(request, 'misastreria/alquileres/devolver.html', {'alquiler': alquiler})

@login_required
def exportar_comprobante_alquiler_pdf(request, id):
    alquiler = get_object_or_404(Alquiler, id=id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="comprobante_alquiler_{alquiler.codigo}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Comprobante de Alquiler", styles['Heading1']))
    elements.append(Paragraph(f"Código: {alquiler.codigo}", styles['Normal']))

    data = [
        ['Campo', 'Valor'],
        ['Cliente', str(alquiler.cliente) if alquiler.cliente else '-'],
        ['Artículo', str(alquiler.articulo)],
        ['Costo de Alquiler', f"${alquiler.costo_alquiler:.2f}"],
        ['Fecha de Alquiler', alquiler.fecha_alquiler.strftime('%d/%m/%Y')],
        ['Fecha de Devolución', alquiler.fecha_devolucion.strftime('%d/%m/%Y')],
        ['Garantía', alquiler.garantia or '-'],
    ]

    table = Table(data, colWidths=[150, 350])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    doc.build(elements)
    return response

@login_required
def lista_transacciones(request):
    q = request.GET.get('q', '').strip()
    tipo_transaccion = request.GET.get('tipo_transaccion', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    periodo = request.GET.get('periodo', '').strip()

    hoy = date.today()
    if periodo == 'semana':
        desde = (hoy - timedelta(days=7)).isoformat()
        hasta = ''
    elif periodo == 'mes':
        desde = hoy.replace(day=1).isoformat()
        hasta = ''
    elif not desde and not hasta:
        periodo = periodo or '3meses'
        desde = (hoy - timedelta(days=90)).isoformat()

    transacciones = Transaccion.objects.all().order_by('-fecha')
    if q:
        transacciones = transacciones.filter(
            Q(codigo__icontains=q) |
            Q(descripcion__icontains=q)
        )
    if tipo_transaccion:
        transacciones = transacciones.filter(tipo_transaccion=tipo_transaccion)
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
        'desde': desde,
        'hasta': hasta,
        'periodo': periodo,
        'tipo_transaccion_choices': Transaccion.TIPO_TRANSACCION_CHOICES,
    })


@login_required
def crear_transaccion(request):
    if request.method == 'POST':
        form = TransaccionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transacción creada exitosamente.')
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
def lista_inventario(request):
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', 'ACT').strip()

    inventarios = Inventario.objects.all().order_by('-fecha_ingreso')
    if q:
        inventarios = inventarios.filter(
            Q(codigo__icontains=q) |
            Q(articulo__icontains=q)
        )
    if estado:
        inventarios = inventarios.filter(estado=estado)

    total = inventarios.count()
    paginator = Paginator(inventarios, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'misastreria/inventario/lista.html', {
        'page_obj': page_obj,
        'total': total,
        'q': q,
        'estado': estado,
        'estado_choices': Inventario.ESTADO_OPCIONES,
    })


@login_required
def crear_inventario(request):
    if request.method == 'POST':
        form = InventarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Artículo de inventario creado exitosamente.')
            return redirect('lista_inventario')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = InventarioForm()
    return render(request, 'misastreria/inventario/form.html', {
        'form': form,
        'titulo': 'Crear Artículo de Inventario'
    })

@login_required
def editar_inventario(request, id):
    inventario = get_object_or_404(Inventario, id=id)
    if request.method == 'POST':
        form = InventarioForm(request.POST, instance=inventario)
        if form.is_valid():
            form.save()
            messages.success(request, 'Artículo de inventario actualizado exitosamente.')
            return redirect('lista_inventario')
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = InventarioForm(instance=inventario)
    return render(request, 'misastreria/inventario/form.html', {
        'form': form,
        'titulo': 'Editar Artículo de Inventario'
    })

@login_required
def eliminar_inventario(request, id):
    inventario = get_object_or_404(Inventario, id=id)
    if request.method == 'POST':
        try:
            inventario.delete()
            messages.success(request, 'Artículo de inventario eliminado exitosamente.')
        except ProtectedError:
            messages.error(request, 'No se puede eliminar el artículo porque está asociado a una o más ventas.')
        return redirect('lista_inventario')
    return render(request, 'misastreria/inventario/eliminar.html', {'inventario': inventario})

@login_required
def dar_baja_inventario(request, id):
    inventario = get_object_or_404(Inventario, id=id)
    if inventario.estado == 'BAJ':
        messages.error(request, 'El artículo ya está dado de baja.')
        return redirect('lista_inventario')
    
    if request.method == 'POST':
        form = BajaInventarioForm(request.POST)
        if form.is_valid():
            cantidad_baja = form.cleaned_data['cantidad']
            if cantidad_baja > inventario.cantidad:
                messages.error(request, f"La cantidad a dar de baja ({cantidad_baja}) no puede exceder la cantidad disponible ({inventario.cantidad}).")
                return render(request, 'misastreria/inventario/baja.html', {
                    'form': form,
                    'inventario': inventario,
                    'titulo': 'Dar de Baja Artículo de Inventario'
                })
            try:
                baja = form.save(commit=False)
                baja.inventario = inventario
                baja.save()
                inventario.cantidad -= cantidad_baja
                if inventario.cantidad == 0:
                    inventario.estado = 'BAJ'
                    inventario.fecha_baja = baja.fecha_baja
                    inventario.motivo_baja = baja.motivo_baja
                inventario.save()
                messages.success(request, f'{cantidad_baja} unidades dadas de baja exitosamente.')
                return redirect('lista_inventario')
            except ValidationError as e:
                messages.error(request, f"Error al dar de baja: {e}")
        else:
            messages.error(request, f"Por favor corrige los errores: {form.errors.as_text()}")
    else:
        form = BajaInventarioForm()
    return render(request, 'misastreria/inventario/baja.html', {
        'form': form,
        'inventario': inventario,
        'titulo': 'Dar de Baja Artículo de Inventario'
    })

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
            e.get_tipo_contrato_display(),
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
            e.get_tipo_contrato_display(),
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
            'reparaciones': cliente.reparaciones_set.count(), # Asumo 'reparaciones_set' si no hay related_name
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

    context = {
        'form': form,
        'reparaciones': reparaciones_filtradas,
        'selected_fecha_inicio': selected_fecha_inicio,
        'selected_fecha_fin': selected_fecha_fin,
        'selected_cliente': selected_cliente,
        'selected_empleado': selected_empleado,
        'selected_tipo_prenda': selected_tipo_prenda,
        'selected_estado': selected_estado,
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
            tipo_prenda_display = dict(Reparacion.TIPO_PRENDA_CHOICES).get(filtros_aplicados['tipo_prenda'], filtros_aplicados['tipo_prenda'])
            filter_text_lines.append(f"Tipo de Prenda: {tipo_prenda_display}.")
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
        Paragraph('Tipo Prenda', styles['TableHeader']),
        Paragraph('Tipo Reparación', styles['TableHeader']),
        Paragraph('Costo (BOB)', styles['TableHeader']),
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Empleado', styles['TableHeader']),
        Paragraph('Estado', styles['TableHeader'])
    ]]

    for rep in reparaciones_data:
        table_data.append([
            Paragraph(str(rep.codigo), styles['TableContent']),
            Paragraph(rep.fecha_entrega.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(rep.get_tipo_prenda_display(), styles['TableContent']),
            Paragraph(rep.get_tipo_reparacion_display(), styles['TableContent']),
            Paragraph(f"{rep.costo:.2f}" if rep.costo is not None else "N/A", styles['TableContent']),
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

    col_widths = [0.8*inch, 1*inch, 1.2*inch, 1.2*inch, 0.8*inch, 1.5*inch, 1.5*inch, 0.8*inch]
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
            tipo_prenda_display = dict(Reparacion.TIPO_PRENDA_CHOICES).get(filtros_aplicados['tipo_prenda'], filtros_aplicados['tipo_prenda'])
            filter_text = f"Tipo de Prenda: {tipo_prenda_display}."
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
    headers = ['Código', 'Fecha Entrega', 'Tipo Prenda', 'Tipo Reparación', 'Costo (BOB)', 'Cliente', 'Empleado', 'Estado']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    # Datos de la tabla principal
    for rep in reparaciones_data:
        row_data = [
            str(rep.codigo),
            rep.fecha_entrega.strftime('%d/%m/%Y'),
            rep.get_tipo_prenda_display(),
            rep.get_tipo_reparacion_display(),
            float(rep.costo) if rep.costo is not None else "N/A",
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
    ventas = Venta.objects.all()
    clientes = Cliente.objects.all()
    empleados = Empleado.objects.all()
    articulos = Inventario.objects.all().order_by('articulo')

    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_id = request.GET.get('cliente')
    empleado_id = request.GET.get('empleado')
    selected_articulo_id = request.GET.get('articulo')

    if fecha_desde:
        ventas = ventas.filter(fecha_venta__gte=fecha_desde)
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        ventas = ventas.filter(fecha_venta__lt=fecha_hasta_dt)
    if cliente_id and cliente_id != '':
        ventas = ventas.filter(cliente__id=cliente_id)
    if empleado_id and empleado_id != '':
        ventas = ventas.filter(empleado__id=empleado_id)
    
    if selected_articulo_id and selected_articulo_id != '':
        ventas = ventas.filter(articulo__id=selected_articulo_id)

    ventas = ventas.order_by('fecha_venta')

    total_ventas = ventas.aggregate(Sum('precio_total'))['precio_total__sum'] or 0.00

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_ventas_pdf(request, ventas, fecha_desde, fecha_hasta, total_ventas)
    elif export_format == 'excel':
        return exportar_reporte_ventas_excel(request, ventas, fecha_desde, fecha_hasta, total_ventas)

    context = {
        'ventas': ventas,
        'clientes': clientes,
        'empleados': empleados,
        'articulos': articulos,
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_cliente': cliente_id,
        'selected_empleado': empleado_id,
        'selected_articulo': selected_articulo_id,
        'total_ventas': total_ventas,
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
    
    selected_articulo_id = request.GET.get('articulo')
    if selected_articulo_id and selected_articulo_id != '':
        try:
            articulo_obj = Inventario.objects.get(id=selected_articulo_id)
            filter_text += f"Nombre del Artículo: {articulo_obj.articulo}. "
        except ObjectDoesNotExist:
            filter_text += f"Artículo (ID {selected_articulo_id}) no encontrado. "
    else:
        filter_text += "Nombre del Artículo: Todos los Artículos. "


    if filter_text:
        elements.append(Paragraph(filter_text.strip(), styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    data = [[
        Paragraph('Código Venta', styles['TableHeader']),
        Paragraph('Fecha', styles['TableHeader']),
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Vendedor', styles['TableHeader']),
        Paragraph('Nombre del Artículo', styles['TableHeader']),
        Paragraph('Cant.', styles['TableHeader']),
        Paragraph('P. Unit (Bs.)', styles['TableHeader']),
        Paragraph('Total (Bs.)', styles['TableHeader'])
    ]]

    for venta in ventas:
        cliente_full_name = f"{venta.cliente.nombres} {venta.cliente.apellido_paterno} {venta.cliente.apellido_materno}".strip() if venta.cliente else "N/A"
        empleado_full_name = f"{venta.empleado.nombres} {venta.empleado.apellido_paterno}".strip() if hasattr(venta, 'empleado') and venta.empleado else "N/A"
        
        data.append([
            Paragraph(venta.codigo, styles['TableContent']),
            Paragraph(venta.fecha_venta.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(cliente_full_name, styles['TableContent']),
            Paragraph(empleado_full_name, styles['TableContent']),
            Paragraph(venta.articulo.articulo, styles['TableContent']),
            Paragraph(str(venta.cantidad), styles['TableContent']),
            Paragraph(f"{venta.precio_unitario:.2f}", styles['TableContent']),
            Paragraph(f"{venta.precio_total:.2f}", styles['TableContent'])
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
    
    selected_articulo_id = request.GET.get('articulo')
    if selected_articulo_id and selected_articulo_id != '':
        try:
            articulo_obj = Inventario.objects.get(id=selected_articulo_id)
            filter_text += f"Nombre del Artículo: {articulo_obj.articulo}. "
        except ObjectDoesNotExist:
            filter_text += f"Artículo (ID {selected_articulo_id}) no encontrado. "
    else:
        filter_text += "Nombre del Artículo: Todos los Artículos. "


    if filter_text:
        ws.merge_cells(f'A{filter_row}:H{filter_row}')
        ws[f'A{filter_row}'] = filter_text.strip()
        ws[f'A{filter_row}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        filter_row += 1
    
    header_row = filter_row + 1

    headers = ['Código Venta', 'Fecha', 'Cliente', 'Vendedor', 'Nombre del Artículo', 'Cantidad', 'P. Unitario (Bs.)', 'Total (Bs.)']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    for venta in ventas:
        cliente_full_name = f"{venta.cliente.nombres} {venta.cliente.apellido_paterno} {venta.cliente.apellido_materno}".strip() if venta.cliente else "N/A"
        empleado_full_name = f"{venta.empleado.nombres} {venta.empleado.apellido_paterno}".strip() if hasattr(venta, 'empleado') and venta.empleado else "N/A"

        row_data = [
            venta.codigo,
            venta.fecha_venta.strftime('%d/%m/%Y'),
            cliente_full_name,
            empleado_full_name,
            venta.articulo.articulo,
            venta.cantidad,
            venta.precio_unitario,
            venta.precio_total
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
    articulos = Inventario.objects.all().order_by('articulo') # O 'codigo', si es tu campo principal de nombre

    # Aquí puedes añadir lógica de filtrado si lo deseas, similar a reporte_ventas
    # Ejemplo:
    # categoria_id = request.GET.get('categoria')
    # if categoria_id:
    #     articulos = articulos.filter(categoria__id=categoria_id)

    context = {
        'articulos': articulos,
        # 'categorias': Categoria.objects.all(), # Si tienes un filtro por categoría
    }
    return render(request, 'misastreria/reportes/reporte_articulos.html', context)

@login_required
def reporte_confecciones(request):
    confecciones = Confeccion.objects.all()
    clientes = Cliente.objects.all()
    empleados = Empleado.objects.all()
    # Los artículos ahora son tipos de prenda del modelo Confeccion
    tipo_prenda_choices = Confeccion.TIPO_PRENDA_CHOICES 
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
        confecciones = confecciones.filter(tipo_prenda=selected_tipo_prenda)
    
    if selected_estado and selected_estado != '':
        confecciones = confecciones.filter(estado=selected_estado)

    confecciones = confecciones.order_by('fecha_inicio') 

    total_confecciones = confecciones.aggregate(Sum('precio'))['precio__sum'] or 0.00 # Suma 'precio' en lugar de 'precio_total'

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_confecciones_pdf(request, confecciones, fecha_desde, fecha_hasta, total_confecciones)
    elif export_format == 'excel':
        return exportar_reporte_confecciones_excel(request, confecciones, fecha_desde, fecha_hasta, total_confecciones)

    context = {
        'confecciones': confecciones,
        'clientes': clientes,
        'empleados': empleados,
        'tipo_prenda_choices': tipo_prenda_choices, # Pasa las opciones del modelo
        'estado_choices': estado_choices, # Pasa las opciones de estado
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_cliente': cliente_id,
        'selected_empleado': empleado_id,
        'selected_tipo_prenda': selected_tipo_prenda, # Cambiado a tipo_prenda
        'selected_estado': selected_estado, # Nuevo para el estado
        'total_confecciones': total_confecciones,
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
    
    selected_tipo_prenda = request.GET.get('tipo_prenda') # Usar tipo_prenda
    if selected_tipo_prenda and selected_tipo_prenda != '':
        # Obtener el display del tipo de prenda para el filtro
        tipo_prenda_display = dict(Confeccion.TIPO_PRENDA_CHOICES).get(selected_tipo_prenda, selected_tipo_prenda)
        filter_text += f"Tipo de Prenda: {tipo_prenda_display}. "
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
            Paragraph(confeccion.get_tipo_prenda_display(), styles['TableContent']), # Usar get_tipo_prenda_display
            Paragraph(confeccion.get_estado_display(), styles['TableContent']), # Usar get_estado_display
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
    
    selected_tipo_prenda = request.GET.get('tipo_prenda') # Usar tipo_prenda
    if selected_tipo_prenda and selected_tipo_prenda != '':
        tipo_prenda_display = dict(Confeccion.TIPO_PRENDA_CHOICES).get(selected_tipo_prenda, selected_tipo_prenda)
        filter_text += f"Tipo de Prenda: {tipo_prenda_display}. "
    else:
        filter_text += "Tipo de Prenda: Todas las Prendas. "

    selected_estado = request.GET.get('estado') # Nuevo filtro de estado
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
            confeccion.get_tipo_prenda_display(), # Usar get_tipo_prenda_display
            confeccion.get_estado_display(), # Usar get_estado_display
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
    alquileres = Alquiler.objects.all()
    clientes = Cliente.objects.all()
    articulos_inventario = Inventario.objects.all().order_by('articulo') # Para el filtro de artículo
    estado_alquiler_choices = Alquiler.ESTADO_OPCIONES

    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente_id = request.GET.get('cliente')
    selected_articulo_id = request.GET.get('articulo')
    selected_estado = request.GET.get('estado')

    # Aplicar filtros
    if fecha_desde:
        alquileres = alquileres.filter(fecha_alquiler__gte=fecha_desde) 
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        alquileres = alquileres.filter(fecha_alquiler__lt=fecha_hasta_dt)
    if cliente_id and cliente_id != '':
        alquileres = alquileres.filter(cliente__id=cliente_id)
    
    if selected_articulo_id and selected_articulo_id != '':
        alquileres = alquileres.filter(articulo__id=selected_articulo_id)
    
    if selected_estado and selected_estado != '':
        alquileres = alquileres.filter(estado=selected_estado)

    alquileres = alquileres.order_by('fecha_alquiler') 

    total_alquileres = alquileres.aggregate(Sum('costo_alquiler'))['costo_alquiler__sum'] or 0.00

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_alquileres_pdf(request, alquileres, fecha_desde, fecha_hasta, total_alquileres)
    elif export_format == 'excel':
        return exportar_reporte_alquileres_excel(request, alquileres, fecha_desde, fecha_hasta, total_alquileres)

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
    }
    return render(request, 'misastreria/reportes/reporte_alquileres.html', context)


def exportar_reporte_alquileres_pdf(request, alquileres, fecha_desde, fecha_hasta, total_alquileres):
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
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno} {cliente_obj.apellido_materno}. "
        except ObjectDoesNotExist:
            filter_text += f"Cliente (ID {request.GET.get('cliente')}) no encontrado. "
    
    selected_articulo_id = request.GET.get('articulo')
    if selected_articulo_id and selected_articulo_id != '':
        try:
            articulo_obj = Inventario.objects.get(id=selected_articulo_id)
            filter_text += f"Artículo: {articulo_obj.articulo}. "
        except ObjectDoesNotExist:
            filter_text += f"Artículo (ID {selected_articulo_id}) no encontrado. "
    else:
        filter_text += "Artículo: Todos los Artículos. "

    selected_estado = request.GET.get('estado')
    if selected_estado and selected_estado != '':
        estado_display = dict(Alquiler.ESTADO_OPCIONES).get(selected_estado, selected_estado)
        filter_text += f"Estado: {estado_display}. "
    else:
        filter_text += "Estado: Todos los Estados. "


    if filter_text:
        elements.append(Paragraph(filter_text.strip(), styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))

    data = [[
        Paragraph('Código Alq.', styles['TableHeader']),
        Paragraph('Fecha Alquiler', styles['TableHeader']),
        Paragraph('Cliente', styles['TableHeader']),
        Paragraph('Artículo', styles['TableHeader']),
        Paragraph('Cant.', styles['TableHeader']),
        Paragraph('Fecha Devolución', styles['TableHeader']),
        Paragraph('Estado', styles['TableHeader']),
        Paragraph('Costo (Bs.)', styles['TableHeader'])
    ]]

    for alquiler in alquileres:
        cliente_full_name = f"{alquiler.cliente.nombres} {alquiler.cliente.apellido_paterno} {alquiler.cliente.apellido_materno}".strip() if alquiler.cliente else "N/A"
        
        row_data = [
            Paragraph(alquiler.codigo, styles['TableContent']),
            Paragraph(alquiler.fecha_alquiler.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(cliente_full_name, styles['TableContent']),
            Paragraph(alquiler.articulo.articulo, styles['TableContent']),
            Paragraph(str(alquiler.cantidad), styles['TableContent']),
            Paragraph(alquiler.fecha_devolucion.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(alquiler.get_estado_display(), styles['TableContent']),
            Paragraph(f"{alquiler.costo_alquiler:.2f}", styles['TableContent'])
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
        0.8*inch, # Código Alq.
        0.9*inch, # Fecha Alquiler
        1.2*inch, # Cliente
        1.2*inch, # Artículo
        0.5*inch, # Cant.
        0.9*inch, # Fecha Devolución
        0.8*inch, # Estado
        0.8*inch  # Costo
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
    total_alignment = Alignment(horizontal="right")

    ws.merge_cells('A1:H1') # Ajusta el rango por el número de columnas (8 columnas)
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:H2') # Ajusta el rango por el número de columnas (8 columnas)
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
            filter_text += f"Cliente: {cliente_obj.nombres} {cliente_obj.apellido_paterno} {cliente_obj.apellido_materno}. "
        except ObjectDoesNotExist:
            filter_text += f"Cliente (ID {request.GET.get('cliente')}) no encontrado. "
    
    selected_articulo_id = request.GET.get('articulo')
    if selected_articulo_id and selected_articulo_id != '':
        try:
            articulo_obj = Inventario.objects.get(id=selected_articulo_id)
            filter_text += f"Artículo: {articulo_obj.articulo}. "
        except ObjectDoesNotExist:
            filter_text += f"Artículo (ID {selected_articulo_id}) no encontrado. "
    else:
        filter_text += "Artículo: Todos los Artículos. "

    selected_estado = request.GET.get('estado')
    if selected_estado and selected_estado != '':
        estado_display = dict(Alquiler.ESTADO_OPCIONES).get(selected_estado, selected_estado)
        filter_text += f"Estado: {estado_display}. "
    else:
        filter_text += "Estado: Todos los Estados. "


    if filter_text:
        ws.merge_cells(f'A{filter_row}:H{filter_row}') # Ajusta el rango por el número de columnas (8 columnas)
        ws[f'A{filter_row}'] = filter_text.strip()
        ws[f'A{filter_row}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        filter_row += 1
    
    header_row = filter_row + 1

    headers = ['Código Alq.', 'Fecha Alquiler', 'Cliente', 'Artículo', 'Cantidad', 'Fecha Devolución', 'Estado', 'Costo (Bs.)'] # Nuevos encabezados
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    for alquiler in alquileres:
        cliente_full_name = f"{alquiler.cliente.nombres} {alquiler.cliente.apellido_paterno} {alquiler.cliente.apellido_materno}".strip() if alquiler.cliente else "N/A"

        row_data = [
            alquiler.codigo,
            alquiler.fecha_alquiler.strftime('%d/%m/%Y'),
            cliente_full_name,
            alquiler.articulo.articulo,
            alquiler.cantidad,
            alquiler.fecha_devolucion.strftime('%d/%m/%Y'),
            alquiler.get_estado_display(),
            alquiler.costo_alquiler
        ]
        
        ws.append(row_data)
        for col_num, cell in enumerate(ws[ws.max_row]):
            cell.font = content_font
            cell.border = full_border
            if col_num == 7: # El Costo (Bs.) ahora está en la columna 7 (índice base 0)
                cell.number_format = '#,##0.00'
            else:
                cell.alignment = Alignment(horizontal="center")


    last_data_row = ws.max_row
    ws.merge_cells(start_row=last_data_row + 2, start_column=1, end_row=last_data_row + 2, end_column=7) # Ajusta el colspan a 7 para 8 columnas en total
    total_label_cell = ws.cell(row=last_data_row + 2, column=1)
    total_label_cell.value = "Total de Alquileres Filtrados: Bs."
    total_label_cell.font = total_font
    total_label_cell.alignment = total_alignment

    total_value_cell = ws.cell(row=last_data_row + 2, column=8) # El Total (Bs.) ahora está en la columna 8
    total_value_cell.value = total_alquileres
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
    response['Content-Disposition'] = 'attachment; filename="reporte_alquileres.xlsx"'
    wb.save(response)
    return response

# --- FIN de funciones de Reporte de Alquileres ---

@login_required
def reporte_transacciones(request):
    transacciones = Transaccion.objects.all()
    tipo_transaccion_choices = Transaccion.TIPO_TRANSACCION_CHOICES
    tipo_servicio_choices = Transaccion.TIPO_SERVICIO_CHOICES

    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    selected_tipo_transaccion = request.GET.get('tipo_transaccion')
    selected_tipo_servicio = request.GET.get('tipo_servicio')
    descripcion_filtro = request.GET.get('descripcion')

    # Aplicar filtros
    if fecha_desde:
        transacciones = transacciones.filter(fecha__gte=fecha_desde) 
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        transacciones = transacciones.filter(fecha__lt=fecha_hasta_dt)
    
    if selected_tipo_transaccion and selected_tipo_transaccion != '':
        transacciones = transacciones.filter(tipo_transaccion=selected_tipo_transaccion)
    
    if selected_tipo_servicio and selected_tipo_servicio != '':
        transacciones = transacciones.filter(tipo_servicio=selected_tipo_servicio)

    if descripcion_filtro:
        # Busca la descripción de forma insensible a mayúsculas/minúsculas y que contenga el texto
        transacciones = transacciones.filter(descripcion__icontains=descripcion_filtro)

    transacciones = transacciones.order_by('fecha') 

    # Calcular totales de ingresos y gastos
    total_ingresos = transacciones.filter(tipo_transaccion='ingreso').aggregate(Sum('monto'))['monto__sum'] or 0.00
    total_gastos = transacciones.filter(tipo_transaccion='gasto').aggregate(Sum('monto'))['monto__sum'] or 0.00
    saldo_neto = total_ingresos - total_gastos

    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_transacciones_pdf(request, transacciones, fecha_desde, fecha_hasta, total_ingresos, total_gastos, saldo_neto)
    elif export_format == 'excel':
        return exportar_reporte_transacciones_excel(request, transacciones, fecha_desde, fecha_hasta, total_ingresos, total_gastos, saldo_neto)

    context = {
        'transacciones': transacciones,
        'tipo_transaccion_choices': tipo_transaccion_choices,
        'tipo_servicio_choices': tipo_servicio_choices,
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_tipo_transaccion': selected_tipo_transaccion,
        'selected_tipo_servicio': selected_tipo_servicio,
        'selected_descripcion': descripcion_filtro,
        'total_ingresos': total_ingresos,
        'total_gastos': total_gastos,
        'saldo_neto': saldo_neto,
    }
    return render(request, 'misastreria/reportes/reporte_transacciones.html', context)


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

# --- INICIO de funciones de Reporte de INVENTARIO (NUEVO) ---

@login_required
def reporte_inventario(request):
    inventario_items = Inventario.objects.all()
    estado_choices = Inventario.ESTADO_OPCIONES
    categorias = Categoria.objects.all()

    # Parámetros de filtro
    articulo_filtro = request.GET.get('articulo')
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    selected_estado = request.GET.get('estado')
    selected_categoria_id = request.GET.get('categoria')
    selected_inventario_id = request.GET.get('inventario_id') # Para el "Kardex"

    # Aplicar filtros
    if articulo_filtro:
        inventario_items = inventario_items.filter(articulo__icontains=articulo_filtro)
    
    if fecha_desde:
        inventario_items = inventario_items.filter(fecha_ingreso__gte=fecha_desde) 
    if fecha_hasta:
        fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date() + timedelta(days=1)
        inventario_items = inventario_items.filter(fecha_ingreso__lt=fecha_hasta_dt)
    
    if selected_estado and selected_estado != '':
        inventario_items = inventario_items.filter(estado=selected_estado)

    if selected_categoria_id and selected_categoria_id != '':
        inventario_items = inventario_items.filter(categoria__id=selected_categoria_id)

    inventario_items = inventario_items.order_by('articulo')

    # Calcular valor total del inventario activo
    # Anotamos el valor total por item (cantidad * precio) antes de sumar
    valor_total_inventario_activo = Inventario.objects.filter(estado='ACT').annotate(
        valor_item=ExpressionWrapper(F('cantidad') * F('precio'), output_field=DecimalField())
    ).aggregate(total_valor=Sum('valor_item'))['total_valor'] or 0.00
    
    # Manejo del "Kardex" (movimientos de un artículo específico)
    articulo_seleccionado = None
    bajas_articulo = None
    if selected_inventario_id:
        try:
            articulo_seleccionado = Inventario.objects.get(id=selected_inventario_id)
            bajas_articulo = BajaInventario.objects.filter(inventario=articulo_seleccionado).order_by('fecha_baja')
        except ObjectDoesNotExist:
            articulo_seleccionado = None
            bajas_articulo = None


    export_format = request.GET.get('export_format')
    if export_format == 'pdf':
        return exportar_reporte_inventario_pdf(request, inventario_items, articulo_seleccionado, bajas_articulo, fecha_desde, fecha_hasta, selected_estado, selected_categoria_id, articulo_filtro, valor_total_inventario_activo)
    elif export_format == 'excel':
        return exportar_reporte_inventario_excel(request, inventario_items, articulo_seleccionado, bajas_articulo, fecha_desde, fecha_hasta, selected_estado, selected_categoria_id, articulo_filtro, valor_total_inventario_activo)


    context = {
        'inventario_items': inventario_items,
        'estado_choices': estado_choices,
        'categorias': categorias,
        'selected_articulo': articulo_filtro,
        'selected_fecha_desde': fecha_desde,
        'selected_fecha_hasta': fecha_hasta,
        'selected_estado': selected_estado,
        'selected_categoria_id': selected_categoria_id,
        'selected_inventario_id': selected_inventario_id, # Pasa el ID seleccionado
        'articulo_seleccionado': articulo_seleccionado, # Pasa el objeto para sus detalles
        'bajas_articulo': bajas_articulo, # Pasa las bajas si hay un artículo seleccionado
        'valor_total_inventario_activo': valor_total_inventario_activo,
    }
    return render(request, 'misastreria/reportes/reporte_inventario.html', context)


def exportar_reporte_inventario_pdf(request, inventario_items, articulo_seleccionado, bajas_articulo, fecha_desde, fecha_hasta, selected_estado, selected_categoria_id, articulo_filtro, valor_total_inventario_activo):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=inch/4, leftMargin=inch/4,
                            topMargin=inch/4, bottomMargin=inch/4)
    styles = getSampleStyleSheet()

    # Estilos personalizados (asegúrate de que DejaVuSans esté registrado)
    styles.add(ParagraphStyle(name='CompanyTitle',
                              fontSize=20, leading=24, alignment=1, fontName='DejaVuSans', textColor=colors.HexColor('#1e3a8a')))
    styles.add(ParagraphStyle(name='ReportTitle',
                              fontSize=16, leading=20, alignment=1, fontName='DejaVuSans', textColor=colors.HexColor('#2563eb')))
    styles.add(ParagraphStyle(name='SubTitle',
                              fontSize=10, leading=12, alignment=1, fontName='DejaVuSans'))
    styles.add(ParagraphStyle(name='TableHeader',
                              fontSize=9, fontName='DejaVuSans', alignment=1))
    styles.add(ParagraphStyle(name='TableContent',
                              fontSize=7, fontName='DejaVuSans', alignment=0))
    styles.add(ParagraphStyle(name='TotalStyle',
                              fontSize=10, fontName='DejaVuSans', alignment=2))
    styles.add(ParagraphStyle(name='KardexTitle',
                              fontSize=14, leading=18, alignment=0, fontName='DejaVuSans', textColor=colors.HexColor('#10b981'))) # Color para Kardex
    styles.add(ParagraphStyle(name='KardexContent',
                              fontSize=8, fontName='DejaVuSans', alignment=0))


    elements = []

    elements.append(Paragraph("SISTEMA DE GESTION SASTRERIA CONFORT Y MAS", styles['CompanyTitle']))
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(Paragraph("REPORTE DE INVENTARIO", styles['ReportTitle']))
    elements.append(Spacer(1, 0.2 * inch))

    # Filtros aplicados
    filter_text_lines = []
    if articulo_filtro:
        filter_text_lines.append(f"Artículo contiene: '{articulo_filtro}'.")
    if fecha_desde and fecha_hasta:
        filter_text_lines.append(f"Fecha de Ingreso: {fecha_desde} al {fecha_hasta}.")
    elif fecha_desde:
        filter_text_lines.append(f"Fecha de Ingreso Desde: {fecha_desde}.")
    elif fecha_hasta:
        filter_text_lines.append(f"Fecha de Ingreso Hasta: {fecha_hasta}.")
    
    estado_display = dict(Inventario.ESTADO_OPCIONES).get(selected_estado, "Todos")
    filter_text_lines.append(f"Estado: {estado_display}.")

    if selected_categoria_id:
        try:
            categoria_obj = Categoria.objects.get(id=selected_categoria_id)
            filter_text_lines.append(f"Categoría: {categoria_obj.nombre}.")
        except ObjectDoesNotExist:
            pass # Categoría no encontrada
    else:
        filter_text_lines.append("Categoría: Todas.")

    if filter_text_lines:
        for line in filter_text_lines:
            elements.append(Paragraph(line, styles['SubTitle']))
        elements.append(Spacer(1, 0.1 * inch))


    # Tabla principal de Inventario
    data = [[
        Paragraph('Código', styles['TableHeader']),
        Paragraph('Artículo', styles['TableHeader']),
        Paragraph('Cant.', styles['TableHeader']),
        Paragraph('Costo (Bs.)', styles['TableHeader']),
        Paragraph('Precio (Bs.)', styles['TableHeader']),
        Paragraph('F. Ingreso', styles['TableHeader']),
        Paragraph('Categoría', styles['TableHeader']),
        Paragraph('Estado', styles['TableHeader']),
    ]]

    for item in inventario_items:
        row_data = [
            Paragraph(item.codigo, styles['TableContent']),
            Paragraph(item.articulo, styles['TableContent']),
            Paragraph(str(item.cantidad), styles['TableContent']),
            Paragraph(f"{item.costo:.2f}" if item.costo is not None else "N/A", styles['TableContent']),
            Paragraph(f"{item.precio:.2f}", styles['TableContent']),
            Paragraph(item.fecha_ingreso.strftime('%d/%m/%Y'), styles['TableContent']),
            Paragraph(item.categoria.nombre if item.categoria else 'Sin Categoría', styles['TableContent']),
            Paragraph(item.get_estado_display(), styles['TableContent']),
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
        1.5*inch,  # Artículo
        0.5*inch,  # Cant.
        0.8*inch,  # Costo
        0.8*inch,  # Precio
        0.9*inch,  # F. Ingreso
        1.0*inch,  # Categoría
        0.6*inch   # Estado
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.2 * inch))

    # Total del valor de inventario activo
    elements.append(Paragraph(f"Valor Total de Inventario Activo: Bs. {valor_total_inventario_activo:.2f}", styles['TotalStyle']))
    elements.append(Spacer(1, 0.2 * inch))

    # Sección de Kardex (si hay un artículo seleccionado)
    if articulo_seleccionado:
        elements.append(PageBreak()) # Nueva página para el Kardex
        elements.append(Paragraph(f"KARDEX DEL ARTÍCULO: {articulo_seleccionado.articulo} ({articulo_seleccionado.codigo})", styles['KardexTitle']))
        elements.append(Spacer(1, 0.1 * inch))

        elements.append(Paragraph(f"Fecha de Ingreso Inicial: {articulo_seleccionado.fecha_ingreso.strftime('%d/%m/%Y')}", styles['KardexContent']))
        elements.append(Paragraph(f"Cantidad Actual: {articulo_seleccionado.cantidad}", styles['KardexContent']))
        elements.append(Paragraph(f"Estado: {articulo_seleccionado.get_estado_display()}", styles['KardexContent']))
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("MOVIMIENTOS DE BAJA:", styles['KardexContent']))
        elements.append(Spacer(1, 0.05 * inch))

        if bajas_articulo:
            kardex_data = [[
                Paragraph('Fecha Baja', styles['TableHeader']),
                Paragraph('Cantidad Baja', styles['TableHeader']),
                Paragraph('Motivo Baja', styles['TableHeader'])
            ]]
            for baja in bajas_articulo:
                kardex_data.append([
                    Paragraph(baja.fecha_baja.strftime('%d/%m/%Y'), styles['TableContent']),
                    Paragraph(str(baja.cantidad), styles['TableContent']),
                    Paragraph(baja.motivo_baja, styles['TableContent'])
                ])
            
            kardex_table = Table(kardex_data, colWidths=[1.5*inch, 1.5*inch, 3.0*inch])
            kardex_table.setStyle(table_style) # Reusar estilo de tabla
            elements.append(kardex_table)
        else:
            elements.append(Paragraph("No hay movimientos de baja registrados para este artículo.", styles['KardexContent']))

    doc.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_inventario.pdf"'
    return response


def exportar_reporte_inventario_excel(request, inventario_items, articulo_seleccionado, bajas_articulo, fecha_desde, fecha_hasta, selected_estado, selected_categoria_id, articulo_filtro, valor_total_inventario_activo):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte de Inventario"

    # Estilos de Excel
    header_font = Font(name='Calibri', bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    border_style = Side(border_style="thin", color="000000")
    full_border = Border(left=border_style, right=border_style, top=border_style, bottom=border_style)
    
    content_font = Font(name='Calibri', size=10)
    total_font = Font(name='Calibri', bold=True, size=12)
    total_alignment = Alignment(horizontal="right")
    
    # Títulos principales
    ws.merge_cells('A1:H1') # 8 columnas
    ws['A1'] = "SISTEMA DE GESTION SASTRERIA CONFORT Y MAS"
    ws['A1'].font = Font(name='Calibri', size=20, bold=True, color='1E3A8A')
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells('A2:H2') # 8 columnas
    ws['A2'] = "REPORTE DE INVENTARIO"
    ws['A2'].font = Font(name='Calibri', size=16, bold=True, color='2563EB')
    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")

    # Filtros aplicados
    filter_row_start = 4
    filter_col_span = 8
    filter_text_lines = []
    if articulo_filtro:
        filter_text_lines.append(f"Artículo contiene: '{articulo_filtro}'.")
    if fecha_desde and fecha_hasta:
        filter_text_lines.append(f"Fecha de Ingreso: {fecha_desde} al {fecha_hasta}.")
    elif fecha_desde:
        filter_text_lines.append(f"Fecha de Ingreso Desde: {fecha_desde}.")
    elif fecha_hasta:
        filter_text_lines.append(f"Fecha de Ingreso Hasta: {fecha_hasta}.")
    
    estado_display = dict(Inventario.ESTADO_OPCIONES).get(selected_estado, "Todos")
    filter_text_lines.append(f"Estado: {estado_display}.")

    if selected_categoria_id:
        try:
            categoria_obj = Categoria.objects.get(id=selected_categoria_id)
            filter_text_lines.append(f"Categoría: {categoria_obj.nombre}.")
        except ObjectDoesNotExist:
            pass
    else:
        filter_text_lines.append("Categoría: Todas.")

    for i, line in enumerate(filter_text_lines):
        ws.merge_cells(start_row=filter_row_start + i, start_column=1, end_row=filter_row_start + i, end_column=filter_col_span)
        ws[f'A{filter_row_start + i}'] = line
        ws[f'A{filter_row_start + i}'].font = Font(name='Calibri', size=10)
        ws[f'A{filter_row_start + i}'].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    header_row = filter_row_start + len(filter_text_lines) + 1


    # Cabecera de la tabla principal
    headers = ['Código', 'Artículo', 'Cantidad', 'Costo (Bs.)', 'Precio (Bs.)', 'Fecha Ingreso', 'Categoría', 'Estado']
    ws.append(headers)

    for col_num, cell in enumerate(ws[header_row]):
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = full_border

    # Datos de la tabla principal
    for item in inventario_items:
        row_data = [
            item.codigo,
            item.articulo,
            item.cantidad,
            item.costo,
            item.precio,
            item.fecha_ingreso.strftime('%d/%m/%Y'),
            item.categoria.nombre if item.categoria else 'Sin Categoría',
            item.get_estado_display(),
        ]
        ws.append(row_data)
        for col_num, cell in enumerate(ws[ws.max_row]):
            cell.font = content_font
            cell.border = full_border
            if col_num in [3, 4]: # Costo y Precio
                cell.number_format = '#,##0.00'
            elif col_num == 2: # Cantidad
                cell.number_format = '#,##0'
            else:
                cell.alignment = Alignment(horizontal="center")

    last_data_row = ws.max_row

    # Total del valor de inventario activo
    total_label_row = last_data_row + 2
    ws.merge_cells(start_row=total_label_row, start_column=1, end_row=total_label_row, end_column=7) # Ajusta el colspan
    total_label = ws.cell(row=total_label_row, column=1)
    total_label.value = "Valor Total de Inventario Activo:"
    total_label.font = total_font
    total_label.alignment = total_alignment
    
    total_value = ws.cell(row=total_label_row, column=8)
    total_value.value = valor_total_inventario_activo
    total_value.font = Font(name='Calibri', bold=True, size=12, color='059669') # Verde
    total_value.alignment = Alignment(horizontal="right")
    total_value.number_format = '#,##0.00'


    # Sección de Kardex (si hay un artículo seleccionado)
    if articulo_seleccionado:
        kardex_start_row = ws.max_row + 4
        ws.merge_cells(start_row=kardex_start_row, start_column=1, end_row=kardex_start_row, end_column=8)
        ws.cell(row=kardex_start_row, column=1).value = f"KARDEX DEL ARTÍCULO: {articulo_seleccionado.articulo} ({articulo_seleccionado.codigo})"
        ws.cell(row=kardex_start_row, column=1).font = Font(name='Calibri', size=14, bold=True, color='10B981')
        ws.cell(row=kardex_start_row, column=1).alignment = Alignment(horizontal="center")

        kardex_start_row += 2
        ws.merge_cells(start_row=kardex_start_row, start_column=1, end_row=kardex_start_row, end_column=3)
        ws.cell(row=kardex_start_row, column=1).value = f"Fecha de Ingreso Inicial: {articulo_seleccionado.fecha_ingreso.strftime('%d/%m/%Y')}"
        ws.cell(row=kardex_start_row, column=1).font = content_font
        ws.cell(row=kardex_start_row, column=1).alignment = Alignment(horizontal="left")

        kardex_start_row += 1
        ws.merge_cells(start_row=kardex_start_row, start_column=1, end_row=kardex_start_row, end_column=3)
        ws.cell(row=kardex_start_row, column=1).value = f"Cantidad Actual: {articulo_seleccionado.cantidad}"
        ws.cell(row=kardex_start_row, column=1).font = content_font
        ws.cell(row=kardex_start_row, column=1).alignment = Alignment(horizontal="left")

        kardex_start_row += 1
        ws.merge_cells(start_row=kardex_start_row, start_column=1, end_row=kardex_start_row, end_column=3)
        ws.cell(row=kardex_start_row, column=1).value = f"Estado: {articulo_seleccionado.get_estado_display()}"
        ws.cell(row=kardex_start_row, column=1).font = content_font
        ws.cell(row=kardex_start_row, column=1).alignment = Alignment(horizontal="left")

        kardex_start_row += 2
        ws.merge_cells(start_row=kardex_start_row, start_column=1, end_row=kardex_start_row, end_column=3)
        ws.cell(row=kardex_start_row, column=1).value = "MOVIMIENTOS DE BAJA:"
        ws.cell(row=kardex_start_row, column=1).font = content_font
        ws.cell(row=kardex_start_row, column=1).alignment = Alignment(horizontal="left")

        kardex_start_row += 1
        if bajas_articulo:
            kardex_headers = ['Fecha Baja', 'Cantidad Baja', 'Motivo Baja']
            ws.append(kardex_headers)
            for col_num, cell in enumerate(ws[ws.max_row]):
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = full_border

            for baja in bajas_articulo:
                ws.append([
                    baja.fecha_baja.strftime('%d/%m/%Y'),
                    baja.cantidad,
                    baja.motivo_baja
                ])
                for col_num, cell in enumerate(ws[ws.max_row]):
                    cell.font = content_font
                    cell.border = full_border
                    if col_num == 1: # Cantidad Baja
                        cell.number_format = '#,##0'
                    else:
                        cell.alignment = Alignment(horizontal="center")
        else:
            ws.merge_cells(start_row=ws.max_row + 1, start_column=1, end_row=ws.max_row + 1, end_column=3)
            ws.cell(row=ws.max_row + 1, column=1).value = "No hay movimientos de baja registrados para este artículo."
            ws.cell(row=ws.max_row + 1, column=1).font = content_font
            ws.cell(row=ws.max_row + 1, column=1).alignment = Alignment(horizontal="center")


    # Ajustar ancho de columnas para todas las columnas existentes
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
    response['Content-Disposition'] = 'attachment; filename="reporte_inventario.xlsx"'
    wb.save(response)
    return response

# --- FIN de funciones de Reporte de Inventario ---

@login_required
def reporte_stock(request):
    inventarios = Inventario.objects.all()
    return render(request, 'misastreria/reportes/stock.html', {'inventarios': inventarios})

@login_required
def reporte_ingresos(request):
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    transacciones = Transaccion.objects.all()
    
    if fecha_inicio and fecha_fin:
        transacciones = transacciones.filter(fecha__range=[fecha_inicio, fecha_fin])
    
    total_ingresos = transacciones.aggregate(Sum('precio'))['precio__sum'] or 0
    return render(request, 'misastreria/reportes/ingresos.html', {
        'transacciones': transacciones,
        'total_ingresos': total_ingresos,
    })