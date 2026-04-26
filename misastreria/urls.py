from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import RedirectView

urlpatterns = [
    # Redirige la URL base del sistema a la página de login
    path('', RedirectView.as_view(pattern_name='login', permanent=False), name='index'),

    # Login y Logout
    path('login/', LoginView.as_view(template_name='misastreria/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    # Empleados
    path('empleados/', views.lista_empleados, name='lista_empleados'),
    path('empleados/crear/', views.crear_empleado, name='crear_empleado'),
    path('empleados/editar/<int:id>/', views.editar_empleado, name='editar_empleado'),
    path('empleados/eliminar/<int:id>/', views.eliminar_empleado, name='eliminar_empleado'),
    path('empleados/permiso/<int:empleado_id>/', views.crear_permiso, name='crear_permiso'),
    path('empleados/falta/<int:empleado_id>/', views.crear_falta, name='crear_falta'),
    path('empleados/reporte/dias_trabajados/', views.reporte_dias_trabajados, name='reporte_dias_trabajados'),
    # Clientes
    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('clientes/buscar/', views.buscar_clientes, name='buscar_clientes'),
    path('clientes/crear/', views.crear_cliente, name='crear_cliente'),
    path('clientes/editar/<int:id>/', views.editar_cliente, name='editar_cliente'),
    path('clientes/eliminar/<int:id>/', views.eliminar_cliente, name='eliminar_cliente'),
    path('clientes/<int:id>/historial/', views.historial_cliente, name='historial_cliente'),
    # Reparaciones
    path('reparaciones/', views.lista_reparaciones, name='lista_reparaciones'),
    path('reparaciones/crear/', views.crear_reparacion, name='crear_reparacion'),
    path('reparaciones/editar/<int:id>/', views.editar_reparacion, name='editar_reparacion'),
    path('reparaciones/eliminar/<int:id>/', views.eliminar_reparacion, name='eliminar_reparacion'),
    path('reparaciones/recibo_reparacion/<int:id>/', views.exportar_recibo_reparacion_pdf, name='exportar_recibo_reparacion_pdf'),
    path('reparaciones/entregado/<int:id>/', views.marcar_entregado, name='marcar_entregado'),
    # Ventas
    path('ventas/', views.lista_ventas, name='lista_ventas'),
    path('ventas/crear/', views.crear_venta, name='crear_venta'),
    path('ventas/editar/<int:id>/', views.editar_venta, name='editar_venta'),
    path('ventas/eliminar/<int:id>/', views.eliminar_venta, name='eliminar_venta'),
    path('ventas/recibo/<int:id>/', views.exportar_recibo_pdf, name='exportar_recibo_pdf'),
    path('ventas/get_precio_articulo/', views.get_precio_articulo, name='get_precio_articulo'),
    # Confecciones
    path('confecciones/', views.lista_confecciones, name='lista_confecciones'),
    path('confecciones/crear/', views.crear_confeccion, name='crear_confeccion'),
    path('confecciones/editar/<int:id>/', views.editar_confeccion, name='editar_confeccion'),
    path('confecciones/eliminar/<int:id>/', views.eliminar_confeccion, name='eliminar_confeccion'),
     # Alquileres
    path('alquileres/', views.lista_alquileres, name='lista_alquileres'),
    path('alquileres/crear/', views.crear_alquiler, name='crear_alquiler'),
    path('alquileres/editar/<int:id>/', views.editar_alquiler, name='editar_alquiler'),
    path('alquileres/eliminar/<int:id>/', views.eliminar_alquiler, name='eliminar_alquiler'),
    path('alquileres/devolver/<int:id>/', views.devolver_alquiler, name='devolver_alquiler'),
    path('alquileres/comprobante/pdf/<int:id>/', views.exportar_comprobante_alquiler_pdf, name='exportar_comprobante_alquiler_pdf'),
    # Confecciones
    path('confecciones/', views.lista_confecciones, name='lista_confecciones'),
    path('confecciones/crear/', views.crear_confeccion, name='crear_confeccion'),
    path('confecciones/editar/<int:id>/', views.editar_confeccion, name='editar_confeccion'),
    path('confecciones/eliminar/<int:id>/', views.eliminar_confeccion, name='eliminar_confeccion'),
    path('confecciones/entregar/<int:id>/', views.entregar_confeccion, name='entregar_confeccion'),
    path('confecciones/recibo/<int:id>/', views.exportar_recibo_confeccion_pdf, name='exportar_recibo_confeccion_pdf'),
    # Inventario
    path('inventario/', views.lista_inventario, name='lista_inventario'),
    path('inventario/crear/', views.crear_inventario, name='crear_inventario'),
    path('inventario/editar/<int:id>/', views.editar_inventario, name='editar_inventario'),
    path('inventario/eliminar/<int:id>/', views.eliminar_inventario, name='eliminar_inventario'),
    path('inventario/baja/<int:id>/', views.dar_baja_inventario, name='dar_baja_inventario'),
    # Transacciones
    path('transacciones/', views.lista_transacciones, name='lista_transacciones'),
    path('transacciones/crear/', views.crear_transaccion, name='crear_transaccion'),
    path('transacciones/editar/<int:id>/', views.editar_transaccion, name='editar_transaccion'),
    path('transacciones/eliminar/<int:id>/', views.eliminar_transaccion, name='eliminar_transaccion'),
    # Reportes
    path('reportes/empleados/', views.reporte_empleados, name='reporte_empleados'),
    path('reportes/empleados/pdf/', views.exportar_empleados_pdf, name='exportar_empleados_pdf'),
    path('reportes/empleados/excel/', views.exportar_empleados_excel, name='exportar_empleados_excel'),
    path('reportes/clientes/', views.reporte_clientes, name='reporte_clientes'),
    path('reportes/reparaciones/', views.reporte_reparaciones, name='reporte_reparaciones'),
    path('reportes/reparaciones/pdf/', views.exportar_reparaciones_pdf, name='exportar_reparaciones_pdf'),
    path('reportes/reparaciones/excel/', views.exportar_reparaciones_excel, name='exportar_reparaciones_excel'),
    path('reportes/ventas/', views.reporte_ventas, name='reporte_ventas'),
    path('reportes/confecciones/', views.reporte_confecciones, name='reporte_confecciones'),
    path('reportes/alquileres/', views.reporte_alquileres, name='reporte_alquileres'),
    path('reportes/transacciones/', views.reporte_transacciones, name='reporte_transacciones'),
    path('reportes/inventario/', views.reporte_inventario, name='reporte_inventario'),
    path('reportes/articulos/', views.reporte_articulos, name='reporte_articulos'),
    path('reportes/stock/', views.reporte_stock, name='reporte_stock'),
    path('reportes/ingresos/', views.reporte_ingresos, name='reporte_ingresos'),
]