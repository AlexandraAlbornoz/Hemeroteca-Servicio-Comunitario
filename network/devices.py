"""Identidad por computadora y firmas de peticiones; no basta conocer una IP."""

import base64
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from config.settings import NETWORK_CONFIG_PATH
from database.connection import transaction
from services.access_service import AccessDenied

KEY_PATH = NETWORK_CONFIG_PATH.parent / 'device.key'


def peticion_canonica(method, path, timestamp, nonce, body, token, fingerprint):
    """Serializa método, ruta, instante, nonce y resúmenes del cuerpo, token y certificado para firmar la petición."""
    marca_tiempo = timestamp
    cuerpo = body
    huella = fingerprint
    metodo = method
    ruta = path
    token_sesion = token
    return '\n'.join((metodo, ruta, str(marca_tiempo), nonce, hashlib.sha256(cuerpo).hexdigest(),
                      hashlib.sha256((token_sesion or '').encode()).hexdigest(), huella)).encode()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
canonical_request = peticion_canonica


def identificador_clave_publica(public_key):
    """Valida una clave pública Ed25519 en Base64 y devuelve su identificador SHA-256."""
    publico_clave = public_key
    publico_clave_local = publico_clave
    clave_publica = publico_clave_local
    if not isinstance(clave_publica, str) or len(clave_publica) != 44:
        raise ValueError('La identidad de la computadora no es válida.')
    contenido_crudo = base64.b64decode(clave_publica, validate=True)
    if len(contenido_crudo) != 32:
        raise ValueError('La identidad de la computadora no es válida.')
    return hashlib.sha256(contenido_crudo).hexdigest()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
public_key_id = identificador_clave_publica


class IdentidadDispositivo:
    """Mantiene la identidad Ed25519 de una computadora y firma sus peticiones de red."""
    def __init__(self, path=KEY_PATH):
        """Carga o crea de forma exclusiva la clave privada local y deriva la clave pública y el identificador del equipo."""
        ruta = path
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if ruta.exists():
            self.key = serialization.load_pem_private_key(ruta.read_bytes(), password=None)
            if not isinstance(self.key, Ed25519PrivateKey):
                raise ValueError('Identidad de computadora inválida.')
        else:
            self.key = Ed25519PrivateKey.generate()
            # Creación exclusiva: no sustituye una identidad creada por otra instancia.
            try:
                with ruta.open('xb') as salida:
                    salida.write(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                        serialization.NoEncryption()))
                ruta.chmod(0o600)
            except FileExistsError:
                self.key = serialization.load_pem_private_key(ruta.read_bytes(), password=None)
        contenido_crudo = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.public_key = base64.b64encode(contenido_crudo).decode('ascii')
        self.device_id = hashlib.sha256(contenido_crudo).hexdigest()

    def firmar(self, message):
        """Firma bytes con la clave privada Ed25519 y devuelve la firma codificada en Base64."""
        mensaje = message
        return base64.b64encode(self.key.sign(mensaje)).decode('ascii')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    sign = firmar

    def cabeceras(self, method, path, body, token, fingerprint):
        """Genera instante y nonce nuevos y devuelve las cabeceras que autentican una petición concreta."""
        cuerpo = body
        huella = fingerprint
        metodo = method
        ruta = path
        token_sesion = token
        marca_tiempo, nonce = int(time.time()), secrets.token_hex(16)
        firma = self.sign(canonical_request(metodo, ruta, marca_tiempo, nonce, cuerpo, token_sesion, huella))
        return {'X-Hemeroteca-Device': self.device_id, 'X-Hemeroteca-Time': str(marca_tiempo),
                'X-Hemeroteca-Nonce': nonce, 'X-Hemeroteca-Signature': firma}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    headers = cabeceras
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
DeviceIdentity = IdentidadDispositivo


def verificar_firma(public_key, signature, message):
    'Valida la firma del dispositivo y rechaza mensajes alterados o identidades inválidas.'
    publico_clave = public_key
    publico_clave_local = publico_clave
    firma = signature
    mensaje = message
    clave_publica = publico_clave_local
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(clave_publica, validate=True)).verify(
            base64.b64decode(firma, validate=True), mensaje)
    except (InvalidSignature, ValueError, TypeError) as excepcion:
        raise AccessDenied('No se pudo verificar la identidad de la computadora.') from excepcion
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
verify_signature = verificar_firma


def verificar_device(connection, headers, method, path, body, fingerprint):
    """Verifica equipo autorizado, firma y antigüedad de la petición; registra el nonce para impedir su reutilización."""
    cuerpo = body
    conexion = connection
    huella = fingerprint
    cabeceras = headers
    metodo = method
    ruta = path
    identificador_dispositivo, nonce = cabeceras.get('X-Hemeroteca-Device', ''), cabeceras.get('X-Hemeroteca-Nonce', '')
    try:
        marca_tiempo = int(cabeceras.get('X-Hemeroteca-Time', '0'))
    except ValueError as excepcion:
        raise AccessDenied('La solicitud de la computadora no es válida.') from excepcion
    if len(identificador_dispositivo) != 64 or len(nonce) != 32 or any(elemento_breve not in '0123456789abcdef' for elemento_breve in identificador_dispositivo + nonce):
        raise AccessDenied('Esta computadora no está autorizada. El maestro debe conectarla desde la PC principal.')
    if abs(int(time.time()) - marca_tiempo) > 300:
        raise AccessDenied('Ajusta la fecha y hora automáticas de Windows en ambas computadoras.')
    registro = conexion.execute('SELECT public_key FROM authorized_devices WHERE device_id=? AND active=1', (identificador_dispositivo,)).fetchone()
    if not registro:
        raise AccessDenied('Esta computadora no está autorizada. El maestro debe conectarla desde la PC principal.')
    token_sesion = cabeceras.get('Authorization', '').removeprefix('Bearer ')
    verify_signature(registro[0], cabeceras.get('X-Hemeroteca-Signature', ''),
                     canonical_request(metodo, ruta, marca_tiempo, nonce, cuerpo, token_sesion, huella))
    with transaction(conexion):
        if not conexion.execute('SELECT 1 FROM authorized_devices WHERE device_id=? AND active=1 AND public_key=?', (identificador_dispositivo, registro[0])).fetchone():
            raise AccessDenied('El administrador retiró el acceso de esta computadora.')
        conexion.execute('DELETE FROM device_nonces WHERE expires_at<?', (int(time.time()),))
        try:
            conexion.execute('INSERT INTO device_nonces(device_id,nonce,expires_at) VALUES(?,?,?)', (identificador_dispositivo, nonce, int(time.time()) + 610))
        except sqlite3.IntegrityError as excepcion:
            raise AccessDenied('La solicitud ya fue utilizada.') from excepcion
    return identificador_dispositivo
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
verify_device = verificar_device
