"""Reglas comunes para entradas nuevas, compartidas por interfaz y servicios."""
import re
import unicodedata


def validar_nombre(valor):
    """Exige nombre y apellido con letras y guarda sus iniciales en mayúscula."""
    if not isinstance(valor, str) or any(caracter != ' ' and not caracter.isalpha() for caracter in valor):
        raise ValueError('Nombre y apellido solo admiten letras, tildes y espacios.')
    partes = unicodedata.normalize('NFC', valor).split()
    if len(partes) < 2 or len(valor) > 150 or any(len(parte) < 2 for parte in partes):
        raise ValueError('Escribe nombre y apellido, con al menos dos letras cada uno (máximo 150 caracteres).')
    normalizado = ' '.join(parte.capitalize() for parte in partes)
    if len(normalizado) > 150:
        raise ValueError('El nombre normalizado debe tener un máximo de 150 caracteres.')
    return normalizado


def validar_documento_nuevo(valor):
    """Acepta únicamente cédulas V de 6–8 dígitos y E de 7–8 dígitos."""
    if not isinstance(valor, str) or not re.fullmatch(r'(?:V-[0-9]{6,8}|E-[0-9]{7,8})', valor, re.ASCII):
        raise ValueError('Selecciona V con 6 a 8 dígitos o E con 7 u 8 dígitos, sin espacios ni letras en el número.')
    return valor


def validar_respuesta_nueva(valor):
    """Rechaza respuestas vacías, de una sola letra, controles y más de 50 caracteres."""
    if not isinstance(valor, str) or any(unicodedata.category(c).startswith('C') for c in valor):
        raise ValueError('Escribe una respuesta válida, sin caracteres de control.')
    respuesta = ' '.join(unicodedata.normalize('NFKC', valor).split())
    if not 2 <= len(respuesta) <= 50 or sum(c.isalnum() for c in respuesta) < 2:
        raise ValueError('Cada respuesta debe tener de 2 a 50 caracteres y al menos dos letras o números.')
    return respuesta


def validar_numero(valor, etiqueta, *, opcional=False):
    """Permite exclusivamente dígitos ASCII en números de edición y ubicación."""
    if opcional and valor == '':
        return valor
    if not isinstance(valor, str) or not re.fullmatch(r'[0-9]{1,12}', valor, re.ASCII):
        raise ValueError(f'{etiqueta}: escribe únicamente números (máximo 12 dígitos).')
    return valor


def validar_edicion(valor):
    """Admite nombres de edición legibles, con letras, números, espacios y guiones."""
    if not isinstance(valor, str) or not 2 <= len(valor) <= 50 or not any(c.isalnum() for c in valor) or any(not (c.isalnum() or c in ' -') for c in valor):
        raise ValueError('Edición: escribe entre 2 y 50 caracteres, usando letras, números, espacios o guiones.')
    return valor
