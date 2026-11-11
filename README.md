# Facturación ARCA

Sistema simple para armar comprobantes con calma y emitirlos cuando estén listos:

- **Factura electrónica (ARCA)**: con CAE. La clase depende de tu condición frente al IVA: **Monotributo y Exento → Factura C**, **Responsable Inscripto → Facturas A y B** (la interfaz deshabilita las que no corresponden y el backend también las rechaza).
- **Comprobante no fiscal**: no se informa a ARCA; sale con la leyenda "Documento no válido como factura" y numeración interna (`NF-00000001`).

## Stack

- **Backend**: Django 4.2 + Django REST Framework (`core/`).
- **ARCA**: [`django-afip`](https://github.com/hobarrera/django-afip) (WSAA/WSFEv1, CAE, PDF con QR).
- **PDF**: WeasyPrint (requiere GTK3 en Windows).
- **Base de datos**: MySQL (driver PyMySQL).
- **Frontend**: Angular 18 (`frontend/`).

## Cómo correrlo

```bash
# Backend
cd core
../venv/Scripts/activate
pip install -r ../requirements.txt
python manage.py migrate
python manage.py afipmetadata        # una sola vez: carga tipos de comprobante de ARCA
python manage.py runserver

# Frontend (otra terminal)
cd frontend
npm install
npm start
```

- App: http://localhost:4200 · API: http://localhost:8000/api/ · Admin: http://localhost:8000/admin
- Base de datos: copiar `core/.env.example` a `core/.env` y completar `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- Tests: `python manage.py test facturacion` (desde `core/`).

## Modo simulación (`MODO_SIMULACION`)

Permite desarrollar sin CUIT, certificados ni internet. Se controla con la variable `MODO_SIMULACION` (en `core/.env`; por defecto **True**, ver `core/core/settings.py`).

- **True**: las facturas electrónicas (A, B o C) se emiten con un **CAE ficticio** (empieza con `99`) y se guardan solo en la base local, con numeración propia por tipo y punto de venta. El PDF lleva la leyenda "SIMULACIÓN - SIN VALIDEZ FISCAL". No se toca ninguna tabla de `django-afip`. La interfaz muestra un banner amarillo.
- **False**: se usa ARCA real (ver más abajo). Por ahora solo Facturas C.

En modo simulación, si todavía no hay datos del negocio, se crea sola la **Empresa Demo S.A.** (CUIT 20-40937847-2, punto de venta 1, Responsable Inscripto). Cambiá la condición frente al IVA en *Mi negocio* para probar las reglas de cada tipo de factura.

**Antes de facturar de verdad poné `MODO_SIMULACION=False`**: con el valor por defecto las facturas no tienen validez fiscal.

## Primeros pasos en la app

1. **Mi negocio**: cargar razón social, CUIT, domicilio y condición frente al IVA.
2. **Clientes**: cargar a quién le vas a facturar.
3. **Comprobantes → Nuevo**: elegir tipo, cliente, ítems. Guardar borrador y seguir después, o emitir.

Los comprobantes no fiscales y las facturas simuladas funcionan sin más configuración. Para facturar en ARCA de verdad falta el paso siguiente.

## Habilitar facturación electrónica en ARCA

Se hace una vez en el admin (`/admin`). **Empezá siempre en homologación** (entorno de pruebas de ARCA).

1. Admin → **Contribuyentes** → agregar: nombre, CUIT, "is sandboxed" tildado (homologación) y fecha de inicio de actividad.
2. Seleccionarlo y ejecutar las acciones **Generar clave** y luego **Generar CSR** (descarga el pedido de certificado).
3. En ARCA (con clave fiscal), subir ese CSR: en homologación se usa el servicio de autogestión de certificados de homologación; en producción, "Administración de certificados digitales". Descargar el certificado `.crt` resultante.
4. En ARCA, **asociar el certificado al servicio "Facturación Electrónica" (wsfe)** y crear un punto de venta con sistema "Web Services" (los nombres exactos del portal pueden cambiar).
5. Volver al admin, subir el `.crt` al Contribuyente y ejecutar **Traer puntos de venta**.
6. En la app, **Mi negocio → Punto de venta**: elegir el punto de venta traído.

Para pasar a producción: repetir con un Contribuyente con "is sandboxed" destildado.

## Qué falta (próximos pasos)

- Facturas **A y B con ARCA real**: hoy se pueden emitir en simulación, pero falta discriminar el IVA por alícuota (importes, `Vat` en django-afip).
- **Multicomercio (SaaS)**: hoy hay una sola empresa (*Mi negocio*). Falta asociar clientes y comprobantes a una empresa y a usuarios.
- Notas de crédito/débito y anulaciones.
- Login de usuarios (hoy la API no tiene autenticación: no exponer fuera de tu red).
- Cambiar la contraseña del usuario `admin` de desarrollo.
- Envío del PDF por email al cliente.
