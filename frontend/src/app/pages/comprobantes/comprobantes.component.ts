import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { ApiService, mensajeError } from '../../api.service';
import { Comprobante, FILTROS_VACIOS, FiltrosComprobantes } from '../../models';

/** Mensaje que ve el usuario al abrir la copia recién creada. */
export function avisoDuplicado(original: Comprobante): string {
  const cual = original.numero_formateado ? ` ${original.numero_formateado}` : '';
  return `Este borrador es una copia de ${original.nombre_tipo}${cual}, con fecha de hoy. Revisalo y emitilo cuando esté listo.`;
}

/** Se recuerdan al ir a un comprobante y volver al listado. */
let ultimosFiltros: FiltrosComprobantes = { ...FILTROS_VACIOS };

@Component({
  selector: 'app-comprobantes',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './comprobantes.component.html'
})
export class ComprobantesComponent implements OnInit, OnDestroy {
  comprobantes: Comprobante[] = [];
  filtros: FiltrosComprobantes = { ...ultimosFiltros };
  pagina = 1;
  total = 0;
  hayAnterior = false;
  haySiguiente = false;
  cargando = true;
  error = '';

  private esperaBusqueda?: ReturnType<typeof setTimeout>;

  constructor(
    public api: ApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.cargar();
  }

  ngOnDestroy(): void {
    clearTimeout(this.esperaBusqueda);
  }

  get hayFiltros(): boolean {
    return Object.values(this.filtros).some((v) => v.trim() !== '');
  }

  cargar(): void {
    this.cargando = true;
    this.error = '';
    ultimosFiltros = { ...this.filtros };
    this.api.listarComprobantes(this.pagina, this.filtros).subscribe({
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

  /** Al cambiar un filtro se vuelve a la primera página. */
  filtrar(): void {
    clearTimeout(this.esperaBusqueda);
    this.pagina = 1;
    this.cargar();
  }

  /** Para el texto de búsqueda: espera a que termines de escribir. */
  filtrarAlEscribir(): void {
    clearTimeout(this.esperaBusqueda);
    this.esperaBusqueda = setTimeout(() => this.filtrar(), 350);
  }

  limpiarFiltros(): void {
    this.filtros = { ...FILTROS_VACIOS };
    this.filtrar();
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

  duplicar(c: Comprobante): void {
    this.api.duplicarComprobante(c.id).subscribe({
      next: (copia) =>
        this.router.navigate(['/comprobantes', copia.id], {
          state: { aviso: avisoDuplicado(c) }
        }),
      error: (e) => (this.error = mensajeError(e))
    });
  }

  etiquetaTipo(c: Comprobante): string {
    if (c.clase === 'nota_credito') {
      return c.modalidad === 'arca' ? `Nota de crédito ${c.tipo_comprobante}` : 'Nota de crédito (no fiscal)';
    }
    return c.modalidad === 'arca' ? `Factura ${c.tipo_comprobante}` : 'No fiscal';
  }

  /** 'Anulada', 'Anulada en parte' o '' según las notas de crédito emitidas. */
  anulacion(c: Comprobante): string {
    if (c.pendiente_de_acreditar === null || !c.notas_credito.some((n) => n.estado === 'emitido')) {
      return '';
    }
    return +c.pendiente_de_acreditar <= 0 ? 'Anulada' : 'Anulada en parte';
  }
}
