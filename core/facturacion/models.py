from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import F, Sum

from django_afip.models import PointOfSales, Receipt

# El valor guardado coincide con los textos que usa django-afip para sus PDF.
CONDICIONES_IVA_EMISOR = [
    ('Responsable Monotributo', 'Monotributo'),
    ('IVA Responsable Inscripto', 'Responsable Inscripto'),
    ('IVA Exento', 'Exento'),
]

# Qué clases de factura puede emitir cada condición frente al IVA.
TIPOS_FACTURA_POR_CONDICION = {
    'Responsable Monotributo': ['C'],
    'IVA Exento': ['C'],
    'IVA Responsable Inscripto': ['A', 'B'],
}


class Emisor(models.Model):
    """Datos del negocio que emite los comprobantes (se usa una sola fila)."""

    razon_social = models.CharField(max_length=128)
    cuit = models.CharField(max_length=13, help_text='Ej: 20-12345678-9')
    domicilio = models.CharField(max_length=200)
    condicion_iva_emisor = models.CharField(
        max_length=48, choices=CONDICIONES_IVA_EMISOR, default='Responsable Monotributo'
    )
    ingresos_brutos = models.CharField(max_length=48, blank=True)
    inicio_actividades = models.DateField(null=True, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    punto_venta_numero = models.PositiveSmallIntegerField(
        default=1,
        help_text='Número de punto de venta. Con ARCA real se toma del punto de venta elegido abajo.',
    )
    punto_de_venta = models.ForeignKey(
        PointOfSales,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text='Punto de venta de ARCA con el que se emiten las facturas electrónicas.',
    )

    class Meta:
        verbose_name_plural = 'emisor'

    def __str__(self):
        return self.razon_social

    @property
    def tipos_factura_permitidos(self) -> list[str]:
        return TIPOS_FACTURA_POR_CONDICION.get(self.condicion_iva_emisor, [])

    @property
    def punto_venta_efectivo(self) -> int:
        return self.punto_de_venta.number if self.punto_de_venta_id else self.punto_venta_numero

    @classmethod
    def crear_demo(cls) -> 'Emisor':
        """Empresa ficticia para desarrollar y probar sin un CUIT real."""
        return cls.objects.create(
            razon_social='Empresa Demo S.A.',
            cuit='20-40937847-2',
            domicilio='Av. Siempreviva 742, CABA',
            condicion_iva_emisor='IVA Responsable Inscripto',
            ingresos_brutos='901-123456-7',
            inicio_actividades=date(2020, 1, 1),
            email='demo@empresademo.com.ar',
            telefono='011 4000-0000',
            punto_venta_numero=1,
        )


class Cliente(models.Model):
    """Cliente al que se le emiten comprobantes."""

    class TipoDocumento(models.TextChoices):
        CUIT = '80', 'CUIT'
        CUIL = '86', 'CUIL'
        DNI = '96', 'DNI'
        SIN_IDENTIFICAR = '99', 'Sin identificar'

    class CondicionIva(models.TextChoices):
        CONSUMIDOR_FINAL = '5', 'Consumidor Final'
        RESPONSABLE_INSCRIPTO = '1', 'IVA Responsable Inscripto'
        MONOTRIBUTO = '6', 'Responsable Monotributo'
        EXENTO = '4', 'IVA Sujeto Exento'

    nombre = models.CharField(max_length=200)
    tipo_documento = models.CharField(
        max_length=2, choices=TipoDocumento.choices, default=TipoDocumento.SIN_IDENTIFICAR
    )
    numero_documento = models.CharField(max_length=13, blank=True)
    condicion_iva = models.CharField(
        max_length=2, choices=CondicionIva.choices, default=CondicionIva.CONSUMIDOR_FINAL
    )
    domicilio = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Comprobante(models.Model):
    """Comprobante que el usuario arma a su ritmo y emite cuando está listo.

    - `arca`: factura electrónica con CAE. Con MODO_SIMULACION el CAE es simulado
      (`simulado=True`) y no tiene validez fiscal.
    - `no_fiscal`: comprobante interno, NO válido como factura.
    """

    class Modalidad(models.TextChoices):
        ARCA = 'arca', 'Factura electrónica (ARCA)'
        NO_FISCAL = 'no_fiscal', 'Comprobante no fiscal'

    class Estado(models.TextChoices):
        BORRADOR = 'borrador', 'Borrador'
        EMITIDO = 'emitido', 'Emitido'

    class Concepto(models.TextChoices):
        PRODUCTOS = 'productos', 'Productos'
        SERVICIOS = 'servicios', 'Servicios'

    class TipoFactura(models.TextChoices):
        A = 'A', 'Factura A'
        B = 'B', 'Factura B'
        C = 'C', 'Factura C'

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='comprobantes')
    modalidad = models.CharField(max_length=10, choices=Modalidad.choices, default=Modalidad.ARCA)
    tipo_comprobante = models.CharField(
        max_length=1, choices=TipoFactura.choices, default=TipoFactura.C
    )
    concepto = models.CharField(max_length=10, choices=Concepto.choices, default=Concepto.SERVICIOS)
    fecha = models.DateField()
    condicion_venta = models.CharField(max_length=48, default='Contado')
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)

    # Solo no fiscales: numeración interna correlativa.
    numero_interno = models.PositiveIntegerField(null=True, blank=True, unique=True)

    # Solo ARCA (reales y simulados): numeración y CAE.
    simulado = models.BooleanField(default=False)
    punto_venta = models.PositiveSmallIntegerField(null=True, blank=True)
    numero_arca = models.PositiveIntegerField(null=True, blank=True)
    cae = models.CharField(max_length=14, blank=True)
    cae_vencimiento = models.DateField(null=True, blank=True)
    # Solo ARCA reales: comprobante electrónico generado por django-afip.
    receipt = models.OneToOneField(
        Receipt, null=True, blank=True, on_delete=models.PROTECT, related_name='comprobante'
    )
    error_arca = models.TextField(blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado']
        constraints = [
            models.UniqueConstraint(
                fields=['simulado', 'tipo_comprobante', 'punto_venta', 'numero_arca'],
                name='comprobante_numero_arca_unico',
            )
        ]

    def __str__(self):
        return f'{self.get_modalidad_display()} - {self.cliente}'

    @property
    def total(self) -> Decimal:
        total = self.items.aggregate(t=Sum(F('cantidad') * F('precio_unitario')))['t']
        return total or Decimal('0.00')

    @property
    def numero_formateado(self) -> str:
        if self.modalidad == self.Modalidad.ARCA:
            if self.numero_arca:
                return f'{self.punto_venta:04d}-{self.numero_arca:08d}'
            return ''
        if self.numero_interno:
            return f'NF-{self.numero_interno:08d}'
        return ''


class ItemComprobante(models.Model):
    comprobante = models.ForeignKey(Comprobante, on_delete=models.CASCADE, related_name='items')
    descripcion = models.CharField(max_length=128)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def subtotal(self) -> Decimal:
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return self.descripcion
