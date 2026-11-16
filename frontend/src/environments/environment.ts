/**
 * Configuración para publicar (`ng build`).
 *
 * Supone que el backend se sirve en el mismo dominio que la app, bajo `/api` y `/admin`.
 * Si el backend va a estar en otro dominio, poné acá la dirección completa
 * (por ejemplo `https://api.midominio.com.ar/api`) y sumala a CORS_ALLOWED_ORIGINS en el backend.
 */
export const environment = {
  apiUrl: '/api',
  adminUrl: '/admin'
};
