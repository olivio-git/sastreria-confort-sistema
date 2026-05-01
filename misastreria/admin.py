from django.contrib import admin
from .models import Cliente, PrendaInventario, Insumo, Venta, VentaItem, Alquiler, AlquilerItem, Transaccion, Reparacion, Empleado, Permiso, Falta, Confeccion, OrdenProduccion, InsumoCortado

admin.site.register(Reparacion)
admin.site.register(Empleado)
admin.site.register(Permiso)
admin.site.register(Falta)
admin.site.register(Confeccion)

@admin.register(PrendaInventario)
class PrendaInventarioAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombre', 'tipo', 'talla', 'color', 'condicion', 'cantidad', 'precio', 'estado']
    list_filter  = ['tipo', 'condicion', 'estado']
    search_fields = ['codigo', 'nombre', 'color', 'talla', 'codigo_referencia']
    list_per_page = 20
    readonly_fields = ['codigo', 'veces_alquilado']

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

@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'descripcion', 'tipo_servicio', 'fecha', 'cantidad', 'monto']
    list_filter   = ['tipo_servicio', 'fecha']
    search_fields = ['codigo', 'descripcion']
    list_per_page = 20

class InsumoCortadoInline(admin.TabularInline):
    model = InsumoCortado
    extra = 1

@admin.register(OrdenProduccion)
class OrdenProduccionAdmin(admin.ModelAdmin):
    list_display  = ['codigo', 'descripcion', 'estado', 'empleado', 'fecha_inicio', 'fecha_estimada']
    list_filter   = ['estado', 'fecha_inicio']
    search_fields = ['codigo', 'descripcion', 'empleado__nombres']
    readonly_fields = ['codigo']
    list_per_page = 20
    inlines = [InsumoCortadoInline]
