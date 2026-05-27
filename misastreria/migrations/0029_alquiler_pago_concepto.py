from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0028_reparacion_multi_item'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cajamovimiento',
            name='concepto',
            field=models.CharField(
                choices=[
                    ('alquiler_cobro', 'Cobro de alquiler'),
                    ('alquiler_pago', 'Pago de alquiler'),
                    ('garantia_alquiler', 'Garantía de alquiler'),
                    ('garantia_devolucion', 'Devolución de garantía'),
                    ('venta_cobro', 'Cobro de venta'),
                    ('confeccion_adelanto', 'Adelanto de confección'),
                    ('confeccion_saldo', 'Saldo de confección'),
                    ('reparacion_cobro', 'Cobro de reparación'),
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
                ],
                max_length=40,
                verbose_name='Concepto',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='cajamovimiento',
            name='unique_mov_alquiler_activo',
        ),
        migrations.AddConstraint(
            model_name='cajamovimiento',
            constraint=models.UniqueConstraint(
                condition=models.Q(movimiento_reverso__isnull=True) & ~models.Q(concepto='alquiler_pago'),
                fields=['referencia_alquiler', 'concepto'],
                name='unique_mov_alquiler_activo',
            ),
        ),
    ]
