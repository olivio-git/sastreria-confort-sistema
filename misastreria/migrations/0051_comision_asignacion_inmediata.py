from decimal import Decimal

from django.db import migrations, models
import django.core.validators


def backfill(apps, schema_editor):
    """Convert stored percentage values to fixed Bs amounts.

    RenameField ran first, so the old % value is already in monto_comision_fijo.
    We multiply in-place: new = stored_pct × base / 100.
    """
    CE = apps.get_model('misastreria', 'ConfeccionEmpleado')
    VI = apps.get_model('misastreria', 'VentaItem')
    AI = apps.get_model('misastreria', 'AlquilerItem')
    HUNDRED = Decimal('100')

    for ce in CE.objects.select_related('confeccion').all():
        base = ce.confeccion.precio or Decimal('0')
        stored_pct = ce.monto_comision_fijo or Decimal('0')
        ce.monto_comision_fijo = (base * stored_pct / HUNDRED).quantize(Decimal('0.01'))
        ce.save(update_fields=['monto_comision_fijo'])

    for Model in (VI, AI):
        for item in Model.objects.all():
            if item.monto_comision_fijo is None:
                continue  # preserve NULL (no commission assigned)
            base = item.precio_reparacion or Decimal('0')
            stored_pct = item.monto_comision_fijo
            item.monto_comision_fijo = (base * stored_pct / HUNDRED).quantize(Decimal('0.01'))
            item.save(update_fields=['monto_comision_fijo'])


def reverse(apps, schema_editor):
    # One-way data migration; reverse is a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('misastreria', '0050_confeccionitem_costo'),
    ]

    operations = [
        # 1. Rename the three fields (preserves stored % value in new column name)
        migrations.RenameField(
            model_name='confeccionempleado',
            old_name='porcentaje_comision',
            new_name='monto_comision_fijo',
        ),
        migrations.RenameField(
            model_name='ventaitem',
            old_name='porcentaje_comision',
            new_name='monto_comision_fijo',
        ),
        migrations.RenameField(
            model_name='alquileritem',
            old_name='porcentaje_comision',
            new_name='monto_comision_fijo',
        ),

        # 2. AlterField x3 — update max_digits, validators, null/default, verbose_name, help_text
        migrations.AlterField(
            model_name='confeccionempleado',
            name='monto_comision_fijo',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                default=Decimal('0'),
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Comisión (Bs)',
                help_text='Monto fijo en Bs que gana el empleado por esta confección.',
            ),
        ),
        migrations.AlterField(
            model_name='ventaitem',
            name='monto_comision_fijo',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Comisión (Bs)',
                help_text='Monto fijo en Bs que gana el empleado por el arreglo.',
            ),
        ),
        migrations.AlterField(
            model_name='alquileritem',
            name='monto_comision_fijo',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                null=True,
                blank=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Comisión (Bs)',
                help_text='Monto fijo en Bs que gana el empleado por el arreglo.',
            ),
        ),

        # 3. Backfill: multiply stored % by base price to convert to Bs amounts
        migrations.RunPython(backfill, reverse),
    ]
