"""Configuración por computadora y certificado propio del servidor."""

import hashlib
import ipaddress
import json
import os
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from hemeroteca.config.settings import NETWORK_CONFIG_PATH, NETWORK_TLS_PATH


def cargar_configuracion(path=NETWORK_CONFIG_PATH):
    """Lee los ajustes JSON o crea la configuración local inicial; rechaza modos o identificadores inválidos."""
    ruta = path
    ruta = Path(ruta)
    if ruta.exists():
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    else:
        datos = {'node_id': str(uuid.uuid4()), 'mode': 'local', 'bind': '0.0.0.0', 'port': 8765, 'server_url': '', 'fingerprint': ''}  # nosec B104 # escucha LAN intencional para emparejamiento/servidor TLS; requiere red privada y autorización de equipos
        save_settings(datos, ruta)
    if (not isinstance(datos, dict) or datos.get('mode') not in ('local', 'server', 'client')
            or not isinstance(datos.get('node_id'), str) or not datos['node_id'].strip()):
        raise ValueError('Configuración de red inválida.')
    return datos
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
load_settings = cargar_configuracion


def guardar_configuracion(data, path=NETWORK_CONFIG_PATH):
    'Escribe la configuración en un archivo temporal y lo reemplaza de forma atómica.'
    datos = data
    ruta = path
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding='utf-8')
        os.chmod(temporal, 0o600)
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
save_settings = guardar_configuracion


def validar_direccion(url):
    """Acepta una dirección HTTPS con IPv4 privada y puerto válido, sin rutas, credenciales ni parámetros."""
    if not isinstance(url, str):
        raise ValueError('Escribe una dirección HTTPS local válida.')
    valor = urlsplit(url.strip())
    if valor.scheme != 'https' or not valor.hostname or valor.username or valor.password or valor.query or valor.fragment or valor.path not in ('', '/'):
        raise ValueError('Escribe https://IP-DE-LA-PC:8765 sin rutas ni credenciales.')
    puerto = valor.port or 443
    if not 1024 <= puerto <= 65535:
        raise ValueError('Usa un puerto entre 1024 y 65535.')
    try:
        direccion = ipaddress.IPv4Address(valor.hostname)
    except ipaddress.AddressValueError as excepcion:
        raise ValueError('Usa la dirección IPv4 local del servidor, por ejemplo 192.168.1.10.') from excepcion
    if not (direccion.is_private or direccion.is_loopback) or direccion.is_unspecified or direccion.is_multicast:
        raise ValueError('El servidor debe tener una dirección IPv4 de la red local.')
    return url.strip().rstrip('/')
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
validate_address = validar_direccion


def normalizar_huella(value):
    """Retira separadores de una huella SHA-256 y exige exactamente 64 caracteres hexadecimales."""
    valor = value
    if not isinstance(valor, str):
        raise ValueError('La huella SHA-256 debe ser texto hexadecimal.')
    valor = valor.replace(':', '').replace(' ', '').lower()
    if len(valor) != 64 or any(elemento_breve not in '0123456789abcdef' for elemento_breve in valor):
        raise ValueError('La huella SHA-256 debe contener 64 caracteres hexadecimales.')
    return valor
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
normalize_fingerprint = normalizar_huella


def asegurar_certificado():
    'Carga o crea el certificado TLS y comprueba su vigencia antes de habilitar la red.'
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    NETWORK_TLS_PATH.mkdir(parents=True, exist_ok=True)
    certificado_path, clave_path = NETWORK_TLS_PATH / 'server.pem', NETWORK_TLS_PATH / 'server.key'
    if not certificado_path.exists() or not clave_path.exists():
        clave = ec.generate_private_key(ec.SECP256R1())
        nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Hemeroteca LAN')])
        ahora = datetime.now(timezone.utc)
        certificado = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
                       .serial_number(x509.random_serial_number()).not_valid_before(ahora - timedelta(minutes=5))
                       .not_valid_after(ahora + timedelta(days=730)).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                       .sign(clave, hashes.SHA256()))
        clave_path.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.chmod(clave_path, 0o600)
        certificado_path.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    certificado = x509.load_pem_x509_certificate(certificado_path.read_bytes())
    if certificado.not_valid_after_utc <= datetime.now(timezone.utc):
        raise ValueError(f'El certificado del servidor venció. Renueva los archivos de {NETWORK_TLS_PATH} y vuelve a emparejar los clientes.')
    huella = certificado.fingerprint(hashes.SHA256()).hex()
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    contexto.load_cert_chain(str(certificado_path), str(clave_path))
    return contexto, huella
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
ensure_certificate = asegurar_certificado
