"""Validación de documentos argentinos (CUIT, CUIL y DNI)."""
from __future__ import annotations

import re

# Pesos del algoritmo "módulo 11" con el que ARCA calcula el dígito verificador.
_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_SOLO_NUMEROS_Y_SEPARADORES = re.compile(r'[\d.\-\s]*')


class DocumentoInvalido(ValueError):
    """El mensaje está pensado para mostrárselo al usuario."""


def _digitos(texto: str) -> str:
    if not _SOLO_NUMEROS_Y_SEPARADORES.fullmatch(texto):
        raise DocumentoInvalido('Usá solo números (podés separar con guiones o puntos).')
    return re.sub(r'\D', '', texto)


def digito_verificador_cuit(primeros_diez: str) -> int | None:
    """Dígito verificador que corresponde, o None si esa numeración no existe."""
    suma = sum(int(d) * peso for d, peso in zip(primeros_diez, _PESOS_CUIT))
    verificador = 11 - suma % 11
    if verificador == 11:
        return 0
    return None if verificador == 10 else verificador


def normalizar_cuit(texto: str, nombre: str = 'CUIT') -> str:
    """Valida un CUIT o CUIL y lo devuelve con el formato 20-12345678-9."""
    digitos = _digitos(texto)
    if len(digitos) != 11:
        raise DocumentoInvalido(f'El {nombre} tiene que tener 11 números (tiene {len(digitos)}).')
    if digito_verificador_cuit(digitos[:10]) != int(digitos[10]):
        raise DocumentoInvalido(
            f'El {nombre} no es válido: revisá que no falte ni esté cambiado ningún número.'
        )
    return f'{digitos[:2]}-{digitos[2:10]}-{digitos[10]}'


def normalizar_dni(texto: str) -> str:
    """Valida un DNI y lo devuelve solo con números."""
    digitos = _digitos(texto)
    if not 7 <= len(digitos) <= 8:
        raise DocumentoInvalido(f'El DNI tiene que tener 7 u 8 números (tiene {len(digitos)}).')
    return digitos
