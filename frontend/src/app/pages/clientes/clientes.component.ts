import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ApiService, mensajeError } from '../../api.service';
import { errorDocumento } from '../../documento';
import { CONDICIONES_IVA_CLIENTE, Cliente, TIPOS_DOCUMENTO } from '../../models';

function clienteVacio(): Partial<Cliente> {
  return {
    nombre: '',
    tipo_documento: '99',
    numero_documento: '',
    condicion_iva: '5',
    domicilio: '',
    email: ''
  };
}

/** Minúsculas y sin tildes, para que "perez" encuentre a "Pérez". */
function normalizar(texto: string | undefined): string {
  return (texto ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

@Component({
  selector: 'app-clientes',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './clientes.component.html'
})
export class ClientesComponent implements OnInit {
  readonly tiposDocumento = TIPOS_DOCUMENTO;
  readonly condiciones = CONDICIONES_IVA_CLIENTE;

  clientes: Cliente[] = [];
  buscar = '';
  actual: Partial<Cliente> = clienteVacio();
  cargando = true;
  guardando = false;
  error = '';
  exito = '';

  ngOnInit(): void {
    this.cargar();
  }

  constructor(private api: ApiService) {}

  private cargar(): void {
    this.api.listarClientes().subscribe({
      next: (clientes) => {
        this.clientes = clientes;
        this.cargando = false;
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.cargando = false;
      }
    });
  }

  /** Clientes que coinciden con la búsqueda (por nombre, documento o email; sin importar tildes). */
  get clientesFiltrados(): Cliente[] {
    const texto = normalizar(this.buscar);
    if (!texto) {
      return this.clientes;
    }
    const soloNumeros = texto.replace(/\D/g, '');
    return this.clientes.filter(
      (c) =>
        normalizar(c.nombre).includes(texto) ||
        normalizar(c.email).includes(texto) ||
        (soloNumeros.length > 0 && c.numero_documento.replace(/\D/g, '').includes(soloNumeros))
    );
  }

  get sinDocumento(): boolean {
    return this.actual.tipo_documento === '99';
  }

  /** Problema del número de documento que se está escribiendo ('' si está bien o vacío). */
  get errorDocumento(): string {
    return errorDocumento(this.actual.tipo_documento, this.actual.numero_documento);
  }

  editar(cliente: Cliente): void {
    this.actual = { ...cliente };
    this.error = '';
    this.exito = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  cancelar(): void {
    this.actual = clienteVacio();
  }

  guardar(): void {
    this.error = '';
    this.exito = '';
    this.guardando = true;
    const datos = { ...this.actual };
    if (this.sinDocumento) {
      datos.numero_documento = '';
    }
    this.api.guardarCliente(datos).subscribe({
      next: (c) => {
        this.exito = `Cliente “${c.nombre}” guardado.`;
        this.actual = clienteVacio();
        this.guardando = false;
        this.cargar();
      },
      error: (e) => {
        this.error = mensajeError(e);
        this.guardando = false;
      }
    });
  }

  eliminar(cliente: Cliente): void {
    if (!confirm(`¿Eliminar a ${cliente.nombre}?`)) {
      return;
    }
    this.error = '';
    this.exito = '';
    this.api.eliminarCliente(cliente.id).subscribe({
      next: () => this.cargar(),
      error: (e) => (this.error = mensajeError(e))
    });
  }

  etiquetaDocumento(c: Cliente): string {
    if (c.tipo_documento === '99') {
      return 'Sin identificar';
    }
    const tipo = this.tiposDocumento.find((t) => t.valor === c.tipo_documento)?.etiqueta;
    return `${tipo} ${c.numero_documento}`;
  }

  etiquetaCondicion(c: Cliente): string {
    return this.condiciones.find((x) => x.valor === c.condicion_iva)?.etiqueta ?? '';
  }
}
