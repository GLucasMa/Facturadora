from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.template.loader import render_to_string

from django_afip import models as afip
from django_afip.models import ClientVatCondition

from .models import Cliente, Comprobante, Emisor

CODIGO_AFIP_FACTURA_C = '11'
CONCEPTO_ARCA = {
    Comprobante.Concepto.PRODUCTOS: '1',
    Comprobante.Concepto.SERVICIOS: '2',
}


class ErrorEmision(Exception):
    """Error mostrable al usuario cuando no se puede emitir un comprobante."""


def modo_simulacion() -> bool:
    return bool(getattr(settings, 'MODO_SIMULACION', False))


def obtener_emisor() -> Emisor | None:
    """El emisor configurado; en modo simulación se crea la empresa demo si no hay ninguno."""
    emisor = Emisor.objects.first()
    if emisor is None and modo_simulacion():
        emisor = Emisor.crear_demo()
    return emisor


def error_tipo_no_permitido(emisor: Emisor, tipo: str) -> str | None:
    permitidos = emisor.tipos_factura_permitidos
    if tipo in permitidos:
        return None
    nombres = ' y '.join(f'Factura {t}' for t in permitidos) or 'ninguna factura'
    return (
        f'Con tu condición frente al IVA ({emisor.get_condicion_iva_emisor_display()}) '
        f'no podés emitir Factura {tipo}. Podés emitir: {nombres}.'
    )


def emitir(comprobante: Comprobante) -> Comprobante:
    if comprobante.estado != Comprobante.Estado.BORRADOR:
        raise ErrorEmision('Este comprobante ya fue emitido.')
    if not comprobante.items.exists() or comprobante.total <= 0:
        raise ErrorEmision('Agregá al menos un ítem con importe mayor a cero.')

    emisor = obtener_emisor()
    if emisor is None:
        raise ErrorEmision('Primero completá tus datos en la sección Mi negocio.')

    if comprobante.modalidad == Comprobante.Modalidad.ARCA:
        mensaje = error_tipo_no_permitido(emisor, comprobante.tipo_comprobante)
        if mensaje:
            raise ErrorEmision(mensaje)
        if modo_simulacion():
            _emitir_arca_simulado(comprobante, emisor)
        else:
            _emitir_arca(comprobante, emisor)
    else:
        _emitir_no_fiscal(comprobante)
    return comprobante


def _emitir_no_fiscal(comprobante: Comprobante) -> None:
    with transaction.atomic():
        # Bloquea el emisor para que dos emisiones simultáneas no tomen el mismo número.
        Emisor.objects.select_for_update().first()
        ultimo = Comprobante.objects.aggregate(m=Max('numero_interno'))['m'] or 0
        comprobante.numero_interno = ultimo + 1
        comprobante.estado = Comprobante.Estado.EMITIDO
        comprobante.error_arca = ''
        comprobante.save()


def _emitir_arca_simulado(comprobante: Comprobante, emisor: Emisor) -> None:
    """Emite con CAE simulado: no usa internet, certificados ni las tablas de ARCA."""
    punto_venta = emisor.punto_venta_efectivo
    with transaction.atomic():
        Emisor.objects.select_for_update().first()
        ultimo = (
            Comprobante.objects.filter(
                simulado=True,
                tipo_comprobante=comprobante.tipo_comprobante,
                punto_venta=punto_venta,
            ).aggregate(m=Max('numero_arca'))['m']
            or 0
        )
        comprobante.simulado = True
        comprobante.punto_venta = punto_venta
        comprobante.numero_arca = ultimo + 1
        # Empieza con 99 para reconocerlo a simple vista como no real.
        comprobante.cae = '99' + ''.join(secrets.choice('0123456789') for _ in range(12))
        comprobante.cae_vencimiento = comprobante.fecha + timedelta(days=10)
        comprobante.estado = Comprobante.Estado.EMITIDO
        comprobante.error_arca = ''
        comprobante.save()


def _emitir_arca(comprobante: Comprobante, emisor: Emisor) -> None:
    if comprobante.tipo_comprobante != Comprobante.TipoFactura.C:
        raise ErrorEmision(
            'Con ARCA real todavía solo se emiten Facturas C. '
            'Las Facturas A y B se pueden probar en modo simulación.'
        )
    if emisor.punto_de_venta is None:
        raise ErrorEmision(
            'Falta el punto de venta de ARCA. Elegilo en la sección Mi negocio '
            '(requiere cargar tu CUIT y certificado en el panel de administración).'
        )

    try:
        with transaction.atomic():
            receipt = _crear_receipt(comprobante, emisor)
            receipt.validate()
            if not receipt.is_validated:
                # Se revierte todo: un comprobante rechazado no consume numeración.
                raise ErrorEmision(_motivo_rechazo(receipt))
    except ErrorEmision as e:
        _registrar_error(comprobante, str(e))
        raise
    except Exception as e:
        mensaje = f'No se pudo comunicar con ARCA: {e}'
        _registrar_error(comprobante, mensaje)
        raise ErrorEmision(mensaje) from e

    comprobante.receipt = receipt
    comprobante.punto_venta = receipt.point_of_sales.number
    comprobante.numero_arca = receipt.receipt_number
    comprobante.cae = receipt.validation.cae
    comprobante.cae_vencimiento = receipt.validation.cae_expiration
    comprobante.estado = Comprobante.Estado.EMITIDO
    comprobante.error_arca = ''
    comprobante.save()

    try:
        _generar_pdf_arca(comprobante, emisor)
    except Exception:
        # La factura ya está autorizada por ARCA; el PDF se reintenta al pedirlo.
        pass


def _registrar_error(comprobante: Comprobante, mensaje: str) -> None:
    comprobante.error_arca = mensaje
    comprobante.save(update_fields=['error_arca', 'actualizado'])


def _crear_receipt(comprobante: Comprobante, emisor: Emisor) -> afip.Receipt:
    cliente = comprobante.cliente
    total = comprobante.total
    es_servicio = comprobante.concepto == Comprobante.Concepto.SERVICIOS

    receipt = afip.Receipt.objects.create(
        point_of_sales=emisor.punto_de_venta,
        receipt_type=afip.ReceiptType.objects.get(code=CODIGO_AFIP_FACTURA_C),
        concept=afip.ConceptType.objects.get(code=CONCEPTO_ARCA[comprobante.concepto]),
        document_type=afip.DocumentType.objects.get(code=cliente.tipo_documento),
        document_number=_numero_documento(cliente),
        issued_date=comprobante.fecha,
        total_amount=total,
        net_untaxed=0,
        net_taxed=total,
        exempt_amount=0,
        service_start=comprobante.fecha if es_servicio else None,
        service_end=comprobante.fecha if es_servicio else None,
        expiration_date=comprobante.fecha if es_servicio else None,
        client_vat_condition=ClientVatCondition.objects.get(code=cliente.condicion_iva),
    )
    for item in comprobante.items.all():
        afip.ReceiptEntry.objects.create(
            receipt=receipt,
            description=item.descripcion,
            quantity=item.cantidad,
            unit_price=item.precio_unitario,
        )
    return receipt


def _numero_documento(cliente: Cliente) -> int:
    digitos = ''.join(c for c in cliente.numero_documento if c.isdigit())
    return int(digitos) if digitos else 0


def _motivo_rechazo(receipt: afip.Receipt) -> str:
    validation = getattr(receipt, 'validation', None)
    if validation is not None:
        observaciones = [o.message for o in validation.observations.all()]
        if observaciones:
            return 'ARCA rechazó el comprobante: ' + ' | '.join(observaciones)
    return 'ARCA no autorizó el comprobante.'


def _generar_pdf_arca(comprobante: Comprobante, emisor: Emisor) -> afip.ReceiptPDF:
    receipt = comprobante.receipt
    pdf, creado = afip.ReceiptPDF.objects.get_or_create(
        receipt=receipt,
        defaults=dict(
            issuing_name=emisor.razon_social,
            issuing_address=emisor.domicilio,
            issuing_email=emisor.email,
            vat_condition=emisor.condicion_iva_emisor,
            gross_income_condition=emisor.ingresos_brutos or 'Exento',
            client_name=comprobante.cliente.nombre,
            client_address=comprobante.cliente.domicilio,
            client_vat_condition=comprobante.cliente.get_condicion_iva_display(),
            sales_terms=comprobante.condicion_venta,
        ),
    )
    if not pdf.pdf_file:
        pdf.save_pdf()
    return pdf


def pdf_comprobante(comprobante: Comprobante) -> bytes:
    """Devuelve el PDF del comprobante emitido (ARCA, simulado o no fiscal)."""
    if comprobante.estado != Comprobante.Estado.EMITIDO:
        raise ErrorEmision('El comprobante todavía no fue emitido.')

    if comprobante.modalidad == Comprobante.Modalidad.NO_FISCAL:
        return _renderizar_pdf(
            comprobante,
            titulo='Comprobante no fiscal',
            aviso='DOCUMENTO NO VÁLIDO COMO FACTURA',
            pie='Este documento no es una factura y no tiene validez fiscal.',
        )
    if comprobante.simulado:
        return _renderizar_pdf(
            comprobante,
            titulo=comprobante.get_tipo_comprobante_display(),
            aviso='SIMULACIÓN - SIN VALIDEZ FISCAL',
            pie='Factura generada en modo simulación. El CAE es ficticio y no fue emitido por ARCA.',
        )

    pdf = _generar_pdf_arca(comprobante, Emisor.objects.first())
    with pdf.pdf_file.open('rb') as f:
        return f.read()


def _renderizar_pdf(comprobante: Comprobante, titulo: str, aviso: str, pie: str) -> bytes:
    from weasyprint import HTML

    html = render_to_string(
        'facturacion/comprobante_pdf.html',
        {
            'comprobante': comprobante,
            'emisor': Emisor.objects.first(),
            'items': list(comprobante.items.all()),
            'titulo': titulo,
            'aviso': aviso,
            'pie': pie,
        },
    )
    return HTML(string=html).write_pdf()
