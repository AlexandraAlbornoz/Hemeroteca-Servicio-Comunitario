"""Escritura privada y protección de claves con DPAPI del usuario de Windows."""

import base64
import ctypes
import json
import os
import tempfile
from pathlib import Path


def privado_escritura(path, content):
    """Escribe bytes en un temporal privado, sincroniza el contenido y reemplaza atómicamente el archivo de destino."""
    contenido = content
    ruta = path
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(prefix='.' + ruta.name + '.', dir=ruta.parent)
    try:
        with os.fdopen(descriptor, 'wb') as flujo:
            flujo.write(contenido)
            flujo.flush()
            os.fsync(flujo.fileno())
        os.chmod(temporal, 0o600)
        os.replace(temporal, ruta)
    finally:
        Path(temporal).unlink(missing_ok=True)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
private_write = privado_escritura


def escritura_json(path, value):
    """Serializa un objeto como JSON UTF-8 legible y lo guarda mediante escritura privada atómica."""
    ruta = path
    valor = value
    private_write(ruta, json.dumps(valor, ensure_ascii=False, indent=2).encode('utf-8'))
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
write_json = escritura_json


def _dpapi(value, decrypt=False):
    """Protege o recupera bytes mediante DPAPI para la cuenta actual de Windows y libera la memoria nativa devuelta."""
    valor = value
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        """Representa el bloque de tamaño y puntero que espera la API criptográfica de Windows."""
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(valor)
    origen = Blob(len(valor), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destino = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    operacion = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operacion.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operacion.restype = wintypes.BOOL
    # UI_FORBIDDEN; sin LOCAL_MACHINE: solo la cuenta Windows que configuró las copias.
    if not operacion(ctypes.byref(origen), None, None, None, None, 1, ctypes.byref(destino)):
        raise ValueError("Windows no pudo abrir la clave local. Configura los respaldos desde esta cuenta de Windows.")
    try:
        return ctypes.string_at(destino.data, destino.size)
    finally:
        kernel32.LocalFree(ctypes.cast(destino.data, wintypes.HLOCAL))


def proteger_clave(key):
    """Protege la clave con DPAPI en Windows; en desarrollo fuera de Windows usa almacenamiento sujeto a permisos de archivo."""
    clave = key
    if os.name == 'nt':
        return {'protection': 'windows-dpapi', 'key': base64.b64encode(_dpapi(clave)).decode('ascii')}
    # Entorno de desarrollo macOS/Linux; la distribución de usuario se usa en Windows.
    return {'protection': 'file-permissions', 'key': base64.b64encode(clave).decode('ascii')}
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
protect_key = proteger_clave


def desproteger_clave(settings):
    """Recupera una clave de 32 bytes con el mecanismo local indicado y rechaza configuraciones incompatibles o dañadas."""
    configuracion = settings
    try:
        valor = base64.b64decode(configuracion['key'], validate=True)
        if configuracion['protection'] == 'windows-dpapi' and os.name == 'nt':
            valor = _dpapi(valor, decrypt=True)
        elif configuracion['protection'] != 'file-permissions' or os.name == 'nt':
            raise ValueError
        if len(valor) != 32:
            raise ValueError
        return valor
    except (KeyError, TypeError, ValueError) as excepcion:
        raise ValueError("Configura de nuevo la clave de respaldos en esta computadora. Las copias anteriores conservan su clave original.") from excepcion
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
unprotect_key = desproteger_clave
