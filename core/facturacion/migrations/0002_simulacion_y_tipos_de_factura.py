from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facturacion', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='emisor',
            old_name='condicion_iva',
            new_name='condicion_iva_emisor',
        ),
        migrations.AlterField(
            model_name='emisor',
            name='condicion_iva_emisor',
            field=models.CharField(
                choices=[
                    ('Responsable Monotributo', 'Monotributo'),
                    ('IVA Responsable Inscripto', 'Responsable Inscripto'),
                    ('IVA Exento', 'Exento'),
                ],
                default='Responsable Monotributo',
                max_length=48,
            ),
        ),
        migrations.AddField(
            model_name='emisor',
            name='punto_venta_numero',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Número de punto de venta. Con ARCA real se toma del punto de venta elegido abajo.',
            ),
        ),
        migrations.AddField(
            model_name='comprobante',
            name='tipo_comprobante',
            field=models.CharField(
                choices=[('A', 'Factura A'), ('B', 'Factura B'), ('C', 'Factura C')],
                default='C',
                max_length=1,
            ),
        ),
        migrations.AddField(
            model_name='comprobante',
            name='simulado',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='comprobante',
            name='punto_venta',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comprobante',
            name='numero_arca',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comprobante',
            name='cae',
            field=models.CharField(blank=True, max_length=14),
        ),
        migrations.AddField(
            model_name='comprobante',
            name='cae_vencimiento',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='comprobante',
            constraint=models.UniqueConstraint(
                fields=('simulado', 'tipo_comprobante', 'punto_venta', 'numero_arca'),
                name='comprobante_numero_arca_unico',
            ),
        ),
    ]
