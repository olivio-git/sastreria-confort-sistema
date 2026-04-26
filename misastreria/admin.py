from django.contrib import admin
from .models import Cliente, Inventario, Venta, Categoria, Alquiler, Transaccion, Reparacion, Empleado, Permiso, Falta, BajaInventario, Confeccion, BajaInventario
from django.urls import reverse
from django.utils.html import format_html
from django.conf import settings

admin.site.register(Reparacion)
admin.site.register(Empleado)
admin.site.register(Permiso)
admin.site.register(Falta)
admin.site.register(Confeccion)

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre']
    search_fields = ['nombre']
    list_per_page = 20

@admin.register(Inventario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'articulo', 'cantidad', 'costo', 'precio', 'categoria', 'estado', 'fecha_ingreso', 'fecha_baja', 'ultima_modificacion', 'ver_bajas']
    list_filter = ['categoria', 'estado', 'fecha_ingreso', 'fecha_baja']
    search_fields = ['codigo', 'articulo', 'motivo_baja']
    list_per_page = 20
    readonly_fields = ['ultima_modificacion', 'estado']
    fieldsets = (
        (None, {
            'fields': ('codigo', 'articulo', 'categoria', 'estado')
        }),
        ('Detalles', {
            'fields': ('cantidad', 'costo', 'precio', 'fecha_ingreso', 'ultima_modificacion')
        }),
        ('Baja', {
            'fields': ('fecha_baja', 'motivo_baja')
        }),
    )

    def ver_bajas(self, obj):
        count = obj.bajas.count()
        url = reverse('admin:misastreria_bajainventario_changelist') + f'?inventario__id__exact={obj.id}'
        return format_html('<a href="{}">{} baja(s)</a>', url, count)
    ver_bajas.short_description = "Bajas"

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'email']
    search_fields = ['codigo', 'nombres', 'apellido_paterno', 'apellido_materno', 'email']
    list_per_page = 20

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'fecha_venta', 'articulo', 'cantidad', 'precio_unitario', 'precio_total', 'cliente']
    list_filter = ['fecha_venta', 'articulo', 'cliente']
    search_fields = ['codigo', 'articulo__articulo', 'cliente__nombres', 'cliente__apellido_paterno']
    readonly_fields = ['precio_unitario', 'precio_total']
    autocomplete_fields = ['articulo', 'cliente'] if 'dal' in settings.INSTALLED_APPS else []

@admin.register(BajaInventario)
class BajaInventarioAdmin(admin.ModelAdmin):
    list_display = ['inventario', 'cantidad', 'fecha_baja', 'motivo_baja', 'creado_en']
    list_filter = ['fecha_baja', 'inventario']
    search_fields = ['inventario__articulo', 'motivo_baja']
    list_per_page = 20
    readonly_fields = ['creado_en']

@admin.register(Alquiler)
class AlquilerAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'fecha_alquiler', 'articulo', 'cantidad', 'costo_alquiler', 'fecha_devolucion', 'estado', 'cliente']
    list_filter = ['fecha_alquiler', 'estado']
    search_fields = ['codigo', 'articulo__articulo', 'cliente__nombres']
    list_per_page = 20

@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'descripcion', 'tipo_servicio', 'fecha', 'cantidad', 'monto']
    list_filter = ['tipo_servicio', 'fecha']
    search_fields = ['codigo', 'descripcion']
    list_per_page = 20