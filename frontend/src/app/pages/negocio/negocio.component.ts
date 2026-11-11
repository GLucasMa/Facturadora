import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService, mensajeError } from '../../api.service';
import { CONDICIONES_IVA_EMISOR, Emisor, PuntoDeVenta } from '../../models';

@Component({
  selector: 'app-negocio',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './negocio.component.html'
})
export class NegocioComponent implements OnInit {
  readonly condiciones = CONDICIONES_IVA_EMISOR;

  emisor: Emisor = {
    razon_social: '',
    cuit: '',
    domicilio: '',
    condicion_iva_emisor: 'Responsable Monotributo',
    ingresos_brutos: '',
    inicio_actividades: null,
    email: '',
    telefono: '',
    punto_venta_numero: 1,
    punto_de_venta: null,
    tipos_factura_permitidos: ['C']
  };
  modoSimulacion = false;
  puntosDeVenta: PuntoDeVenta[] = [];

  cargando = true;
  guardando = false;
  error = '';
  exito = '';

  constructor(private api: ApiService) {}

  get textoTiposPermitidos(): string {
    return this.emisor.tipos_factura_permitidos.map((t) => `Factura ${t}`).join(' y ');
  }

  ngOnInit(): void {
    this.api.configuracion().subscribe({ next: (c) => (this.modoSimulacion = c.modo_simulacion) });
    this.api.listarPuntosDeVenta().subscribe({ next: (p) => (this.puntosDeVenta = p) });
    this.api.obtenerEmisor().subscribe({
      next: (emisor) => {
        if (emisor) {
          this.emisor = emisor;
        }
        this.cargando = false;
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.cargando = false;
      }
    });
  }

  guardar(): void {
    this.error = '';
    this.exito = '';
    this.guardando = true;
    this.api.guardarEmisor({ ...this.emisor, inicio_actividades: this.emisor.inicio_actividades || null }).subscribe({
      next: (emisor) => {
        this.emisor = emisor;
        this.exito = 'Datos guardados.';
        this.guardando = false;
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.guardando = false;
      }
    });
  }
}
