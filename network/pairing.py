"""Espera temporal en la PC de consulta; el maestro autoriza desde el servidor."""

import hashlib
import hmac
import json
import secrets
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from network.http_server import TLSHTTPServer

from network.configuration import ensure_certificate, normalize_fingerprint, validate_address
from network.devices import DeviceIdentity
from network.discovery import DiscoveryResponder, private_ip
from network.transport import ErrorConexion, request

ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
PAIRING_PORT = 8767


def canonico(value):
    """Produce JSON ASCII con claves ordenadas y sin espacios para calcular pruebas reproducibles."""
    valor = value
    return json.dumps(valor, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
canonical = canonico


def normalizar_codigo(value):
    """Normaliza el código temporal retirando espacios y guiones y convirtiendo letras a mayúsculas."""
    valor = value
    return ''.join(str(valor).upper().split()).replace('-', '')
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
normalize_code = normalizar_codigo


def prueba(code, value):
    """Calcula una prueba HMAC-SHA256 del mensaje canónico usando una clave derivada del código temporal."""
    codigo = code
    valor = value
    return hmac.new(hashlib.sha256(normalize_code(codigo).encode()).digest(), canonical(valor), hashlib.sha256).hexdigest()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
proof = prueba


class ReceptorEmparejamiento:
    """Mantiene una invitación temporal y coordina oferta y confirmación de conexión con la PC principal."""
    def __init__(self, node_id, on_accept):
        """Genera una invitación de cinco minutos y prepara identidad, TLS, descubrimiento UDP y servidor de emparejamiento."""
        on_aceptar_local_local = on_accept
        identificador_nodo = node_id
        on_aceptar_local = on_aceptar_local_local
        on_aceptar = on_aceptar_local
        self.node_id, self.on_accept = identificador_nodo, on_aceptar
        self.identity = DeviceIdentity()
        self.invitation_id, self.nonce = str(uuid.uuid4()), secrets.token_hex(24)
        self.code = '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))
        self.name = ''.join(elemento_breve for elemento_breve in socket.gethostname()[:80] if elemento_breve.isprintable()) or 'PC de consulta'
        self.expires_at = int(time.time()) + 300
        self.state, self.failures, self.offer = 'waiting', 0, None
        self.lock = threading.RLock()
        contexto, self.fingerprint = ensure_certificate()
        receptor = self

        class ManejadorPeticiones(BaseHTTPRequestHandler):
            """Atiende exclusivamente las rutas HTTP de saludo, oferta y confirmación del emparejamiento temporal."""
            def inicializacion(self):
                """Prepara los flujos HTTP e impone quince segundos de espera máxima a la conexión."""
                super().setup()
                self.connection.settimeout(15)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            setup = inicializacion

            def registrar_mensaje_http(self, *args):
                """Suprime el registro HTTP por defecto para no imprimir detalles de solicitudes de emparejamiento."""
                argumentos = args
                pass
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            log_message = registrar_mensaje_http

            def respond(self, value, status=200):
                """Envía JSON con longitud explícita, desactiva su caché e indica el cierre de la conexión."""
                estado = status
                valor = value
                cuerpo = json.dumps(valor).encode()
                self.send_response(estado)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(cuerpo)

            def atender_consulta_http(self):
                'Atiende la comprobación de disponibilidad del servidor HTTP.'
                if self.path != '/pair/hello' or not private_ip(self.client_address[0]):
                    self.respond({'error': 'No disponible.'}, 404)
                    return
                with receptor.lock:
                    if receptor.expired() or receptor.state not in ('waiting', 'offered'):
                        self.respond({'error': 'La preparación venció. Vuelve a prepararla en la PC de consulta.'}, 400)
                        return
                    self.respond(dict(receptor.description() or {}, public_key=receptor.identity.public_key, nonce=receptor.nonce))
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            do_GET = atender_consulta_http

            def atender_operacion_http(self):
                'Valida una petición firmada y ejecuta únicamente operaciones permitidas.'
                try:
                    if not private_ip(self.client_address[0]):
                        raise ValueError('La conexión debe provenir de la red local.')
                    longitud = int(self.headers.get('Content-Length', '0'))
                    if not 0 < longitud <= 8192:
                        raise ValueError('Solicitud inválida.')
                    carga = json.loads(self.rfile.read(longitud))
                    with receptor.lock:
                        if receptor.expired():
                            raise ValueError('El código venció. Vuelve a preparar esta PC.')
                        if self.path == '/pair/offer':
                            resultado = receptor.accept_offer(carga)
                        elif self.path == '/pair/commit':
                            resultado = receptor.commit(carga)
                        else:
                            raise ValueError('Operación no disponible.')
                    self.respond(resultado)
                except (ValueError, KeyError, TypeError, AttributeError) as excepcion:
                    self.respond({'error': str(excepcion)}, 400)
                except OSError:
                    self.respond({'error': 'No se pudo guardar la conexión. Revisa los permisos de esta carpeta.'}, 500)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            do_POST = atender_operacion_http
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        Handler = ManejadorPeticiones

        self.httpd = TLSHTTPServer(('0.0.0.0', PAIRING_PORT), Handler, contexto)
        try:
            self.discovery = DiscoveryResponder(self.description)
        except BaseException:
            self.httpd.server_close()
            raise
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name='hemeroteca-autorizacion')

    def iniciar(self):
        'Inicia el trabajador o servidor y conserva su referencia para el cierre.'
        self.thread.start()
        self.discovery.start()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    start = iniciar

    def vencido(self):
        """Indica si la invitación expiró, acumuló cinco fallos o fue cancelada."""
        return time.time() >= self.expires_at or self.failures >= 5 or self.state == 'cancelled'
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    expired = vencido

    def descripcion(self):
        """Devuelve los datos públicos de la invitación mientras pueda recibir una oferta; en otro caso devuelve None."""
        with self.lock:
            if self.expired() or self.state not in ('waiting', 'offered'):
                return None
            return {'invitation_id': self.invitation_id, 'name': self.name, 'port': PAIRING_PORT,
                    'fingerprint': self.fingerprint, 'expires_at': self.expires_at, 'node_id': self.node_id}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    description = descripcion

    def verificar_prueba(self, value, supplied):
        """Compara la prueba HMAC sin diferencias de tiempo deliberadas y cuenta los intentos incorrectos."""
        valor = value
        if not isinstance(supplied, str) or not hmac.compare_digest(proof(self.code, valor), supplied):
            self.failures += 1
            raise ValueError('El código temporal no coincide. Revisa el código de la otra computadora.')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    check_proof = verificar_prueba

    def aceptar_oferta(self, payload):
        """Comprueba el código y los datos del destinatario; conserva la oferta aceptada y devuelve su firma."""
        carga = payload
        if self.state not in ('waiting', 'offered'):
            raise ValueError('Esta autorización ya terminó.')
        oferta = carga['offer']
        self.check_proof(oferta, carga.get('proof'))
        if (oferta['invitation_id'] != self.invitation_id or oferta['nonce'] != self.nonce
                or oferta['public_key'] != self.identity.public_key or oferta['client_pin'] != self.fingerprint
                or oferta['client_node_id'] != self.node_id):
            raise ValueError('La solicitud corresponde a otra computadora. Repite la búsqueda.')
        validate_address(oferta['server_url'])
        normalize_fingerprint(oferta['server_pin'])
        if self.offer is not None and self.offer != oferta:
            raise ValueError('Esta PC ya está esperando la confirmación de otra solicitud.')
        self.offer, self.state = oferta, 'offered'
        return {'signature': self.identity.sign(canonical(oferta)), 'device_id': self.identity.device_id}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    accept_offer = aceptar_oferta

    def confirmar(self, payload):
        """Valida la confirmación y la autorización real en el servidor antes de guardar la conexión local."""
        carga = payload
        if self.offer is None or self.state not in ('offered', 'connected'):
            raise ValueError('Primero debe autorizarse la computadora desde la PC principal.')
        valor = carga['commit']
        self.check_proof(valor, carga.get('proof'))
        esperado = {'kind': 'commit', 'invitation_id': self.invitation_id,
                    'offer_hash': hashlib.sha256(canonical(self.offer)).hexdigest()}
        if valor != esperado:
            raise ValueError('La confirmación no corresponde a esta autorización.')
        if self.state == 'connected':
            return {'connected': True}
        # Comprueba que el host realmente aprobó esta clave antes de cambiar la configuración local.
        try:
            request(self.offer['server_url'], self.offer['server_pin'], '/device/verify', {},
                    identity=self.identity, max_response=8192, timeout=4)
        except ErrorConexion as error:
            raise ValueError('PC principal: deja Hemeroteca abierta y pulsa «Permitir la red en Windows» allí. '
                             'Luego vuelve a autorizar usando el código vigente.') from error
        self.on_accept(self.offer)
        self.state = 'connected'
        return {'connected': True}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    commit = confirmar

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        with self.lock:
            if self.state != 'connected':
                self.state = 'cancelled'
        self.discovery.close()
        self.httpd.shutdown()
        self.httpd.server_close()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
PairingReceiver = ReceptorEmparejamiento
