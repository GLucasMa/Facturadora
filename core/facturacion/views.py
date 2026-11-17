import re

from django.db import transaction
from django.db.models import ProtectedError, Q
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from django_afip.models import PointOfSales
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Cliente, Comprobante, Emisor
from .serializers import (
    ClienteSerializer,
    ComprobanteSerializer,
    EmisorSerializer,
    PuntoDeVentaSerializer,
)


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar un cliente que tiene comprobantes.'},
                status=status.HTTP_409_CONFLICT,
            )


def _q_numero(texto: str) -> Q:
    """Condición para buscar un comprobante por su número, escrito como se ve en pantalla.

    "NF-12" → no fiscal 12 · "NC-3" → nota de crédito no fiscal 3 ·
    "0001-00000012" → punto de venta 1, número 12 · "12" → cualquiera con número 12.
    """
    interno = re.fullmatch(r'(NF|NC)\s*-?\s*(\d+)', texto, re.IGNORECASE)
    if interno:
        clase = Comprobante.Clase.NOTA_CREDITO if interno[1].upper() == 'NC' else Comprobante.Clase.FACTURA
        return Q(modalidad=Comprobante.Modalidad.NO_FISCAL, clase=clase, numero_interno=int(interno[2]))
    arca = re.fullmatch(r'(\d{1,5})\s*-\s*(\d+)', texto)
    if arca:
        return Q(punto_venta=int(arca[1]), numero_arca=int(arca[2]))
    if texto.isdigit():
        return Q(numero_arca=int(texto)) | Q(numero_interno=int(texto))
    return Q(pk__in=[])  # no es un número: solo cuenta la búsqueda por cliente


class ComprobanteViewSet(viewsets.ModelViewSet):
    queryset = Comprobante.objects.select_related('cliente', 'comprobante_asociado').prefetch_related(
        'items',
        'notas_credito__items',
        'comprobante_asociado__items',
        'comprobante_asociado__notas_credito__items',
    )
    serializer_class = ComprobanteSerializer

    def get_queryset(self):
        """Filtros del listado: ?buscar= &estado= &tipo= &clase= &desde= &hasta="""
        queryset = super().get_queryset()
        if self.action != 'list':
            return queryset
        parametros = self.request.query_params

        buscar = parametros.get('buscar', '').strip()
        if buscar:
            queryset = queryset.filter(Q(cliente__nombre__icontains=buscar) | _q_numero(buscar))

        estado = parametros.get('estado')
        if estado in Comprobante.Estado.values:
            queryset = queryset.filter(estado=estado)

        clase = parametros.get('clase')
        if clase in Comprobante.Clase.values:
            queryset = queryset.filter(clase=clase)

        tipo = parametros.get('tipo')
        if tipo == Comprobante.Modalidad.NO_FISCAL:
            queryset = queryset.filter(modalidad=Comprobante.Modalidad.NO_FISCAL)
        elif tipo in Comprobante.TipoFactura.values:
            queryset = queryset.filter(modalidad=Comprobante.Modalidad.ARCA, tipo_comprobante=tipo)

        for nombre, lookup in (('desde', 'fecha__gte'), ('hasta', 'fecha__lte')):
            valor = parametros.get(nombre)
            if valor:
                try:
                    fecha = parse_date(valor)
                except ValueError:  # bien escrita pero inexistente, ej: 2026-02-30
                    fecha = None
                if fecha is None:
                    raise ValidationError({nombre: 'Usá el formato AAAA-MM-DD.'})
                queryset = queryset.filter(**{lookup: fecha})
        return queryset

    def _exigir_borrador(self, comprobante):
        # Relee el estado bloqueando la fila: si justo se está emitiendo, espera a que
        # termine y ve el estado final (evita pisar un comprobante recién emitido).
        estado = (
            Comprobante.objects.select_for_update()
            .values_list('estado', flat=True)
            .get(pk=comprobante.pk)
        )
        if estado != Comprobante.Estado.BORRADOR:
            raise ValidationError({'detail': 'Un comprobante emitido no se puede modificar.'})

    @transaction.atomic
    def perform_update(self, serializer):
        self._exigir_borrador(serializer.instance)
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        self._exigir_borrador(instance)
        instance.delete()

    @action(detail=True, methods=['post'])
    def emitir(self, request, pk=None):
        comprobante = self.get_object()
        try:
            services.emitir(comprobante)
        except services.ErrorEmision as e:
            return Response({'detail': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        comprobante.refresh_from_db()
        return Response(self.get_serializer(comprobante).data)

    def _crear_desde(self, funcion):
        """Corre `funcion(comprobante)` y responde con el borrador nuevo (201)."""
        try:
            nuevo = funcion(self.get_object())
        except services.ErrorEmision as e:
            return Response({'detail': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        nuevo = self.get_queryset().get(pk=nuevo.pk)
        return Response(self.get_serializer(nuevo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def duplicar(self, request, pk=None):
        return self._crear_desde(services.duplicar)

    @action(detail=True, methods=['post'], url_path='nota-de-credito')
    def nota_de_credito(self, request, pk=None):
        return self._crear_desde(services.crear_nota_credito)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        comprobante = self.get_object()
        try:
            contenido = services.pdf_comprobante(comprobante)
        except services.ErrorEmision as e:
            return Response({'detail': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        nombre = comprobante.numero_formateado or f'comprobante-{comprobante.pk}'
        respuesta = HttpResponse(contenido, content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="{nombre}.pdf"'
        return respuesta


class EmisorView(APIView):
    """Datos del negocio: una única configuración."""

    def get(self, request):
        emisor = services.obtener_emisor()
        if emisor is None:
            return Response(None)
        return Response(EmisorSerializer(emisor).data)

    def put(self, request):
        serializer = EmisorSerializer(services.obtener_emisor(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PuntoDeVentaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PointOfSales.objects.filter(blocked=False).select_related('owner').order_by('number')
    serializer_class = PuntoDeVentaSerializer


class ConfiguracionView(APIView):
    """Ajustes globales que necesita conocer la interfaz."""

    def get(self, request):
        return Response({'modo_simulacion': services.modo_simulacion()})
