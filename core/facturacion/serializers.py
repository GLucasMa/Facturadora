from django.db import transaction
from django_afip.models import PointOfSales
from rest_framework import serializers

from . import services
from .models import Cliente, Comprobante, Emisor, ItemComprobante


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            'id',
            'nombre',
            'tipo_documento',
            'numero_documento',
            'condicion_iva',
            'domicilio',
            'email',
        ]

    def validate(self, datos):
        tipo = datos.get('tipo_documento', getattr(self.instance, 'tipo_documento', None))
        numero = datos.get('numero_documento', getattr(self.instance, 'numero_documento', ''))
        if tipo != Cliente.TipoDocumento.SIN_IDENTIFICAR and not numero.strip():
            raise serializers.ValidationError(
                {'numero_documento': 'Ingresá el número de documento.'}
            )
        return datos


class EmisorSerializer(serializers.ModelSerializer):
    punto_de_venta_numero = serializers.IntegerField(
        source='punto_de_venta.number', read_only=True, default=None
    )
    tipos_factura_permitidos = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Emisor
        fields = [
            'razon_social',
            'cuit',
            'domicilio',
            'condicion_iva_emisor',
            'ingresos_brutos',
            'inicio_actividades',
            'email',
            'telefono',
            'punto_venta_numero',
            'punto_de_venta',
            'punto_de_venta_numero',
            'tipos_factura_permitidos',
        ]


class ItemComprobanteSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ItemComprobante
        fields = ['id', 'descripcion', 'cantidad', 'precio_unitario', 'subtotal']
        read_only_fields = ['id']

    def validate_cantidad(self, valor):
        if valor <= 0:
            raise serializers.ValidationError('La cantidad debe ser mayor a cero.')
        return valor

    def validate_precio_unitario(self, valor):
        if valor < 0:
            raise serializers.ValidationError('El precio no puede ser negativo.')
        return valor


class ComprobanteSerializer(serializers.ModelSerializer):
    items = ItemComprobanteSerializer(many=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    numero_formateado = serializers.CharField(read_only=True)

    class Meta:
        model = Comprobante
        fields = [
            'id',
            'cliente',
            'cliente_nombre',
            'modalidad',
            'tipo_comprobante',
            'concepto',
            'fecha',
            'condicion_venta',
            'observaciones',
            'estado',
            'numero_formateado',
            'total',
            'simulado',
            'cae',
            'cae_vencimiento',
            'error_arca',
            'items',
            'creado',
        ]
        read_only_fields = ['estado', 'simulado', 'cae', 'cae_vencimiento', 'error_arca', 'creado']

    def validate(self, datos):
        modalidad = datos.get('modalidad', getattr(self.instance, 'modalidad', None))
        tipo = datos.get('tipo_comprobante', getattr(self.instance, 'tipo_comprobante', None))
        if modalidad == Comprobante.Modalidad.ARCA:
            emisor = services.obtener_emisor()
            mensaje = emisor and services.error_tipo_no_permitido(emisor, tipo)
            if mensaje:
                raise serializers.ValidationError({'tipo_comprobante': mensaje})
        return datos

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('Agregá al menos un ítem.')
        return items

    @transaction.atomic
    def create(self, datos):
        items = datos.pop('items')
        comprobante = Comprobante.objects.create(**datos)
        ItemComprobante.objects.bulk_create(
            [ItemComprobante(comprobante=comprobante, **item) for item in items]
        )
        return comprobante

    @transaction.atomic
    def update(self, comprobante, datos):
        items = datos.pop('items', None)
        for campo, valor in datos.items():
            setattr(comprobante, campo, valor)
        comprobante.save()
        if items is not None:
            comprobante.items.all().delete()
            ItemComprobante.objects.bulk_create(
                [ItemComprobante(comprobante=comprobante, **item) for item in items]
            )
        return comprobante


class PuntoDeVentaSerializer(serializers.ModelSerializer):
    contribuyente = serializers.CharField(source='owner.name', read_only=True)

    class Meta:
        model = PointOfSales
        fields = ['id', 'number', 'contribuyente']
