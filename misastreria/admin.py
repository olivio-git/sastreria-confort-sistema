from django.contrib import admin
from .models import (
    Cliente, PrendaInventario, PrendaItem, Insumo,
    Venta, VentaItem, Alquiler, AlquilerItem, Transaccion,
    Reparacion, Empleado, Permiso, Falta, Confeccion,
    OrdenProduccion, OrdenProduccionEmpleado, InsumoCortado,
    TipoGasto, CajaSesion, CajaMovimiento,
)
from .kardex_events import (
    emit_ingreso, emit_alquiler, emit_venta, emit_baja, emit_devolucion,
    delete_eventos_alquiler, delete_eventos_venta,
)

admin.site.register(Reparacion)
admin.site.register(Empleado)
admin.site.register(Permiso)
admin.site.register(Falta)
admin.site.register(Confeccion)

@admin.register(PrendaInventario)
class PrendaInventarioAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'talla', 'color', 'precio', 'estado']
    list_filter  = ['estado']
    search_fields = ['codigo', 'nombre', 'color', 'talla', 'codigo_referencia']
    list_per_page = 20
    readonly_fields = ['codigo']


@admin.register(PrendaItem)
class PrendaItemAdmin(admin.ModelAdmin):
    list_display = ['codigo_item', 'prenda', 'tipo', 'condicion', 'estado', 'veces_alquilado', 'ubicacion']
    list_filter  = ['tipo', 'condicion', 'estado']
    search_fields = ['codigo_item', 'prenda__codigo', 'prenda__nombre']
    list_per_page = 20
    readonly_fields = ['codigo_item', 'creado', 'actualizado']

    def save_model(self, request, obj, form, change):
        prev_estado = None
        if change and obj.pk:
            prev_estado = PrendaItem.objects.filter(pk=obj.pk).values_list('estado', flat=True).first()
        super().save_model(request, obj, form, change)
        if not change:
            emit_ingreso(obj)
        elif prev_estado != 'baja' and obj.estado == 'baja':
            emit_baja(obj)

@admin.register(Insumo)
class InsumoAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'articulo', 'tipo_material', 'coleccion', 'color', 'cantidad', 'unidad_medida', 'estado']
    list_filter   = ['tipo_material', 'estado']
    search_fields = ['codigo', 'articulo', 'coleccion', 'color', 'codigo_referencia']
    list_per_page = 20
    readonly_fields = ['codigo']

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'email']
    search_fields = ['codigo', 'nombres', 'apellido_paterno', 'apellido_materno', 'email']
    list_per_page = 20

class VentaItemInline(admin.TabularInline):
    model = VentaItem
    extra = 1
    readonly_fields = ['subtotal']

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'fecha_venta', 'cliente', 'empleado', 'total']
    list_filter   = ['fecha_venta']
    search_fields = ['codigo', 'cliente__nombres', 'cliente__apellido_paterno']
    readonly_fields = ['subtotal', 'total']
    list_per_page = 20
    inlines = [VentaItemInline]

    def save_related(self, request, form, formsets, change):
        venta = form.instance
        if change:
            delete_eventos_venta(venta)
        super().save_related(request, form, formsets, change)
        for vi in venta.items.select_related('prenda_item').all():
            emit_venta(vi.prenda_item, venta, vi.precio_unitario)

class AlquilerItemInline(admin.TabularInline):
    model = AlquilerItem
    extra = 1
    readonly_fields = ['subtotal']

@admin.register(Alquiler)
class AlquilerAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'fecha_alquiler', 'cliente', 'total', 'fecha_devolucion', 'estado']
    list_filter   = ['fecha_alquiler', 'estado']
    search_fields = ['codigo', 'cliente__nombres']
    list_per_page = 20
    inlines       = [AlquilerItemInline]
    readonly_fields = ['subtotal', 'total']

    def save_related(self, request, form, formsets, change):
        alquiler = form.instance
        if change:
            delete_eventos_alquiler(alquiler)
        super().save_related(request, form, formsets, change)
        if alquiler.estado == 'alquilado':
            for ai in alquiler.items.select_related('prenda_item').all():
                emit_alquiler(ai.prenda_item, alquiler, ai.precio_unitario)

@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'descripcion', 'tipo_servicio', 'fecha', 'cantidad', 'monto']
    list_filter   = ['tipo_servicio', 'fecha']
    search_fields = ['codigo', 'descripcion']
    list_per_page = 20

class InsumoCortadoInline(admin.TabularInline):
    model = InsumoCortado
    extra = 1

class OrdenProduccionEmpleadoInline(admin.TabularInline):
    model = OrdenProduccionEmpleado
    extra = 1

@admin.register(OrdenProduccion)
class OrdenProduccionAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'descripcion', 'tipo', 'estado', 'fecha_inicio', 'fecha_estimada']
    list_filter   = ['tipo', 'estado', 'fecha_inicio']
    search_fields = ['codigo', 'descripcion', 'empleados_produccion__empleado__nombres']
    readonly_fields = ['codigo']
    list_per_page = 20
    inlines = [InsumoCortadoInline, OrdenProduccionEmpleadoInline]


# ============================================================
# MÓDULO DE CAJA
# ============================================================

@admin.register(TipoGasto)
class TipoGastoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo', 'creado']
    list_filter = ['activo']
    search_fields = ['nombre']
    list_per_page = 20


@admin.register(CajaSesion)
class CajaSesionAdmin(admin.ModelAdmin):
    list_display = ['id', 'fecha_apertura', 'estado', 'monto_apertura', 'diferencia', 'usuario_apertura']
    list_filter = ['estado']
    search_fields = ['id']
    readonly_fields = ['creado', 'monto_cierre_sistema', 'diferencia']
    list_per_page = 20


@admin.register(CajaMovimiento)
class CajaMovimientoAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'fecha', 'tipo', 'concepto', 'origen', 'forma_pago', 'monto', 'sesion']
    list_filter = ['tipo', 'concepto', 'origen', 'forma_pago']
    search_fields = ['codigo', 'descripcion']
    readonly_fields = ['codigo', 'creado', 'tipo']
    list_per_page = 20
