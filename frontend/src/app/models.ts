export type Modalidad = 'arca' | 'no_fiscal';
export type TipoFactura = 'A' | 'B' | 'C';
export type Concepto = 'productos' | 'servicios';
export type EstadoComprobante = 'borrador' | 'emitido';
export type Clase = 'factura' | 'nota_credito';

export interface Pagina<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Cliente {
  id: number;
  nombre: string;
  tipo_documento: string;
  numero_documento: string;
  condicion_iva: string;
  domicilio: string;
  email: string;
}

export interface Item {
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal?: string;
}

/** Comprobante relacionado (la factura de una nota de crédito, o sus notas de crédito). */
export interface ComprobanteResumen {
  id: number;
  nombre_tipo: string;
  numero_formateado: string;
  fecha: string;
  estado: EstadoComprobante;
  total: string;
  pendiente_de_acreditar: string | null;
}

export interface Comprobante {
  id: number;
  cliente: number;
  cliente_nombre: string;
  modalidad: Modalidad;
  clase: Clase;
  nombre_tipo: string;
  asociado: ComprobanteResumen | null;
  notas_credito: ComprobanteResumen[];
  /** Solo facturas emitidas: cuánto falta anular con notas de crédito. */
  pendiente_de_acreditar: string | null;
  tipo_comprobante: TipoFactura;
  concepto: Concepto;
  fecha: string;
  condicion_venta: string;
  observaciones: string;
  estado: EstadoComprobante;
  numero_formateado: string;
  total: string;
  simulado: boolean;
  cae: string;
  cae_vencimiento: string | null;
  error_arca: string;
  items: Item[];
  creado: string;
}

export interface Emisor {
  razon_social: string;
  cuit: string;
  domicilio: string;
  condicion_iva_emisor: string;
  ingresos_brutos: string;
  inicio_actividades: string | null;
  email: string;
  telefono: string;
  punto_venta_numero: number;
  punto_de_venta: number | null;
  punto_de_venta_numero?: number | null;
  tipos_factura_permitidos: TipoFactura[];
}

export interface PuntoDeVenta {
  id: number;
  number: number;
  contribuyente: string;
}

export const TIPOS_DOCUMENTO = [
  { valor: '96', etiqueta: 'DNI' },
  { valor: '80', etiqueta: 'CUIT' },
  { valor: '86', etiqueta: 'CUIL' },
  { valor: '99', etiqueta: 'Sin identificar' }
];

export const CONDICIONES_IVA_CLIENTE = [
  { valor: '5', etiqueta: 'Consumidor Final' },
  { valor: '6', etiqueta: 'Monotributo' },
  { valor: '1', etiqueta: 'Responsable Inscripto' },
  { valor: '4', etiqueta: 'IVA Exento' }
];

export const CONDICIONES_IVA_EMISOR = [
  { valor: 'Responsable Monotributo', etiqueta: 'Monotributo' },
  { valor: 'IVA Responsable Inscripto', etiqueta: 'Responsable Inscripto' },
  { valor: 'IVA Exento', etiqueta: 'Exento' }
];

export const TIPOS_FACTURA: TipoFactura[] = ['A', 'B', 'C'];

/** Filtros del listado de comprobantes (los vacíos no se envían). */
export interface FiltrosComprobantes {
  buscar: string;
  estado: '' | EstadoComprobante;
  tipo: '' | TipoFactura | 'no_fiscal';
  clase: '' | Clase;
  desde: string;
  hasta: string;
}

export const FILTROS_VACIOS: FiltrosComprobantes = {
  buscar: '',
  estado: '',
  tipo: '',
  clase: '',
  desde: '',
  hasta: ''
};
