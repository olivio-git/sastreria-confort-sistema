from decimal import Decimal

from django.db import migrations, models
import django.core.validators


def backfill(apps, schema_editor):
    """Convert stored percentage values on ReparacionEmpleado to fixed Bs amounts.

    RenameField ran first, so the old % value is already in monto_comision_fijo.
    We multiply in-place: new = stored_pct × reparacion.total / 100.
    """
    RE = apps.get_model('misastreria', 'ReparacionEmpleado')
    HUNDRED = Decimal('100')

    for re in RE.objects.select_related('reparacion').all():
        base = re.reparacion.total or Decimal('0')
        stored_pct = re.monto_comision_fijo or Decimal('0')
        re.monto_comision_fijo = (base * stored_pct / HUNDRED).quantize(Decimal('0.01'))
        re.save(update_fields=['monto_comision_fijo'])


def reverse(apps, schema_editor):
    # One-way data migration; reverse is a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0053_alter_cajamovimiento_concepto'),
    ]

    operations = [
        # 1. Rename the field (preserves stored % value in new column name)
        migrations.RenameField(
            model_name='reparacionempleado',
            old_name='porcentaje_comision',
            new_name='monto_comision_fijo',
        ),

        # 2. AlterField — update max_digits, validators, default, verbose_name, help_text
        migrations.AlterField(
            model_name='reparacionempleado',
            name='monto_comision_fijo',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                default=Decimal('0'),
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Comisión (Bs)',
                help_text='Monto fijo en Bs que gana el empleado por esta reparación.',
            ),
        ),

        # 3. Backfill: multiply stored % by reparacion.total to convert to Bs amounts
        migrations.RunPython(backfill, reverse),
    ]
