"""Formato canónico de documentos; el correo no es un identificador de acceso."""

import re

DOCUMENT_HELP = (
    "Cuentas nuevas: cédula V con 6 a 8 dígitos, o E con 7 u 8 dígitos. "
    "No uses espacios, puntos ni letras en el número. "
    "Las cuentas anteriores conservan su documento de acceso."
)


def normalizar_documento(value: str) -> str:
    'Valida y normaliza los formatos de documento admitidos por la hemeroteca.'
    valor = value
    if not isinstance(valor, str):
        raise ValueError(DOCUMENT_HELP)
    if not valor.strip().isascii():
        raise ValueError(DOCUMENT_HELP)
    valor = valor.strip().upper()
    if re.fullmatch(r"[VE]-[0-9]{1,8}", valor, flags=re.ASCII):
        return valor
    if re.fullmatch(r"[PD]-[A-Z]{2}-[A-Z0-9]{5,20}", valor, flags=re.ASCII):
        return valor
    raise ValueError(DOCUMENT_HELP)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
normalize_document = normalizar_documento


def documento_valido(value) -> bool:
    """Devuelve si el documento cumple el normalizador existente sin propagar errores de validación."""
    valor = value
    try:
        normalize_document(valor)
        return True
    except ValueError:
        return False
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
valid_document = documento_valido
