from django.contrib import admin

from .models import Cliente, Comprobante, Emisor, ItemComprobante


@admin.register(Emisor)
class EmisorAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'cuit', 'condicion_iva_emisor', 'punto_venta_numero')


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo_documento', 'numero_documento', 'condicion_iva')
    search_fields = ('nombre', 'numero_documento', 'email')


class ItemInline(admin.TabularInline):
    model = ItemComprobante
    extra = 0


@admin.register(Comprobante)
class ComprobanteAdmin(admin.ModelAdmin):
    list_display = ('numero_formateado', 'cliente', 'modalidad', 'tipo_comprobante', 'fecha', 'estado', 'simulado')
    list_filter = ('modalidad', 'estado', 'simulado')
    search_fields = ('cliente__nombre',)
    inlines = [ItemInline]
