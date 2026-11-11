from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ClienteViewSet,
    ComprobanteViewSet,
    ConfiguracionView,
    EmisorView,
    PuntoDeVentaViewSet,
)

router = DefaultRouter()
router.register('clientes', ClienteViewSet)
router.register('comprobantes', ComprobanteViewSet)
router.register('puntos-de-venta', PuntoDeVentaViewSet)

urlpatterns = [
    path('emisor/', EmisorView.as_view()),
    path('configuracion/', ConfiguracionView.as_view()),
] + router.urls
