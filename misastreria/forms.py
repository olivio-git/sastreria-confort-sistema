from django import forms
from django.utils.safestring import mark_safe
from .models import (
    Empleado, TipoContrato, Cliente, Reparacion, ReparacionItem, TipoPrenda, TipoReparacion,
    Venta, VentaItem, Confeccion, ConfeccionItem, Alquiler, AlquilerItem,
    Transaccion, PrendaInventario, PrendaItem, Insumo, UnidadMedida,
    Permiso, Falta, OrdenProduccion, InsumoCortado,
    TipoGasto, CajaSesion, CajaMovimiento, FORMA_PAGO_CHOICES,
    Conjunto, ConjuntoSlot,
)
from django.forms import DateInput, inlineformset_factory
from django.core.exceptions import ValidationError


COUNTRY_CODE_CHOICES = [
    ('+591', 'Bolivia +591'),
    ('+54',  'Argentina +54'),
    ('+55',  'Brasil +55'),
    ('+56',  'Chile +56'),
    ('+57',  'Colombia +57'),
    ('+593', 'Ecuador +593'),
    ('+52',  'México +52'),
    ('+595', 'Paraguay +595'),
    ('+51',  'Perú +51'),
    ('+598', 'Uruguay +598'),
    ('+58',  'Venezuela +58'),
    ('+506', 'Costa Rica +506'),
    ('+53',  'Cuba +53'),
    ('+503', 'El Salvador +503'),
    ('+502', 'Guatemala +502'),
    ('+509', 'Haití +509'),
    ('+504', 'Honduras +504'),
    ('+505', 'Nicaragua +505'),
    ('+507', 'Panamá +507'),
    ('+501', 'Belice +501'),
    ('+34',  'España +34'),
    ('+1',   'Estados Unidos +1'),
    ('+1',   'Canadá +1'),
    ('+44',  'Reino Unido +44'),
    ('+33',  'Francia +33'),
    ('+49',  'Alemania +49'),
    ('+39',  'Italia +39'),
    ('+351', 'Portugal +351'),
    ('+31',  'Países Bajos +31'),
    ('+41',  'Suiza +41'),
    ('+81',  'Japón +81'),
    ('+86',  'China +86'),
    ('+61',  'Australia +61'),
]


class PhoneWidget(forms.TextInput):
    def _parse(self, value):
        if not value:
            return '+591', ''
        s = str(value)
        for code, _ in sorted(COUNTRY_CODE_CHOICES, key=lambda x: -len(x[0])):
            if s.startswith(code):
                return code, s[len(code):]
        # Código personalizado: extraer el prefijo + hasta que empieza el número
        if s.startswith('+'):
            import re
            m = re.match(r'(\+\d+)(.*)', s)
            if m:
                return m.group(1), m.group(2)
        return '+591', s

    def render(self, name, value, attrs=None, renderer=None):
        current_code, number = self._parse(value)
        attrs = dict(attrs or {})
        attrs['class'] = 'form-control'
        attrs.setdefault('placeholder', '71234567')
        attrs.setdefault('inputmode', 'numeric')
        attrs.setdefault('pattern', '[0-9]+')
        input_html = super().render(name, number, attrs, renderer)
        list_id = f'phone-codes-{name}'
        options = ''.join(
            f'<option value="{code}">{label}</option>'
            for code, label in COUNTRY_CODE_CHOICES
        )
        # datalist fuera del input-group para no interferir con Bootstrap
        datalist_html = f'<datalist id="{list_id}">{options}</datalist>'
        code_input = (
            f'<input type="text" name="{name}_pais" value="{current_code}" '
            f'list="{list_id}" class="form-control" style="max-width:120px;flex-shrink:0" '
            f'placeholder="+591">'
        )
        return mark_safe(f'{datalist_html}<div class="input-group">{code_input}{input_html}</div>')

    def value_from_datadict(self, data, files, name):
        number = (data.get(name) or '').strip()
        code   = (data.get(f'{name}_pais') or '+591').strip()
        if code and not code.startswith('+'):
            code = '+' + code
        return code + number if number else ''


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = ['ci', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'tipo_contrato', 'fecha_ingreso', 'fecha_baja']
        widgets = {
            'ci': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': PhoneWidget(),
            'tipo_contrato': forms.HiddenInput(),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'fecha_baja': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
        }
        labels = {
            'fecha_baja': 'Fecha de Despido / Baja',
        }
        help_texts = {
            'fecha_baja': 'Completar solo si el empleado ya no trabaja aquí. Deja en blanco si sigue activo.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_contrato'].required = False

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
        fields = ['ci', 'nombres', 'apellido_paterno', 'apellido_materno', 'celular', 'pais', 'notas']
        labels = {
            'ci': 'CI / Pasaporte',
            'nombres': 'Nombres',
            'apellido_paterno': 'Apellido Paterno',
            'apellido_materno': 'Apellido Materno',
            'celular': 'Celular',
            'pais': 'País',
            'notas': 'Notas',
        }
        widgets = {
            'ci': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12345678'}),
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': PhoneWidget(),
            'pais': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Bolivia', 'autocomplete': 'off'}),
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
        # empleado/porcentaje_comision ya no se editan aquí: se manejan como
        # asignaciones (varios empleados con % distinto). La vista setea el
        # empleado "lead" desde la primera asignación.
        fields = ['fecha_entrega', 'cliente', 'estado']
        widgets = {
            'fecha_entrega': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'estado':        forms.Select(attrs={'class': 'form-select'}),
            'cliente':       forms.HiddenInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('cliente'):
            self.add_error('cliente', "Debe seleccionar un cliente.")
        return cleaned_data


class ReparacionItemForm(forms.ModelForm):
    class Meta:
        model = ReparacionItem
        fields = ['tipo_prenda', 'tipo_reparacion', 'costo', 'detalles']
        widgets = {
            'tipo_prenda':     forms.HiddenInput(),
            'tipo_reparacion': forms.HiddenInput(),
            'costo':           forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'detalles':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Detalles opcionales'}),
        }


class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['fecha_venta', 'cliente', 'empleado', 'descuento', 'notas', 'estado']
        widgets = {
            'fecha_venta': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'descuento': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
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
        fields = ['prenda_item', 'precio_unitario']
        widgets = {
            'prenda_item':     forms.Select(attrs={'class': 'form-select item-prenda-item'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control item-precio', 'step': '0.01', 'min': '0'}),
        }


class ConfeccionForm(forms.ModelForm):
    class Meta:
        model = Confeccion
        # empleado/porcentaje_comision ya no se editan aquí: se manejan como
        # asignaciones (varios empleados con % distinto). La vista setea el
        # empleado "lead" desde la primera asignación.
        # adelanto/forma_pago/saldo ya NO se editan aquí: los pagos (adelanto inicial
        # y posteriores) se registran como movimientos confeccion_pago, permitiendo
        # varias formas de pago por cobro (pagos divididos). El precio se auto-calcula
        # de los costos por prenda.
        fields = [
            'fecha_inicio', 'color', 'modelo', 'cliente', 'garantia_meses', 'observaciones',
            'precio', 'fecha_prueba', 'fecha_entrega', 'estado',
        ]
        widgets = {
            'fecha_inicio':    forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_prueba':    forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_entrega':   forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'observaciones':   forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'garantia_meses':  forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 60, 'placeholder': 'Ej: 6'}),
            'precio':          forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'
        if self.instance.pk and self.instance.estado == 'entregado':
            self.fields['estado'].widget.attrs['disabled'] = True
            self.fields['estado'].required = False

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.pk and self.instance.estado == 'entregado':
            estado_enviado = cleaned_data.get('estado')
            if not estado_enviado:
                cleaned_data['estado'] = 'entregado'
            elif estado_enviado != 'entregado':
                self.add_error('estado', 'No se puede revertir el estado de una confección ya entregada.')
        return cleaned_data


class ConfeccionItemForm(forms.ModelForm):
    class Meta:
        model = ConfeccionItem
        fields = [
            'tipo_prenda', 'talla', 'costo',
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
        self.fields['tipo_prenda'].widget = forms.HiddenInput(attrs={'class': 'tipo-prenda-hidden'})
        self.fields['tipo_prenda'].required = False
        self.fields['talla'].widget = forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 42 ó 42-43', 'style': 'width:9rem'})
        self.fields['talla'].required = False
        self.fields['costo'].widget = forms.NumberInput(attrs={
            'class': 'form-control costo-input', 'step': '0.01', 'min': '0',
            'placeholder': '0.00', 'style': 'width:8rem;text-align:right',
        })
        self.fields['costo'].required = False
        for name in list(self.fields.keys()):
            if name in ('tipo_prenda', 'talla', 'costo'):
                continue
            self.fields[name].widget = forms.TextInput(attrs={
                'class': 'form-control medida-input',
                'style': 'width:7rem',
                'placeholder': '—',
            })
            self.fields[name].required = False


ConfeccionItemFormSet = inlineformset_factory(
    Confeccion, ConfeccionItem,
    form=ConfeccionItemForm,
    extra=1,
    can_delete=True,
)

class AlquilerForm(forms.ModelForm):
    adelanto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0',
            'placeholder': '0.00',
        }),
        label='Adelanto',
    )
    fecha_evento = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
        label='Fecha del evento',
    )

    class Meta:
        model = Alquiler
        fields = ['fecha_alquiler', 'fecha_devolucion', 'hora_devolucion', 'fecha_evento', 'estado', 'cliente', 'empleado', 'descuento', 'garantia_tipo', 'garantia_monto', 'garantia', 'notas', 'forma_pago']
        widgets = {
            'fecha_alquiler':   forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_devolucion': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'hora_devolucion':  forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'estado':         forms.HiddenInput(),
            'descuento':      forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'garantia_tipo':  forms.HiddenInput(),
            'garantia_monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'garantia':       forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Describa la garantía…'}),
            'notas':          forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'forma_pago':     forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estado'].required = False
        self.fields['garantia_tipo'].required = False
        self.fields['garantia_monto'].required = False
        self.fields['garantia'].required = False
        for name, field in self.fields.items():
            if name in ('estado', 'garantia_tipo'):
                continue
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'

    def clean(self):
        from decimal import Decimal
        cleaned_data = super().clean()
        fecha_alquiler   = cleaned_data.get('fecha_alquiler')
        fecha_devolucion = cleaned_data.get('fecha_devolucion')
        fecha_evento     = cleaned_data.get('fecha_evento')
        if fecha_alquiler and fecha_devolucion and fecha_devolucion < fecha_alquiler:
            self.add_error('fecha_devolucion', "La fecha de devolución no puede ser anterior a la fecha de alquiler.")
        if fecha_evento:
            if fecha_alquiler and fecha_evento < fecha_alquiler:
                self.add_error('fecha_evento', "La fecha del evento no puede ser anterior a la fecha de alquiler.")
            if fecha_devolucion and fecha_evento > fecha_devolucion:
                self.add_error('fecha_evento', "La fecha del evento no puede ser posterior a la fecha de devolución.")
        descuento = cleaned_data.get('descuento')
        if descuento is not None and not (0 <= descuento <= 100):
            self.add_error('descuento', "El descuento debe estar entre 0 y 100.")
        if not cleaned_data.get('estado'):
            cleaned_data['estado'] = 'alquilado'
        if cleaned_data.get('adelanto') is None:
            cleaned_data['adelanto'] = Decimal('0')
        return cleaned_data


class AlquilerItemForm(forms.ModelForm):
    class Meta:
        model = AlquilerItem
        fields = ['prenda_item', 'precio_unitario']
        widgets = {
            'prenda_item':    forms.Select(attrs={'class': 'form-select item-prenda-item'}),
            'precio_unitario':forms.NumberInput(attrs={'class': 'form-control item-precio', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prenda_item'].queryset = PrendaItem.objects.filter(
            tipo='alquiler', prenda__estado='ACT', estado='disponible'
        ).select_related('prenda')
        self.fields['prenda_item'].empty_label = '— Seleccionar item —'


class PagoAlquilerForm(forms.Form):
    from decimal import Decimal as _Decimal
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=_Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00',
        }),
        label='Monto',
    )
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Forma de pago',
    )
    descripcion = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nota (opcional)',
        }),
        label='Nota',
    )
    via_caja = forms.BooleanField(
        required=False,
        initial=True,
        label='Registrar en caja',
        help_text='Si no está marcado, el pago queda en reserva y no entra a caja hasta el pago final.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
    )


class PagoConfeccionForm(forms.Form):
    from decimal import Decimal as _Decimal
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=_Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00',
        }),
        label='Monto',
    )
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Forma de pago',
    )
    descripcion = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nota (opcional)',
        }),
        label='Nota',
    )
    via_caja = forms.BooleanField(
        required=False,
        initial=True,
        label='Registrar en caja',
        help_text='Si no está marcado, el pago queda en reserva y no entra a caja hasta el pago final.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
    )


class PagoReparacionForm(forms.Form):
    from decimal import Decimal as _Decimal
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=_Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00',
        }),
        label='Monto',
    )
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Forma de pago',
    )
    descripcion = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nota (opcional)',
        }),
        label='Nota',
    )
    via_caja = forms.BooleanField(
        required=False,
        initial=True,
        label='Registrar en caja',
        help_text='Si no está marcado, el pago queda en reserva y no entra a caja hasta el pago final.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
    )


class PagoVentaForm(forms.Form):
    from decimal import Decimal as _Decimal
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=_Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00',
        }),
        label='Monto',
    )
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Forma de pago',
    )
    descripcion = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nota (opcional)',
        }),
        label='Nota',
    )
    via_caja = forms.BooleanField(
        required=False,
        initial=True,
        label='Registrar en caja',
        help_text='Si no está marcado, el pago queda en reserva y no entra a caja hasta el pago final.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
    )


class PagoComisionEmpleadoForm(forms.Form):
    from decimal import Decimal as _Decimal
    monto = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=_Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00',
        }),
        label='Monto a pagar',
    )
    forma_pago = forms.ChoiceField(
        choices=FORMA_PAGO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Forma de pago',
    )
    via_caja = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Registrar en caja',
        help_text='Si está activo, crea un egreso en la caja actual. Desactívalo si pagaste fuera de caja.',
    )
    descripcion = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Observaciones (opcional)',
        }),
        label='Descripción',
    )


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
            'nombre', 'modelo', 'talla', 'color', 'codigo_referencia',
            'stock_minimo', 'max_usos_default', 'precio',
            'precio_alquiler_base', 'precio_alquiler_minimo_pct',
            'estado', 'notas',
            'tipo_prenda',
        ]
        labels = {
            'nombre': 'Nombre',
            'modelo': 'Modelo / Línea',
            'talla': 'Talla',
            'color': 'Color',
            'codigo_referencia': 'Código de Referencia',
            'stock_minimo': 'Stock Mínimo',
            'max_usos_default': 'Máx. usos por defecto',
            'precio': 'Precio',
            'precio_alquiler_base': 'Precio alquiler base',
            'precio_alquiler_minimo_pct': 'Mínimo (%)',
            'estado': 'Estado',
            'notas': 'Notas',
            'tipo_prenda': 'Tipo de Prenda',
        }
        help_texts = {
            'max_usos_default': 'Máx. alquileres antes de baja sugerida (opcional)',
        }
        widgets = {
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'precio_alquiler_base': forms.NumberInput(),
            'precio_alquiler_minimo_pct': forms.NumberInput(attrs={'min': 1, 'max': 100}),
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


class PrendaItemForm(forms.ModelForm):
    class Meta:
        model = PrendaItem
        fields = ['tipo', 'condicion', 'ubicacion', 'max_usos', 'notas']
        labels = {
            'tipo': 'Tipo',
            'condicion': 'Condición',
            'ubicacion': 'Ubicación',
            'max_usos': 'Máx. usos',
            'notas': 'Notas',
        }
        help_texts = {
            'max_usos': 'Dejar vacío para heredar límite del SKU',
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
            'unidad_medida': forms.HiddenInput(),
            'tipo_material': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unidad_medida'].required = False
        self.fields['tipo_material'].required = False
        for name, field in self.fields.items():
            if name in ('unidad_medida', 'tipo_material'):
                continue
            if 'class' not in field.widget.attrs:
                is_select = isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                field.widget.attrs['class'] = 'form-select' if is_select else 'form-control'

class EmpleadoReporteForm(forms.Form):
    fecha_inicio = forms.DateField(required=False, label="Desde", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    fecha_fin = forms.DateField(required=False, label="Hasta", widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    tipo_contrato = forms.ModelChoiceField(
        queryset=TipoContrato.objects.all(),
        required=False,
        empty_label="Todos",
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
    tipo_prenda = forms.ModelChoiceField(
        queryset=TipoPrenda.objects.all(),
        label="Tipo de Prenda",
        required=False,
        empty_label="-- Seleccione Tipo de Prenda --",
        widget=forms.Select(attrs={'class': 'form-select'}),
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
        fields = [
            'tipo', 'descripcion', 'confeccion',
            'prenda_inventario', 'cantidad',
            'fecha_inicio', 'fecha_estimada', 'empleado', 'notas',
        ]
        widgets = {
            'descripcion':    forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'fecha_inicio':   forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'fecha_estimada': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'notas':          forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'cantidad':       forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'step': '1'}),
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
        self.fields['prenda_inventario'].required = False
        self.fields['cantidad'].required = False

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')
        if tipo == 'stock':
            if not cleaned.get('prenda_inventario'):
                self.add_error('prenda_inventario', 'Requerido para órdenes de inventario.')
            cantidad = cleaned.get('cantidad')
            if not cantidad or cantidad < 1:
                self.add_error('cantidad', 'Debe ser al menos 1.')
            cleaned['confeccion'] = None
        elif tipo == 'cliente':
            if not cleaned.get('confeccion'):
                self.add_error('confeccion', 'Requerido para órdenes de cliente.')
            cleaned['prenda_inventario'] = None
            cleaned['cantidad'] = None
        return cleaned


class InsumoCortadoForm(forms.ModelForm):
    class Meta:
        model = InsumoCortado
        fields = ['insumo', 'cantidad']
        widgets = {
            'insumo':   forms.Select(attrs={'class': 'form-select item-insumo'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control item-cantidad', 'step': '0.001', 'min': '0.001'}),
        }


# ============================================================
# MÓDULO DE CAJA — Formularios
# ============================================================

class CajaSesionAperturaForm(forms.ModelForm):
    class Meta:
        model = CajaSesion
        fields = ['monto_apertura', 'observaciones']
        widgets = {
            'monto_apertura': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Monto inicial en efectivo',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Observaciones (opcional)',
            }),
        }
        labels = {
            'monto_apertura': 'Monto de Apertura (Bs)',
            'observaciones': 'Observaciones',
        }


class CajaSesionCierreForm(forms.ModelForm):
    class Meta:
        model = CajaSesion
        fields = ['monto_cierre_declarado', 'observaciones']
        widgets = {
            'monto_cierre_declarado': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Total contado al cerrar',
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones (requerido si hay diferencia)',
            }),
        }
        labels = {
            'monto_cierre_declarado': 'Monto Declarado (Bs)',
            'observaciones': 'Observaciones',
        }


class CajaMovimientoManualForm(forms.ModelForm):
    """Formulario para movimientos manuales. Filtra concepto a MANUAL_CONCEPTOS."""

    class Meta:
        model = CajaMovimiento
        fields = ['concepto', 'monto', 'forma_pago', 'tipo_gasto', 'cliente', 'descripcion']
        widgets = {
            'concepto': forms.Select(attrs={'class': 'form-select', 'id': 'id_concepto'}),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
            }),
            'forma_pago': forms.Select(attrs={'class': 'form-select'}),
            'tipo_gasto': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_gasto'}),
            'cliente': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'concepto': 'Concepto',
            'monto': 'Monto (Bs)',
            'forma_pago': 'Forma de Pago',
            'tipo_gasto': 'Tipo de Gasto',
            'cliente': 'Cliente',
            'descripcion': 'Descripción',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict concepto choices to MANUAL_CONCEPTOS only
        manual_choices = [
            (c, label)
            for c, label in CajaMovimiento.CONCEPTO_CHOICES
            if c in CajaMovimiento.MANUAL_CONCEPTOS
        ]
        self.fields['concepto'].choices = [('', '---------')] + manual_choices
        # Only active TipoGasto entries in dropdown
        self.fields['tipo_gasto'].queryset = TipoGasto.objects.filter(activo=True)
        self.fields['tipo_gasto'].required = False
        self.fields['cliente'].required = False
        self.fields['descripcion'].required = False

    def clean(self):
        cleaned = super().clean()
        concepto = cleaned.get('concepto')
        tipo_gasto = cleaned.get('tipo_gasto')
        if concepto in CajaMovimiento.REQUIERE_TIPO_GASTO and not tipo_gasto:
            self.add_error('tipo_gasto', 'Requerido para este tipo de gasto.')
        if concepto and concepto not in CajaMovimiento.MANUAL_CONCEPTOS:
            self.add_error('concepto', 'Concepto no permitido en movimientos manuales.')
        return cleaned


class TipoGastoForm(forms.ModelForm):
    class Meta:
        model = TipoGasto
        fields = ['nombre', 'descripcion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'autofocus': True}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nombre': 'Nombre',
            'descripcion': 'Descripción',
            'activo': 'Activo',
        }


class ConjuntoForm(forms.ModelForm):
    class Meta:
        model = Conjunto
        fields = ['nombre', 'tipo', 'descripcion', 'precio_sugerido', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'precio_sugerido': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['precio_sugerido'].required = False
        labels = {
            'nombre': 'Nombre',
            'tipo': 'Tipo',
            'descripcion': 'Descripción',
            'precio_sugerido': 'Precio sugerido (Bs.)',
            'activo': 'Activo',
        }


class ConjuntoSlotInlineForm(forms.ModelForm):
    class Meta:
        model = ConjuntoSlot
        fields = ['prenda_item', 'opcional']
        widgets = {
            'prenda_item': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        tipo = kwargs.pop('tipo', None)
        super().__init__(*args, **kwargs)
        qs = (
            PrendaItem.objects
            .filter(prenda__estado='ACT')
            .select_related('prenda')
            .order_by('codigo_item')
        )
        if tipo:
            qs = qs.filter(tipo=tipo)
        self.fields['prenda_item'].queryset = qs
        self.fields['prenda_item'].empty_label = '— Seleccionar item —'

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('DELETE') and cleaned.get('prenda_item') is None:
            raise ValidationError({'prenda_item': 'Selecciona un item de prenda.'})
        return cleaned


ConjuntoSlotFormSet = inlineformset_factory(
    Conjunto, ConjuntoSlot, form=ConjuntoSlotInlineForm, extra=0, can_delete=True,
)