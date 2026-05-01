from django import forms
from django.utils.safestring import mark_safe
from .models import Empleado, Cliente, Reparacion, Venta, VentaItem, Confeccion, ConfeccionItem, Alquiler, AlquilerItem, Transaccion, PrendaInventario, Insumo, Permiso, Falta, OrdenProduccion, InsumoCortado
from django.forms import DateInput, inlineformset_factory


class BolivianPhoneWidget(forms.TextInput):
    def render(self, name, value, attrs=None, renderer=None):
        if value and str(value).startswith('+591'):
            value = str(value)[4:]
        attrs = attrs or {}
        attrs.setdefault('class', 'form-control')
        attrs.setdefault('placeholder', '71234567')
        attrs.setdefault('inputmode', 'numeric')
        attrs.setdefault('pattern', '[0-9]+')
        input_html = super().render(name, value, attrs, renderer)
        return mark_safe(f'<div class="input-group"><span class="input-group-text">+591</span>{input_html}</div>')


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = ['ci', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'tipo_contrato', 'fecha_ingreso', 'fecha_baja']
        widgets = {
            'ci': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': BolivianPhoneWidget(),
            'tipo_contrato': forms.Select(attrs={'class': 'form-select'}),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'fecha_baja': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
        }
        labels = {
            'fecha_baja': 'Fecha de Despido / Baja',
        }
        help_texts = {
            'fecha_baja': 'Completar solo si el empleado ya no trabaja aquí. Deja en blanco si sigue activo.',
        }

    def clean_celular(self):
        celular = self.cleaned_data.get('celular', '').strip()
        if celular and not celular.startswith('+'):
            celular = '+591' + celular
        return celular

class PermisoForm(forms.ModelForm):
    class Meta:
        model = Permiso
        fields = ['fecha_permiso', 'motivo']
        widgets = {
            'fecha_permiso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'motivo': forms.TextInput(attrs={'class': 'form-control'}),
        }

class FaltaForm(forms.ModelForm):
    class Meta:
        model = Falta
        fields = ['fecha_falta', 'motivo']
        widgets = {
            'fecha_falta': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'motivo': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['ci', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'notas']
        labels = {
            'ci': 'CI (Cédula de Identidad)',
            'nombres': 'Nombres',
            'apellido_paterno': 'Apellido Paterno',
            'apellido_materno': 'Apellido Materno',
            'celular': 'Celular',
            'notas': 'Notas',
        }
        widgets = {
            'ci': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': BolivianPhoneWidget(),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_celular(self):
        celular = self.cleaned_data.get('celular', '').strip()
        if celular and not celular.startswith('+'):
            celular = '+591' + celular
        return celular

class ReparacionForm(forms.ModelForm):
    class Meta:
        model = Reparacion
        fields = [
            'tipo_prenda', 'otro_prenda', 'tipo_reparacion', 'otro_reparacion',
            'costo', 'detalles', 'fecha_entrega', 'empleado', 'cliente', 'estado'
        ]
        widgets = {
            'fecha_entrega': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'detalles': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'tipo_prenda': forms.Select(attrs={'class': 'form-control'}),
            'tipo_reparacion': forms.Select(attrs={'class': 'form-control'}),
            'estado': forms.Select(attrs={'class': 'form-control'}),
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


class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['fecha_venta', 'cliente', 'empleado', 'descuento', 'notas']
        widgets = {
            'fecha_venta': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'descuento': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        descuento = cleaned_data.get('descuento')
        if descuento is not None and not (0 <= descuento <= 100):
            self.add_error('descuento', "El descuento debe estar entre 0 y 100.")
        return cleaned_data


class VentaItemForm(forms.ModelForm):
    class Meta:
        model = VentaItem
        fields = ['articulo', 'cantidad', 'precio_unitario']
        widgets = {
            'articulo':        forms.Select(attrs={'class': 'form-select item-articulo'}),
            'cantidad':        forms.NumberInput(attrs={'class': 'form-control item-cantidad', 'min': '1'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control item-precio', 'step': '0.01', 'min': '0'}),
        }


class ConfeccionForm(forms.ModelForm):
    class Meta:
        model = Confeccion
        fields = [
            'fecha_inicio', 'color', 'modelo', 'cliente', 'empleado', 'observaciones',
            'precio', 'adelanto', 'saldo', 'fecha_prueba', 'fecha_entrega', 'estado',
        ]
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_prueba': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_entrega': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'saldo': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'


class ConfeccionItemForm(forms.ModelForm):
    class Meta:
        model = ConfeccionItem
        fields = [
            'tipo_prenda',
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
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tp = self.fields['tipo_prenda']
        tp.widget.attrs.update({'class': 'form-select form-select-sm tipo-prenda-select'})
        tp.choices = [('', '— Tipo de prenda —')] + list(ConfeccionItem.TIPO_PRENDA_CHOICES)
        tp.required = False
        for name in list(self.fields.keys()):
            if name == 'tipo_prenda':
                continue
            self.fields[name].widget = forms.NumberInput(attrs={
                'class': 'form-control form-control-sm medida-input',
                'step': '0.01',
                'style': 'width:5.5rem',
            })
            self.fields[name].required = False


ConfeccionItemFormSet = inlineformset_factory(
    Confeccion, ConfeccionItem,
    form=ConfeccionItemForm,
    extra=1,
    can_delete=True,
)

class AlquilerForm(forms.ModelForm):
    class Meta:
        model = Alquiler
        fields = ['fecha_alquiler', 'fecha_devolucion', 'estado', 'cliente', 'empleado', 'descuento', 'garantia', 'notas']
        widgets = {
            'fecha_alquiler':   forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_devolucion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'estado':    forms.Select(attrs={'class': 'form-select'}),
            'descuento': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'garantia': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notas':    forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        fecha_alquiler   = cleaned_data.get('fecha_alquiler')
        fecha_devolucion = cleaned_data.get('fecha_devolucion')
        if fecha_alquiler and fecha_devolucion and fecha_devolucion <= fecha_alquiler:
            self.add_error('fecha_devolucion', "La fecha de devolución debe ser posterior a la fecha de alquiler.")
        descuento = cleaned_data.get('descuento')
        if descuento is not None and not (0 <= descuento <= 100):
            self.add_error('descuento', "El descuento debe estar entre 0 y 100.")
        return cleaned_data


class AlquilerItemForm(forms.ModelForm):
    class Meta:
        model = AlquilerItem
        fields = ['articulo', 'cantidad', 'precio_unitario']
        widgets = {
            'articulo':       forms.Select(attrs={'class': 'form-select item-articulo'}),
            'cantidad':       forms.NumberInput(attrs={'class': 'form-control item-cantidad', 'min': '1'}),
            'precio_unitario':forms.NumberInput(attrs={'class': 'form-control item-precio', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['articulo'].queryset = PrendaInventario.objects.filter(tipo='alquiler', estado='ACT')
        self.fields['articulo'].empty_label = '— Seleccionar prenda —'

class TransaccionForm(forms.ModelForm):
    class Meta:
        model = Transaccion
        fields = ['tipo_transaccion', 'descripcion', 'tipo_servicio', 'fecha', 'cantidad', 'monto']
        labels = {
            'tipo_transaccion': 'Tipo de Transacción',
            'descripcion': 'Descripción',
            'tipo_servicio': 'Tipo de Servicio',
            'fecha': 'Fecha',
            'cantidad': 'Cantidad',
            'monto': 'Monto',
        }
        widgets = {
            'tipo_transaccion': forms.Select(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'tipo_servicio': forms.Select(attrs={'class': 'form-control'}),
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

class PrendaInventarioForm(forms.ModelForm):
    class Meta:
        model = PrendaInventario
        fields = [
            'tipo', 'nombre', 'modelo', 'talla', 'color', 'codigo_referencia',
            'condicion', 'cantidad', 'stock_minimo', 'precio', 'estado', 'notas',
        ]
        labels = {
            'tipo': 'Tipo',
            'nombre': 'Nombre',
            'modelo': 'Modelo / Línea',
            'talla': 'Talla',
            'color': 'Color',
            'codigo_referencia': 'Código de Referencia',
            'condicion': 'Condición',
            'cantidad': 'Cantidad en Stock',
            'stock_minimo': 'Stock Mínimo',
            'precio': 'Precio',
            'estado': 'Estado',
            'notas': 'Notas',
        }
        widgets = {
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'

    def clean(self):
        cleaned_data = super().clean()
        precio = cleaned_data.get('precio')
        if precio is not None and precio <= 0:
            self.add_error('precio', "El precio debe ser mayor que cero.")
        return cleaned_data


class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = [
            'tipo_material', 'articulo', 'coleccion', 'color', 'codigo_referencia',
            'tipo_tela', 'unidad_medida', 'cantidad', 'stock_minimo',
            'precio_costo', 'estado', 'proveedor', 'notas',
        ]
        labels = {
            'tipo_material': 'Tipo de Material',
            'articulo': 'Artículo',
            'coleccion': 'Colección / Cuaderno',
            'color': 'Color',
            'codigo_referencia': 'Código de Referencia',
            'tipo_tela': 'Tipo de Tela',
            'unidad_medida': 'Unidad de Medida',
            'cantidad': 'Cantidad',
            'stock_minimo': 'Stock Mínimo',
            'precio_costo': 'Precio de Costo',
            'estado': 'Estado',
            'proveedor': 'Proveedor',
            'notas': 'Notas',
        }
        widgets = {
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'

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


class OrdenProduccionForm(forms.ModelForm):
    class Meta:
        model = OrdenProduccion
        fields = ['descripcion', 'confeccion', 'fecha_inicio', 'fecha_estimada', 'empleado', 'notas']
        widgets = {
            'descripcion':    forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'fecha_inicio':   forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_estimada': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'notas':          forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'
        self.fields['confeccion'].required = False
        self.fields['fecha_estimada'].required = False
        self.fields['empleado'].required = False


class InsumoCortadoForm(forms.ModelForm):
    class Meta:
        model = InsumoCortado
        fields = ['insumo', 'cantidad']
        widgets = {
            'insumo':   forms.Select(attrs={'class': 'form-select item-insumo'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control item-cantidad', 'step': '0.001', 'min': '0.001'}),
        }