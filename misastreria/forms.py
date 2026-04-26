from django import forms
from .models import Empleado, Cliente, Reparacion, Venta, Confeccion, Alquiler, Transaccion, Inventario, Permiso, Falta, BajaInventario
from django.forms import DateInput
import re
class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = ['codigo', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'email', 'tipo_contrato', 'fecha_ingreso', 'fecha_baja', 'activo']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'tipo_contrato': forms.Select(attrs={'class': 'form-control'}),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_baja': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PermisoForm(forms.ModelForm):
    class Meta:
        model = Permiso
        fields = ['fecha_permiso', 'motivo']
        widgets = {
            'fecha_permiso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control'}),
        }

class FaltaForm(forms.ModelForm):
    class Meta:
        model = Falta
        fields = ['fecha_falta', 'motivo']
        widgets = {
            'fecha_falta': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['codigo', 'nombres', 'apellido_paterno', 'apellido_materno', 'edad', 'celular', 'email', 'fecha_registro', 'notas']
        labels = {
            'codigo': 'Código de Cliente',
            'nombres': 'Nombres',
            'apellido_paterno': 'Apellido Paterno',
            'apellido_materno': 'Apellido Materno',
            'edad': 'Edad',
            'celular': 'Celular',
            'email': 'Correo Electrónico',
            'fecha_registro': 'Fecha de Registro',
            'notas': 'Notas',
        }
        widgets = {
            'fecha_registro': forms.DateInput(attrs={'type': 'date'}),
            'notas': forms.Textarea(attrs={'rows': 3}),
        }

class ReparacionForm(forms.ModelForm):
    class Meta:
        model = Reparacion
        fields = [
            'codigo', 'tipo_prenda', 'otro_prenda', 'tipo_reparacion', 'otro_reparacion',
            'costo', 'detalles', 'fecha_entrega', 'empleado', 'cliente', 'estado'
        ]
        widgets = {
            'fecha_entrega': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'detalles': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'tipo_prenda': forms.Select(attrs={'class': 'form-control'}),
            'tipo_reparacion': forms.Select(attrs={'class': 'form-control'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'otro_prenda': forms.TextInput(attrs={'class': 'form-control'}),
            'otro_reparacion': forms.TextInput(attrs={'class': 'form-control'}),
            'costo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'empleado': forms.Select(attrs={'class': 'form-control'}),
            'cliente': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        tipo_prenda = cleaned_data.get('tipo_prenda')
        otro_prenda = cleaned_data.get('otro_prenda')
        tipo_reparacion = cleaned_data.get('tipo_reparacion')
        otro_reparacion = cleaned_data.get('otro_reparacion')
        costo = cleaned_data.get('costo')
        cliente = cleaned_data.get('cliente')

        if tipo_prenda == 'otro' and not otro_prenda:
            self.add_error('otro_prenda', "Especifique otra prenda si selecciona 'Otro'.")
        elif tipo_prenda != 'otro':
            cleaned_data['otro_prenda'] = ''

        if tipo_reparacion == 'otro' and not otro_reparacion:
            self.add_error('otro_reparacion', "Especifique otra reparación si selecciona 'Otro'.")
        elif tipo_reparacion != 'otro':
            cleaned_data['otro_reparacion'] = ''

        if costo is not None and costo < 0:
            self.add_error('costo', "El costo no puede ser negativo.")
        
        if not cliente:
            self.add_error('cliente', "Debe seleccionar un cliente.")

        return cleaned_data


class EmpleadoReporteForm(forms.Form):
    fecha_inicio = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    fecha_fin = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    tipo_contrato = forms.ChoiceField(choices=[('', 'Todos')] + Empleado.TIPO_CONTRATO_CHOICES, required=False)


class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['codigo', 'fecha_venta', 'articulo', 'cantidad', 'cliente']
        labels = {
            'codigo': 'Código',
            'fecha_venta': 'Fecha de Venta',
            'articulo': 'Artículo',
            'cantidad': 'Cantidad',
            'cliente': 'Cliente',
        }
        widgets = {
            'fecha_venta': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'articulo': forms.Select(attrs={'class': 'form-control'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'cliente': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        cantidad = cleaned_data.get('cantidad')
        articulo = cleaned_data.get('articulo')
        codigo = cleaned_data.get('codigo')
        if cantidad and cantidad <= 0:
            self.add_error('cantidad', "La cantidad debe ser mayor que cero.")
        if articulo and cantidad and cantidad > articulo.cantidad:
            self.add_error('cantidad', f"No hay suficiente stock. Stock disponible: {articulo.cantidad}")
        if codigo and not codigo.startswith('VEN-'):
            self.add_error('codigo', "El código debe comenzar con 'VEN-'.")
        return cleaned_data


class ConfeccionForm(forms.ModelForm):
    class Meta:
        model = Confeccion
        fields = [
            'codigo', 'fecha_inicio', 'tipo_prenda', 'color', 'modelo', 'cliente', 'empleado', 'observaciones',
            'pantalon_largo_total', 'pantalon_contorno_cintura', 'pantalon_contorno_cadera',
            'pantalon_largo_entrepierna', 'pantalon_contorno_pierna', 'pantalon_contorno_rodilla',
            'pantalon_contorno_bota', 'pantalon_tiro_delantero', 'pantalon_tiro_trasero',
            'chaleco_contorno_busto', 'chaleco_contorno_cintura', 'chaleco_contorno_cadera',
            'chaleco_largo_talle', 'chaleco_largo_total', 'chaleco_altura_botones',
            'saco_contorno_busto', 'saco_contorno_cintura', 'saco_contorno_cadera',
            'saco_largo_talle', 'saco_largo_total', 'saco_ancho_hombros',
            'saco_ancho_espalda', 'saco_contorno_brazo', 'saco_largo_manga', 'saco_contorno_puno',
            'saco_mujer_contorno_busto', 'saco_mujer_contorno_cintura', 'saco_mujer_contorno_cadera',
            'saco_mujer_ancho_hombros', 'saco_mujer_ancho_espalda', 'saco_mujer_largo_talle',
            'saco_mujer_largo_total', 'saco_mujer_altura_busto', 'saco_mujer_separacion_busto',
            'saco_mujer_dif_talle',
            'chaleco_mujer_contorno_busto', 'chaleco_mujer_contorno_cintura', 'chaleco_mujer_contorno_cadera',
            'chaleco_mujer_largo_talle', 'chaleco_mujer_largo_total', 'chaleco_mujer_altura_busto',
            'chaleco_mujer_separacion_busto', 'chaleco_mujer_largo_delantero',
            'precio', 'adelanto', 'saldo', 'fecha_prueba', 'fecha_entrega', 'estado'
        ]
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_prueba': forms.DateInput(attrs={'type': 'date'}),
            'fecha_entrega': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            ultimo = Confeccion.objects.order_by('-id').first()
            numero = (ultimo.id + 1) if ultimo else 1
            self.initial['codigo'] = f"CONF-{numero:03d}"

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo']
        if not re.match(r'^CONF-\d{3}$', codigo):
            raise forms.ValidationError("El código debe tener el formato CONF-XXX (tres dígitos).")
        return codigo


class AlquilerForm(forms.ModelForm):
    class Meta:
        model = Alquiler
        fields = ['codigo', 'fecha_alquiler', 'articulo', 'cantidad', 'costo_alquiler', 'fecha_devolucion', 'estado', 'cliente', 'garantia']
        labels = {
            'codigo': 'Código',
            'fecha_alquiler': 'Fecha de Alquiler',
            'articulo': 'Artículo',
            'cantidad': 'Cantidad',
            'costo_alquiler': 'Costo de Alquiler',
            'fecha_devolucion': 'Fecha de Devolución',
            'estado': 'Estado',
            'cliente': 'Cliente',
            'garantia': 'Garantía',
        }
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'fecha_alquiler': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'articulo': forms.Select(attrs={'class': 'form-control'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'costo_alquiler': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'fecha_devolucion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
            'cliente': forms.Select(attrs={'class': 'form-control'}),
            'garantia': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['articulo'].queryset = Inventario.objects.filter(estado='ACT', cantidad__gt=0)
        if not self.instance.pk:
            last = Alquiler.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.initial['codigo'] = f"ALQ-{numero:03d}"

class TransaccionForm(forms.ModelForm):
    class Meta:
        model = Transaccion
        fields = ['codigo', 'tipo_transaccion', 'descripcion', 'tipo_servicio', 'fecha', 'cantidad', 'monto']
        labels = {
            'codigo': 'Código',
            'tipo_transaccion': 'Tipo de Transacción',
            'descripcion': 'Descripción',
            'tipo_servicio': 'Tipo de Servicio',
            'fecha': 'Fecha',
            'cantidad': 'Cantidad',
            'monto': 'Monto',
        }
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'tipo_transaccion': forms.Select(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'tipo_servicio': forms.Select(attrs={'class': 'form-control'}),
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            last = Transaccion.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.initial['codigo'] = f"TXN-{numero:03d}"

class InventarioForm(forms.ModelForm):
    class Meta:
        model = Inventario
        fields = ['codigo', 'articulo', 'cantidad', 'costo', 'precio', 'fecha_ingreso', 'categoria', 'estado']
        labels = {
            'codigo': 'Código',
            'articulo': 'Artículo',
            'cantidad': 'Cantidad',
            'costo': 'Costo (Opcional)',
            'precio': 'Precio',
            'fecha_ingreso': 'Fecha de Ingreso',
            'categoria': 'Categoría',
            'estado': 'Estado',
        }
        widgets = {
            'fecha_ingreso': forms.DateInput(attrs={'type': 'date'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'articulo': forms.TextInput(attrs={'class': 'form-control'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
            'costo': forms.NumberInput(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-control'}),
            'estado': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        precio = cleaned_data.get('precio')
        if precio is not None and precio <= 0:
            self.add_error('precio', "El precio debe ser mayor que cero.")
        return cleaned_data




class BajaInventarioForm(forms.ModelForm):
    class Meta:
        model = BajaInventario
        fields = ['cantidad', 'fecha_baja', 'motivo_baja']
        labels = {
            'cantidad': 'Cantidad a Dar de Baja',
            'fecha_baja': 'Fecha de Baja',
            'motivo_baja': 'Motivo de Baja',
        }
        widgets = {
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'fecha_baja': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'motivo_baja': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        cantidad = cleaned_data.get('cantidad')
        fecha_baja = cleaned_data.get('fecha_baja')
        motivo_baja = cleaned_data.get('motivo_baja')
        if not cantidad:
            self.add_error('cantidad', "La cantidad a dar de baja es obligatoria.")
        if not fecha_baja:
            self.add_error('fecha_baja', "La fecha de baja es obligatoria.")
        if not motivo_baja:
            self.add_error('motivo_baja', "El motivo de baja es obligatorio.")
        return cleaned_data

class EmpleadoReporteForm(forms.Form):
    fecha_inicio = forms.DateField(required=False, label="Desde", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    fecha_fin = forms.DateField(required=False, label="Hasta", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    tipo_contrato = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos')] + Empleado.TIPO_CONTRATO_CHOICES,
        label="Tipo de Contrato",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class ClienteReporteForm(forms.Form):
    fecha_inicio = forms.DateField(
        label="Fecha de Registro Desde",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    fecha_fin = forms.DateField(
        label="Fecha de Registro Hasta",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    TIPO_OPERACION_CHOICES = [
        ('', 'Todas las Operaciones'),
        ('ventas', 'Ventas'),
        ('reparaciones', 'Reparaciones'),
        ('confecciones', 'Confecciones'),
        ('alquileres', 'Alquileres'),
    ]
    tipo_operacion = forms.ChoiceField(
        label="Tipo de Operación",
        choices=TIPO_OPERACION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class ReparacionReporteForm(forms.Form):
    fecha_inicio = forms.DateField(
        label="Fecha de Entrega Desde", # Cambiado a "Fecha de Entrega Desde" para mayor claridad
        required=False,
        widget=DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    fecha_fin = forms.DateField(
        label="Fecha de Entrega Hasta", # Cambiado a "Fecha de Entrega Hasta" para mayor claridad
        required=False,
        widget=DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all().order_by('nombres', 'apellido_paterno'), # Ordenado por nombre y apellido
        label="Cliente",
        required=False,
        empty_label="-- Seleccione Cliente --",
        widget=forms.Select(attrs={'class': 'form-select'}) # Usando form-select
    )
    empleado = forms.ModelChoiceField(
        queryset=Empleado.objects.all().order_by('nombres', 'apellido_paterno'), # Ordenado por nombre y apellido
        label="Empleado Encargado", # Cambiado a "Empleado Encargado" para mayor claridad
        required=False,
        empty_label="-- Seleccione Empleado --",
        widget=forms.Select(attrs={'class': 'form-select'}) # Usando form-select
    )
    tipo_prenda = forms.ChoiceField(
        choices=[('', '-- Seleccione Tipo de Prenda --')] + list(Reparacion.TIPO_PRENDA_CHOICES),
        label="Tipo de Prenda",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}) # Usando form-select
    )
    estado = forms.ChoiceField(
        choices=[('', '-- Seleccione Estado --')] + list(Reparacion.ESTADO_CHOICES),
        label="Estado",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}) # Usando form-select
    )