import { Component, OnInit } from '@angular/core';
import { CommonModule, Location } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { ApiService, mensajeError } from '../../api.service';
import {
  CONDICIONES_IVA_EMISOR,
  Clase,
  Cliente,
  Comprobante,
  ComprobanteResumen,
  Concepto,
  Emisor,
  Item,
  Modalidad,
  TIPOS_FACTURA,
  TipoFactura
} from '../../models';
import { avisoDuplicado } from '../comprobantes/comprobantes.component';

function hoy(): string {
  const d = new Date();
  const mes = String(d.getMonth() + 1).padStart(2, '0');
  const dia = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mes}-${dia}`;
}

@Component({
  selector: 'app-comprobante-form',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './comprobante-form.component.html',
  styleUrl: './comprobante-form.component.css'
})
export class ComprobanteFormComponent implements OnInit {
  readonly tipos = TIPOS_FACTURA;

  id: number | null = null;
  estado: 'borrador' | 'emitido' = 'borrador';
  numero = '';
  nombreTipo = '';
  cae = '';
  caeVencimiento: string | null = null;
  simulado = false;

  clase: Clase = 'factura';
  /** Nota de crédito: la factura que anula. */
  asociado: ComprobanteResumen | null = null;
  /** Factura: sus notas de crédito. */
  notasCredito: ComprobanteResumen[] = [];
  pendienteDeAcreditar: number | null = null;

  modalidad: Modalidad = 'arca';
  tipo: TipoFactura = 'C';
  clienteId: number | null = null;
  concepto: Concepto = 'servicios';
  fecha = hoy();
  condicionVenta = 'Contado';
  observaciones = '';
  items: Item[] = [];

  clientes: Cliente[] = [];
  emisor: Emisor | null = null;

  cargando = true;
  trabajando = false;
  error = '';
  exito = '';
  info = '';

  constructor(
    public api: ApiService,
    private route: ActivatedRoute,
    private router: Router,
    private location: Location
  ) {}

  ngOnInit(): void {
    this.api.listarClientes().subscribe({
      next: (clientes) => (this.clientes = clientes),
      error: (e) => (this.error = mensajeError(e))
    });
    this.api.obtenerEmisor().subscribe({
      next: (emisor) => {
        this.emisor = emisor;
        this.ajustarTipo();
      }
    });

    // Angular reutiliza esta pantalla al pasar de un comprobante a otro (por ejemplo de una
    // factura a su nota de crédito), así que se recarga cada vez que cambia el id.
    this.route.paramMap.subscribe((parametros) => {
      this.reiniciar();
      this.info = this.router.getCurrentNavigation()?.extras.state?.['aviso'] ?? '';
      const idRuta = parametros.get('id');
      if (!idRuta) {
        this.cargando = false;
        return;
      }
      this.cargando = true;
      this.api.obtenerComprobante(+idRuta).subscribe({
        next: (c) => {
          this.cargar(c);
          this.ajustarTipo();
          this.cargando = false;
        },
        error: (e) => {
          this.error = mensajeError(e);
          this.cargando = false;
        }
      });
    });
  }

  private reiniciar(): void {
    this.id = null;
    this.estado = 'borrador';
    this.numero = '';
    this.nombreTipo = '';
    this.cae = '';
    this.caeVencimiento = null;
    this.simulado = false;
    this.clase = 'factura';
    this.asociado = null;
    this.notasCredito = [];
    this.pendienteDeAcreditar = null;
    this.modalidad = 'arca';
    this.tipo = this.tiposPermitidos[0] ?? 'C';
    this.clienteId = null;
    this.concepto = 'servicios';
    this.fecha = hoy();
    this.condicionVenta = 'Contado';
    this.observaciones = '';
    this.items = [{ descripcion: '', cantidad: 1, precio_unitario: 0 }];
    this.error = '';
    this.exito = '';
    this.info = '';
  }

  get esNotaCredito(): boolean {
    return this.clase === 'nota_credito';
  }

  get tiposPermitidos(): TipoFactura[] {
    return this.emisor?.tipos_factura_permitidos ?? [];
  }

  get textoCondicion(): string {
    const valor = this.emisor?.condicion_iva_emisor;
    return CONDICIONES_IVA_EMISOR.find((c) => c.valor === valor)?.etiqueta ?? '';
  }

  get textoTiposPermitidos(): string {
    return this.tiposPermitidos.map((t) => `Factura ${t}`).join(' y ');
  }

  permitido(tipo: TipoFactura): boolean {
    return this.tiposPermitidos.includes(tipo);
  }

  /** En un borrador de factura, deja elegido un tipo que la condición del emisor permita. */
  private ajustarTipo(): void {
    if (!this.soloLectura && !this.esNotaCredito && this.tiposPermitidos.length && !this.permitido(this.tipo)) {
      this.tipo = this.tiposPermitidos[0];
    }
  }

  get soloLectura(): boolean {
    return this.estado === 'emitido';
  }

  get titulo(): string {
    if (this.soloLectura) {
      return `${this.nombreTipo} ${this.numero}`;
    }
    if (this.esNotaCredito) {
      return 'Nota de crédito (borrador)';
    }
    return this.id ? 'Continuar borrador' : 'Nuevo comprobante';
  }

  get total(): number {
    return this.items.reduce((suma, i) => suma + (+i.cantidad || 0) * (+i.precio_unitario || 0), 0);
  }

  /** Nota de crédito en borrador: lo que todavía se puede anular de su factura. */
  get maximoNotaCredito(): number | null {
    const pendiente = this.asociado?.pendiente_de_acreditar;
    return pendiente === null || pendiente === undefined ? null : +pendiente;
  }

  get superaMaximo(): boolean {
    const maximo = this.maximoNotaCredito;
    return !this.soloLectura && maximo !== null && this.total > maximo + 0.001;
  }

  get puedeGuardar(): boolean {
    return (
      !!this.clienteId &&
      this.items.length > 0 &&
      this.items.every((i) => i.descripcion.trim() && +i.cantidad > 0 && +i.precio_unitario >= 0) &&
      this.total > 0
    );
  }

  get puedeHacerNotaCredito(): boolean {
    return this.soloLectura && !this.esNotaCredito && (this.pendienteDeAcreditar ?? 0) > 0;
  }

  get textoBotonEmitir(): string {
    if (this.trabajando) {
      return 'Procesando...';
    }
    if (this.esNotaCredito) {
      return 'Emitir nota de crédito';
    }
    return this.modalidad === 'arca' ? `Emitir Factura ${this.tipo}` : 'Emitir comprobante no fiscal';
  }

  agregarItem(): void {
    this.items = [...this.items, { descripcion: '', cantidad: 1, precio_unitario: 0 }];
  }

  quitarItem(indice: number): void {
    this.items = this.items.filter((_, i) => i !== indice);
  }

  guardarBorrador(): void {
    this.ejecutar(this.guardar(), 'Borrador guardado.');
  }

  emitir(): void {
    let aviso: string;
    if (this.esNotaCredito) {
      aviso = `Se emitirá la nota de crédito que anula ${this.asociado?.nombre_tipo} ${this.asociado?.numero_formateado}. No se podrá modificar después. ¿Emitir?`;
    } else if (this.modalidad === 'arca') {
      aviso = 'Esta factura se enviará a ARCA y NO se podrá modificar después. ¿Emitir?';
    } else {
      aviso = 'Se emitirá el comprobante no fiscal y no se podrá modificar después. ¿Emitir?';
    }
    if (!confirm(aviso)) {
      return;
    }
    this.error = '';
    this.exito = '';
    this.trabajando = true;
    this.guardar().subscribe({
      next: (guardado) => {
        this.api.emitirComprobante(guardado.id).subscribe({
          next: (emitido) => {
            this.cargar(emitido);
            this.info = '';
            this.exito = this.esNotaCredito ? 'Nota de crédito emitida correctamente.' : 'Comprobante emitido correctamente.';
            this.trabajando = false;
          },
          error: (e) => {
            this.error = mensajeError(e);
            this.trabajando = false;
          }
        });
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.trabajando = false;
      }
    });
  }

  duplicar(): void {
    const original = { nombre_tipo: this.nombreTipo, numero_formateado: this.numero } as Comprobante;
    this.trabajando = true;
    this.api.duplicarComprobante(this.id!).subscribe({
      next: (copia) => {
        this.trabajando = false;
        this.router.navigate(['/comprobantes', copia.id], { state: { aviso: avisoDuplicado(original) } });
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.trabajando = false;
      }
    });
  }

  hacerNotaCredito(): void {
    this.trabajando = true;
    this.api.crearNotaCredito(this.id!).subscribe({
      next: (nota) => {
        this.trabajando = false;
        this.router.navigate(['/comprobantes', nota.id], {
          state: {
            aviso:
              'Se armó la nota de crédito con los mismos ítems, para anular la factura completa. ' +
              'Si querés anular solo una parte, bajá cantidades o quitá líneas antes de emitir.'
          }
        });
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.trabajando = false;
      }
    });
  }

  private guardar(): Observable<Comprobante> {
    return this.api
      .guardarComprobante({
        id: this.id ?? undefined,
        cliente: this.clienteId!,
        modalidad: this.modalidad,
        tipo_comprobante: this.tipo,
        concepto: this.concepto,
        fecha: this.fecha,
        condicion_venta: this.condicionVenta,
        observaciones: this.observaciones,
        items: this.items.map((i) => ({
          descripcion: i.descripcion.trim(),
          cantidad: +i.cantidad,
          precio_unitario: +i.precio_unitario
        }))
      })
      .pipe(
        tap((c) => {
          if (!this.id) {
            this.id = c.id;
            this.location.replaceState(`/comprobantes/${c.id}`);
          }
        })
      );
  }

  private ejecutar(operacion: Observable<Comprobante>, mensajeExito: string): void {
    this.error = '';
    this.exito = '';
    this.trabajando = true;
    operacion.subscribe({
      next: (c) => {
        this.cargar(c);
        this.exito = mensajeExito;
        this.trabajando = false;
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.trabajando = false;
      }
    });
  }

  private cargar(c: Comprobante): void {
    this.id = c.id;
    this.estado = c.estado;
    this.numero = c.numero_formateado;
    this.nombreTipo = c.nombre_tipo;
    this.cae = c.cae;
    this.caeVencimiento = c.cae_vencimiento;
    this.simulado = c.simulado;
    this.clase = c.clase;
    this.asociado = c.asociado;
    this.notasCredito = c.notas_credito;
    this.pendienteDeAcreditar = c.pendiente_de_acreditar === null ? null : +c.pendiente_de_acreditar;
    this.modalidad = c.modalidad;
    this.tipo = c.tipo_comprobante;
    this.clienteId = c.cliente;
    this.concepto = c.concepto;
    this.fecha = c.fecha;
    this.condicionVenta = c.condicion_venta;
    this.observaciones = c.observaciones;
    this.items = c.items.map((i) => ({
      descripcion: i.descripcion,
      cantidad: +i.cantidad,
      precio_unitario: +i.precio_unitario
    }));
    if (c.error_arca && c.estado === 'borrador') {
      this.error = c.error_arca;
    }
  }

  volver(): void {
    this.router.navigate(['/comprobantes']);
  }
}
