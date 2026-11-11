import { Routes } from '@angular/router';

import { ClientesComponent } from './pages/clientes/clientes.component';
import { ComprobanteFormComponent } from './pages/comprobante-form/comprobante-form.component';
import { ComprobantesComponent } from './pages/comprobantes/comprobantes.component';
import { NegocioComponent } from './pages/negocio/negocio.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'comprobantes' },
  { path: 'comprobantes', component: ComprobantesComponent },
  { path: 'comprobantes/nuevo', component: ComprobanteFormComponent },
  { path: 'comprobantes/:id', component: ComprobanteFormComponent },
  { path: 'clientes', component: ClientesComponent },
  { path: 'configuracion', component: NegocioComponent },
  { path: '**', redirectTo: 'comprobantes' }
];
