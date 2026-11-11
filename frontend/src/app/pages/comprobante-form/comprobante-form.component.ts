import { Component, OnInit } from '@angular/core';
import { CommonModule, Location } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { ApiService, mensajeError } from '../../api.service';
import {
  CONDICIONES_IVA_EMISOR,
  Cliente,
  Comprobante,
  Concepto,
  Emisor,
  Item,
  Modalidad,
  TIPOS_FACTURA,
  TipoFactura
} from '../../models';

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
  id: number | null = null;
  estado: 'borrador' | 'emitido' = 'borrador';
  numero = '';
  cae = '';
  caeVencimiento: string | null = null;
  simulado = false;

  readonly tipos = TIPOS_FACTURA;
  modalidad: Modalidad = 'arca';
  tipo: TipoFactura = 'C';
  clienteId: number | null = null;
  concepto: Concepto = 'servicios';
  fecha = hoy();
  condicionVenta = 'Contado';
  observaciones = '';
  items: Item[] = [{ descripcion: '', cantidad: 1, precio_unitario: 0 }];

  clientes: Cliente[] = [];
  emisor: Emisor | null = null;

  cargando = true;
  trabajando = false;
  error = '';
  exito = '';

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

    const idRuta = this.route.snapshot.paramMap.get('id');
    if (idRuta) {
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
    } else {
      this.cargando = false;
    }
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

  /** En un borrador, deja elegido un tipo que la condición del emisor permita. */
  private ajustarTipo(): void {
    if (!this.soloLectura && this.tiposPermitidos.length && !this.permitido(this.tipo)) {
      this.tipo = this.tiposPermitidos[0];
    }
  }

  get soloLectura(): boolean {
    return this.estado === 'emitido';
  }

  get total(): number {
    return this.items.reduce((suma, i) => suma + (+i.cantidad || 0) * (+i.precio_unitario || 0), 0);
  }

  get puedeGuardar(): boolean {
    return (
      !!this.clienteId &&
      this.items.length > 0 &&
      this.items.every((i) => i.descripcion.trim() && +i.cantidad > 0 && +i.precio_unitario >= 0) &&
      this.total > 0
    );
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
    const aviso =
      this.modalidad === 'arca'
        ? 'Esta factura se enviará a ARCA y NO se podrá modificar después. ¿Emitir?'
        : 'Se emitirá el comprobante no fiscal y no se podrá modificar después. ¿Emitir?';
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
            this.exito = 'Comprobante emitido correctamente.';
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
    this.cae = c.cae;
    this.caeVencimiento = c.cae_vencimiento;
    this.simulado = c.simulado;
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
