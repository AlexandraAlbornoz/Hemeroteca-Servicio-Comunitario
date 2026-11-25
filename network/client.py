"""Adaptadores de consultas, operaciones autorizadas y credenciales personales."""

from services.access_service import AccessDenied
from services.recovery_service import RegistrationResult
from network.transport import request

# PUBLIC significa sin sesión de usuario; la firma de una PC autorizada es obligatoria.
PUBLIC = {'auth.needs_setup', 'auth.authenticate', 'auth.authenticate_with_code',
          'auth.obtener_preguntas_recuperacion', 'auth.autenticar_con_preguntas',
          'auth.migration_accounts', 'auth.migrate_document', 'users.register_user'}
READS = {
    'users.buscar_usuarios', 'audit.acciones_disponibles', 'audit.buscar_eventos', 'audit.resultados_disponibles',
    'requests.resumen_solicitudes', 'requests.buscar_solicitudes', 'periodicos.buscar_eliminados',
    'access.estado_sesion', 'periodicos.buscar_fechas_ausentes',
    'access.current_user', 'access.require_access', 'access.permissions', 'access.has_grant',
    'audit.list_events', 'users.users', 'users.get_user', 'users.grants', 'requests.requests',
    'requests.available_permissions',
    'periodicos.search_issues', 'periodicos.consult_issues', 'periodicos.consult_absent_dates',
    'periodicos.list_issues', 'periodicos.list_absent_dates', 'periodicos.get_issue',
    'periodicos.list_deleted_issues', 'periodicos.get_deleted_issue', 'periodicos.has_absent_date',
    'recovery.needs_configuration', 'recovery.configured_questions', 'recovery.needs_code',
    'reports.generate',
}
AUTHENTICATION = {'auth.change_password', 'auth.verify_master', 'auth.logout', 'recovery.configure_questions', 'recovery.enroll_code', 'recovery.renovar_codigo_propio'}
REQUESTS = {'requests.submit_request'}
CATALOG_WRITES = {'periodicos.corregir_fecha_ausente', 'periodicos.register_issue', 'periodicos.save_record', 'periodicos.delete_issue'}
CONTROL = {'network.transfer', 'network.rollback_transfer'}
ALLOWED = PUBLIC | READS | AUTHENTICATION | REQUESTS | CATALOG_WRITES | CONTROL


class ClienteRemoto:
    """Transporta operaciones permitidas al servidor HTTPS y conserva el token de la sesión."""
    def __init__(self, settings, manager=None):
        """Copia los ajustes de conexión y registra el gestor que seguirá traslados del servidor; empieza sin sesión."""
        gestor = manager
        configuracion = settings
        self.settings = dict(configuracion)
        self.manager = gestor
        self.token = None

    def salir(self):
        """Solicita cerrar la sesión remota y borra el token local incluso si el servidor no está disponible."""
        if self.token:
            try:
                self.call('auth.logout')
            except ValueError:
                pass  # Las sesiones inaccesibles vencen automáticamente en el servidor.
        self.token = None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    logout = salir

    def llamar(self, method, *args, **kwargs):
        """Valida la operación, envía sus argumentos por HTTPS y sigue hasta tres redirecciones de servidor."""
        argumentos = args
        opciones = kwargs
        metodo = method
        if metodo not in ALLOWED:
            raise AccessDenied('Esta operación solo está disponible en la PC principal.')
        for _ in range(3):
            resultado = request(self.settings['server_url'], self.settings['fingerprint'], '/rpc',
                             {'method': metodo, 'args': argumentos, 'kwargs': opciones}, self.token,
                             timeout=120 if metodo == 'reports.generate' else 12)
            if resultado.get('moved'):
                self.settings.update(server_url=resultado['server_url'], fingerprint=resultado['fingerprint'])
                if self.manager:
                    self.manager.follow_server(self.settings)
                continue
            if resultado.get('token'):
                self.token = resultado['token']
            return resultado.get('result')
        raise ValueError('No se pudo resolver el servidor activo.')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    call = llamar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RemoteClient = ClienteRemoto


class AdaptadorRemoto:
    """Expone la API de un servicio local mediante llamadas RPC y adapta los resultados recibidos."""
    def __init__(self, client, name):
        """Vincula el cliente de transporte con el nombre del servicio que representará."""
        cliente = client
        nombre = name
        self.client, self.name = cliente, nombre

    def __getattr__(self, name):
        'Resuelve un atributo o método del servicio adaptado conservando su contrato.'
        nombre = name
        metodo = self.name + '.' + nombre
        if metodo == 'access.actor_label':
            return lambda actor: f"{actor['name']} · {actor['identity']}" if actor else 'Sin sesión'
        if metodo == 'audit.record':
            return lambda *args, **kwargs: None
        def invocar(*args, **kwargs):
            """Retira el actor del envío para que el servidor lo obtenga del token y reconstruye tipos de respuesta locales."""
            argumentos = args
            opciones = kwargs
            if metodo not in PUBLIC:
                argumentos = argumentos[1:]  # La identidad se obtiene del token en el servidor, nunca del JSON del cliente.
            resultado = self.client.call(metodo, *argumentos, **opciones)
            if metodo == 'users.register_user':
                return RegistrationResult(**resultado)
            if metodo == 'access.permissions':
                # El servidor aplica los permisos de cada operación al guardar.
                return set(resultado)
            return resultado
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        invoke = invocar
        return invoke
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RemoteProxy = AdaptadorRemoto


class ServiciosRemotos:
    """Reúne los adaptadores de servicios para una PC cliente sin abrir una base local."""
    read_only = True
    connection = None

    def __init__(self, client, manager):
        """Crea un adaptador por servicio autorizado y conserva el gestor de red compartido."""
        cliente = client
        gestor = manager
        self.network = gestor
        self.client = cliente
        for nombre in ('auth', 'access', 'audit', 'users', 'requests', 'periodicos', 'recovery', 'reports'):
            setattr(self, nombre, RemoteProxy(cliente, nombre))

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        self.client.logout()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RemoteServices = ServiciosRemotos
