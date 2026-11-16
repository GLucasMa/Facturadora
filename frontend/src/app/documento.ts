/**
 * Validación de CUIT, CUIL y DNI para avisar mientras se escribe.
 * El backend hace el mismo control al guardar (`core/facturacion/validators.py`).
 */

const PESOS_CUIT = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];

/** Dígito verificador que corresponde, o null si esa numeración no existe. */
function digitoVerificadorCuit(primerosDiez: string): number | null {
  const suma = [...primerosDiez].reduce((total, d, i) => total + +d * PESOS_CUIT[i], 0);
  const verificador = 11 - (suma % 11);
  if (verificador === 11) {
    return 0;
  }
  return verificador === 10 ? null : verificador;
}

/** Devuelve el problema del CUIT/CUIL en palabras simples, o '' si está bien. */
export function errorCuit(texto: string, nombre = 'CUIT'): string {
  if (!/^[\d.\-\s]*$/.test(texto)) {
    return 'Usá solo números (podés separar con guiones).';
  }
  const digitos = texto.replace(/\D/g, '');
  if (digitos.length !== 11) {
    return `El ${nombre} tiene que tener 11 números (llevás ${digitos.length}).`;
  }
  if (digitoVerificadorCuit(digitos.slice(0, 10)) !== +digitos[10]) {
    return `El ${nombre} no es válido: revisá que no falte ni esté cambiado ningún número.`;
  }
  return '';
}

/** Devuelve el problema del DNI en palabras simples, o '' si está bien. */
export function errorDni(texto: string): string {
  if (!/^[\d.\-\s]*$/.test(texto)) {
    return 'Usá solo números.';
  }
  const digitos = texto.replace(/\D/g, '');
  if (digitos.length < 7 || digitos.length > 8) {
    return `El DNI tiene que tener 7 u 8 números (llevás ${digitos.length}).`;
  }
  return '';
}

/** Valida según el tipo de documento de ARCA: 80 CUIT, 86 CUIL, 96 DNI, 99 sin identificar. */
export function errorDocumento(tipo: string | undefined, numero: string | undefined): string {
  const texto = (numero ?? '').trim();
  if (tipo === '99' || !texto) {
    return '';
  }
  if (tipo === '96') {
    return errorDni(texto);
  }
  return errorCuit(texto, tipo === '86' ? 'CUIL' : 'CUIT');
}
