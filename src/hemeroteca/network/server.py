"""API LAN con TLS, sesiones revocables y una lista cerrada de operaciones."""

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict, deque
from contextlib import closing
from http.server import BaseHTTPRequestHandler
from hemeroteca.network.http_server import TLSHTTPServer
from pathlib import Path

from hemeroteca.network.client import ALLOWED, PUBLIC, CONTROL
from hemeroteca.network.configuration import save_settings, validate_address, normalize_fingerprint
from hemeroteca.network.transport import request
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.audit_service import append_event
from hemeroteca.services.container import create_services
from hemeroteca.services.recovery_service import RegistrationResult
from hemeroteca.database.connection import transaction
from hemeroteca.database.maintenance import database_guard
from hemeroteca.network.devices import DeviceIdentity, verify_device
from hemeroteca.utils.timestamps import utc_now
import socket

MAX_DATABASE = 64 * 1024 * 1024
MAX_REQUEST = 32 * 1024
SESSION_SECONDS = 8 * 60 * 60
MAX_REGISTRATIONS_PER_MINUTE = 10
PRIVATE_FIELDS = {'password', 'answer_1', 'answer_2', 'answer_3', 'code_hash', 'token_hash'}


def decodificar_solicitud(cuerpo):
    """Clasifica el exceso de anidamiento JSON como datos inválidos del cliente."""
    try:
        return json.loads(cuerpo)
    except RecursionError as excepcion:
        raise ValueError('Solicitud JSON demasiado anidada.') from excepcion


def codigo_acceso_denegado(responsable):
    """Distingue falta de sesión (401) de permiso insuficiente (403)."""
    return 403 if responsable is not None else 401


def publico_value(value):
    'Convierte resultados al contrato JSON excluyendo campos secretos.'
    valor = value
    if isinstance(valor, RegistrationResult):
        # El código recién emitido se entrega una sola vez a la PC solicitante.
        return {'user_id': valor.user_id, 'recovery_code': valor.recovery_code}
    if isinstance(valor, sqlite3.Row):
        valor = dict(valor)
    if isinstance(valor, dict):
        return {clave_breve: public_value(valor_breve) for clave_breve, valor_breve in valor.items() if clave_breve not in PRIVATE_FIELDS}
    if isinstance(valor, (tuple, list, set)):
        return [public_value(valor_breve) for valor_breve in valor]
    return valor
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
public_value = publico_value


class ServidorRedLocal:
    """Expone operaciones RPC autorizadas y coordina sesiones, límites de peticiones y traslado del servidor."""
    def __init__(self, database, settings, context, *, ready=True, config_path=None):
        """Prepara identidad, límites, estado de traslado y servidor TLS con su manejador de operaciones."""
        ruta_configuracion = config_path
        contexto = context
        base_datos = database
        configuracion = settings
        self.database, self.settings = Path(base_datos), dict(configuracion)
        self.ready, self.config_path = ready, ruta_configuracion
        self.state_lock = threading.RLock()
        self.cancelled = False
        self.cancel_token = secrets.token_urlsafe(48)
        self.identity = DeviceIdentity()
        self._rates = defaultdict(deque)
        self._rate_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(12)
        controlador = self

        class ManejadorPeticiones(BaseHTTPRequestHandler):
            """Atiende disponibilidad, peticiones firmadas y cancelaciones de traslado aplicando los controles del servidor."""
            def inicializacion(self):
                """Prepara los flujos HTTP y limita a veinte segundos la espera de la conexión."""
                super().setup()
                self.connection.settimeout(20)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            setup = inicializacion

            def registrar_mensaje_http(self, *args):
                """Suprime el registro HTTP por defecto para evitar imprimir detalles de peticiones y sesiones."""
                argumentos = args
                pass  # No registra documentos, contraseñas, tokens ni cuerpos HTTP.
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            log_message = registrar_mensaje_http

            def respond(self, data, status=200):
                """Convierte el resultado a datos públicos y envía JSON UTF-8 sin caché con longitud y cierre explícitos."""
                datos = data
                estado = status
                cuerpo = json.dumps(public_value(datos), ensure_ascii=False).encode('utf-8')
                self.send_response(estado)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(cuerpo)

            def atender_consulta_http(self):
                'Atiende la comprobación de disponibilidad del servidor HTTP.'
                if self.path != '/health':
                    self.respond({'error': 'Ruta no disponible.'}, 404)
                    return
                self.respond({'node_id': controlador.settings['node_id'], 'ready': controlador.ready})
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            do_GET = atender_consulta_http

            def atender_operacion_http(self):
                'Valida una petición firmada y ejecuta únicamente operaciones permitidas.'
                if self.path == '/cancel-transfer':
                    try:
                        longitud = int(self.headers.get('Content-Length', '0'))
                        if not 0 < longitud <= MAX_REQUEST:
                            raise ValueError('Solicitud inválida.')
                        carga = decodificar_solicitud(self.rfile.read(longitud))
                        self.respond(controlador.cancel_stage(carga.get('token')))
                    except (ValueError, TypeError, AttributeError) as excepcion:
                        self.respond({'error': str(excepcion)}, 400)
                    return
                if self.path not in ('/rpc', '/device/verify') or not controlador.ready:
                    self.respond({'error': 'El servidor todavía no está activo.'}, 503)
                    return
                if not controlador.allow_request(self.client_address[0]) or not controlador._slots.acquire(blocking=False):
                    self.respond({'error': 'Demasiadas solicitudes. Espera un minuto.'}, 429)
                    return
                servicios = None
                proteccion = None
                protegido = False
                responsable = None
                try:
                    longitud = int(self.headers.get('Content-Length', '0'))
                    if not 0 < longitud <= MAX_REQUEST or self.headers.get_content_type() != 'application/json':
                        raise ValueError('Solicitud JSON inválida o demasiado grande.')
                    cuerpo = self.rfile.read(longitud)
                    entrada = decodificar_solicitud(cuerpo)
                    if not isinstance(entrada, dict):
                        raise ValueError('Solicitud inválida.')
                    proteccion = database_guard(controlador.database, exclusive=entrada.get('method') in CONTROL)
                    proteccion.__enter__()
                    protegido = True
                    servicios = create_services(controlador.database, node_id=controlador.settings['node_id'], initialize=False)
                    identificador_dispositivo = verify_device(servicios.connection, self.headers, 'POST', self.path, cuerpo, controlador.settings['fingerprint'])
                    if self.path == '/device/verify':
                        if controlador.redirect(servicios):
                            raise AccessDenied('Autoriza la computadora desde el servidor principal actual.')
                        self.respond({'authorized': True})
                        return
                    # El mismo JSON ya fue decodificado y validado antes de autorizar la PC.
                    carga = entrada
                    metodo, argumentos, opciones = carga.get('method'), carga.get('args', []), carga.get('kwargs', {})
                    if metodo not in ALLOWED or not isinstance(argumentos, list) or not isinstance(opciones, dict):
                        raise AccessDenied('Operación no permitida en una computadora de consulta.')
                    if 'actor' in opciones or any(str(clave_breve).startswith('_') for clave_breve in opciones):
                        raise ValueError('Argumentos inválidos.')
                    moved = controlador.redirect(servicios)
                    if moved and metodo not in CONTROL:
                        self.respond(moved)
                        return
                    if metodo == 'users.register_user' and not controlador.allow_request(
                            identificador_dispositivo, limit=MAX_REGISTRATIONS_PER_MINUTE, group='registration'):
                        self.respond({'error': 'Se intentaron demasiados registros desde esta PC. Espera un minuto.'}, 429)
                        return
                    responsable = None
                    if metodo not in PUBLIC:
                        responsable = controlador.actor_from_token(servicios, self.headers.get('Authorization', ''), identificador_dispositivo)
                    if metodo in ('network.transfer', 'hemeroteca.network.transfer'):
                        resultado = controlador.transfer(servicios, responsable, *argumentos, **opciones)
                    elif metodo in ('network.rollback_transfer', 'hemeroteca.network.rollback_transfer'):
                        resultado = controlador.rollback_transfer(servicios, responsable, *argumentos, **opciones)
                    elif metodo == 'auth.needs_setup':
                        resultado = False  # El maestro se configura presencialmente en el servidor.
                    elif metodo == 'auth.logout':
                        resumen_criptografico = hashlib.sha256(self.headers['Authorization'].removeprefix('Bearer ').encode()).hexdigest()
                        with servicios.connection:
                            servicios.connection.execute('DELETE FROM api_sessions WHERE token_hash=?', (resumen_criptografico,))
                        resultado = True
                    else:
                        grupo, nombre = metodo.split('.')
                        operacion = getattr(getattr(servicios, grupo), nombre)
                        if metodo == 'reports.generate':
                            # El servicio protege la lectura y la entrega. Componer el PDF no bloquea las consultas LAN.
                            proteccion.__exit__(None, None, None)
                            protegido = False
                        resultado = operacion(*argumentos, **opciones) if metodo in PUBLIC else operacion(responsable, *argumentos, **opciones)
                    respuesta = {'result': resultado}
                    if metodo in {'auth.authenticate', 'auth.authenticate_with_code', 'auth.autenticar_con_preguntas', 'auth.migrate_document', 'auth.change_password'}:
                        respuesta['token'] = controlador.new_session(servicios, resultado, identificador_dispositivo)
                    if protegido:
                        proteccion.__exit__(None, None, None)
                        protegido = False
                    self.respond(respuesta)
                except AccessDenied as excepcion:
                    # Sesión ausente/inválida: 401. Sesión válida sin permiso: 403.
                    self.respond({'error': str(excepcion), 'error_type': 'AccessDenied'},
                                 codigo_acceso_denegado(responsable))
                except (ValueError, TypeError, sqlite3.IntegrityError) as excepcion:
                    mensaje = 'Los datos enviados no son válidos o ya están registrados.' if isinstance(excepcion, (TypeError, sqlite3.IntegrityError)) else str(excepcion)
                    self.respond({'error': mensaje}, 400)
                except (sqlite3.Error, OSError, RuntimeError):
                    self.respond({'error': 'No se pudo completar la operación. Revisa el servidor.'}, 500)
                finally:
                    if servicios:
                        servicios.close()
                    if protegido:
                        proteccion.__exit__(None, None, None)
                    controlador._slots.release()
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            do_POST = atender_operacion_http
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        Handler = ManejadorPeticiones

        self.httpd = TLSHTTPServer((configuracion['bind'], int(configuracion['port'])), Handler, contexto)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name='hemeroteca-lan')

    def iniciar(self):
        'Inicia el trabajador o servidor y conserva su referencia para el cierre.'
        self.thread.start()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    start = iniciar

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        # shutdown espera a serve_forever: antes de start bloquearía el cierre.
        if self.thread.is_alive():
            self.httpd.shutdown()
            self.thread.join()
        self.httpd.server_close()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar

    def cancel_stage(self, token):
        """Cancelación atómica: gana la activación o gana la cancelación, nunca ambas."""
        token_sesion = token
        if not isinstance(token_sesion, str) or not hmac.compare_digest(token_sesion, self.cancel_token):
            raise ValueError('No se pudo autorizar la cancelación del traslado.')
        with self.state_lock:
            if self.ready:
                return {'cancelled': False, 'node_id': self.settings['node_id']}
            self.cancelled = True
            return {'cancelled': True, 'node_id': self.settings['node_id']}

    def permitir_solicitud(self, address, *, limit=360, group='requests'):
        """Aplica un límite por grupo y origen durante una ventana de sesenta segundos y descarta historial expirado."""
        grupo = group
        direccion = address
        limite = limit
        ahora = time.monotonic()
        with self._rate_lock:
            # Evita que una lista de direcciones antiguas crezca indefinidamente.
            if len(self._rates) > 256:
                self._rates = defaultdict(deque, {clave_breve: valor_breve for clave_breve, valor_breve in self._rates.items() if valor_breve and valor_breve[-1] > ahora - 60})
            valores = self._rates[(grupo, direccion)]
            while valores and valores[0] < ahora - 60:
                valores.popleft()
            if len(valores) >= limite:
                return False
            valores.append(ahora)
            return True
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    allow_request = permitir_solicitud

    def redirect(self, services):
        """Lee el propietario activo y devuelve la nueva dirección y huella cuando esta PC dejó de ser el servidor."""
        servicios = services
        valores = dict(servicios.connection.execute('SELECT key,value FROM system_settings'))
        propietario = valores.get('active_host_id')
        if propietario and propietario != self.settings['node_id']:
            return {'moved': True, 'server_url': valores['active_host_url'], 'fingerprint': valores['active_host_pin']}
        return None

    def responsable_from_token(self, services, authorization, device_id):
        """Resuelve un token vigente ligado al equipo y comprueba cuenta, versión de contraseña y generación de recuperación."""
        identificador_dispositivo = device_id
        servicios = services
        token_sesion = authorization.removeprefix('Bearer ')
        if not authorization.startswith('Bearer ') or not 32 <= len(token_sesion) <= 256:
            raise AccessDenied('Inicia sesión para consultar el servidor.')
        resumen_criptografico = hashlib.sha256(token_sesion.encode()).hexdigest()
        session = servicios.connection.execute('SELECT * FROM api_sessions WHERE token_hash=? AND expires_at>?', (resumen_criptografico, int(time.time()))).fetchone()
        if session is None or session['device_id'] != identificador_dispositivo:
            raise AccessDenied('La sesión venció. Vuelve a iniciar sesión.')
        usuario = servicios.connection.execute('SELECT * FROM users WHERE id=? AND active=1', (session['user_id'],)).fetchone()
        if usuario is None or usuario['password_version'] != session['password_version']:
            raise AccessDenied('La cuenta cambió. Vuelve a iniciar sesión.')
        responsable = dict(usuario, _auth_method=session['method'])
        if session['method'] == 'recovery':
            responsable['_recovery_generation'] = session['recovery_generation']
            if not servicios.access._recovery_valid(responsable):
                raise AccessDenied('El código de recuperación ya no está vigente.')
        return responsable
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    actor_from_token = responsable_from_token

    def crear_sesion(self, services, actor, device_id):
        """Genera un token aleatorio y guarda solo su hash junto al usuario, equipo, método y vencimiento."""
        identificador_dispositivo = device_id
        responsable = actor
        servicios = services
        token_sesion = secrets.token_urlsafe(48)
        with servicios.connection:
            servicios.access.require_host_write()
            servicios.connection.execute('DELETE FROM api_sessions WHERE expires_at<=?', (int(time.time()),))
            servicios.connection.execute('''INSERT INTO api_sessions(token_hash,user_id,password_version,method,recovery_generation,expires_at,device_id)
                VALUES(?,?,?,?,?,?,?)''', (hashlib.sha256(token_sesion.encode()).hexdigest(), responsable['id'], responsable['password_version'],
                                        responsable.get('_auth_method', 'password'), responsable.get('_recovery_generation'), int(time.time()) + SESSION_SECONDS, identificador_dispositivo))
        return token_sesion
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    new_session = crear_sesion

    def traslado(self, services, actor, new_url, new_fingerprint, new_node_id, master_password, cancel_token):
        'Traslada el servidor mediante el protocolo de confirmación entre equipos.'
        maestro_contrasena_local = master_password
        nueva_huella_local_local = new_fingerprint
        nueva_node_id = new_node_id
        nueva_url_local_local = new_url
        token_cancelacion = cancel_token
        maestro_contrasena = maestro_contrasena_local
        nueva_huella_local = nueva_huella_local_local
        nueva_node_id_local = nueva_node_id
        nueva_url_local = nueva_url_local_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        nueva_huella = nueva_huella_local
        identificador_nodo_nuevo = nueva_node_id_local
        nueva_url = nueva_url_local
        servicios = services
        with self.state_lock:
            return self._transfer(servicios, responsable, nueva_url, nueva_huella, identificador_nodo_nuevo, contrasena_maestro, token_cancelacion)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    transfer = traslado

    def _traslado(self, services, actor, new_url, new_fingerprint, new_node_id, master_password, cancel_token):
        """Verifica al maestro y al destino, transfiere la propiedad y entrega una instantánea con datos de reversión."""
        maestro_contrasena_local = master_password
        nueva_huella_local_local = new_fingerprint
        nueva_node_id = new_node_id
        nueva_url_local_local = new_url
        token_cancelacion = cancel_token
        maestro_contrasena = maestro_contrasena_local
        nueva_huella_local = nueva_huella_local_local
        nueva_node_id_local = nueva_node_id
        nueva_url_local = nueva_url_local_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        nueva_huella = nueva_huella_local
        identificador_nodo_nuevo = nueva_node_id_local
        nueva_url = nueva_url_local
        servicios = services
        nueva_url, nueva_huella = validate_address(nueva_url), normalize_fingerprint(nueva_huella)
        if not isinstance(identificador_nodo_nuevo, str) or len(identificador_nodo_nuevo) > 100 or identificador_nodo_nuevo == self.settings['node_id']:
            raise ValueError('La nueva computadora debe ser distinta del servidor actual.')
        if not isinstance(token_cancelacion, str) or not 32 <= len(token_cancelacion) <= 256:
            raise ValueError('El destino no preparó la cancelación del traslado.')
        servicios.auth.verify_master(responsable, contrasena_maestro)
        equipo_remoto = request(nueva_url, nueva_huella, '/health')
        if equipo_remoto.get('node_id') != identificador_nodo_nuevo or equipo_remoto.get('ready'):
            raise ValueError('La nueva PC no está preparada para recibir la base de datos.')
        clave_reversion = secrets.token_urlsafe(48)
        with servicios.access.authorized_write(responsable, action='Trasladar servidor', master=True):
            # El servidor anterior se convertirá en cliente de este mismo conjunto de datos.
            servicios.connection.execute('INSERT INTO authorized_devices(device_id,public_key,node_id,name,active,approved_by,approved_at) VALUES(?,?,?,?,1,?,?) ON CONFLICT(device_id) DO UPDATE SET active=1',
                (self.identity.device_id, self.identity.public_key, self.settings['node_id'], socket.gethostname()[:80], servicios.access.actor_label(responsable), utc_now()))
            # El bloqueo se confirma antes de exportar. Las escrituras del host anterior se rechazan.
            for clave, valor in {'active_host_id': identificador_nodo_nuevo, 'active_host_url': nueva_url, 'active_host_pin': nueva_huella,
                               'transfer_rollback_hash': hashlib.sha256(clave_reversion.encode()).hexdigest(),
                               'transfer_cancel_token': token_cancelacion}.items():
                servicios.connection.execute('INSERT INTO system_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (clave, valor))
            append_event(servicios.connection, servicios.access.actor_label(responsable), 'Servidor trasladado a ' + nueva_url)
        try:
            with tempfile.TemporaryDirectory(prefix='hemeroteca-transfer-') as directorio:
                instantanea_path = Path(directorio) / 'snapshot.db'
                with closing(sqlite3.connect(instantanea_path)) as destino:
                    servicios.connection.backup(destino)
                contenido = instantanea_path.read_bytes()
            if len(contenido) > MAX_DATABASE:
                raise ValueError('La base supera 64 MiB. El traslado requiere una copia de respaldo manual supervisada.')
        except BaseException:
            # Todavía no se entregó la instantánea; la nueva PC no puede activarse.
            self._restore_owner(servicios, hashlib.sha256(clave_reversion.encode()).hexdigest())
            raise
        configuracion = dict(self.settings, mode='client', server_url=nueva_url, fingerprint=nueva_huella)
        save_settings(configuracion, self.config_path)
        return {'database': base64.b64encode(contenido).decode('ascii'), 'sha256': hashlib.sha256(contenido).hexdigest(),
                'rollback_key': clave_reversion, 'old_url': self.settings['server_url'], 'old_fingerprint': self.settings['fingerprint']}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _transfer = _traslado

    def _restaurar_propietario(self, services, expected_transfer):
        """Restituye la propiedad local solo si coincide la transferencia pendiente y elimina sus claves de control."""
        expected_traslado_local_local = expected_transfer
        expected_traslado_local = expected_traslado_local_local
        expected_traslado = expected_traslado_local
        servicios = services
        with self.state_lock, transaction(servicios.connection):
            actual = dict(servicios.connection.execute('SELECT key,value FROM system_settings'))
            pendiente = actual.get('transfer_rollback_hash', '')
            if not pendiente and actual.get('active_host_id') == self.settings['node_id']:
                return
            if not hmac.compare_digest(pendiente, expected_traslado):
                raise AccessDenied('El estado del traslado cambió. Actualiza la conexión antes de continuar.')
            valores = {'active_host_id': self.settings['node_id'], 'active_host_url': self.settings['server_url'], 'active_host_pin': self.settings['fingerprint']}
            for clave, valor in valores.items():
                servicios.connection.execute('INSERT INTO system_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (clave, valor))
            servicios.connection.execute("DELETE FROM system_settings WHERE key='transfer_rollback_hash'")
            servicios.connection.execute("DELETE FROM system_settings WHERE key='transfer_cancel_token'")
            save_settings(dict(self.settings, mode='server'), self.config_path)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _restore_owner = _restaurar_propietario

    def revertir_traslado(self, services, actor, master_password, rollback_key):
        # Solo se permite antes de activar el nuevo servidor y con el secreto de esa transferencia.
        'Revierte un traslado pendiente tras comprobar autorización y estado.'
        maestro_contrasena_local = master_password
        revertir_clave = rollback_key
        maestro_contrasena = maestro_contrasena_local
        revertir_clave_local = revertir_clave
        responsable = actor
        contrasena_maestro = maestro_contrasena
        clave_reversion = revertir_clave_local
        servicios = services
        servicios.auth.verify_master(responsable, contrasena_maestro)
        valores = dict(servicios.connection.execute('SELECT key,value FROM system_settings'))
        esperado = valores.get('transfer_rollback_hash', '')
        if valores.get('active_host_id') == self.settings['node_id'] and not esperado:
            return True  # Una cancelación previa ya restauró este host.
        if not esperado or not hmac.compare_digest(esperado, hashlib.sha256(clave_reversion.encode()).hexdigest()):
            raise AccessDenied('No se puede cancelar esta transferencia.')
        equipo_remoto = request(valores['active_host_url'], valores['active_host_pin'], '/cancel-transfer', {'token': valores.get('transfer_cancel_token')})
        if not equipo_remoto.get('cancelled') or equipo_remoto.get('node_id') != valores['active_host_id']:
            raise AccessDenied('El servidor destino ya está activo. No se puede reactivar la copia anterior.')
        self._restore_owner(servicios, esperado)
        return True
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    rollback_transfer = revertir_traslado
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
LANServer = ServidorRedLocal
