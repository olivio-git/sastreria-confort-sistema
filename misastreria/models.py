from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db import models, transaction
from django.core.validators import EmailValidator, RegexValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError


def calcular_precio_alquiler(base, min_pct, veces_alquilado, max_usos_efectivo):
    """
    Returns the suggested rental price for a PrendaItem given its wear.
    - base: Decimal or None
    - min_pct: int (1-100), default 20
    - veces_alquilado: int >= 0
    - max_usos_efectivo: int or None
    Returns Decimal (quantized to 0.01) or base if max_usos not set, None if base is None/0.
    """
    if not base:
        return None
    base = Decimal(str(base))
    floor = base * Decimal(str(min_pct)) / Decimal('100')
    if not max_usos_efectivo:
        return base.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    n = Decimal(str(veces_alquilado))
    m = Decimal(str(max_usos_efectivo))
    raw = base * (1 - n / m)
    return max(raw, floor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class TipoContrato(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = "Tipo de Contrato"
        verbose_name_plural = "Tipos de Contrato"

    def __str__(self):
        return self.nombre


class Empleado(models.Model):
    codigo = models.CharField(max_length=10, unique=True, blank=True, verbose_name="Código")
    ci = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="CI")
    nombres = models.CharField(max_length=100, verbose_name="Nombres")
    apellido_paterno = models.CharField(max_length=100, blank=True, verbose_name="Apellido Paterno")
    apellido_materno = models.CharField(max_length=100, blank=True, verbose_name="Apellido Materno")
    celular = models.CharField(max_length=15, validators=[RegexValidator(r'^\+?\d{9,15}$')], verbose_name="Celular")
    email = models.EmailField(null=True, blank=True, validators=[EmailValidator()], verbose_name="Correo Electrónico")
    tipo_contrato = models.ForeignKey(TipoContrato, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Tipo de Contrato")
    fecha_ingreso = models.DateField(verbose_name="Fecha de Ingreso")
    fecha_baja = models.DateField(null=True, blank=True, verbose_name="Fecha de Baja")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = Empleado.objects.order_by('id').last()
            numero = (int(last.codigo.split('-')[1]) + 1) if last and last.codigo and '-' in last.codigo else 1
            self.codigo = f"EMP-{numero:03d}"
        self.activo = self.fecha_baja is None
        self.nombres = ' '.join(word.capitalize() for word in self.nombres.split())
        if self.apellido_paterno:
            self.apellido_paterno = self.apellido_paterno.capitalize()
        if self.apellido_materno:
            self.apellido_materno = self.apellido_materno.capitalize()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ['nombres', 'apellido_paterno']

    def get_tipo_contrato_display(self):
        return str(self.tipo_contrato) if self.tipo_contrato else '—'

    def __str__(self):
        parts = [self.nombres, self.apellido_paterno, self.apellido_materno]
        return ' '.join(p for p in parts if p)


class Permiso(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='permisos')
    fecha_permiso = models.DateField(verbose_name="Fecha de Permiso")
    motivo = models.CharField(max_length=200, blank=True, verbose_name="Motivo")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    def __str__(self):
        return f"Permiso de {self.empleado} el {self.fecha_permiso}"


class Falta(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='faltas')
    fecha_falta = models.DateField(verbose_name="Fecha de Falta")
    motivo = models.CharField(max_length=200, blank=True, verbose_name="Motivo")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    def __str__(self):
        return f"Falta de {self.empleado} el {self.fecha_falta}"


class Cliente(models.Model):
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código de Cliente")
    ci = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="CI")
    nombres = models.CharField(max_length=100, verbose_name="Nombres")
    apellido_paterno = models.CharField(max_length=100, verbose_name="Apellido Paterno")
    apellido_materno = models.CharField(max_length=100, blank=True, verbose_name="Apellido Materno")
    edad = models.PositiveIntegerField(null=True, blank=True, verbose_name="Edad")
    celular = models.CharField(max_length=15, validators=[RegexValidator(r'^\+?\d{9,15}$')], verbose_name="Celular")
    email = models.EmailField(null=True, blank=True, verbose_name="Correo Electrónico")
    pais = models.CharField(max_length=100, blank=True, verbose_name="País")
    fecha_registro = models.DateField(default=timezone.now, verbose_name="Fecha de Registro")
    notas = models.TextField(blank=True, verbose_name="Notas")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = Cliente.objects.order_by('-id').first()
            numero = (int(last.codigo.split('-')[1]) + 1) if last and '-' in last.codigo else 1
            self.codigo = f"CLI-{numero:03d}"
        self.nombres = ' '.join(w.capitalize() for w in self.nombres.split())
        self.apellido_paterno = self.apellido_paterno.capitalize()
        if self.apellido_materno:
            self.apellido_materno = self.apellido_materno.capitalize()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['-creado']

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno} {self.apellido_materno}".strip()


class Servicio(models.Model):
    TIPO_SERVICIO_CHOICES = [
        ('reparaciones', 'Reparaciones'),
        ('confeccion', 'Confección de Trajes'),
        ('ventas', 'Ventas'),
        ('alquiler', 'Alquiler'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_SERVICIO_CHOICES, verbose_name="Tipo de Servicio")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        abstract = True


class TipoPrenda(models.Model):
    PLANTILLA_CHOICES = [
        ('', 'Sin medidas'),
        ('pantalon', 'Pantalón'),
        ('chaleco', 'Chaleco'),
        ('saco', 'Saco'),
        ('saco_mujer', 'Saco Mujer'),
        ('chaleco_mujer', 'Chaleco Mujer'),
    ]
    nombre    = models.CharField(max_length=100)
    plantilla = models.CharField(max_length=20, choices=PLANTILLA_CHOICES, blank=True, default='')

    class Meta:
        ordering = ['nombre']
        verbose_name = "Tipo de Prenda"
        verbose_name_plural = "Tipos de Prenda"

    def __str__(self):
        return self.nombre


class TipoReparacion(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        ordering = ['nombre']
        verbose_name = "Tipo de Reparación"
        verbose_name_plural = "Tipos de Reparación"

    def __str__(self):
        return self.nombre


FORMA_PAGO_CHOICES = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
    ('qr', 'QR'),
    ('tarjeta', 'Tarjeta'),
]


class PagoComisionEmpleado(models.Model):
    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    empleado = models.ForeignKey(
        Empleado, on_delete=models.PROTECT,
        related_name='pagos_comision',
        verbose_name="Empleado",
    )
    monto = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Monto",
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")
    via_caja = models.BooleanField(
        default=True,
        verbose_name="Vía caja",
        help_text="Si está activo, crea un egreso en caja. Si no, registra el pago sin afectar caja.",
    )
    forma_pago = models.CharField(
        max_length=15, choices=FORMA_PAGO_CHOICES, default='efectivo',
        verbose_name="Forma de Pago",
    )
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Usuario",
    )
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Pago de Comisión"
        verbose_name_plural = "Pagos de Comisión"
        ordering = ['-fecha', '-id']

    def save(self, *args, **kwargs):
        if not self.codigo:
            with transaction.atomic():
                last = PagoComisionEmpleado.objects.select_for_update().order_by('-id').first()
                next_id = (last.id + 1) if last else 1
                self.codigo = f"COM-{next_id:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} — {self.empleado} Bs {self.monto}"


class Reparacion(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('entregado', 'Entregado'),
    ]

    codigo = models.CharField(max_length=10, unique=True, blank=True, verbose_name="Código")
    fecha_entrega = models.DateField(verbose_name="Fecha de Entrega")
    empleado = models.ForeignKey(Empleado, on_delete=models.SET_NULL, null=True, related_name='reparaciones', verbose_name="Asignado a")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, related_name='reparaciones', verbose_name="Cliente")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente', verbose_name="Estado")
    forma_pago = models.CharField(max_length=15, choices=FORMA_PAGO_CHOICES, default='efectivo', blank=True, verbose_name="Forma de Pago")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    porcentaje_comision = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name="Porcentaje Comisión (%)",
        help_text="Comisión del empleado sobre el total. Solo aplica si la reparación está entregada.",
    )
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Reparación"
        verbose_name_plural = "Reparaciones"
        ordering = ['-creado']

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = Reparacion.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
            self.codigo = f"REP-{numero:03d}"
        super().save(*args, **kwargs)

    @property
    def total_pagado(self):
        from .caja_signals import _calcular_pagado_reparacion
        return _calcular_pagado_reparacion(self)

    @property
    def saldo_pendiente(self):
        from decimal import Decimal
        return max(Decimal('0'), (self.total or Decimal('0')) - self.total_pagado)

    def recalcular_total(self):
        from django.db.models import Sum
        total = self.items.aggregate(t=Sum('costo'))['t'] or 0
        self.total = total
        self.save(update_fields=['total'])

    def __str__(self):
        return f"Reparación {self.codigo}"


class ReparacionItem(models.Model):
    reparacion = models.ForeignKey(Reparacion, on_delete=models.CASCADE, related_name='items')
    tipo_prenda = models.ForeignKey(TipoPrenda, on_delete=models.PROTECT, verbose_name="Tipo de Prenda")
    tipo_reparacion = models.ForeignKey(TipoReparacion, on_delete=models.PROTECT, verbose_name="Tipo de Reparación")
    costo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Costo")
    detalles = models.TextField(blank=True, verbose_name="Detalles")

    class Meta:
        verbose_name = "Item de Reparación"
        verbose_name_plural = "Items de Reparación"

    def __str__(self):
        return f"{self.tipo_prenda} — {self.tipo_reparacion}"


class PrendaInventario(models.Model):
    ESTADO_OPCIONES = [
        ('ACT', 'Activo'),
        ('BAJ', 'Baja'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    modelo = models.CharField(max_length=100, blank=True, verbose_name="Modelo / Línea")
    talla = models.CharField(max_length=20, blank=True, verbose_name="Talla")
    color = models.CharField(max_length=50, blank=True, verbose_name="Color")
    codigo_referencia = models.CharField(max_length=100, blank=True, verbose_name="Código de Referencia")
    stock_minimo = models.PositiveIntegerField(null=True, blank=True, verbose_name="Stock Mínimo")
    max_usos_default = models.PositiveIntegerField(null=True, blank=True, verbose_name="Máx. usos por defecto")
    precio_alquiler_base = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Precio alquiler base",
        help_text="Precio de alquiler cuando la prenda es nueva. Si no se define, no se sugiere precio.",
    )
    precio_alquiler_minimo_pct = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        verbose_name="Precio mínimo (%)",
        help_text="Porcentaje mínimo del precio base al que puede llegar. Default: 20%",
    )
    precio = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0.01)], verbose_name="Precio"
    )
    estado = models.CharField(max_length=3, choices=ESTADO_OPCIONES, default='ACT', verbose_name="Estado")
    notas = models.TextField(blank=True, verbose_name="Notas")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso")
    tipo_prenda = models.ForeignKey(
        'TipoPrenda',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='prendas_inventario',
        verbose_name="Tipo de Prenda",
    )

    class Meta:
        verbose_name = "Prenda"
        verbose_name_plural = "Prendas"
        ordering = ['nombre', 'talla']

    @property
    def cantidad(self):
        """
        Stock total (disponible + alquilado). Excluye items en baja.
        Si el queryset fue anotado con stock_total, lo usa sin disparar query (evita N+1).
        """
        if hasattr(self, 'stock_total'):
            return self.stock_total
        return self.items.exclude(estado='baja').count()

    @property
    def stock_disponible(self):
        if hasattr(self, '_stock_disponible'):
            return self._stock_disponible
        return self.items.filter(estado='disponible').count()

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = PrendaInventario.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
            self.codigo = f"PRN-{numero:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        parts = [self.nombre]
        if self.codigo_referencia:
            parts.append(self.codigo_referencia)
        if self.color:
            parts.append(self.color)
        if self.talla:
            parts.append(f"T{self.talla}")
        return ' / '.join(parts)


class UbicacionItem(models.Model):
    nombre = models.CharField(max_length=80, unique=True, verbose_name="Nombre")

    class Meta:
        ordering = ['nombre']
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"

    def __str__(self):
        return self.nombre


class PrendaItem(models.Model):
    TIPO_CHOICES = [
        ('alquiler', 'Para Alquiler'),
        ('venta',    'Para Venta'),
    ]
    CONDICION_CHOICES = [
        ('nueva',  'Nueva'),
        ('usada',  'Usada'),
        ('remate', 'Remate'),
    ]
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('alquilado',  'Alquilado'),
        ('reservado',  'Reservado'),
        ('baja',       'Baja'),
    ]

    prenda = models.ForeignKey(
        PrendaInventario,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Prenda (SKU)",
    )
    codigo_item = models.CharField(
        max_length=30, unique=True, blank=True,
        verbose_name="Código de Item",
        help_text="Auto-generado: <codigo SKU>-ITM-<NN>",
    )
    tipo = models.CharField(
        max_length=10, choices=TIPO_CHOICES, default='alquiler',
        verbose_name="Tipo",
    )
    ubicacion = models.ForeignKey(
        UbicacionItem,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Ubicación física",
    )
    condicion = models.CharField(
        max_length=10, choices=CONDICION_CHOICES, default='nueva',
        verbose_name="Condición",
    )
    estado = models.CharField(
        max_length=12, choices=ESTADO_CHOICES, default='disponible',
        verbose_name="Estado",
    )
    veces_alquilado = models.PositiveIntegerField(
        default=0, verbose_name="Veces alquilado",
    )
    max_usos = models.PositiveIntegerField(null=True, blank=True, verbose_name="Máx. usos")
    notas = models.TextField(blank=True, verbose_name="Notas")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de alta")
    actualizado = models.DateTimeField(auto_now=True)
    fecha_baja = models.DateField(null=True, blank=True, verbose_name="Fecha de Baja")

    class Meta:
        verbose_name = "Item de Prenda"
        verbose_name_plural = "Items de Prenda"
        ordering = ['prenda__codigo', 'codigo_item']
        indexes = [
            models.Index(fields=['prenda', 'estado']),
        ]

    def save(self, *args, **kwargs):
        if not self.codigo_item:
            base = self.prenda.codigo
            last = (
                PrendaItem.objects
                .filter(prenda=self.prenda)
                .order_by('-id')
                .first()
            )
            if last and last.codigo_item:
                try:
                    n = int(last.codigo_item.rsplit('-', 1)[-1]) + 1
                except (ValueError, IndexError):
                    n = self.prenda.items.count() + 1
            else:
                n = 1
            self.codigo_item = f"{base}-ITM-{n:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_item} ({self.get_condicion_display()})"

    @property
    def max_usos_efectivo(self):
        return self.max_usos or self.prenda.max_usos_default

    @property
    def precio_alquiler_sugerido(self):
        """Suggested rental price applying linear depreciation with floor."""
        return calcular_precio_alquiler(
            base=self.prenda.precio_alquiler_base,
            min_pct=self.prenda.precio_alquiler_minimo_pct,
            veces_alquilado=self.veces_alquilado,
            max_usos_efectivo=self.max_usos_efectivo,
        )

    @property
    def porcentaje_vida_util(self):
        m = self.max_usos_efectivo
        if not m:
            return None
        return min(int(self.veces_alquilado / m * 100), 100)

    @property
    def estado_vida_util(self):
        p = self.porcentaje_vida_util
        if p is None:
            return None
        if p >= 90:
            return 'critico'
        if p >= 70:
            return 'advertencia'
        return 'ok'


class UnidadMedida(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = "Unidad de Medida"
        verbose_name_plural = "Unidades de Medida"

    def __str__(self):
        return self.nombre


class TipoMaterial(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = "Tipo de Material"
        verbose_name_plural = "Tipos de Material"

    def __str__(self):
        return self.nombre


class Insumo(models.Model):
    ESTADO_OPCIONES = [
        ('ACT', 'Activo'),
        ('BAJ', 'Baja'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    tipo_material = models.ForeignKey(TipoMaterial, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Tipo de Material")
    articulo = models.CharField(max_length=100, verbose_name="Artículo")
    coleccion = models.CharField(max_length=100, blank=True, verbose_name="Colección / Cuaderno")
    color = models.CharField(max_length=50, blank=True, verbose_name="Color")
    codigo_referencia = models.CharField(max_length=100, blank=True, verbose_name="Código de Referencia")
    tipo_tela = models.CharField(max_length=50, blank=True, verbose_name="Tipo de Tela")
    unidad_medida = models.ForeignKey(UnidadMedida, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Unidad de Medida")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Cantidad")
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Stock Mínimo")
    precio_costo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Precio de Costo")
    estado = models.CharField(max_length=3, choices=ESTADO_OPCIONES, default='ACT', verbose_name="Estado")
    proveedor = models.CharField(max_length=100, blank=True, verbose_name="Proveedor")
    notas = models.TextField(blank=True, verbose_name="Notas")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso")

    class Meta:
        verbose_name = "Insumo"
        verbose_name_plural = "Insumos"
        ordering = ['tipo_material__nombre', 'articulo']

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = Insumo.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
            self.codigo = f"INS-{numero:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        if self.coleccion and self.color:
            return f"{self.coleccion} / {self.color}"
        if self.codigo_referencia:
            return f"{self.articulo} {self.codigo_referencia}"
        parts = [p for p in [self.tipo_tela, self.articulo, self.color] if p]
        return ' '.join(parts) if parts else self.articulo


class Venta(Servicio):
    codigo = models.CharField(max_length=10, unique=True, blank=True, verbose_name="Código")
    fecha_venta = models.DateField(default=timezone.now, verbose_name="Fecha de Venta")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas', verbose_name="Cliente")
    empleado = models.ForeignKey('Empleado', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas', verbose_name="Empleado")
    descuento = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Descuento (%)")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    notas = models.TextField(blank=True, verbose_name="Notas")
    forma_pago = models.CharField(max_length=15, choices=FORMA_PAGO_CHOICES, default='efectivo', blank=True, verbose_name="Forma de Pago")

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']

    def save(self, *args, **kwargs):
        self.tipo = 'ventas'
        if not self.codigo:
            last = Venta.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"VEN-{numero:03d}"
        super().save(*args, **kwargs)

    def recalcular_totales(self):
        from decimal import Decimal
        self.subtotal = sum(item.subtotal for item in self.items.all())
        self.total = self.subtotal * (1 - self.descuento / Decimal('100'))
        Venta.objects.filter(pk=self.pk).update(subtotal=self.subtotal, total=self.total)

    def __str__(self):
        return f"Venta {self.codigo}"


class VentaItem(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='items')
    prenda_item = models.ForeignKey(
        'PrendaItem',
        on_delete=models.PROTECT,
        related_name='venta_items',
        verbose_name="Item de Prenda",
        null=True, blank=True,
    )
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    tipo_reparacion = models.ForeignKey(
        'TipoReparacion', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Tipo de Arreglo",
    )
    precio_reparacion = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name="Precio Arreglo",
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    grupo_conjunto = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Ítem de Venta"
        verbose_name_plural = "Ítems de Venta"

    def save(self, *args, **kwargs):
        self.subtotal = self.precio_unitario + (self.precio_reparacion or Decimal('0'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.prenda_item.codigo_item}"


class ModeloConfeccion(models.Model):
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")

    class Meta:
        verbose_name = "Modelo de Confección"
        verbose_name_plural = "Modelos de Confección"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Confeccion(models.Model):
    ESTADO_CHOICES = [
        ('pendiente',  'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('entregado',  'Entregado'),
    ]

    codigo       = models.CharField(max_length=20, unique=True, blank=True)
    fecha_inicio = models.DateField(default=timezone.now)
    color        = models.CharField(max_length=50)
    modelo       = models.CharField(max_length=100)
    cliente      = models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True)
    empleado     = models.ForeignKey(Empleado, on_delete=models.PROTECT, null=True, blank=True, related_name='confecciones')
    garantia_meses= models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Garantía (meses)")
    garantia_hasta= models.DateField(null=True, blank=True, verbose_name="Garantía hasta")
    observaciones = models.TextField(blank=True)
    precio       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    porcentaje_comision = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name="Porcentaje Comisión (%)",
        help_text="Comisión del empleado sobre el precio. Solo aplica si la confección está entregada.",
    )
    adelanto     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_prueba = models.DateField(null=True, blank=True)
    fecha_entrega= models.DateField(null=True, blank=True)
    estado       = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    forma_pago   = models.CharField(max_length=15, choices=FORMA_PAGO_CHOICES, default='efectivo', blank=True, verbose_name="Forma de Pago")
    creado       = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Confección"
        verbose_name_plural = "Confecciones"
        ordering = ['-creado']

    @property
    def garantia_estado(self):
        from datetime import date
        if not self.garantia_hasta:
            return None
        return 'vigente' if self.garantia_hasta >= date.today() else 'vencida'

    @property
    def tipos_prenda_display(self):
        return ', '.join(str(item.tipo_prenda) for item in self.items.all() if item.tipo_prenda)

    @property
    def total_pagado(self):
        from .caja_signals import _calcular_pagado_confeccion
        return _calcular_pagado_confeccion(self)

    @property
    def saldo_pendiente(self):
        from decimal import Decimal
        return max(Decimal('0'), (self.precio or Decimal('0')) - self.total_pagado)

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = Confeccion.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last and last.codigo and '-' in last.codigo else 1
            self.codigo = f"CONF-{numero:03d}"
        self.saldo = self.precio - self.adelanto
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} - {self.cliente or 'Sin cliente'}"


class ConfeccionItem(models.Model):
    confeccion = models.ForeignKey(Confeccion, on_delete=models.CASCADE, related_name='items')
    tipo_prenda = models.ForeignKey(TipoPrenda, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tipo de Prenda")
    talla = models.CharField(max_length=30, blank=True, verbose_name="Talla")

    # Pantalón
    pantalon_largo_total        = models.CharField(max_length=20, blank=True)
    pantalon_contorno_cintura   = models.CharField(max_length=20, blank=True)
    pantalon_contorno_cadera    = models.CharField(max_length=20, blank=True)
    pantalon_largo_entrepierna  = models.CharField(max_length=20, blank=True)
    pantalon_contorno_pierna    = models.CharField(max_length=20, blank=True)
    pantalon_contorno_rodilla   = models.CharField(max_length=20, blank=True)
    pantalon_contorno_bota      = models.CharField(max_length=20, blank=True)
    pantalon_tiro_delantero     = models.CharField(max_length=20, blank=True)
    pantalon_tiro_trasero       = models.CharField(max_length=20, blank=True)

    # Chaleco
    chaleco_contorno_busto   = models.CharField(max_length=20, blank=True)
    chaleco_contorno_cintura = models.CharField(max_length=20, blank=True)
    chaleco_contorno_cadera  = models.CharField(max_length=20, blank=True)
    chaleco_largo_talle      = models.CharField(max_length=20, blank=True)
    chaleco_largo_total      = models.CharField(max_length=20, blank=True)
    chaleco_altura_botones   = models.CharField(max_length=20, blank=True)

    # Saco
    saco_contorno_busto   = models.CharField(max_length=20, blank=True)
    saco_contorno_cintura = models.CharField(max_length=20, blank=True)
    saco_contorno_cadera  = models.CharField(max_length=20, blank=True)
    saco_largo_talle      = models.CharField(max_length=20, blank=True)
    saco_largo_total      = models.CharField(max_length=20, blank=True)
    saco_ancho_hombros    = models.CharField(max_length=20, blank=True)
    saco_ancho_espalda    = models.CharField(max_length=20, blank=True)
    saco_contorno_brazo   = models.CharField(max_length=20, blank=True)
    saco_largo_manga      = models.CharField(max_length=20, blank=True)
    saco_contorno_puno    = models.CharField(max_length=20, blank=True)

    # Saco – Mujer
    saco_mujer_contorno_busto    = models.CharField(max_length=20, blank=True)
    saco_mujer_contorno_cintura  = models.CharField(max_length=20, blank=True)
    saco_mujer_contorno_cadera   = models.CharField(max_length=20, blank=True)
    saco_mujer_ancho_hombros     = models.CharField(max_length=20, blank=True)
    saco_mujer_ancho_espalda     = models.CharField(max_length=20, blank=True)
    saco_mujer_largo_talle       = models.CharField(max_length=20, blank=True)
    saco_mujer_largo_total       = models.CharField(max_length=20, blank=True)
    saco_mujer_altura_busto      = models.CharField(max_length=20, blank=True)
    saco_mujer_separacion_busto  = models.CharField(max_length=20, blank=True)
    saco_mujer_dif_talle         = models.CharField(max_length=20, blank=True)

    # Chaleco – Mujer
    chaleco_mujer_contorno_busto   = models.CharField(max_length=20, blank=True)
    chaleco_mujer_contorno_cintura = models.CharField(max_length=20, blank=True)
    chaleco_mujer_contorno_cadera  = models.CharField(max_length=20, blank=True)
    chaleco_mujer_largo_talle      = models.CharField(max_length=20, blank=True)
    chaleco_mujer_largo_total      = models.CharField(max_length=20, blank=True)
    chaleco_mujer_altura_busto     = models.CharField(max_length=20, blank=True)
    chaleco_mujer_separacion_busto = models.CharField(max_length=20, blank=True)
    chaleco_mujer_largo_delantero  = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return str(self.tipo_prenda) if self.tipo_prenda else '—'


class EstadoAlquiler(models.Model):
    COLOR_CHOICES = [
        ('alquilado', 'Azul (Alquilado)'),
        ('devuelto',  'Verde (Devuelto)'),
        ('warning',   'Naranja (Alerta)'),
        ('danger',    'Rojo (Crítico)'),
    ]
    nombre = models.CharField(max_length=50, unique=True)
    color  = models.CharField(max_length=20, choices=COLOR_CHOICES, default='warning')

    class Meta:
        ordering = ['nombre']
        verbose_name = "Estado de Alquiler"
        verbose_name_plural = "Estados de Alquiler"

    def __str__(self):
        return self.nombre.replace('_', ' ').title()


class Alquiler(Servicio):
    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    fecha_alquiler = models.DateField(default=timezone.now, verbose_name="Fecha de Alquiler")
    fecha_devolucion = models.DateField(verbose_name="Fecha de Devolución")
    fecha_evento = models.DateField(null=True, blank=True, verbose_name="Fecha del evento")
    hora_devolucion = models.TimeField(null=True, blank=True, verbose_name="Hora de Devolución")
    estado = models.CharField(max_length=50, default='alquilado', verbose_name="Estado")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='alquileres', verbose_name="Cliente")
    empleado = models.ForeignKey(Empleado, on_delete=models.SET_NULL, null=True, blank=True, related_name='alquileres', verbose_name="Empleado")
    descuento = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Descuento (%)")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    GARANTIA_TIPO_CHOICES = [
        ('', 'Sin garantía'),
        ('efectivo', 'Efectivo'),
        ('qr', 'QR'),
        ('transferencia', 'Transferencia'),
        ('descripcion', 'Descripción'),
    ]
    garantia_tipo = models.CharField(
        max_length=15, choices=GARANTIA_TIPO_CHOICES, blank=True, default='',
        verbose_name="Tipo de Garantía",
    )
    garantia_monto = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Monto de Garantía",
    )
    garantia = models.TextField(blank=True, verbose_name="Descripción de Garantía")
    notas = models.TextField(blank=True, verbose_name="Notas")
    forma_pago = models.CharField(max_length=15, choices=FORMA_PAGO_CHOICES, default='efectivo', blank=True, verbose_name="Forma de Pago")

    class Meta:
        verbose_name = "Alquiler"
        verbose_name_plural = "Alquileres"
        ordering = ['-fecha_alquiler']

    def save(self, *args, **kwargs):
        self.tipo = 'alquiler'
        if not self.codigo:
            last = Alquiler.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"ALQ-{numero:03d}"
        super().save(*args, **kwargs)

    def recalcular_totales(self):
        from decimal import Decimal
        self.subtotal = sum(item.subtotal for item in self.items.all())
        self.total = self.subtotal * (1 - self.descuento / Decimal('100'))
        Alquiler.objects.filter(pk=self.pk).update(subtotal=self.subtotal, total=self.total)

    @property
    def estado_display(self):
        return self.estado.replace('_', ' ').title()

    @property
    def con_recargo(self):
        from django.utils import timezone
        ahora_local = timezone.localtime(timezone.now())
        hoy = ahora_local.date()
        if self.fecha_devolucion < hoy:
            return True
        if self.fecha_devolucion == hoy and self.hora_devolucion:
            return ahora_local.time() > self.hora_devolucion
        return False

    @property
    def estado_color(self):
        try:
            return EstadoAlquiler.objects.get(nombre=self.estado).color
        except EstadoAlquiler.DoesNotExist:
            return 'secondary'

    @property
    def total_pagado(self):
        from .caja_signals import _calcular_pagado_alquiler
        return _calcular_pagado_alquiler(self)

    @property
    def saldo_pendiente(self):
        from decimal import Decimal
        return max(Decimal('0'), (self.total or Decimal('0')) - self.total_pagado)

    def __str__(self):
        return f"Alquiler {self.codigo}"


class AlquilerItem(models.Model):
    alquiler = models.ForeignKey(Alquiler, on_delete=models.CASCADE, related_name='items')
    prenda_item = models.ForeignKey(
        'PrendaItem',
        on_delete=models.PROTECT,
        related_name='alquiler_items',
        verbose_name="Item de Prenda",
        null=True, blank=True,
    )
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    tipo_reparacion = models.ForeignKey(
        'TipoReparacion', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Tipo de Arreglo",
    )
    precio_reparacion = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name="Precio Arreglo",
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    grupo_conjunto = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Ítem de Alquiler"
        verbose_name_plural = "Ítems de Alquiler"

    def save(self, *args, **kwargs):
        self.subtotal = self.precio_unitario + (self.precio_reparacion or Decimal('0'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.prenda_item.codigo_item}"


class KardexEvento(models.Model):
    TIPO_CHOICES = [
        ('ingreso',    'Ingreso'),
        ('alquiler',   'Alquiler'),
        ('devolucion', 'Devolución'),
        ('venta',      'Venta'),
        ('baja',       'Baja'),
    ]
    tipo        = models.CharField(max_length=20, choices=TIPO_CHOICES)
    timestamp   = models.DateTimeField(default=timezone.now, db_index=True)
    prenda_item = models.ForeignKey('PrendaItem', on_delete=models.CASCADE, related_name='kardex_eventos')
    alquiler    = models.ForeignKey('Alquiler', on_delete=models.SET_NULL, null=True, blank=True, related_name='kardex_eventos')
    venta       = models.ForeignKey('Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='kardex_eventos')
    cliente     = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='kardex_eventos')
    monto       = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    descripcion = models.CharField(max_length=200, blank=True)
    creado      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento de Kardex"
        verbose_name_plural = "Eventos de Kardex"
        ordering = ['timestamp', 'id']
        indexes = [
            models.Index(fields=['prenda_item', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.prenda_item_id} @ {self.timestamp:%Y-%m-%d %H:%M}"


class Transaccion(models.Model):
    TIPO_TRANSACCION_CHOICES = [
        ('ingreso', 'Ingreso'),
        ('gasto', 'Gasto'),
    ]

    TIPO_SERVICIO_CHOICES = [
        ('servicio_basico', 'Servicio Básico'),
        ('caja_chica', 'Caja Chica'),
        ('otros', 'Otros'),
    ]

    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código", help_text="Formato: TXN-001")
    tipo_transaccion = models.CharField(max_length=10, choices=TIPO_TRANSACCION_CHOICES, default='ingreso', verbose_name="Tipo de Transacción")
    descripcion = models.TextField(verbose_name="Descripción")
    tipo_servicio = models.CharField(max_length=20, choices=TIPO_SERVICIO_CHOICES, verbose_name="Tipo de Servicio")
    fecha = models.DateField(default=timezone.now, verbose_name="Fecha")
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad")
    monto = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name="Monto")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Transacción"
        verbose_name_plural = "Transacciones"
        ordering = ['-creado']

    def clean(self):
        if not self.descripcion:
            raise ValidationError("La descripción es obligatoria.")
        if self.cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor que cero.")
        if self.monto <= 0:
            raise ValidationError("El monto debe ser mayor que cero.")

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = Transaccion.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"TXN-{numero:03d}"
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Transacción {self.codigo} - {self.descripcion[:50]}"


class OrdenProduccion(models.Model):
    ESTADO_CHOICES = [
        ('corte',     'En Corte'),
        ('costura',   'En Costura'),
        ('terminado', 'Terminado'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    descripcion = models.TextField(verbose_name="Descripción")
    confeccion = models.ForeignKey(
        Confeccion, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordenes_produccion', verbose_name="Confección asociada",
    )
    TIPO_CHOICES = [
        ('cliente', 'Para cliente'),
        ('stock',   'Para inventario'),
    ]
    tipo = models.CharField(
        max_length=10, choices=TIPO_CHOICES, default='cliente',
        verbose_name="Tipo de orden",
    )
    prenda_inventario = models.ForeignKey(
        'PrendaInventario', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='ordenes_produccion',
        verbose_name="Prenda destino (stock)",
    )
    cantidad = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Cantidad a producir",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='corte', verbose_name="Estado")
    fecha_inicio = models.DateField(default=timezone.now, verbose_name="Fecha de Inicio")
    fecha_estimada = models.DateField(null=True, blank=True, verbose_name="Fecha Estimada")
    empleado = models.ForeignKey(
        Empleado, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ordenes_produccion', verbose_name="Responsable",
    )
    notas = models.TextField(blank=True, verbose_name="Notas")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Orden de Producción"
        verbose_name_plural = "Órdenes de Producción"
        ordering = ['-creado']

    ESTADO_SIGUIENTE = {'corte': 'costura', 'costura': 'terminado'}

    def save(self, *args, **kwargs):
        if not self.codigo:
            last = OrdenProduccion.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"PROD-{numero:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Orden {self.codigo}"


class InsumoCortado(models.Model):
    orden = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name='insumos')
    insumo = models.ForeignKey(Insumo, on_delete=models.PROTECT, verbose_name="Insumo")
    cantidad = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Cantidad usada")

    class Meta:
        verbose_name = "Insumo Utilizado"
        verbose_name_plural = "Insumos Utilizados"

    def __str__(self):
        return f"{self.insumo} × {self.cantidad}"


# ============================================================
# MÓDULO DE CAJA
# ============================================================

class TipoGasto(models.Model):
    nombre = models.CharField(max_length=80, unique=True, verbose_name="Nombre")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Tipo de gasto'
        verbose_name_plural = 'Tipos de gasto'

    def __str__(self):
        return self.nombre


class CajaSesion(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada'),
    ]

    fecha_apertura = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Apertura")
    monto_apertura = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name="Monto de Apertura",
    )
    usuario_apertura = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='sesiones_abiertas',
        verbose_name="Usuario Apertura",
    )

    fecha_cierre = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Cierre")
    monto_cierre_declarado = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Monto Cierre Declarado",
    )
    monto_cierre_sistema = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Monto Cierre Sistema",
    )
    diferencia = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Diferencia",
    )
    usuario_cierre = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='sesiones_cerradas',
        verbose_name="Usuario Cierre",
    )

    estado = models.CharField(
        max_length=10, choices=ESTADO_CHOICES, default='abierta',
        verbose_name="Estado",
    )
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        ordering = ['-fecha_apertura']
        verbose_name = 'Caja Sesión'
        verbose_name_plural = 'Caja Sesiones'
        constraints = [
            models.UniqueConstraint(
                fields=['estado'],
                condition=models.Q(estado='abierta'),
                name='unique_caja_abierta',
            ),
        ]
        indexes = [
            models.Index(fields=['-fecha_apertura']),
            models.Index(fields=['estado']),
        ]

    def __str__(self):
        fa = self.fecha_apertura.strftime('%Y-%m-%d %H:%M')
        return f"Caja #{self.id} {fa} ({self.get_estado_display()})"

    _CONCEPTOS_GARANTIA = ('garantia_alquiler', 'garantia_devolucion')

    @property
    def saldo_sistema(self):
        """Apertura + ingresos operativos - egresos operativos. Excluye garantías."""
        from django.db.models import Sum
        movs = self.movimientos.filter(
            movimiento_reverso__isnull=True
        ).exclude(concepto__in=self._CONCEPTOS_GARANTIA)
        ingresos = (
            movs.filter(tipo='ingreso')
            .exclude(concepto='apertura_caja')
            .aggregate(s=Sum('monto'))['s'] or Decimal('0')
        )
        egresos = movs.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
        return (self.monto_apertura or Decimal('0')) + ingresos - egresos

    @property
    def saldo_efectivo_sistema(self):
        """Solo efectivo: apertura + ingresos efectivo - egresos efectivo. Excluye garantías."""
        from django.db.models import Sum
        movs = self.movimientos.filter(
            movimiento_reverso__isnull=True,
            forma_pago='efectivo',
        ).exclude(concepto__in=self._CONCEPTOS_GARANTIA)
        ingresos = (
            movs.filter(tipo='ingreso')
            .exclude(concepto='apertura_caja')
            .aggregate(s=Sum('monto'))['s'] or Decimal('0')
        )
        egresos = movs.filter(tipo='egreso').aggregate(s=Sum('monto'))['s'] or Decimal('0')
        return (self.monto_apertura or Decimal('0')) + ingresos - egresos

    @property
    def total_ingresos(self):
        from django.db.models import Sum
        return (
            self.movimientos
            .filter(tipo='ingreso', movimiento_reverso__isnull=True)
            .exclude(concepto__in=('apertura_caja', 'garantia_alquiler'))
            .aggregate(s=Sum('monto'))['s'] or Decimal('0')
        )

    @property
    def total_egresos(self):
        from django.db.models import Sum
        return (
            self.movimientos
            .filter(tipo='egreso', movimiento_reverso__isnull=True)
            .exclude(concepto='garantia_devolucion')
            .aggregate(s=Sum('monto'))['s'] or Decimal('0')
        )

    @property
    def saldo_garantias(self):
        """Garantías recibidas menos garantías devueltas (plata del cliente aún en caja)."""
        from django.db.models import Sum
        recibido = (
            self.movimientos
            .filter(tipo='ingreso', concepto='garantia_alquiler', movimiento_reverso__isnull=True)
            .aggregate(s=Sum('monto'))['s'] or Decimal('0')
        )
        devuelto = (
            self.movimientos
            .filter(tipo='egreso', concepto='garantia_devolucion', movimiento_reverso__isnull=True)
            .aggregate(s=Sum('monto'))['s'] or Decimal('0')
        )
        return recibido - devuelto


class CajaMovimiento(models.Model):
    TIPO_CHOICES = [('ingreso', 'Ingreso'), ('egreso', 'Egreso')]

    ORIGEN_CHOICES = [
        ('automatico', 'Automático'),
        ('manual', 'Manual'),
    ]

    FORMA_PAGO_MOV_CHOICES = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('qr', 'QR'),
        ('tarjeta', 'Tarjeta'),
        ('cheque', 'Cheque'),
        ('mixto', 'Mixto'),
    ]

    CONCEPTO_TIPO_MAP = {
        'alquiler_cobro': 'ingreso',
        'alquiler_pago': 'ingreso',
        'alquiler_ajuste': 'ingreso',
        'garantia_alquiler': 'ingreso',
        'garantia_devolucion': 'egreso',
        'venta_cobro': 'ingreso',
        'venta_ajuste': 'ingreso',
        'confeccion_adelanto': 'ingreso',
        'confeccion_saldo': 'ingreso',
        'confeccion_pago': 'ingreso',
        'reparacion_cobro': 'ingreso',
        'reparacion_pago': 'ingreso',
        'reparacion_saldo': 'ingreso',
        'reparacion_ajuste': 'ingreso',
        'ingreso_manual': 'ingreso',
        'egreso_manual': 'egreso',
        'apertura_caja': 'ingreso',
        'sobrante_caja': 'ingreso',
        'gasto_fijo': 'egreso',
        'gasto_operativo': 'egreso',
        'retiro': 'egreso',
        'devolucion_cliente': 'egreso',
        'anulacion_cobro': 'egreso',
        'faltante_caja': 'egreso',
        'gasto_varios': 'egreso',
        'comision_empleado': 'egreso',
    }

    CONCEPTO_CHOICES = [
        ('alquiler_cobro', 'Cobro de alquiler'),
        ('alquiler_pago', 'Pago de alquiler'),
        ('alquiler_ajuste', 'Ajuste de alquiler'),
        ('garantia_alquiler', 'Garantía de alquiler'),
        ('garantia_devolucion', 'Devolución de garantía'),
        ('venta_cobro', 'Cobro de venta'),
        ('venta_ajuste', 'Ajuste de venta'),
        ('confeccion_adelanto', 'Adelanto de confección'),
        ('confeccion_saldo', 'Saldo de confección'),
        ('confeccion_pago', 'Pago de confección'),
        ('reparacion_cobro', 'Cobro de reparación'),
        ('reparacion_pago', 'Pago de reparación'),
        ('reparacion_saldo', 'Saldo de reparación'),
        ('reparacion_ajuste', 'Ajuste de reparación'),
        ('ingreso_manual', 'Ingreso manual'),
        ('egreso_manual', 'Egreso manual'),
        ('apertura_caja', 'Apertura de caja'),
        ('sobrante_caja', 'Sobrante de caja'),
        ('gasto_fijo', 'Gasto fijo'),
        ('gasto_operativo', 'Gasto operativo'),
        ('retiro', 'Retiro del dueño'),
        ('devolucion_cliente', 'Devolución a cliente'),
        ('anulacion_cobro', 'Anulación de cobro'),
        ('faltante_caja', 'Faltante de caja'),
        ('gasto_varios', 'Gasto varios'),
        ('comision_empleado', 'Comisión de empleado'),
    ]

    MANUAL_CONCEPTOS = [
        'ingreso_manual',
        'egreso_manual',
        'gasto_fijo',
        'gasto_operativo',
        'retiro',
        'devolucion_cliente',
        'gasto_varios',
    ]

    REQUIERE_TIPO_GASTO = ['gasto_fijo', 'gasto_operativo', 'gasto_varios']

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    sesion = models.ForeignKey(
        'CajaSesion', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='movimientos',
        verbose_name="Sesión",
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, verbose_name="Tipo")
    concepto = models.CharField(max_length=40, choices=CONCEPTO_CHOICES, verbose_name="Concepto")
    origen = models.CharField(
        max_length=12, choices=ORIGEN_CHOICES, default='manual',
        verbose_name="Origen",
    )
    forma_pago = models.CharField(
        max_length=15, choices=FORMA_PAGO_MOV_CHOICES, default='efectivo',
        verbose_name="Forma de Pago",
    )
    monto = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Monto",
    )
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha")

    cliente = models.ForeignKey(
        'Cliente', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='caja_movimientos',
        verbose_name="Cliente",
    )
    tipo_gasto = models.ForeignKey(
        'TipoGasto', on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='movimientos',
        verbose_name="Tipo de Gasto",
    )

    referencia_alquiler = models.ForeignKey(
        'Alquiler', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='caja_movimientos',
        verbose_name="Alquiler",
    )
    referencia_venta = models.ForeignKey(
        'Venta', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='caja_movimientos',
        verbose_name="Venta",
    )
    referencia_confeccion = models.ForeignKey(
        'Confeccion', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='caja_movimientos',
        verbose_name="Confección",
    )
    referencia_reparacion = models.ForeignKey(
        'Reparacion', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='caja_movimientos',
        verbose_name="Reparación",
    )
    referencia_pago_comision = models.ForeignKey(
        'PagoComisionEmpleado', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='caja_movimientos',
        verbose_name="Pago de Comisión",
    )

    movimiento_reverso = models.OneToOneField(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reverso_de',
        verbose_name="Movimiento Reverso",
    )
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Usuario",
    )
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'Movimiento de Caja'
        verbose_name_plural = 'Movimientos de Caja'
        indexes = [
            models.Index(fields=['-fecha']),
            models.Index(fields=['sesion', '-fecha']),
            models.Index(fields=['concepto', '-fecha']),
            models.Index(fields=['forma_pago', '-fecha']),
            models.Index(fields=['tipo', '-fecha']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['referencia_alquiler', 'concepto'],
                condition=models.Q(movimiento_reverso__isnull=True) & ~models.Q(concepto__in=['alquiler_pago', 'alquiler_ajuste', 'anulacion_cobro']),
                name='unique_mov_alquiler_activo',
            ),
            models.UniqueConstraint(
                fields=['referencia_venta', 'concepto'],
                condition=models.Q(movimiento_reverso__isnull=True) & ~models.Q(concepto__in=['venta_ajuste', 'anulacion_cobro']),
                name='unique_mov_venta_activo',
            ),
            models.UniqueConstraint(
                fields=['referencia_confeccion', 'concepto'],
                condition=models.Q(movimiento_reverso__isnull=True) & ~models.Q(concepto__in=['confeccion_pago', 'anulacion_cobro']),
                name='unique_mov_confeccion_activo',
            ),
            models.UniqueConstraint(
                fields=['referencia_reparacion', 'concepto'],
                condition=models.Q(movimiento_reverso__isnull=True) & ~models.Q(concepto__in=['reparacion_pago', 'reparacion_ajuste', 'anulacion_cobro']),
                name='unique_mov_reparacion_activo',
            ),
            models.UniqueConstraint(
                fields=['referencia_pago_comision', 'concepto'],
                condition=models.Q(movimiento_reverso__isnull=True),
                name='unique_mov_comision_activo',
            ),
        ]

    def __str__(self):
        return f"{self.codigo} {self.get_tipo_display()} Bs {self.monto} ({self.get_concepto_display()})"

    @classmethod
    def concepto_tipo(cls, concepto):
        """Returns 'ingreso' or 'egreso' for a given concepto. Raises ValueError if unknown."""
        try:
            return cls.CONCEPTO_TIPO_MAP[concepto]
        except KeyError:
            raise ValueError(f"Concepto desconocido: {concepto}")

    def save(self, *args, **kwargs):
        # Auto-derive tipo from concepto (defensive)
        if self.concepto and not self.tipo:
            self.tipo = self.concepto_tipo(self.concepto)
        # Auto-generate codigo
        if not self.codigo:
            with transaction.atomic():
                last = CajaMovimiento.objects.select_for_update().order_by('-id').first()
                next_id = (last.id + 1) if last else 1
                self.codigo = f"MOV-{next_id:04d}"
        super().save(*args, **kwargs)

    @property
    def es_reverso(self):
        return self.movimiento_reverso_id is not None

    @property
    def fue_reversado(self):
        return hasattr(self, 'reverso_de')


class Conjunto(models.Model):
    TIPO_CHOICES = [('alquiler', 'Alquiler'), ('venta', 'Venta')]

    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    tipo = models.CharField(
        max_length=10,
        choices=TIPO_CHOICES,
        default='alquiler',
        verbose_name="Tipo",
    )
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    precio_sugerido = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Precio sugerido",
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        ordering = ['nombre']
        verbose_name = "Conjunto"
        verbose_name_plural = "Conjuntos"

    def __str__(self):
        return self.nombre


class ConjuntoSlot(models.Model):
    conjunto = models.ForeignKey(
        Conjunto,
        on_delete=models.CASCADE,
        related_name='slots',
    )
    prenda_item = models.ForeignKey(
        'PrendaItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conjunto_slots',
        verbose_name='Item de prenda',
    )
    opcional = models.BooleanField(default=False, verbose_name="Opcional")
    orden = models.PositiveSmallIntegerField(default=0, verbose_name="Orden")

    class Meta:
        ordering = ['orden', 'id']
        verbose_name = "Slot de conjunto"
        verbose_name_plural = "Slots de conjunto"

    def __str__(self):
        return f"{self.prenda_item} (orden {self.orden})" if self.prenda_item else f"(sin asignar, orden {self.orden})"
