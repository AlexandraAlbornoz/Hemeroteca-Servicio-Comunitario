"""Modos por equipo y traslado controlado de la base al nuevo servidor."""

import base64
import hashlib
import hmac
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path

from config.settings import DB_PATH, NETWORK_CONFIG_PATH
from network.client import RemoteClient, RemoteServices
from network.configuration import load_settings, save_settings, ensure_certificate, validate_address, normalize_fingerprint
from network.server import LANServer, MAX_DATABASE
from network.transport import ErrorConexion, request
from services.container import create_services
from services.access_service import AccessDenied
from services.audit_service import append_event
from utils.timestamps import utc_now
from network.devices import public_key_id, verify_signature
from network.discovery import discover_waiting, local_address
from network.pairing import PairingReceiver, canonical, proof, normalize_code, ALPHABET


class GestorRed:
    """Coordina modo local, servidor y cliente, emparejamiento de equipos y traslado de la base principal."""
    def __init__(self, database=DB_PATH, config_path=NETWORK_CONFIG_PATH):
        """Carga rutas y ajustes de red y prepara el bloqueo, los controladores y el receptor de emparejamiento."""
        ruta_configuracion = config_path
        base_datos = database
        self.database, self.config_path = Path(base_datos), Path(ruta_configuracion)
        self.settings = load_settings(self.config_path)
        self.controllers = []
        self.receiver = None
        self._lock = threading.RLock()

    def describir(self):
        'Lee la configuración actual de este equipo y devuelve una copia independiente.'
        self.settings = load_settings(self.config_path)
        return dict(self.settings)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    describe = describir

    def seguir_servidor(self, settings):
        """Guarda bajo bloqueo la nueva dirección y huella del servidor y cambia la configuración al modo cliente."""
        configuracion = settings
        with self._lock:
            self.settings = dict(self.settings, mode='client', server_url=configuracion['server_url'], fingerprint=configuracion['fingerprint'])
            save_settings(self.settings, self.config_path)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    follow_server = seguir_servidor

    def servicios(self):
        """Construye servicios locales o remotos según la configuración y respeta el propietario activo de la base."""
        self.settings = load_settings(self.config_path)
        if self.settings['mode'] == 'client':
            return RemoteServices(RemoteClient(self.settings, self), self)
        servicios = create_services(self.database, node_id=self.settings['node_id'])
        servicios.network = self
        servicios.backups.network_path = self.config_path
        with servicios.connection:
            servicios.connection.execute("INSERT OR IGNORE INTO system_settings(key,value) VALUES('active_host_id',?)", (self.settings['node_id'],))
        propietario = dict(servicios.connection.execute('SELECT key,value FROM system_settings'))
        if propietario.get('active_host_id') != self.settings['node_id']:
            # Una copia que ya fue trasladada no puede convertirse en un segundo host.
            servicios.close()
            self.follow_server({'server_url': propietario['active_host_url'], 'fingerprint': propietario['active_host_pin']})
            return self.services()
        if self.settings['mode'] == 'server' and not any(elemento_breve.ready for elemento_breve in self.controllers):
            if servicios.auth.needs_setup():
                # Una base nueva necesita configurar al responsable antes de abrir la LAN.
                self.settings = dict(self.settings, mode='local')
                save_settings(self.settings, self.config_path)
                return servicios
            contexto, huella = ensure_certificate()
            if huella != self.settings['fingerprint']:
                servicios.close()
                raise ValueError('El certificado cambió. Reconfigura el servidor y empareja los clientes.')
            self._start(self.settings, contexto)
        return servicios
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    services = servicios

    def _iniciar(self, settings, context, *, ready=True):
        """Crea e inicia un controlador LAN con la disponibilidad indicada y lo conserva para su cierre."""
        contexto = context
        configuracion = settings
        controlador = LANServer(self.database, configuracion, contexto, ready=ready, config_path=self.config_path)
        controlador.start()
        self.controllers.append(controlador)
        return controlador
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _start = _iniciar

    def conectar(self, *args, **kwargs):
        """Rechaza la conexión directa antigua: la autorización debe realizarla el maestro desde la PC principal."""
        argumentos = args
        opciones = kwargs
        raise AccessDenied('La conexión debe autorizarla el maestro desde Computadoras conectadas en la PC principal.')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    connect = conectar

    def preparar_consultation_pc(self, services):
        """Prepara una invitación temporal únicamente en una PC cliente o sin hemeroteca propia configurada."""
        servicios = services
        if not servicios.read_only and not servicios.auth.needs_setup():
            raise AccessDenied('Esta PC ya tiene una hemeroteca propia. Conecta las otras computadoras desde el menú de su administrador principal.')
        if self.receiver:
            self.receiver.close()
        def aceptar(offer):
            """Guarda la dirección y huella aceptadas durante el emparejamiento y activa el modo cliente."""
            oferta = offer
            configuracion = load_settings(self.config_path)
            configuracion.update(mode='client', server_url=oferta['server_url'], fingerprint=oferta['server_pin'])
            save_settings(configuracion, self.config_path)
            self.settings = configuracion
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        accept = aceptar
        self.receiver = PairingReceiver(self.settings['node_id'], accept)
        self.receiver.start()
        return self.receiver
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    prepare_consultation_pc = preparar_consultation_pc

    def detener_preparation(self):
        """Cierra el receptor temporal de emparejamiento y elimina su referencia."""
        if self.receiver:
            self.receiver.close()
            self.receiver = None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    stop_preparation = detener_preparation

    def activate_principal(self, services, actor, password):
        """Configura esta computadora como servidor usando su dirección local y el puerto guardado."""
        responsable = actor
        contrasena = password
        servicios = services
        return self.configure_server(servicios, responsable, contrasena, local_address(), self.settings.get('port', 8765))

    def descubrir_computers(self, services, actor):
        """Exige administración maestra en la PC principal y devuelve las invitaciones detectadas en la LAN."""
        responsable = actor
        servicios = services
        if servicios.read_only:
            raise AccessDenied('La búsqueda se realiza desde la PC principal.')
        servicios.access.require_access(responsable, action='Buscar computadoras en espera', master=True)
        return discover_waiting()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    discover_computers = descubrir_computers

    def approved_computers(self, services, actor):
        """Consulta los equipos autorizados desde la PC principal con la autorización del administrador maestro."""
        responsable = actor
        servicios = services
        if servicios.read_only:
            raise AccessDenied('Gestiona las computadoras desde la PC principal.')
        servicios.access.require_access(responsable, action='Consultar computadoras autorizadas', master=True)
        return servicios.connection.execute('SELECT device_id,name,active,approved_at FROM authorized_devices ORDER BY approved_at DESC').fetchall()

    def aprobar_computadora(self, services, actor, candidate, code, master_password):
        """Verifica al maestro y la identidad del equipo, registra su autorización y confirma el emparejamiento remoto."""
        confirmar = self.registrar_autorizacion(services, actor, candidate, code, master_password)
        return confirmar()

    def registrar_autorizacion(self, services, actor, candidate, code, master_password):
        """Guarda la autorización y devuelve la confirmación que requiere acceso de vuelta al servidor."""
        maestro_contrasena_local = master_password
        candidato = candidate
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        codigo = code
        contrasena_maestro = maestro_contrasena
        servicios = services
        if servicios.read_only:
            raise AccessDenied('Solo la PC principal puede aprobar otra computadora.')
        servicios.auth.verify_master(responsable, contrasena_maestro)
        if self.settings['mode'] != 'server':
            raise ValueError('Primero activa esta PC como principal.')
        codigo = normalize_code(codigo)
        if len(codigo) != 12 or any(character not in ALPHABET for character in codigo):
            raise ValueError('Copia las doce letras y números que muestra la PC de consulta.')
        huella = normalize_fingerprint(candidato['fingerprint'])
        aviso_consulta = (f"PC de consulta ({candidato['name']}): deja abierta «Preparar PC de consulta» "
                          'y pulsa «Permitir la red en Windows» allí. Después vuelve a buscarla desde la principal.')
        for direccion in candidato.get('urls') or [candidato['url']]:
            url = validate_address(direccion)
            try:
                hello = request(url, huella, '/pair/hello', max_response=8192, timeout=2)
            except ErrorConexion:
                continue
            if hello.get('invitation_id') == candidato['invitation_id']:
                break
        else:
            raise ValueError(aviso_consulta)
        if any(not isinstance(hello.get(clave), str) or len(hello[clave]) > 100 for clave in ('public_key', 'nonce', 'node_id')):
            raise ValueError('La preparación de la otra PC no es válida. Vuelve a prepararla.')
        identificador_dispositivo = public_key_id(hello['public_key'])
        from urllib.parse import urlsplit
        try:
            ip_principal = local_address(urlsplit(url).hostname)
        except ValueError as error:
            raise ValueError('PC principal: comprueba que esté conectada a la misma red local que la PC de consulta.') from error
        servidor_url = f"https://{ip_principal}:{self.settings['port']}"
        oferta = {'kind': 'offer', 'invitation_id': hello['invitation_id'], 'nonce': hello['nonce'],
                 'public_key': hello['public_key'], 'client_pin': huella, 'client_node_id': hello['node_id'],
                 'server_url': servidor_url, 'server_pin': self.settings['fingerprint'], 'server_node_id': self.settings['node_id']}
        try:
            respuesta = request(url, huella, '/pair/offer', {'offer': oferta, 'proof': proof(codigo, oferta)}, max_response=8192, timeout=4)
        except ErrorConexion as error:
            raise ValueError(aviso_consulta) from error
        verify_signature(hello['public_key'], respuesta['signature'], canonical(oferta))
        if respuesta.get('device_id') != identificador_dispositivo:
            raise AccessDenied('La identidad de la otra computadora no coincide.')
        with servicios.access.authorized_write(responsable, action='Autorizar computadora de consulta', master=True):
            if self.settings['mode'] != 'server':
                raise AccessDenied('Esta PC ya no es el servidor principal.')
            servicios.connection.execute('''INSERT INTO authorized_devices(device_id,public_key,node_id,name,active,approved_by,approved_at)
                VALUES(?,?,?,?,1,?,?) ON CONFLICT(device_id) DO UPDATE SET name=excluded.name,node_id=excluded.node_id,active=1,
                approved_by=excluded.approved_by,approved_at=excluded.approved_at''',
                (identificador_dispositivo, hello['public_key'], hello['node_id'], candidato['name'], servicios.access.actor_label(responsable), utc_now()))
            append_event(servicios.connection, servicios.access.actor_label(responsable), 'Computadora autorizada: ' + candidato['name'])
        confirmacion_envio = {'kind': 'commit', 'invitation_id': hello['invitation_id'], 'offer_hash': hashlib.sha256(canonical(oferta)).hexdigest()}
        def confirmar():
            try:
                respuesta = request(url, huella, '/pair/commit', {'commit': confirmacion_envio, 'proof': proof(codigo, confirmacion_envio)}, max_response=8192)
                if respuesta.get('connected') is not True:
                    raise ValueError('El cliente no confirmó la conexión.')
            except ErrorConexion as error:
                raise ValueError('La autorización se guardó. ' + aviso_consulta) from error
            except ValueError as error:
                raise ValueError('La autorización se guardó. ' + str(error)) from error
            return identificador_dispositivo

        return confirmar
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    approve_computer = aprobar_computadora

    def revocar_computadora(self, services, actor, device_id, master_password):
        """Verifica al maestro, desactiva el equipo elegido y retira sus sesiones dejando constancia en auditoría."""
        maestro_contrasena_local = master_password
        identificador_dispositivo = device_id
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        servicios = services
        if servicios.read_only:
            raise AccessDenied('Solo la PC principal puede retirar una computadora.')
        servicios.auth.verify_master(responsable, contrasena_maestro)
        with servicios.access.authorized_write(responsable, action='Desconectar computadora', master=True):
            fila = servicios.connection.execute('SELECT name FROM authorized_devices WHERE device_id=?', (identificador_dispositivo,)).fetchone()
            if not fila:
                raise ValueError('La computadora ya no figura en la lista.')
            servicios.connection.execute('UPDATE authorized_devices SET active=0 WHERE device_id=?', (identificador_dispositivo,))
            servicios.connection.execute('DELETE FROM api_sessions WHERE device_id=?', (identificador_dispositivo,))
            append_event(servicios.connection, servicios.access.actor_label(responsable), 'Computadora desconectada: ' + fila['name'])
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    revoke_computer = revocar_computadora

    def configurar_servidor(self, services, actor, master_password, host, port):
        """Valida credenciales, dirección y puerto; activa el servidor local o coordina el traslado desde otra PC."""
        maestro_contrasena_local = master_password
        maestro_contrasena = maestro_contrasena_local
        puerto = port
        responsable = actor
        contrasena_maestro = maestro_contrasena
        servicios = services
        servicios.auth.verify_master(responsable, contrasena_maestro)
        try:
            puerto = int(puerto)
        except (ValueError, TypeError) as excepcion:
            raise ValueError('El puerto debe ser un número.') from excepcion
        url = validate_address(f'https://{host.strip()}:{puerto}')
        contexto, huella = ensure_certificate()
        destinatario = dict(self.settings, mode='server', bind='0.0.0.0', port=puerto, server_url=url, fingerprint=huella)
        if servicios.read_only:
            return self._promote(servicios, responsable, contrasena_maestro, destinatario, contexto)
        anterior = [elemento_breve for elemento_breve in self.controllers if elemento_breve.ready]
        if not anterior or destinatario['port'] != self.settings['port']:
            self._start(destinatario, contexto)
        with servicios.access.authorized_write(responsable, action='Configurar servidor LAN', master=True):
            for clave, valor in {'active_host_id': destinatario['node_id'], 'active_host_url': url, 'active_host_pin': huella}.items():
                servicios.connection.execute('INSERT INTO system_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (clave, valor))
        self.settings = destinatario
        save_settings(destinatario, self.config_path)
        for controlador in anterior:
            if int(controlador.settings['port']) != puerto:
                controlador.close()
                self.controllers.remove(controlador)
            else:
                controlador.settings = dict(destinatario)
        return dict(destinatario)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    configure_server = configurar_servidor

    def _promover(self, services, actor, master_password, target, context):
        """Prepara el servidor destino, importa la instantánea y activa su propiedad; coordina la reversión si falla."""
        maestro_contrasena_local = master_password
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        contexto = context
        contrasena_maestro = maestro_contrasena
        servicios = services
        destinatario = target
        if self.controllers:
            raise ValueError('Reinicia esta aplicación antes de trasladar nuevamente el servidor a esta PC.')
        # El destino sirve únicamente /health hasta terminar de importar la instantánea.
        controlador = self._start(destinatario, contexto, ready=False)
        old_configuracion = dict(servicios.client.settings)
        recibido = None
        try:
            respuesta = request(old_configuracion['server_url'], old_configuracion['fingerprint'], '/rpc',
                               {'method': 'network.transfer', 'args': [destinatario['server_url'], destinatario['fingerprint'], destinatario['node_id'], contrasena_maestro, controlador.cancel_token], 'kwargs': {}},
                               servicios.client.token)
            if respuesta.get('moved'):
                raise ValueError('El servidor cambió durante el traslado. Vuelve a iniciar sesión y repite la operación.')
            recibido = respuesta['result']
            self._import_snapshot(recibido, destinatario['node_id'])
            with controlador.state_lock:
                if controlador.cancelled:
                    raise ValueError('El traslado se canceló desde el servidor anterior. Reinicia esta aplicación antes de repetirlo.')
                self.settings = destinatario
                save_settings(destinatario, self.config_path)
                controlador.ready = True
            return dict(destinatario)
        except BaseException as excepcion:
            # Mantiene /health accesible para probar que el destino NO se activó antes de cancelar.
            if recibido and not controlador.ready:
                try:
                    request(old_configuracion['server_url'], old_configuracion['fingerprint'], '/rpc',
                            {'method': 'network.rollback_transfer', 'args': [contrasena_maestro, recibido['rollback_key']], 'kwargs': {}}, servicios.client.token)
                except ValueError:
                    raise ValueError('El traslado quedó pendiente y el servidor anterior está bloqueado para evitar dos copias activas. Mantén ambas aplicaciones abiertas y consulta la recuperación del traslado en docs/RED_LOCAL.md.') from excepcion
            if not recibido:
                raise ValueError('No se completó la transferencia. Si el servidor anterior quedó bloqueado, mantén ambas aplicaciones abiertas y usa «Recuperar traslado pendiente» en esa PC.') from excepcion
            raise
        finally:
            if not controlador.ready:
                # Mantener la sonda es necesario para recuperar un envío cuya respuesta se perdió.
                controlador.settings['pending'] = True
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _promote = _promover

    def _importar_instantanea(self, received, node_id):
        """Valida tamaño, huella, integridad y propietario de la copia recibida; respalda la base anterior antes de sustituirla."""
        identificador_nodo = node_id
        recibido = received
        contenido = base64.b64decode(recibido['database'], validate=True)
        if len(contenido) > MAX_DATABASE or not contenido.startswith(b'SQLite format 3\x00') or not hmac.compare_digest(hashlib.sha256(contenido).hexdigest(), recibido['sha256']):
            raise ValueError('La copia recibida está dañada o excede 64 MiB.')
        self.database.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.database.with_suffix('.incoming.db')
        try:
            temporal.write_bytes(contenido)
            with closing(sqlite3.connect(temporal)) as check:
                if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('La copia recibida no superó la revisión de integridad.')
                propietario = check.execute("SELECT value FROM system_settings WHERE key='active_host_id'").fetchone()
                if not propietario or propietario[0] != identificador_nodo:
                    raise ValueError('La copia recibida pertenece a otra transferencia.')
                check.execute("DELETE FROM system_settings WHERE key='transfer_rollback_hash'")
                check.execute("DELETE FROM system_settings WHERE key='transfer_cancel_token'")
                check.commit()
            if self.database.exists():
                respaldos = self.database.parent / 'backups'
                respaldos.mkdir(exist_ok=True)
                ruta_respaldo = respaldos / ('antes-de-traslado-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db')
                with closing(sqlite3.connect(self.database)) as origen, closing(sqlite3.connect(ruta_respaldo)) as destino:
                    origen.backup(destino)
            temporal.replace(self.database)
        finally:
            temporal.unlink(missing_ok=True)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _import_snapshot = _importar_instantanea

    def recuperar_pending_traslado(self, document, password):
        """Recuperación presencial en el antiguo host; jamás si el destino está activo."""
        documento = document
        contrasena = password
        from utils.identity import normalize_document
        from utils.security import password_matches
        from config.settings import ROLES
        local = create_services(self.database, node_id=self.settings['node_id'])
        try:
            usuario = local.connection.execute('SELECT * FROM users WHERE document=? AND active=1', (normalize_document(documento),)).fetchone()
            if not usuario or usuario['role'] != ROLES[0] or not password_matches(contrasena, usuario['password']):
                raise ValueError('Las credenciales del administrador maestro no son correctas.')
            valores = dict(local.connection.execute('SELECT key,value FROM system_settings'))
            if not valores.get('transfer_rollback_hash') or valores.get('active_host_id') == self.settings['node_id']:
                raise ValueError('No existe un traslado pendiente en esta computadora.')
            # La huella y URL anteriores se conservan en el controlador que inició el traslado.
            controlador = next((elemento_breve for elemento_breve in self.controllers if elemento_breve.settings['node_id'] == self.settings['node_id'] and elemento_breve.ready), None)
            if controlador is None:
                raise ValueError('Abre la recuperación en la sesión original del servidor anterior. Consulta docs/RED_LOCAL.md.')
            equipo_remoto = request(valores['active_host_url'], valores['active_host_pin'], '/cancel-transfer', {'token': valores.get('transfer_cancel_token')})
            if not equipo_remoto.get('cancelled') or equipo_remoto.get('node_id') != valores['active_host_id']:
                raise ValueError('El destino ya está activo. Continúa usando ese servidor.')
            controlador._restore_owner(local, valores['transfer_rollback_hash'])
            self.settings = load_settings(self.config_path)
        finally:
            local.close()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    recover_pending_transfer = recuperar_pending_traslado

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        self.stop_preparation()
        for controlador in self.controllers:
            controlador.close()
        self.controllers.clear()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
NetworkManager = GestorRed
