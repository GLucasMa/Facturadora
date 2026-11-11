import { Component, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ApiService } from './api.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  modoSimulacion = false;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.api.configuracion().subscribe({
      next: (config) => (this.modoSimulacion = config.modo_simulacion)
    });
  }
}
