from django.db.models import ProtectedError
from django.http import HttpResponse
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


class ComprobanteViewSet(viewsets.ModelViewSet):
    queryset = Comprobante.objects.select_related('cliente').prefetch_related('items')
    serializer_class = ComprobanteSerializer

    def _exigir_borrador(self, comprobante):
        if comprobante.estado != Comprobante.Estado.BORRADOR:
            raise ValidationError({'detail': 'Un comprobante emitido no se puede modificar.'})

    def perform_update(self, serializer):
        self._exigir_borrador(serializer.instance)
        serializer.save()

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
