import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from misastreria.models import (
    Empleado, Permiso, Falta,
    Cliente,
    PrendaInventario, Insumo,
    Reparacion,
    Confeccion, ConfeccionItem,
    Alquiler, AlquilerItem,
    Venta, VentaItem,
    Transaccion,
    OrdenProduccion, InsumoCortado,
)


def rand_fecha(dias_max=365, dias_min=0):
    return date.today() - timedelta(days=random.randint(dias_min, dias_max))


NOMBRES = ['Carlos', 'Juan', 'Luis', 'Marco', 'Diego', 'Rodrigo', 'Fernando',
           'Álvaro', 'Gonzalo', 'Pablo', 'Óscar', 'Héctor', 'Miguel', 'Sergio',
           'María', 'Ana', 'Lucía', 'Sofía', 'Valeria', 'Camila', 'Patricia',
           'Sandra', 'Laura', 'Claudia', 'Gabriela', 'Rosa', 'Carmen', 'Elena']

APELLIDOS = ['Mamani', 'Quispe', 'Choque', 'Lima', 'Flores', 'García', 'Condori',
             'Vargas', 'Mendoza', 'Rojas', 'Sánchez', 'Torrez', 'Huanca', 'Copa',
             'Apaza', 'Villca', 'Cusi', 'Poma', 'Laime', 'Colque', 'Alanoca',
             'Catacora', 'Mamani', 'Ticona', 'Herrera', 'Gutierrez', 'Aliaga']


class Command(BaseCommand):
    help = 'Inserta datos de prueba masivos para Sastrería Confort'

    def handle(self, *args, **kwargs):
        self.stdout.write('Limpiando datos previos...')
        self._limpiar()

        self.stdout.write('Creando empleados...')
        empleados = self._crear_empleados()

        self.stdout.write('Creando clientes...')
        clientes = self._crear_clientes()

        self.stdout.write('Creando inventario de prendas...')
        prendas_alq, prendas_vta = self._crear_prendas()

        self.stdout.write('Creando insumos...')
        insumos = self._crear_insumos()

        self.stdout.write('Creando reparaciones...')
        self._crear_reparaciones(clientes, empleados)

        self.stdout.write('Creando confecciones...')
        confecciones = self._crear_confecciones(clientes, empleados)

        self.stdout.write('Creando alquileres...')
        self._crear_alquileres(clientes, empleados, prendas_alq)

        self.stdout.write('Creando ventas...')
        self._crear_ventas(clientes, empleados, prendas_vta)

        self.stdout.write('Creando órdenes de producción...')
        self._crear_ordenes(confecciones, empleados, insumos)

        self.stdout.write('Creando transacciones...')
        self._crear_transacciones()

        self.stdout.write(self.style.SUCCESS('✓ Datos de prueba creados exitosamente.'))

    # ------------------------------------------------------------------ #

    def _limpiar(self):
        InsumoCortado.objects.all().delete()
        OrdenProduccion.objects.all().delete()
        VentaItem.objects.all().delete()
        Venta.objects.all().delete()
        AlquilerItem.objects.all().delete()
        Alquiler.objects.all().delete()
        ConfeccionItem.objects.all().delete()
        Confeccion.objects.all().delete()
        Reparacion.objects.all().delete()
        Transaccion.objects.all().delete()
        Falta.objects.all().delete()
        Permiso.objects.all().delete()
        Empleado.objects.all().delete()
        Cliente.objects.all().delete()
        PrendaInventario.objects.all().delete()
        Insumo.objects.all().delete()

    # ------------------------------------------------------------------ #

    def _crear_empleados(self):
        # (nombres, ap, am, ci, tipo_contrato, fecha_baja)
        datos = [
            ('Carlos',   'Mamani',  'Quispe',  '7123456', 'fijo',       None),
            ('Juan',     'Condori', 'Lima',     '7234567', 'fijo',       None),
            ('Luis',     'Flores',  'Garcia',   '7345678', 'contrato',   None),
            ('Maria',    'Choque',  'Vargas',   '7456789', 'fijo',       None),
            ('Ana',      'Quispe',  'Mendoza',  '7567890', 'porcentaje', None),
            ('Diego',    'Torrez',  'Apaza',    '7678901', 'contrato',   None),
            ('Patricia', 'Rojas',   'Huanca',   '7789012', 'porcentaje', None),
            ('Rodrigo',  'Vargas',  'Sanchez',  '7890123', 'contrato',   rand_fecha(60, 30)),
            ('Sofia',    'Lima',    'Colque',   '7901234', 'fijo',       None),
            ('Marco',    'Huanca',  'Villca',   '8012345', 'contrato',   None),
        ]
        empleados = []
        for nombres, ap, am, ci, contrato, fecha_baja in datos:
            e = Empleado(
                nombres=nombres, apellido_paterno=ap, apellido_materno=am,
                ci=ci, tipo_contrato=contrato,
                fecha_ingreso=rand_fecha(900, 180),
                fecha_baja=fecha_baja,
                celular=f'7{random.randint(1000000, 9999999)}',
            )
            e.save()
            empleados.append(e)

        motivos_permiso = [
            'Control medico de rutina', 'Emergencia familiar',
            'Tramites personales', 'Cita medica',
        ]
        motivos_falta = [
            'Enfermedad sin aviso', 'Emergencia familiar',
            'Sin justificacion', 'Transporte',
        ]
        for emp in random.sample(empleados, 6):
            for _ in range(random.randint(1, 4)):
                Permiso.objects.create(
                    empleado=emp,
                    fecha_permiso=rand_fecha(300, 10),
                    motivo=random.choice(motivos_permiso),
                )
        for emp in random.sample(empleados, 5):
            for _ in range(random.randint(1, 3)):
                Falta.objects.create(
                    empleado=emp,
                    fecha_falta=rand_fecha(200, 5),
                    motivo=random.choice(motivos_falta),
                )
        return empleados

    # ------------------------------------------------------------------ #

    def _crear_clientes(self):
        clientes = []
        cis_usados = set()
        combos = [(n, a1, a2) for n in NOMBRES for a1 in APELLIDOS for a2 in APELLIDOS]
        random.shuffle(combos)
        direcciones = [
            'Av. Siempre Viva 123', 'Calle Murillo 456', 'Av. Montes 789',
            'Calle Colón 321', 'Av. Arce 654', 'Calle Potosí 987',
            'Zona Sur, Calle 15 Nro. 8', 'Miraflores, Av. Bush 100',
            'Villa Copacabana, Calle 3', 'El Alto, Av. 6 de Marzo 55',
            'Sopocachi, Calle Presbítero Medina', 'San Pedro, Calle Catacora',
        ]
        for nombres, ap, am in combos:
            ci = str(random.randint(5000000, 9999999))
            if ci in cis_usados:
                continue
            cis_usados.add(ci)
            c = Cliente(
                nombres=nombres, apellido_paterno=ap, apellido_materno=am,
                ci=ci,
                celular=f'7{random.randint(1000000, 9999999)}',
                notas=random.choice(['', '', 'Cliente frecuente', 'Referido', 'Pago puntual']),
            )
            c.save()
            clientes.append(c)
            if len(clientes) >= 40:
                break
        return clientes

    # ------------------------------------------------------------------ #

    def _crear_prendas(self):
        # (nombre, modelo, talla, color, condicion, cantidad, stock_min, precio)
        alquiler_data = [
            ('Terno Clásico',         'Clásico',   'M',  'Negro',  'nueva', 8,  2, 120),
            ('Terno Clásico',         'Clásico',   'L',  'Negro',  'nueva', 6,  2, 120),
            ('Terno Moderno',         'Slim Fit',  'M',  'Azul',   'nueva', 5,  2, 130),
            ('Terno Moderno',         'Slim Fit',  'XL', 'Azul',   'nueva', 4,  1, 130),
            ('Frac',                  'Formal',    'M',  'Negro',  'nueva', 3,  1, 180),
            ('Frac',                  'Formal',    'L',  'Negro',  'nueva', 2,  1, 180),
            ('Smoking',               'Elegante',  'M',  'Negro',  'usada', 4,  1, 160),
            ('Levita',                'Vintage',   'M',  'Gris',   'usada', 2,  1, 150),
            ('Camisa Formal',         'Clásica',   'M',  'Blanco', 'nueva', 12, 3, 40),
            ('Camisa Formal',         'Clásica',   'L',  'Blanco', 'nueva', 10, 3, 40),
            ('Camisa Formal',         'Clásica',   'S',  'Blanco', 'nueva', 8,  2, 40),
            ('Corbata',               'Clásica',   'U',  'Negro',  'nueva', 20, 5, 20),
            ('Corbata',               'Elegante',  'U',  'Rojo',   'nueva', 15, 5, 20),
            ('Corbata',               'Moderna',   'U',  'Azul',   'nueva', 15, 5, 20),
            ('Chaleco',               'Formal',    'M',  'Negro',  'nueva', 8,  2, 50),
            ('Chaleco',               'Formal',    'L',  'Negro',  'nueva', 6,  2, 50),
            ('Chaleco',               'Moderno',   'M',  'Gris',   'nueva', 5,  2, 55),
            ('Moño',                  'Clásico',   'U',  'Negro',  'nueva', 25, 5, 15),
            ('Faja',                  'Formal',    'U',  'Negro',  'nueva', 18, 4, 25),
            ('Pantalón Formal',       'Classic',   'M',  'Negro',  'usada', 10, 3, 45),
            # Stock bajo para ver alerta en dashboard
            ('Smoking Blanco',        'Premium',   'M',  'Blanco', 'nueva', 1,  3, 200),
        ]
        prendas_alq = []
        for nombre, modelo, talla, color, cond, cant, stock_min, precio in alquiler_data:
            p = PrendaInventario(
                tipo='alquiler', nombre=nombre, modelo=modelo, talla=talla,
                color=color, condicion=cond, cantidad=cant,
                stock_minimo=stock_min, precio=Decimal(str(precio)), estado='ACT',
            )
            p.save()
            prendas_alq.append(p)

        venta_data = [
            ('Terno Completo',    'Slim Fit',  '42', 'Negro',  10, 3, 850),
            ('Terno Completo',    'Classic',   '44', 'Azul',   8,  2, 880),
            ('Terno Completo',    'Modern',    '40', 'Gris',   6,  2, 820),
            ('Saco',              'Formal',    '42', 'Negro',  7,  2, 420),
            ('Saco',              'Sport',     '44', 'Azul',   5,  1, 380),
            ('Pantalón Formal',   'Slim',      '32', 'Negro',  12, 3, 220),
            ('Pantalón Formal',   'Classic',   '34', 'Azul',   10, 3, 210),
            ('Camisa Manga Larga','Formal',    'M',  'Blanco', 15, 4, 120),
            ('Camisa Manga Larga','Formal',    'L',  'Celeste',14, 4, 120),
            ('Corbata Seda',      'Premium',   'U',  'Varios', 20, 5, 80),
            ('Chaleco Formal',    'Classic',   'M',  'Negro',  8,  2, 180),
            ('Pañuelo Bolsillo',  'Elegante',  'U',  'Blanco', 30, 8, 35),
            # Stock bajo para ver alerta
            ('Terno Juvenil',     'Moderno',   '38', 'Marrón', 1,  4, 750),
        ]
        prendas_vta = []
        for nombre, modelo, talla, color, cant, stock_min, precio in venta_data:
            p = PrendaInventario(
                tipo='venta', nombre=nombre, modelo=modelo, talla=talla,
                color=color, cantidad=cant, stock_minimo=stock_min,
                precio=Decimal(str(precio)), estado='ACT',
            )
            p.save()
            prendas_vta.append(p)

        return prendas_alq, prendas_vta

    # ------------------------------------------------------------------ #

    def _crear_insumos(self):
        # (articulo, tipo_material, unidad_medida, cantidad, stock_min, precio_costo)
        datos = [
            ('Tela Casimir',       'tela',      'metro',  45,  10, Decimal('85')),
            ('Tela Casimir',       'tela',      'metro',  38,  10, Decimal('85')),
            ('Tela Casimir Gris',  'tela',      'metro',  30,  10, Decimal('80')),
            ('Tela Popelina',      'tela',      'metro',  60,  15, Decimal('35')),
            ('Tela Popelina',      'tela',      'metro',  50,  15, Decimal('35')),
            ('Entretela',          'entretela', 'metro',  40,  10, Decimal('22')),
            ('Forro Negro',        'tela',      'metro',  35,   8, Decimal('30')),
            ('Forro Azul',         'tela',      'metro',  28,   8, Decimal('30')),
            ('Hilo Negro',         'hilo',      'rollo',  25,   5, Decimal('18')),
            ('Hilo Blanco',        'hilo',      'rollo',  22,   5, Decimal('18')),
            ('Hilo Azul',          'hilo',      'rollo',  15,   5, Decimal('18')),
            ('Botones Saco',       'accesorio', 'unidad', 120, 30, Decimal('2')),
            ('Botones Dorados',    'accesorio', 'unidad', 80,  20, Decimal('3')),
            ('Cierre Nylon',       'accesorio', 'unidad', 80,  20, Decimal('4')),
            ('Cierre Invisible',   'accesorio', 'unidad', 60,  15, Decimal('6')),
            ('Cinta Sesgo',        'otro',      'metro',  100, 25, Decimal('3')),
            # Stock bajo para ver alerta
            ('Tela Seda Blanca',   'tela',      'metro',  2,   10, Decimal('120')),
        ]
        insumos = []
        colores = ['Negro', 'Azul marino', 'Gris', 'Blanco', 'Celeste', '']
        for i, (articulo, tipo, unidad, cant, stock_min, precio) in enumerate(datos):
            ins = Insumo(
                articulo=articulo,
                tipo_material=tipo,
                unidad_medida=unidad,
                cantidad=Decimal(str(cant)),
                stock_minimo=Decimal(str(stock_min)),
                precio_costo=precio,
                color=colores[i % len(colores)],
                estado='ACT',
            )
            ins.save()
            insumos.append(ins)
        return insumos

    # ------------------------------------------------------------------ #

    def _crear_reparaciones(self, clientes, empleados):
        tipos_prenda = ['camisa', 'pantalon', 'chaqueta', 'vestido', 'falda', 'otro']
        tipos_rep    = ['costura', 'parche', 'cambio_cremallera', 'ajuste', 'otro']
        estados      = ['pendiente', 'en_proceso', 'entregado']
        pesos        = [0.25, 0.25, 0.50]
        detalles_ops = [
            'Reparar costura lateral', 'Cambiar cierre dañado',
            'Ajustar cintura 2 cm', 'Parche interno en rodilla',
            'Reparar bolsillo interno', 'Acortar ruedo 3 cm',
            'Ensanchar talle', 'Reforzar costura hombro',
            'Cambio de cierre trasero', 'Arreglo de dobladillo',
            '', '',
        ]
        for _ in range(50):
            estado = random.choices(estados, pesos)[0]
            creado = rand_fecha(300, 0)
            r = Reparacion(
                tipo_prenda=random.choice(tipos_prenda),
                tipo_reparacion=random.choice(tipos_rep),
                costo=Decimal(str(random.choice([30, 40, 50, 60, 80, 100, 120, 150, 180, 200]))),
                fecha_entrega=creado + timedelta(days=random.randint(2, 10)),
                empleado=random.choice(empleados),
                cliente=random.choice(clientes) if random.random() > 0.1 else None,
                estado=estado,
                detalles=random.choice(detalles_ops),
            )
            r.save()

    # ------------------------------------------------------------------ #

    def _crear_confecciones(self, clientes, empleados):
        tipos_item = ['pantalon', 'chaleco', 'saco', 'saco_mujer', 'chaleco_mujer']
        colores    = ['Negro', 'Azul marino', 'Gris oxford', 'Marrón', 'Blanco roto']
        modelos    = ['Slim Fit', 'Classic', 'Regular', 'Modern', 'Sport']
        estados    = ['pendiente', 'en_proceso', 'entregado']
        pesos      = [0.25, 0.35, 0.40]
        notas_ops  = ['', '', 'Para boda', 'Para grado', 'Para quinceañera',
                      'Urgente — fin de semana', 'Cliente exigente', 'Medidas ajustadas']

        confecciones = []
        for _ in range(38):
            inicio = rand_fecha(300, 5)
            estado = random.choices(estados, pesos)[0]
            precio = Decimal(str(random.choice([500, 600, 700, 800, 900, 1000, 1200, 1400, 1500])))
            adelanto = Decimal(str(random.randint(100, int(precio * Decimal('0.5')))))

            con = Confeccion(
                cliente=random.choice(clientes) if random.random() > 0.05 else None,
                empleado=random.choice(empleados),
                fecha_inicio=inicio,
                fecha_entrega=inicio + timedelta(days=random.randint(7, 30)),
                estado=estado,
                precio=precio,
                adelanto=adelanto,
                color=random.choice(colores),
                modelo=random.choice(modelos),
                observaciones=random.choice(notas_ops),
            )
            con.save()

            tipos_seleccionados = random.sample(tipos_item, random.randint(1, 3))
            for tipo in tipos_seleccionados:
                item = ConfeccionItem(confeccion=con, tipo_prenda=tipo)
                v = lambda: Decimal(str(round(random.uniform(70, 115), 1)))
                if tipo == 'pantalon':
                    item.pantalon_largo_total = Decimal(str(random.randint(100, 112)))
                    item.pantalon_contorno_cintura = v()
                    item.pantalon_contorno_cadera = v()
                    item.pantalon_largo_entrepierna = Decimal(str(random.randint(72, 82)))
                elif tipo == 'saco':
                    item.saco_contorno_busto = v()
                    item.saco_contorno_cintura = v()
                    item.saco_contorno_cadera = v()
                    item.saco_ancho_hombros = Decimal(str(round(random.uniform(42, 52), 1)))
                    item.saco_largo_total = Decimal(str(random.randint(70, 80)))
                    item.saco_largo_manga = Decimal(str(random.randint(60, 68)))
                elif tipo == 'chaleco':
                    item.chaleco_contorno_busto = v()
                    item.chaleco_contorno_cintura = v()
                    item.chaleco_contorno_cadera = v()
                    item.chaleco_largo_total = Decimal(str(random.randint(55, 65)))
                elif tipo == 'saco_mujer':
                    item.saco_mujer_contorno_busto = v()
                    item.saco_mujer_contorno_cintura = v()
                    item.saco_mujer_contorno_cadera = v()
                    item.saco_mujer_ancho_hombros = Decimal(str(round(random.uniform(36, 44), 1)))
                    item.saco_mujer_largo_total = Decimal(str(random.randint(60, 72)))
                elif tipo == 'chaleco_mujer':
                    item.chaleco_mujer_contorno_busto = v()
                    item.chaleco_mujer_contorno_cintura = v()
                    item.chaleco_mujer_contorno_cadera = v()
                    item.chaleco_mujer_largo_total = Decimal(str(random.randint(50, 60)))
                item.save()

            confecciones.append(con)
        return confecciones

    # ------------------------------------------------------------------ #

    def _crear_alquileres(self, clientes, empleados, prendas):
        estados     = ['alquilado', 'devuelto']
        pesos       = [0.30, 0.70]
        disponibles = [p for p in prendas if p.cantidad > 0]
        garantias   = ['', '', 'CI del cliente', 'Depósito Bs. 200', 'Tarjeta de identidad']
        notas_ops   = ['', '', 'Para boda', 'Para grado', 'Para quinceañera',
                       'Evento corporativo', 'Aniversario de empresa']

        for _ in range(55):
            fecha_alq = rand_fecha(365, 1)
            estado    = random.choices(estados, pesos)[0]
            descuento = Decimal(str(random.choice([0, 0, 0, 5, 10, 15])))

            alq = Alquiler(
                cliente=random.choice(clientes) if random.random() > 0.08 else None,
                empleado=random.choice(empleados),
                fecha_alquiler=fecha_alq,
                fecha_devolucion=fecha_alq + timedelta(days=random.randint(1, 7)),
                estado=estado,
                descuento=descuento,
                garantia=random.choice(garantias),
                notas=random.choice(notas_ops),
            )
            alq.save()

            n = random.randint(1, 5)
            seleccion = random.sample(disponibles, min(n, len(disponibles)))
            for prenda in seleccion:
                AlquilerItem.objects.create(
                    alquiler=alq,
                    articulo=prenda,
                    cantidad=random.randint(1, 2),
                    precio_unitario=prenda.precio,
                )
            alq.recalcular_totales()

    # ------------------------------------------------------------------ #

    def _crear_ventas(self, clientes, empleados, prendas):
        disponibles = [p for p in prendas if p.cantidad > 0]
        notas_ops   = ['', '', 'Pago en efectivo', 'Pago con QR',
                       'Cliente frecuente', 'Referido por cliente anterior']

        for _ in range(45):
            descuento = Decimal(str(random.choice([0, 0, 0, 5, 10])))
            v = Venta(
                cliente=random.choice(clientes) if random.random() > 0.1 else None,
                empleado=random.choice(empleados),
                fecha_venta=rand_fecha(365, 0),
                descuento=descuento,
                notas=random.choice(notas_ops),
            )
            v.save()

            n = random.randint(1, 3)
            seleccion = random.sample(disponibles, min(n, len(disponibles)))
            for prenda in seleccion:
                VentaItem.objects.create(
                    venta=v,
                    articulo=prenda,
                    cantidad=random.randint(1, 2),
                    precio_unitario=prenda.precio,
                )
            v.recalcular_totales()

    # ------------------------------------------------------------------ #

    def _crear_ordenes(self, confecciones, empleados, insumos):
        estados  = ['corte', 'costura', 'terminado']
        pesos    = [0.20, 0.30, 0.50]
        notas_op = ['', '', 'Prioridad alta', 'Cliente espera el fin de semana',
                    'Revisar medidas antes de terminar']

        seleccion = random.sample(confecciones, min(30, len(confecciones)))
        for con in seleccion:
            estado = random.choices(estados, pesos)[0]
            inicio = con.fecha_inicio + timedelta(days=1)
            orden  = OrdenProduccion(
                confeccion=con,
                descripcion=f'Orden para confección {con.codigo} — {con.modelo} {con.color}',
                empleado=random.choice(empleados),
                fecha_inicio=inicio,
                fecha_estimada=inicio + timedelta(days=random.randint(5, 20)),
                estado=estado,
                notas=random.choice(notas_op),
            )
            orden.save()

            for ins in random.sample(insumos, random.randint(2, 5)):
                InsumoCortado.objects.create(
                    orden=orden,
                    insumo=ins,
                    cantidad=Decimal(str(round(random.uniform(0.5, 4.0), 2))),
                )

    # ------------------------------------------------------------------ #

    def _crear_transacciones(self):
        datos_ingreso = [
            ('Cobro alquiler trajes — boda',         'servicio_basico'),
            ('Cobro confección terno cliente',        'servicio_basico'),
            ('Cobro venta terno azul',                'servicio_basico'),
            ('Cobro reparación pantalón',             'servicio_basico'),
            ('Anticipo confección',                   'servicio_basico'),
            ('Cobro alquiler graduación',             'servicio_basico'),
            ('Cobro venta saco formal',               'servicio_basico'),
            ('Cobro saldo confección entregada',      'servicio_basico'),
            ('Cobro alquiler quinceañera',            'servicio_basico'),
        ]
        datos_gasto = [
            ('Compra tela casimir',                   'otros'),
            ('Compra hilos y botones',                'caja_chica'),
            ('Pago luz del local',                    'otros'),
            ('Pago alquiler del local',               'otros'),
            ('Compra entretela y forro',              'otros'),
            ('Mantenimiento máquina de coser',        'otros'),
            ('Compra materiales de empaque',          'caja_chica'),
            ('Pago agua',                             'otros'),
            ('Compra tela popelina',                  'otros'),
        ]

        for _ in range(65):
            es_ingreso = random.random() > 0.38
            if es_ingreso:
                desc, servicio = random.choice(datos_ingreso)
                tipo  = 'ingreso'
                monto = Decimal(str(random.choice([150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200])))
            else:
                desc, servicio = random.choice(datos_gasto)
                tipo  = 'gasto'
                monto = Decimal(str(random.choice([80, 100, 150, 200, 250, 350, 500, 650])))

            Transaccion.objects.create(
                tipo_transaccion=tipo,
                descripcion=desc,
                tipo_servicio=servicio,
                fecha=rand_fecha(365, 0),
                cantidad=random.randint(1, 5),
                monto=monto,
            )
