import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

import { ApiService, mensajeError } from '../../api.service';
import { Comprobante } from '../../models';

@Component({
  selector: 'app-comprobantes',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './comprobantes.component.html'
})
export class ComprobantesComponent implements OnInit {
  comprobantes: Comprobante[] = [];
  pagina = 1;
  total = 0;
  hayAnterior = false;
  haySiguiente = false;
  cargando = true;
  error = '';

  constructor(public api: ApiService) {}

  ngOnInit(): void {
    this.cargar();
  }

  cargar(): void {
    this.cargando = true;
    this.api.listarComprobantes(this.pagina).subscribe({
      next: (res) => {
        this.comprobantes = res.results;
        this.total = res.count;
        this.hayAnterior = !!res.previous;
        this.haySiguiente = !!res.next;
        this.cargando = false;
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.cargando = false;
      }
    });
  }

  cambiarPagina(delta: number): void {
    this.pagina += delta;
    this.cargar();
  }

  eliminar(c: Comprobante): void {
    if (!confirm(`¿Eliminar este borrador de ${c.cliente_nombre}?`)) {
      return;
    }
    this.api.eliminarComprobante(c.id).subscribe({
      next: () => {
        if (this.comprobantes.length === 1 && this.pagina > 1) {
          this.pagina--;
        }
        this.cargar();
      },
      error: (e) => (this.error = mensajeError(e))
    });
  }

  etiquetaModalidad(c: Comprobante): string {
    return c.modalidad === 'arca' ? `Factura ${c.tipo_comprobante}` : 'No fiscal';
  }
}
