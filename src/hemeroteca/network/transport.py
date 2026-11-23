"""JSON sobre TLS; valida la huella ANTES de enviar documentos o contraseñas."""

import hashlib
import hmac
import http.client
import json
import ssl
from urllib.parse import urlsplit

from hemeroteca.services.access_service import AccessDenied
from hemeroteca.network.configuration import normalize_fingerprint, validate_address

class ErrorConexion(ValueError):
    """Distingue fallos transitorios de red de una denegación de permisos."""


MAX_RESPONSE = 128 * 1024 * 1024


def solicitud(url, fingerprint, path, payload=None, token=None, *, identity=None, max_response=MAX_RESPONSE, timeout=12):
    'Envía JSON mediante TLS y verifica la huella antes de transportar credenciales.'
    huella = fingerprint
    identidad = identity
    ruta = path
    carga = payload
    tiempo_espera = timeout
    token_sesion = token
    url = validate_address(url)
    huella = normalize_fingerprint(huella)
    direccion = urlsplit(url)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2
    # Autenticación por pin explícito. No se envía HTTP hasta comparar el certificado.
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    conexion = http.client.HTTPSConnection(direccion.hostname, direccion.port or 443, timeout=tiempo_espera, context=contexto)
    try:
        conexion.connect()
        resumen_criptografico = hashlib.sha256(conexion.sock.getpeercert(binary_form=True)).hexdigest()
        if not hmac.compare_digest(resumen_criptografico, huella):
            raise ValueError('La huella del servidor no coincide. No se enviaron credenciales.')
        cabeceras = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token_sesion:
            cabeceras['Authorization'] = 'Bearer ' + token_sesion
        contenido = json.dumps(carga, ensure_ascii=False).encode() if carga is not None else None
        metodo = 'POST' if carga is not None else 'GET'
        if ruta in ('/rpc', '/device/verify'):
            if identidad is None:
                from hemeroteca.network.devices import DeviceIdentity
                identidad = DeviceIdentity()
            cabeceras.update(identidad.headers(metodo, ruta, contenido or b'', token_sesion, huella))
        conexion.request(metodo, ruta, body=contenido, headers=cabeceras)
        respuesta = conexion.getresponse()
        contenido = respuesta.read(max_response + 1)
        if len(contenido) > max_response:
            raise ValueError('La respuesta del servidor es demasiado grande.')
        resultado = json.loads(contenido)
        if not isinstance(resultado, dict):
            raise ValueError('La respuesta del equipo no es válida.')
        if respuesta.status == 401 or resultado.get('error_type') == 'AccessDenied':
            raise AccessDenied(resultado.get('error', 'La sesión no es válida. Inicia sesión nuevamente.'))
        if respuesta.status >= 400:
            raise ValueError(resultado.get('error', 'El servidor no pudo completar la operación.'))
        return resultado
    except (OSError, http.client.HTTPException, json.JSONDecodeError, UnicodeDecodeError) as excepcion:
        raise ErrorConexion('No se pudo contactar al servidor. Revisa la red, la dirección y que la aplicación esté abierta en la PC principal.') from excepcion
    finally:
        conexion.close()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
request = solicitud
