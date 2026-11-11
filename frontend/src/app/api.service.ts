import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, map, shareReplay } from 'rxjs';

import { Cliente, Comprobante, Emisor, Pagina, PuntoDeVenta } from './models';

export const API_URL = 'http://localhost:8000/api';

/** Convierte un error de la API en un texto que el usuario pueda entender. */
export function mensajeError(error: unknown): string {
  if (!(error instanceof HttpErrorResponse) || error.status === 0) {
    return 'No se pudo conectar con el servidor. Revisá que el backend esté funcionando.';
  }
  const cuerpo = error.error;
  if (typeof cuerpo?.detail === 'string') {
    return cuerpo.detail;
  }
  if (cuerpo && typeof cuerpo === 'object') {
    const mensajes = Object.entries(cuerpo).map(([campo, valor]) => {
      const texto = Array.isArray(valor) ? valor.join(' ') : JSON.stringify(valor);
      return campo === 'non_field_errors' ? texto : `${campo}: ${texto}`;
    });
    if (mensajes.length) {
      return mensajes.join(' | ');
    }
  }
  return 'Ocurrió un error inesperado.';
}

export interface Configuracion {
  modo_simulacion: boolean;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private configuracionEnCache?: Observable<Configuracion>;

  constructor(private http: HttpClient) {}

  configuracion(): Observable<Configuracion> {
    this.configuracionEnCache ??= this.http
      .get<Configuracion>(`${API_URL}/configuracion/`)
      .pipe(shareReplay(1));
    return this.configuracionEnCache;
  }

  listarClientes(): Observable<Cliente[]> {
    return this.http
      .get<Pagina<Cliente>>(`${API_URL}/clientes/`, { params: { page_size: 1000 } })
      .pipe(map((pagina) => pagina.results));
  }

  guardarCliente(cliente: Partial<Cliente>): Observable<Cliente> {
    return cliente.id
      ? this.http.put<Cliente>(`${API_URL}/clientes/${cliente.id}/`, cliente)
      : this.http.post<Cliente>(`${API_URL}/clientes/`, cliente);
  }

  eliminarCliente(id: number): Observable<void> {
    return this.http.delete<void>(`${API_URL}/clientes/${id}/`);
  }

  listarComprobantes(pagina: number): Observable<Pagina<Comprobante>> {
    return this.http.get<Pagina<Comprobante>>(`${API_URL}/comprobantes/`, {
      params: { page: pagina }
    });
  }

  obtenerComprobante(id: number): Observable<Comprobante> {
    return this.http.get<Comprobante>(`${API_URL}/comprobantes/${id}/`);
  }

  guardarComprobante(datos: Partial<Comprobante>): Observable<Comprobante> {
    return datos.id
      ? this.http.put<Comprobante>(`${API_URL}/comprobantes/${datos.id}/`, datos)
      : this.http.post<Comprobante>(`${API_URL}/comprobantes/`, datos);
  }

  eliminarComprobante(id: number): Observable<void> {
    return this.http.delete<void>(`${API_URL}/comprobantes/${id}/`);
  }

  emitirComprobante(id: number): Observable<Comprobante> {
    return this.http.post<Comprobante>(`${API_URL}/comprobantes/${id}/emitir/`, {});
  }

  urlPdf(id: number): string {
    return `${API_URL}/comprobantes/${id}/pdf/`;
  }

  obtenerEmisor(): Observable<Emisor | null> {
    return this.http.get<Emisor | null>(`${API_URL}/emisor/`);
  }

  guardarEmisor(emisor: Emisor): Observable<Emisor> {
    return this.http.put<Emisor>(`${API_URL}/emisor/`, emisor);
  }

  listarPuntosDeVenta(): Observable<PuntoDeVenta[]> {
    return this.http
      .get<Pagina<PuntoDeVenta>>(`${API_URL}/puntos-de-venta/`, { params: { page_size: 100 } })
      .pipe(map((pagina) => pagina.results));
  }
}
