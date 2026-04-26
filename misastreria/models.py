from django.db import models
from django.core.validators import EmailValidator, RegexValidator, MinValueValidator
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import ValidationError

class Empleado(models.Model):
    TIPO_CONTRATO_CHOICES = [
        ('fijo', 'Fijo'),
        ('contrato', 'Contrato'),
        ('porcentaje', 'Porcentaje'),
    ]
    
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código")
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
        # Capitalizar nombres, apellido_paterno, apellido_materno
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
    nombres = models.CharField(max_length=100, verbose_name="Nombres")
    apellido_paterno = models.CharField(max_length=100, verbose_name="Apellido Paterno")
    apellido_materno = models.CharField(max_length=100, verbose_name="Apellido Materno")
    edad = models.PositiveIntegerField(verbose_name="Edad")
    celular = models.CharField(max_length=15, validators=[RegexValidator(r'^\+?\d{9,15}$')], verbose_name="Celular")
    email = models.EmailField(null=True, blank=True, verbose_name="Correo Electrónico")
    fecha_registro = models.DateField(default=timezone.now, verbose_name="Fecha de Registro")
    notas = models.TextField(blank=True, verbose_name="Notas")

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombres', 'apellido_paterno']

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

    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código")
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

    def __str__(self):
        return f"Reparación {self.codigo} - {self.tipo_prenda} ({self.tipo_reparacion})"
class Categoria(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    
    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

class Inventario(models.Model):
    ESTADO_OPCIONES = [
        ('ACT', 'Activo'),
        ('BAJ', 'Baja'),
    ]
    
    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código", help_text="Formato: INV-001")
    articulo = models.CharField(max_length=100, verbose_name="Artículo")
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad")
    costo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Costo")
    precio = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name="Precio")
    fecha_ingreso = models.DateField(default=timezone.now, verbose_name="Fecha de Ingreso")
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoría")
    ultima_modificacion = models.DateTimeField(auto_now=True, verbose_name="Última Modificación")
    fecha_baja = models.DateField(null=True, blank=True, verbose_name="Fecha de Baja")
    motivo_baja = models.TextField(blank=True, verbose_name="Motivo de Baja")
    estado = models.CharField(max_length=3, choices=ESTADO_OPCIONES, default='ACT', verbose_name="Estado")

    class Meta:
        verbose_name = "Inventario"
        verbose_name_plural = "Inventarios"
        ordering = ['-fecha_ingreso']

    def clean(self):
        if self.cantidad < 0:
            raise ValidationError("La cantidad no puede ser negativa.")
        if self.costo is not None and self.costo < 0:
            raise ValidationError("El costo no puede ser negativo.")
        if self.fecha_baja and self.fecha_ingreso and self.fecha_baja < self.fecha_ingreso:
            raise ValidationError("La fecha de baja no puede ser anterior a la fecha de ingreso.")
        if self.estado == 'BAJ' and self.cantidad != 0:
            raise ValidationError("Un artículo dado de baja debe tener cantidad 0.")

    def save(self, *args, **kwargs):
        self.full_clean()  # Ejecuta clean() antes de guardar
        if not self.codigo:
            last = Inventario.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"INV-{numero:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.articulo

class BajaInventario(models.Model):
    inventario = models.ForeignKey(Inventario, on_delete=models.PROTECT, related_name='bajas', verbose_name="Artículo")
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad Dada de Baja")
    fecha_baja = models.DateField(default=timezone.now, verbose_name="Fecha de Baja")
    motivo_baja = models.TextField(verbose_name="Motivo de Baja")
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado En")

    class Meta:
        verbose_name = "Baja de Inventario"
        verbose_name_plural = "Bajas de Inventario"
        ordering = ['-fecha_baja']

    def clean(self):
        if self.cantidad <= 0:
            raise ValidationError("La cantidad dada de baja debe ser mayor que cero.")
        if not self.motivo_baja:
            raise ValidationError("El motivo de baja es obligatorio.")
        # La validación de cantidad disponible se mueve a la vista

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Baja de {self.cantidad} unidades de {self.inventario} el {self.fecha_baja}"

class Venta(Servicio):
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código")
    fecha_venta = models.DateField(default=timezone.now, verbose_name="Fecha de Venta")
    articulo = models.ForeignKey(Inventario, on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad")
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Unitario")
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio Total")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, related_name='ventas', verbose_name="Cliente")

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']

    def clean(self):
        if self.articulo and self.cantidad > self.articulo.cantidad:
            raise ValidationError(f"No hay suficiente stock para {self.articulo}. Stock disponible: {self.articulo.cantidad}")
        if self.cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor que cero.")

    def save(self, *args, **kwargs):
        self.tipo = 'ventas'
        if not self.codigo:
            last = Venta.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"VEN-{numero:03d}"
        # Establecer precio_unitario desde Inventario
        self.precio_unitario = self.articulo.precio
        # Calcular precio_total
        self.precio_total = self.cantidad * self.precio_unitario
        self.clean()
        if self.pk:  # Edición
            original = Venta.objects.get(pk=self.pk)
            diferencia = self.cantidad - original.cantidad
            if diferencia != 0:
                self.articulo.cantidad -= diferencia
                self.articulo.save()
        else:  # Creación
            self.articulo.cantidad -= self.cantidad
            self.articulo.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Venta {self.codigo} - {self.articulo}"
class Confeccion(models.Model):
    TIPO_PRENDA_CHOICES = [
        ('pantalon', 'Pantalón'),
        ('chaleco', 'Chaleco'),
        ('saco', 'Saco'),
        ('saco_mujer', 'Saco – Mujer'),
        ('chaleco_mujer', 'Chaleco – Mujer'),
    ]
    
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('entregado', 'Entregado'),
    ]
    
    codigo = models.CharField(max_length=20, unique=True)
    fecha_inicio = models.DateField(default=timezone.now)
    tipo_prenda = models.CharField(max_length=20, choices=TIPO_PRENDA_CHOICES)
    color = models.CharField(max_length=50)
    modelo = models.CharField(max_length=100)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True)
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, null=True, blank=True)
    observaciones = models.TextField(blank=True)
    
    # Medidas para Pantalón
    pantalon_largo_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_largo_entrepierna = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_pierna = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_rodilla = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_contorno_bota = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_tiro_delantero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pantalon_tiro_trasero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Medidas para Chaleco
    chaleco_contorno_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_contorno_cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_largo_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_largo_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_altura_botones = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Medidas para Saco
    saco_contorno_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_largo_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_largo_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_ancho_hombros = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_ancho_espalda = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_brazo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_largo_manga = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_contorno_puno = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Medidas para Saco – Mujer
    saco_mujer_contorno_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_contorno_cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_ancho_hombros = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_ancho_espalda = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_largo_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_largo_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_altura_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_separacion_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    saco_mujer_dif_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Medidas para Chaleco – Mujer
    chaleco_mujer_contorno_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_contorno_cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_contorno_cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_largo_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_largo_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_altura_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_separacion_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    chaleco_mujer_largo_delantero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Pagos y Fechas
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adelanto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_prueba = models.DateField(null=True, blank=True)
    fecha_entrega = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    
    def clean(self):
        if self.adelanto > self.precio:
            raise ValidationError("El adelanto no puede ser mayor que el precio.")
        if self.saldo != self.precio - self.adelanto:
            raise ValidationError("El saldo debe ser igual al precio menos el adelanto.")
        if self.fecha_prueba and self.fecha_inicio and self.fecha_prueba < self.fecha_inicio:
            raise ValidationError("La fecha de prueba no puede ser anterior a la fecha de confección.")
        if self.fecha_entrega and self.fecha_prueba and self.fecha_entrega < self.fecha_prueba:
            raise ValidationError("La fecha de entrega no puede ser anterior a la fecha de prueba.")
        
        # Validar medidas según tipo_prenda
        medidas_requeridas = {
            'pantalon': [
                'pantalon_largo_total', 'pantalon_contorno_cintura', 'pantalon_contorno_cadera',
                'pantalon_largo_entrepierna', 'pantalon_contorno_pierna', 'pantalon_contorno_rodilla',
                'pantalon_contorno_bota', 'pantalon_tiro_delantero', 'pantalon_tiro_trasero'
            ],
            'chaleco': [
                'chaleco_contorno_busto', 'chaleco_contorno_cintura', 'chaleco_contorno_cadera',
                'chaleco_largo_talle', 'chaleco_largo_total', 'chaleco_altura_botones'
            ],
            'saco': [
                'saco_contorno_busto', 'saco_contorno_cintura', 'saco_contorno_cadera',
                'saco_largo_talle', 'saco_largo_total', 'saco_ancho_hombros',
                'saco_ancho_espalda', 'saco_contorno_brazo', 'saco_largo_manga', 'saco_contorno_puno'
            ],
            'saco_mujer': [
                'saco_mujer_contorno_busto', 'saco_mujer_contorno_cintura', 'saco_mujer_contorno_cadera',
                'saco_mujer_ancho_hombros', 'saco_mujer_ancho_espalda', 'saco_mujer_largo_talle',
                'saco_mujer_largo_total', 'saco_mujer_altura_busto', 'saco_mujer_separacion_busto',
                'saco_mujer_dif_talle'
            ],
            'chaleco_mujer': [
                'chaleco_mujer_contorno_busto', 'chaleco_mujer_contorno_cintura', 'chaleco_mujer_contorno_cadera',
                'chaleco_mujer_largo_talle', 'chaleco_mujer_largo_total', 'chaleco_mujer_altura_busto',
                'chaleco_mujer_separacion_busto', 'chaleco_mujer_largo_delantero'
            ]
        }
        
        for tipo, campos in medidas_requeridas.items():
            if self.tipo_prenda == tipo:
                for campo in campos:
                    if getattr(self, campo) is None:
                        raise ValidationError(f"El campo {campo} es requerido para {tipo}.")
            else:
                for campo in campos:
                    if getattr(self, campo) is not None:
                        raise ValidationError(f"El campo {campo} no debe estar lleno para {self.tipo_prenda}.")
    
    def __str__(self):
        return f"{self.codigo} - {self.get_tipo_prenda_display()}"
    
class Alquiler(Servicio):
    ESTADO_OPCIONES = [
        ('alquilado', 'Alquilado'),
        ('devuelto', 'Devuelto'),
    ]
    
    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código", help_text="Formato: ALQ-001")
    fecha_alquiler = models.DateField(default=timezone.now, verbose_name="Fecha de Alquiler")
    articulo = models.ForeignKey(Inventario, on_delete=models.PROTECT, verbose_name="Artículo")
    cantidad = models.PositiveIntegerField(verbose_name="Cantidad")
    costo_alquiler = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)], verbose_name="Costo de Alquiler")
    fecha_devolucion = models.DateField(verbose_name="Fecha de Devolución")
    estado = models.CharField(max_length=20, choices=ESTADO_OPCIONES, default='alquilado', verbose_name="Estado")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, related_name='alquileres', verbose_name="Cliente")
    garantia = models.TextField(blank=True, verbose_name="Garantía")

    class Meta:
        verbose_name = "Alquiler"
        verbose_name_plural = "Alquileres"
        ordering = ['-fecha_alquiler']

    def clean(self):
        if self.cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor que cero.")
        if self.fecha_devolucion <= self.fecha_alquiler:
            raise ValidationError("La fecha de devolución debe ser posterior a la fecha de alquiler.")
        if self.articulo:
            if self.articulo.estado == 'BAJ':
                raise ValidationError(f"El artículo {self.articulo} está dado de baja y no puede alquilarse.")
            if self.cantidad > self.articulo.cantidad:
                raise ValidationError(f"No hay suficiente stock para {self.articulo}. Stock disponible: {self.articulo.cantidad}")

    def save(self, *args, **kwargs):
        self.tipo = 'alquiler'
        if not self.codigo:
            last = Alquiler.objects.order_by('-id').first()
            numero = int(last.codigo.split('-')[1]) + 1 if last else 1
            self.codigo = f"ALQ-{numero:03d}"
        self.clean()
        if self.pk:  # Edición
            original = Alquiler.objects.get(pk=self.pk)
            if original.estado != self.estado:
                if self.estado == 'devuelto':
                    self.articulo.cantidad += self.cantidad
                    self.articulo.save()
                elif original.estado == 'devuelto' and self.estado == 'alquilado':
                    self.articulo.cantidad -= self.cantidad
                    self.articulo.save()
            else:
                diferencia = self.cantidad - original.cantidad
                if diferencia != 0 and self.estado == 'alquilado':
                    self.articulo.cantidad -= diferencia
                    self.articulo.save()
        else:  # Creación
            if self.estado == 'alquilado':
                self.articulo.cantidad -= self.cantidad
                self.articulo.save()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Alquiler {self.codigo} - {self.articulo}"

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

    class Meta:
        verbose_name = "Transacción"
        verbose_name_plural = "Transacciones"
        ordering = ['-fecha']

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
