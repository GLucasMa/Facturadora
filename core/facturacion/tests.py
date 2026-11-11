from datetime import date, datetime, timezone
from unittest import mock

from django.test import TestCase, override_settings
from django_afip import models as afip
from rest_framework.test import APIClient

from .models import Cliente, Comprobante, Emisor


def validar_aprobado(self, *args, **kwargs):
    self.receipt_number = 1
    self.save()
    afip.ReceiptValidation.objects.create(
        receipt=self,
        result=afip.ReceiptValidation.RESULT_APPROVED,
        processed_date=datetime.now(timezone.utc),
        cae='70123456789012',
        cae_expiration=date(2026, 12, 31),
    )
    return []


def validar_rechazado(self, *args, **kwargs):
    validation = afip.ReceiptValidation.objects.create(
        receipt=self,
        result=afip.ReceiptValidation.RESULT_REJECTED,
        processed_date=datetime.now(timezone.utc),
        cae='',
        cae_expiration=date(2026, 12, 31),
    )
    validation.observations.add(afip.Observation.objects.create(code=10016, message='Fecha inválida'))
    return []


class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        afip.load_metadata()
        cls.cliente = Cliente.objects.create(
            nombre='Juan Pérez', tipo_documento='96', numero_documento='30111222', condicion_iva='5'
        )

    def setUp(self):
        self.api = APIClient()

    def crear_emisor(self, con_punto_de_venta=False, condicion='Responsable Monotributo'):
        pdv = None
        if con_punto_de_venta:
            contribuyente = afip.TaxPayer.objects.create(
                name='Test', cuit=20111111112, is_sandboxed=True, active_since=date(2020, 1, 1)
            )
            pdv = afip.PointOfSales.objects.create(
                number=1, issuance_type='CAE', owner=contribuyente
            )
        return Emisor.objects.create(
            razon_social='Mi Negocio',
            cuit='20-11111111-2',
            domicilio='Calle 123',
            condicion_iva_emisor=condicion,
            punto_de_venta=pdv,
        )

    def crear_comprobante(self, modalidad, tipo='C', esperado=201):
        respuesta = self.api.post(
            '/api/comprobantes/',
            {
                'cliente': self.cliente.id,
                'modalidad': modalidad,
                'tipo_comprobante': tipo,
                'concepto': 'servicios',
                'fecha': '2026-10-10',
                'items': [
                    {'descripcion': 'Diseño web', 'cantidad': '2', 'precio_unitario': '1500.50'},
                    {'descripcion': 'Hosting', 'cantidad': '1', 'precio_unitario': '999.00'},
                ],
            },
            format='json',
        )
        self.assertEqual(respuesta.status_code, esperado, respuesta.content)
        return respuesta.data

    def emitir(self, datos):
        return self.api.post(f'/api/comprobantes/{datos["id"]}/emitir/')


@override_settings(MODO_SIMULACION=False)
class ComprobanteBorradorTests(BaseTest):
    def test_total_se_calcula_con_los_items(self):
        datos = self.crear_comprobante('no_fiscal')
        self.assertEqual(datos['total'], '4000.00')
        self.assertEqual(datos['estado'], 'borrador')

    def test_exige_al_menos_un_item(self):
        respuesta = self.api.post(
            '/api/comprobantes/',
            {'cliente': self.cliente.id, 'modalidad': 'arca', 'fecha': '2026-10-10', 'items': []},
            format='json',
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_cliente_con_documento_requiere_numero(self):
        respuesta = self.api.post(
            '/api/clientes/',
            {'nombre': 'X', 'tipo_documento': '80', 'numero_documento': '', 'condicion_iva': '1'},
            format='json',
        )
        self.assertEqual(respuesta.status_code, 400)


@override_settings(MODO_SIMULACION=False)
class NoFiscalTests(BaseTest):
    def test_emitir_asigna_numeracion_correlativa(self):
        self.crear_emisor()
        r1 = self.emitir(self.crear_comprobante('no_fiscal'))
        r2 = self.emitir(self.crear_comprobante('no_fiscal'))

        self.assertEqual(r1.data['numero_formateado'], 'NF-00000001')
        self.assertEqual(r2.data['numero_formateado'], 'NF-00000002')
        self.assertEqual(r1.data['estado'], 'emitido')

    def test_pdf_es_un_pdf_valido(self):
        self.crear_emisor()
        datos = self.crear_comprobante('no_fiscal')
        self.emitir(datos)

        respuesta = self.api.get(f'/api/comprobantes/{datos["id"]}/pdf/')

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_emitido_no_se_puede_modificar_ni_borrar(self):
        self.crear_emisor()
        datos = self.crear_comprobante('no_fiscal')
        self.emitir(datos)

        self.assertEqual(self.api.delete(f'/api/comprobantes/{datos["id"]}/').status_code, 400)
        self.assertEqual(self.emitir(datos).status_code, 422)

    def test_sin_datos_del_negocio_no_emite(self):
        datos = self.crear_comprobante('no_fiscal')
        respuesta = self.emitir(datos)
        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('Mi negocio', respuesta.data['detail'])


@override_settings(MODO_SIMULACION=False)
class ArcaRealTests(BaseTest):
    def test_emision_aprobada_guarda_cae_y_genera_pdf(self):
        self.crear_emisor(con_punto_de_venta=True)
        datos = self.crear_comprobante('arca')

        with mock.patch.object(afip.Receipt, 'validate', validar_aprobado):
            respuesta = self.emitir(datos)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data['estado'], 'emitido')
        self.assertEqual(respuesta.data['cae'], '70123456789012')
        self.assertEqual(respuesta.data['numero_formateado'], '0001-00000001')
        self.assertFalse(respuesta.data['simulado'])

        receipt = Comprobante.objects.get(pk=datos['id']).receipt
        self.assertEqual(receipt.total_amount, 4000)
        self.assertEqual(receipt.entries.count(), 2)
        self.assertEqual(receipt.receipt_type.code, '11')
        self.assertEqual(receipt.client_vat_condition.code, '5')

        pdf = self.api.get(f'/api/comprobantes/{datos["id"]}/pdf/')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

    def test_rechazo_de_arca_deja_borrador_y_muestra_motivo(self):
        self.crear_emisor(con_punto_de_venta=True)
        datos = self.crear_comprobante('arca')

        with mock.patch.object(afip.Receipt, 'validate', validar_rechazado):
            respuesta = self.emitir(datos)

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('Fecha inválida', respuesta.data['detail'])
        comprobante = Comprobante.objects.get(pk=datos['id'])
        self.assertEqual(comprobante.estado, 'borrador')
        self.assertIn('Fecha inválida', comprobante.error_arca)
        self.assertEqual(afip.Receipt.objects.count(), 0)

    def test_falla_de_conexion_se_informa_sin_romper(self):
        self.crear_emisor(con_punto_de_venta=True)
        datos = self.crear_comprobante('arca')

        with mock.patch.object(afip.Receipt, 'validate', side_effect=ConnectionError('sin red')):
            respuesta = self.emitir(datos)

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('sin red', respuesta.data['detail'])
        self.assertEqual(Comprobante.objects.get(pk=datos['id']).estado, 'borrador')

    def test_sin_punto_de_venta_no_emite(self):
        self.crear_emisor(con_punto_de_venta=False)
        datos = self.crear_comprobante('arca')
        respuesta = self.emitir(datos)
        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('punto de venta', respuesta.data['detail'])

    def test_factura_a_o_b_solo_en_simulacion(self):
        self.crear_emisor(con_punto_de_venta=True, condicion='IVA Responsable Inscripto')
        datos = self.crear_comprobante('arca', tipo='A')
        respuesta = self.emitir(datos)
        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('solo se emiten Facturas C', respuesta.data['detail'])


@override_settings(MODO_SIMULACION=True)
class SimulacionTests(BaseTest):
    def test_emite_con_cae_simulado_sin_tocar_las_tablas_de_arca(self):
        self.crear_emisor()  # sin punto de venta ni certificado
        datos = self.crear_comprobante('arca')

        with mock.patch.object(
            afip.Receipt, 'validate', side_effect=AssertionError('no debe llamar a ARCA')
        ):
            respuesta = self.emitir(datos)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.data['estado'], 'emitido')
        self.assertTrue(respuesta.data['simulado'])
        self.assertEqual(len(respuesta.data['cae']), 14)
        self.assertTrue(respuesta.data['cae'].startswith('99'))
        self.assertEqual(respuesta.data['cae_vencimiento'], '2026-10-20')
        self.assertEqual(respuesta.data['numero_formateado'], '0001-00000001')
        self.assertEqual(afip.Receipt.objects.count(), 0)

    def test_numeracion_correlativa_por_tipo(self):
        self.crear_emisor(condicion='IVA Responsable Inscripto')
        a1 = self.emitir(self.crear_comprobante('arca', tipo='A'))
        a2 = self.emitir(self.crear_comprobante('arca', tipo='A'))
        b1 = self.emitir(self.crear_comprobante('arca', tipo='B'))

        self.assertEqual(a1.data['numero_formateado'], '0001-00000001')
        self.assertEqual(a2.data['numero_formateado'], '0001-00000002')
        self.assertEqual(b1.data['numero_formateado'], '0001-00000001')

    def test_pdf_simulado_es_un_pdf_valido(self):
        self.crear_emisor()
        datos = self.crear_comprobante('arca')
        self.emitir(datos)

        respuesta = self.api.get(f'/api/comprobantes/{datos["id"]}/pdf/')

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'%PDF'))

    def test_sin_emisor_crea_la_empresa_demo(self):
        self.assertEqual(Emisor.objects.count(), 0)
        respuesta = self.api.get('/api/emisor/')

        self.assertEqual(respuesta.data['razon_social'], 'Empresa Demo S.A.')
        self.assertEqual(respuesta.data['cuit'], '20-40937847-2')
        self.assertEqual(respuesta.data['punto_venta_numero'], 1)
        self.assertEqual(respuesta.data['condicion_iva_emisor'], 'IVA Responsable Inscripto')
        self.assertEqual(Emisor.objects.count(), 1)

    def test_emitir_sin_emisor_usa_la_empresa_demo(self):
        datos = self.crear_comprobante('arca', tipo='A')
        respuesta = self.emitir(datos)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(Emisor.objects.get().razon_social, 'Empresa Demo S.A.')

    def test_la_demo_no_se_crea_dos_veces(self):
        self.api.get('/api/emisor/')
        self.api.get('/api/emisor/')
        self.assertEqual(Emisor.objects.count(), 1)

    def test_fuera_de_simulacion_no_se_crea_la_demo(self):
        with override_settings(MODO_SIMULACION=False):
            self.assertIsNone(self.api.get('/api/emisor/').data)
        self.assertEqual(Emisor.objects.count(), 0)

    def test_configuracion_informa_el_modo(self):
        self.assertTrue(self.api.get('/api/configuracion/').data['modo_simulacion'])
        with override_settings(MODO_SIMULACION=False):
            self.assertFalse(self.api.get('/api/configuracion/').data['modo_simulacion'])


class TiposDeFacturaTests(BaseTest):
    def test_monotributo_solo_factura_c(self):
        emisor = self.crear_emisor(condicion='Responsable Monotributo')
        self.assertEqual(emisor.tipos_factura_permitidos, ['C'])
        self.crear_comprobante('arca', tipo='C')
        for tipo in ('A', 'B'):
            respuesta = self.crear_comprobante('arca', tipo=tipo, esperado=400)
            self.assertIn('no podés emitir Factura', respuesta['tipo_comprobante'][0])

    def test_responsable_inscripto_solo_a_y_b(self):
        emisor = self.crear_emisor(condicion='IVA Responsable Inscripto')
        self.assertEqual(emisor.tipos_factura_permitidos, ['A', 'B'])
        self.crear_comprobante('arca', tipo='A')
        self.crear_comprobante('arca', tipo='B')
        self.crear_comprobante('arca', tipo='C', esperado=400)

    def test_exento_solo_factura_c(self):
        self.assertEqual(self.crear_emisor(condicion='IVA Exento').tipos_factura_permitidos, ['C'])

    def test_el_tipo_no_aplica_a_comprobantes_no_fiscales(self):
        self.crear_emisor(condicion='IVA Responsable Inscripto')
        self.crear_comprobante('no_fiscal', tipo='C')

    def test_emisor_expone_los_tipos_permitidos(self):
        self.crear_emisor(condicion='IVA Responsable Inscripto')
        self.assertEqual(self.api.get('/api/emisor/').data['tipos_factura_permitidos'], ['A', 'B'])

    def test_si_cambia_la_condicion_el_borrador_ya_no_se_emite(self):
        emisor = self.crear_emisor(condicion='Responsable Monotributo')
        datos = self.crear_comprobante('arca', tipo='C')
        emisor.condicion_iva_emisor = 'IVA Responsable Inscripto'
        emisor.save()

        respuesta = self.emitir(datos)

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('no podés emitir Factura C', respuesta.data['detail'])
