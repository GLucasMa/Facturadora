from __future__ import annotations

import secrets
from datetime import date, timedelta

from django.conf import settings
from django.db import OperationalError, transaction
from django.db.models import Max
from django.template.loader import render_to_string

from django_afip import models as afip
from django_afip.models import ClientVatCondition

from .models import Cliente, Comprobante, Emisor, ItemComprobante

# Códigos de ARCA por clase de comprobante (por ahora solo letra C con ARCA real).
CODIGO_AFIP_FACTURA_C = '11'
CODIGO_AFIP_NOTA_CREDITO_C = '13'
CONCEPTO_ARCA: dict[str, str] = {
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


def _pesos(valor) -> str:
    """Importe con formato argentino: $ 1.234,50."""
    texto = f'{valor:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    return f'$ {texto}'


def _copiar_items(origen: Comprobante, destino: Comprobante) -> None:
    ItemComprobante.objects.bulk_create(
        [
            ItemComprobante(
                comprobante=destino,
                descripcion=item.descripcion,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
            )
            for item in origen.items.all()
        ]
    )


@transaction.atomic
def duplicar(comprobante: Comprobante) -> Comprobante:
    """Crea un borrador nuevo con los mismos datos e ítems, con fecha de hoy."""
    if comprobante.es_nota_credito:
        raise ErrorEmision(
            'Las notas de crédito no se duplican: hacé una nueva desde la factura que querés anular.'
        )
    copia = Comprobante.objects.create(
        cliente=comprobante.cliente,
        modalidad=comprobante.modalidad,
        tipo_comprobante=comprobante.tipo_comprobante,
        concepto=comprobante.concepto,
        fecha=date.today(),
        condicion_venta=comprobante.condicion_venta,
        observaciones=comprobante.observaciones,
    )
    _copiar_items(comprobante, copia)
    return copia


@transaction.atomic
def crear_nota_credito(factura: Comprobante) -> Comprobante:
    """Crea una nota de crédito en borrador que anula la factura por el total pendiente.

    Copia los ítems de la factura; el usuario puede bajar cantidades o quitar líneas
    para hacer una nota de crédito parcial antes de emitirla.
    """
    if factura.es_nota_credito:
        raise ErrorEmision('No se puede hacer una nota de crédito de otra nota de crédito.')
    if factura.estado != Comprobante.Estado.EMITIDO:
        raise ErrorEmision('Solo se pueden anular comprobantes ya emitidos. Un borrador se puede eliminar.')
    if (factura.pendiente_de_acreditar or 0) <= 0:
        raise ErrorEmision('Esta factura ya está anulada por completo con notas de crédito.')
    borrador = factura.notas_credito.filter(estado=Comprobante.Estado.BORRADOR).first()
    if borrador is not None:
        # Evita juntar varios borradores para la misma factura: se sigue el que ya existe.
        return borrador

    nota = Comprobante.objects.create(
        cliente=factura.cliente,
        modalidad=factura.modalidad,
        clase=Comprobante.Clase.NOTA_CREDITO,
        comprobante_asociado=factura,
        tipo_comprobante=factura.tipo_comprobante,
        concepto=factura.concepto,
        fecha=max(date.today(), factura.fecha),
        condicion_venta=factura.condicion_venta,
        observaciones=f'Anula {factura.nombre_tipo} {factura.numero_formateado}.',
    )
    _copiar_items(factura, nota)
    return nota


def emitir(comprobante: Comprobante) -> Comprobante:
    """Emite el comprobante. Devuelve la instancia actualizada (releída de la base).

    Toma un bloqueo sobre la fila del comprobante mientras dura la emisión, para que
    un doble clic o dos pestañas no puedan emitirlo dos veces (dos CAE, dos números).
    """
    error: ErrorEmision | None = None
    with transaction.atomic():
        try:
            # nowait: si otro pedido ya lo está emitiendo, falla enseguida en vez de esperar.
            bloqueado = Comprobante.objects.select_for_update(nowait=True).get(pk=comprobante.pk)
        except OperationalError as e:
            raise ErrorEmision(
                'Este comprobante se está emitiendo en este momento. '
                'Esperá unos segundos y actualizá la página.'
            ) from e
        try:
            _emitir_bloqueado(bloqueado)
        except ErrorEmision as e:
            # Se relanza fuera de la transacción para que no se pierda el `error_arca` guardado.
            error = e
    if error is not None:
        raise error
    return bloqueado


def _emitir_bloqueado(comprobante: Comprobante) -> None:
    # El estado se valida recién acá, con la fila ya bloqueada y releída de la base.
    if comprobante.estado != Comprobante.Estado.BORRADOR:
        raise ErrorEmision('Este comprobante ya fue emitido.')
    if not comprobante.items.exists() or comprobante.total <= 0:
        raise ErrorEmision('Agregá al menos un ítem con importe mayor a cero.')

    emisor = obtener_emisor()
    if emisor is None:
        raise ErrorEmision('Primero completá tus datos en la sección Mi negocio.')

    if comprobante.es_nota_credito:
        _emitir_nota_credito(comprobante, emisor)
        return

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


def _emitir_nota_credito(nota: Comprobante, emisor: Emisor) -> None:
    # Bloquea la factura: dos notas de crédito simultáneas no pueden pasarse del total.
    factura = (
        Comprobante.objects.select_for_update()
        .prefetch_related('items', 'notas_credito__items')
        .get(pk=nota.comprobante_asociado_id)
    )
    pendiente = factura.pendiente_de_acreditar or 0
    if nota.total > pendiente:
        raise ErrorEmision(
            f'La nota de crédito ({_pesos(nota.total)}) supera lo que queda por anular de la '
            f'{factura.nombre_tipo} {factura.numero_formateado} ({_pesos(pendiente)}).'
        )
    if nota.fecha < factura.fecha:
        raise ErrorEmision('La fecha de la nota de crédito no puede ser anterior a la de la factura.')

    if nota.modalidad == Comprobante.Modalidad.NO_FISCAL:
        _emitir_no_fiscal(nota)
    elif factura.simulado:
        # La nota de crédito de una factura simulada también es simulada (nunca va a ARCA).
        _emitir_arca_simulado(nota, emisor)
    elif modo_simulacion():
        raise ErrorEmision(
            'Esta factura fue emitida en ARCA de verdad: para anularla desactivá el modo simulación.'
        )
    else:
        _emitir_arca(nota, emisor)


def _emitir_no_fiscal(comprobante: Comprobante) -> None:
    with transaction.atomic():
        # Bloquea el emisor para que dos emisiones simultáneas no tomen el mismo número.
        Emisor.objects.select_for_update().first()
        ultimo = (
            Comprobante.objects.filter(clase=comprobante.clase).aggregate(m=Max('numero_interno'))['m']
            or 0
        )
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
                clase=comprobante.clase,
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
            'Con ARCA real todavía solo se emiten Facturas C (y sus notas de crédito). '
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

    validacion = afip.ReceiptValidation.objects.get(receipt=receipt)
    comprobante.receipt = receipt
    comprobante.punto_venta = receipt.point_of_sales.number
    comprobante.numero_arca = receipt.receipt_number
    comprobante.cae = validacion.cae
    comprobante.cae_vencimiento = validacion.cae_expiration
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

    codigo = CODIGO_AFIP_NOTA_CREDITO_C if comprobante.es_nota_credito else CODIGO_AFIP_FACTURA_C

    receipt = afip.Receipt.objects.create(
        point_of_sales=emisor.punto_de_venta,
        receipt_type=afip.ReceiptType.objects.get(code=codigo),
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
    if comprobante.es_nota_credito:
        # ARCA exige informar qué factura anula la nota de crédito.
        factura = comprobante.comprobante_asociado
        if factura is None or factura.receipt is None:
            raise ErrorEmision('No se encontró la factura de ARCA que anula esta nota de crédito.')
        receipt.related_receipts.add(factura.receipt)
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
    emisor = Emisor.objects.first()
    if emisor is None:
        raise ErrorEmision('Faltan los datos de tu negocio. Completalos en la sección Mi negocio.')

    if comprobante.modalidad == Comprobante.Modalidad.NO_FISCAL:
        return _renderizar_pdf(
            comprobante,
            emisor,
            titulo=comprobante.nombre_tipo,
            aviso='DOCUMENTO NO VÁLIDO COMO FACTURA',
            pie='Este documento no es una factura y no tiene validez fiscal.',
        )
    if comprobante.simulado:
        return _renderizar_pdf(
            comprobante,
            emisor,
            titulo=comprobante.nombre_tipo,
            aviso='SIMULACIÓN - SIN VALIDEZ FISCAL',
            pie=(
                f'{comprobante.nombre_tipo} generada en modo simulación. '
                'El CAE es ficticio y no fue emitido por ARCA.'
            ),
        )

    pdf = _generar_pdf_arca(comprobante, emisor)
    with pdf.pdf_file.open('rb') as f:
        return f.read()


def _renderizar_pdf(
    comprobante: Comprobante, emisor: Emisor, titulo: str, aviso: str, pie: str
) -> bytes:
    from weasyprint import HTML

    html = render_to_string(
        'facturacion/comprobante_pdf.html',
        {
            'comprobante': comprobante,
            'emisor': emisor,
            'items': list(comprobante.items.all()),
            'titulo': titulo,
            'aviso': aviso,
            'pie': pie,
        },
    )
    pdf = HTML(string=html).write_pdf()
    if pdf is None:
        raise ErrorEmision('No se pudo generar el PDF.')
    return pdf
