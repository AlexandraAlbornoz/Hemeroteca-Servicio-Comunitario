"""Hashes PBKDF2 compatibles con el formato del programa original.

Mantiene las 220.000 iteraciones y el formato sal:hash para verificar las
credenciales existentes sin alterar su representación.
"""

import hashlib
import hmac
import os
import secrets
import unicodedata
from hemeroteca.utils.validaciones import validar_respuesta_nueva
from hemeroteca.config.settings import SECURITY_QUESTIONS


def calcular_hash_contrasena(password: str, salt: bytes | None = None) -> str:
    """Deriva PBKDF2-HMAC-SHA256 con 220.000 iteraciones y devuelve sal y hash hexadecimales separados por dos puntos."""
    contrasena = password
    sal = salt
    sal = sal or os.urandom(16)
    resumen_criptografico = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal, 220_000)
    return sal.hex() + ":" + resumen_criptografico.hex()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
password_hash = calcular_hash_contrasena


def verificar_contrasena(password: str, saved: str) -> bool:
    """Recalcula el hash con la sal guardada y lo compara con compare_digest; devuelve False ante formatos inválidos."""
    contrasena = password
    if not isinstance(contrasena, str) or not 1 <= len(contrasena) <= 128 or not isinstance(saved, str):
        return False
    try:
        salt_hex, digest_hex = saved.split(":", 1)
        return hmac.compare_digest(password_hash(contrasena, bytes.fromhex(salt_hex)).split(":", 1)[1], digest_hex)
    except (ValueError, TypeError):
        return False
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
password_matches = verificar_contrasena


def normalizar_seguridad_respuesta(answer: str) -> str:
    """Ignora mayúsculas y espacios repetidos, conservando las tildes."""
    respuesta_seguridad = answer
    return " ".join(unicodedata.normalize("NFKC", respuesta_seguridad).split()).casefold()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
normalize_security_answer = normalizar_seguridad_respuesta


def nueva_version_contrasena() -> int:
    """Evita validar sesiones antiguas si SQLite reutiliza un ID eliminado."""
    return secrets.randbelow((1 << 60) - 1) + 1
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
new_password_version = nueva_version_contrasena


def preparar_seguridad_preguntas(questions) -> tuple[str, ...]:
    """Valida tres preguntas distintas y genera hashes de sus respuestas."""
    preguntas = questions
    if not isinstance(preguntas, (list, tuple)) or len(preguntas) != 3:
        raise ValueError("Configura tres preguntas de seguridad con sus respuestas.")
    valores = []
    seen_preguntas = set()
    for par in preguntas:
        if (not isinstance(par, (list, tuple)) or len(par) != 2
                or not all(isinstance(valor, str) for valor in par)):
            raise ValueError("Cada pregunta y respuesta debe ser texto.")
        pregunta, respuesta_seguridad = par
        pregunta = " ".join(pregunta.split())
        normalizado = normalize_security_answer(validar_respuesta_nueva(respuesta_seguridad))
        if not 8 <= len(pregunta) <= 200:
            raise ValueError("Cada pregunta debe tener entre 8 y 200 caracteres.")
        if pregunta not in SECURITY_QUESTIONS:
            raise ValueError("Selecciona tres preguntas de la lista disponible.")
        if not 2 <= len(normalizado) <= 50:
            raise ValueError("Completa cada respuesta con entre 2 y 50 caracteres.")
        clave = pregunta.casefold()
        if clave in seen_preguntas:
            raise ValueError("Utiliza tres preguntas diferentes.")
        seen_preguntas.add(clave)
        valores.extend((pregunta, password_hash(normalizado)))
    return tuple(valores)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
prepare_security_questions = preparar_seguridad_preguntas


def validar_contrasena(value):
    'Comprueba longitud y contenido de la contraseña antes de procesar credenciales.'
    valor = value
    if (not isinstance(valor, str) or not 8 <= len(valor) <= 128 or any(c.isspace() for c in valor)
            or not any(c.isupper() for c in valor) or not any(c.islower() for c in valor)
            or not any(c.isascii() and c.isdigit() for c in valor)
            or not any(not c.isalnum() and not c.isspace() and c.isprintable() for c in valor)
            or not valor.isprintable()):
        raise ValueError("La contraseña debe tener de 8 a 128 caracteres, con mayúsculas, minúsculas, números y símbolos, sin espacios.")
    return valor
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
validate_password = validar_contrasena
