from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def backfill(apps, schema_editor):
    """Convierte el 'Responsable' único de cada orden en una fila de la tabla.
    Debe correr ANTES de RemoveField (lee OrdenProduccion.empleado_id)."""
    OP = apps.get_model('misastreria', 'OrdenProduccion')
    OPE = apps.get_model('misastreria', 'OrdenProduccionEmpleado')
    for o in OP.objects.exclude(empleado_id__isnull=True).only('id', 'empleado_id', 'estado'):
        OPE.objects.create(
            orden_id=o.id,
            empleado_id=o.empleado_id,
            responsabilidad=o.estado,   # ESTADO_CHOICES == set de responsabilidad (1:1)
            monto_comision_fijo=Decimal('0'),
        )


def reverse(apps, schema_editor):
    pass  # one-way; el auto-reverse de CreateModel elimina la tabla


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0051_comision_asignacion_inmediata'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrdenProduccionEmpleado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('responsabilidad', models.CharField(choices=[('corte', 'En Corte'), ('costura', 'En Costura'), ('terminado', 'Terminado')], max_length=20, verbose_name='Fase')),
                ('monto_comision_fijo', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Comisión (Bs)', help_text='Monto fijo en Bs que gana el empleado por esta fase.')),
                ('empleado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones_produccion', to='misastreria.empleado', verbose_name='Empleado')),
                ('orden', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='empleados_produccion', to='misastreria.ordenproduccion', verbose_name='Orden')),
            ],
            options={
                'verbose_name': 'Asignación de producción',
                'verbose_name_plural': 'Asignaciones de producción',
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='ordenproduccionempleado',
            constraint=models.UniqueConstraint(fields=['orden', 'empleado', 'responsabilidad'], name='unique_orden_empleado_responsabilidad'),
        ),
        migrations.RunPython(backfill, reverse),
        migrations.RemoveField(
            model_name='ordenproduccion',
            name='empleado',
        ),
    ]
