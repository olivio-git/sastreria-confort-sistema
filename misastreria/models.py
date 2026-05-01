from django.db import models
from django.core.validators import EmailValidator, RegexValidator, MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

class Empleado(models.Model):
    TIPO_CONTRATO_CHOICES = [
        ('fijo', 'Fijo'),
        ('contrato', 'Contrato'),
        ('porcentaje', 'Porcentaje'),
    ]

    codigo = models.CharField(max_length=10, unique=True, blank=True, verbose_name="Código")
    ci = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="CI")
    nombres = models.CharField(max_length=100, verbose_name="Nombres")
    apellido_paterno = models.CharField(max_length=100, verbose_name="Apellido Paterno")
    apellido_materno = models.CharField(max_length=100, verbose_name="Apellido Materno")
    celular = models.CharField(max_length=15, validators=[RegexValidator(r'^\+?\d{9,15}$')], verbose_name="Celular")
    email = models.EmailField(null=True, blank=True, validators=[EmailValidator()], verbose_name="Correo Electrónico")
    tipo_contrato = models.CharField(max_length=20, choices=TIPO_CONTRATO_CHOICES, verbose_name="Tipo de Contrato")
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
        self.apellido_paterno = self.apellido_paterno.capitalize()
        self.apellido_materno = self.apellido_materno.capitalize()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ['nombres', 'apellido_paterno']

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno} {self.apellido_materno}".strip()


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


class Reparacion(models.Model):
    TIPO_PRENDA_CHOICES = [
        ('camisa', 'Camisa'),
        ('pantalon', 'Pantalón'),
        ('chaqueta', 'Chaqueta'),
        ('vestido', 'Vestido'),
        ('falda', 'Falda'),
        ('otro', 'Otro'),
    ]

    TIPO_REPARACION_CHOICES = [
        ('costura', 'Costura'),
        ('parche', 'Parche'),
        ('cambio_cremallera', 'Cambio de Cremallera'),
        ('ajuste', 'Ajuste'),
        ('otro', 'Otro'),
    ]

    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('entregado', 'Entregado'),
    ]

    codigo = models.CharField(max_length=10, unique=True, blank=True, verbose_name="Código")
    tipo_prenda = models.CharField(max_length=20, choices=TIPO_PRENDA_CHOICES, verbose_name="Tipo de Prenda")
    otro_prenda = models.CharField(max_length=100, blank=True, null=True, verbose_name="Otra Prenda")
    tipo_reparacion = models.CharField(max_length=20, choices=TIPO_REPARACION_CHOICES, verbose_name="Tipo de Reparación")
    otro_reparacion = models.CharField(max_length=100, blank=True, null=True, verbose_name="Otra Reparación")
    costo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Costo")
    detalles = models.TextField(blank=True, null=True, verbose_name="Detalles")
    fecha_entrega = models.DateField(verbose_name="Fecha de Entrega")
    empleado = models.ForeignKey(Empleado, on_delete=models.SET_NULL, null=True, related_name='reparaciones', verbose_name="Asignado a")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, related_name='reparaciones', verbose_name="Cliente")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente', verbose_name="Estado")
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

    def __str__(self):
        return f"Reparación {self.codigo} - {self.tipo_prenda} ({self.tipo_reparacion})"


class PrendaInventario(models.Model):
    TIPO_CHOICES = [
        ('venta', 'Para Venta'),
        ('alquiler', 'Para Alquiler'),
    ]
    CONDICION_CHOICES = [
        ('nueva', 'Nueva'),
        ('usada', 'Usada'),
        ('remate', 'Remate'),
    ]
    ESTADO_OPCIONES = [
        ('ACT', 'Activo'),
        ('BAJ', 'Baja'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, verbose_name="Tipo")
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    modelo = models.CharField(max_length=100, blank=True, verbose_name="Modelo / Línea")
    talla = models.CharField(max_length=20, blank=True, verbose_name="Talla")
    color = models.CharField(max_length=50, blank=True, verbose_name="Color")
    codigo_referencia = models.CharField(max_length=100, blank=True, verbose_name="Código de Referencia")
    condicion = models.CharField(
        max_length=10, choices=CONDICION_CHOICES, default='nueva',
        blank=True, verbose_name="Condición",
        help_text="Solo aplica a prendas de alquiler"
    )
    veces_alquilado = models.PositiveIntegerField(default=0, verbose_name="Veces Alquilado")
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad en Stock")
    stock_minimo = models.PositiveIntegerField(null=True, blank=True, verbose_name="Stock Mínimo")
    precio = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0.01)], verbose_name="Precio"
    )
    estado = models.CharField(max_length=3, choices=ESTADO_OPCIONES, default='ACT', verbose_name="Estado")
    notas = models.TextField(blank=True, verbose_name="Notas")
    creado = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso")

    class Meta:
        verbose_name = "Prenda"
        verbose_name_plural = "Prendas"
        ordering = ['nombre', 'talla']

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


class Insumo(models.Model):
    TIPO_MATERIAL_CHOICES = [
        ('tela', 'Tela'),
        ('hilo', 'Hilo'),
        ('accesorio', 'Accesorio'),
        ('entretela', 'Entretela'),
        ('otro', 'Otro'),
    ]
    UNIDAD_MEDIDA_CHOICES = [
        ('metro', 'Metro'),
        ('kg', 'Kilogramo'),
        ('unidad', 'Unidad'),
        ('rollo', 'Rollo'),
    ]
    ESTADO_OPCIONES = [
        ('ACT', 'Activo'),
        ('BAJ', 'Baja'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    tipo_material = models.CharField(max_length=20, choices=TIPO_MATERIAL_CHOICES, verbose_name="Tipo de Material")
    articulo = models.CharField(max_length=100, verbose_name="Artículo")
    coleccion = models.CharField(max_length=100, blank=True, verbose_name="Colección / Cuaderno")
    color = models.CharField(max_length=50, blank=True, verbose_name="Color")
    codigo_referencia = models.CharField(max_length=100, blank=True, verbose_name="Código de Referencia")
    tipo_tela = models.CharField(max_length=50, blank=True, verbose_name="Tipo de Tela")
    unidad_medida = models.CharField(max_length=10, choices=UNIDAD_MEDIDA_CHOICES, default='metro', verbose_name="Unidad de Medida")
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
        ordering = ['tipo_material', 'articulo']

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
    articulo = models.ForeignKey(PrendaInventario, on_delete=models.PROTECT, verbose_name="Prenda")
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")

    class Meta:
        verbose_name = "Ítem de Venta"
        verbose_name_plural = "Ítems de Venta"

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.articulo} × {self.cantidad}"


class Confeccion(models.Model):
    TIPO_PRENDA_CHOICES = [
        ('pantalon',     'Pantalón'),
        ('chaleco',      'Chaleco'),
        ('saco',         'Saco'),
        ('saco_mujer',   'Saco – Mujer'),
        ('chaleco_mujer','Chaleco – Mujer'),
    ]
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
    empleado     = models.ForeignKey(Empleado, on_delete=models.PROTECT, null=True, blank=True)
    observaciones= models.TextField(blank=True)
    precio       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adelanto     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_prueba = models.DateField(null=True, blank=True)
    fecha_entrega= models.DateField(null=True, blank=True)
    estado       = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    creado       = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")

    class Meta:
        verbose_name = "Confección"
        verbose_name_plural = "Confecciones"
        ordering = ['-creado']

    @property
    def tipos_prenda_display(self):
        return ', '.join(item.get_tipo_prenda_display() for item in self.items.all())

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
    TIPO_PRENDA_CHOICES = Confeccion.TIPO_PRENDA_CHOICES

    confeccion = models.ForeignKey(Confeccion, on_delete=models.CASCADE, related_name='items')
    tipo_prenda = models.CharField(max_length=20, choices=TIPO_PRENDA_CHOICES)

    # Pantalón
    pantalon_largo_total        = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_cintura   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_cadera    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_largo_entrepierna  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_pierna    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_rodilla   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_bota      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_tiro_delantero     = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_tiro_trasero       = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Chaleco
    chaleco_contorno_busto   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_contorno_cadera  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_largo_talle      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_largo_total      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_altura_botones   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Saco
    saco_contorno_busto   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_cadera  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_largo_talle      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_largo_total      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_ancho_hombros    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_ancho_espalda    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_brazo   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_largo_manga      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_puno    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Saco – Mujer
    saco_mujer_contorno_busto    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_contorno_cintura  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_contorno_cadera   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_ancho_hombros     = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_ancho_espalda     = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_largo_talle       = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_largo_total       = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_altura_busto      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_separacion_busto  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_dif_talle         = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Chaleco – Mujer
    chaleco_mujer_contorno_busto   = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_contorno_cadera  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_largo_talle      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_largo_total      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_altura_busto     = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_separacion_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_largo_delantero  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return self.get_tipo_prenda_display()


class Alquiler(Servicio):
    ESTADO_OPCIONES = [
        ('alquilado', 'Alquilado'),
        ('devuelto', 'Devuelto'),
    ]

    codigo = models.CharField(max_length=20, unique=True, blank=True, verbose_name="Código")
    fecha_alquiler = models.DateField(default=timezone.now, verbose_name="Fecha de Alquiler")
    fecha_devolucion = models.DateField(verbose_name="Fecha de Devolución")
    estado = models.CharField(max_length=20, choices=ESTADO_OPCIONES, default='alquilado', verbose_name="Estado")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='alquileres', verbose_name="Cliente")
    empleado = models.ForeignKey(Empleado, on_delete=models.SET_NULL, null=True, blank=True, related_name='alquileres', verbose_name="Empleado")
    descuento = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Descuento (%)")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    garantia = models.TextField(blank=True, verbose_name="Garantía")
    notas = models.TextField(blank=True, verbose_name="Notas")

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

    def __str__(self):
        return f"Alquiler {self.codigo}"


class AlquilerItem(models.Model):
    alquiler = models.ForeignKey(Alquiler, on_delete=models.CASCADE, related_name='items')
    articulo = models.ForeignKey(PrendaInventario, on_delete=models.PROTECT, verbose_name="Prenda")
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad")
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")

    class Meta:
        verbose_name = "Ítem de Alquiler"
        verbose_name_plural = "Ítems de Alquiler"

    def save(self, *args, **kwargs):
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.articulo} × {self.cantidad}"


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
