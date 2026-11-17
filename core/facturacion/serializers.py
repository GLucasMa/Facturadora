from django.db import transaction
from django_afip.models import PointOfSales
from rest_framework import serializers

from . import services
from .models import Cliente, Comprobante, Emisor, ItemComprobante
from .validators import DocumentoInvalido, normalizar_cuit, normalizar_dni


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

    def validate(self, attrs):
        if self.instance is not None and not {'tipo_documento', 'numero_documento'} & attrs.keys():
            # Edición parcial que no toca el documento: no hay nada que revisar.
            return attrs
        tipo = attrs.get('tipo_documento', getattr(self.instance, 'tipo_documento', None))
        numero = attrs.get('numero_documento', getattr(self.instance, 'numero_documento', ''))
        numero = numero.strip()
        if tipo == Cliente.TipoDocumento.SIN_IDENTIFICAR:
            return attrs
        if not numero:
            raise serializers.ValidationError(
                {'numero_documento': 'Ingresá el número de documento.'}
            )
        try:
            if tipo == Cliente.TipoDocumento.DNI:
                numero = normalizar_dni(numero)
            else:
                nombre = 'CUIL' if tipo == Cliente.TipoDocumento.CUIL else 'CUIT'
                numero = normalizar_cuit(numero, nombre)
        except DocumentoInvalido as e:
            raise serializers.ValidationError({'numero_documento': str(e)}) from e
        # Se guarda siempre con el mismo formato (CUIT/CUIL con guiones, DNI solo números).
        attrs['numero_documento'] = numero
        return attrs


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

    def validate_cuit(self, valor):
        try:
            return normalizar_cuit(valor)
        except DocumentoInvalido as e:
            raise serializers.ValidationError(str(e)) from e


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


class ComprobanteResumenSerializer(serializers.ModelSerializer):
    """Datos mínimos para mostrar un comprobante relacionado (factura ↔ nota de crédito)."""

    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    pendiente_de_acreditar = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True
    )

    class Meta:
        model = Comprobante
        fields = [
            'id',
            'nombre_tipo',
            'numero_formateado',
            'fecha',
            'estado',
            'total',
            'pendiente_de_acreditar',
        ]
        read_only_fields = fields


class ComprobanteSerializer(serializers.ModelSerializer):
    items = ItemComprobanteSerializer(many=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    numero_formateado = serializers.CharField(read_only=True)
    nombre_tipo = serializers.CharField(read_only=True)
    asociado = ComprobanteResumenSerializer(source='comprobante_asociado', read_only=True)
    notas_credito = ComprobanteResumenSerializer(many=True, read_only=True)
    pendiente_de_acreditar = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, allow_null=True
    )

    class Meta:
        model = Comprobante
        fields = [
            'id',
            'cliente',
            'cliente_nombre',
            'modalidad',
            'clase',
            'nombre_tipo',
            'asociado',
            'notas_credito',
            'pendiente_de_acreditar',
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
        read_only_fields = [
            'clase',
            'estado',
            'simulado',
            'cae',
            'cae_vencimiento',
            'error_arca',
            'creado',
        ]

    def validate(self, attrs):
        if self.instance is not None and self.instance.es_nota_credito:
            # La nota de crédito sigue a su factura: no se le cambia cliente, modalidad ni letra.
            for campo in ('cliente', 'modalidad', 'tipo_comprobante'):
                attrs.pop(campo, None)
            return attrs
        modalidad = attrs.get('modalidad', getattr(self.instance, 'modalidad', None))
        tipo = attrs.get('tipo_comprobante', getattr(self.instance, 'tipo_comprobante', None))
        if modalidad == Comprobante.Modalidad.ARCA:
            emisor = services.obtener_emisor()
            mensaje = emisor and services.error_tipo_no_permitido(emisor, tipo)
            if mensaje:
                raise serializers.ValidationError({'tipo_comprobante': mensaje})
        return attrs

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('Agregá al menos un ítem.')
        return items

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop('items')
        comprobante = Comprobante.objects.create(**validated_data)
        ItemComprobante.objects.bulk_create(
            [ItemComprobante(comprobante=comprobante, **item) for item in items]
        )
        return comprobante

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            ItemComprobante.objects.bulk_create(
                [ItemComprobante(comprobante=instance, **item) for item in items]
            )
        return instance


class PuntoDeVentaSerializer(serializers.ModelSerializer):
    contribuyente = serializers.CharField(source='owner.name', read_only=True)

    class Meta:
        model = PointOfSales
        fields = ['id', 'number', 'contribuyente']
