"""Administración de respaldos diarios y restauración local por el maestro."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess  # nosec B404 # subprocess necesario para herramientas locales; sin shell=True
import sys
import threading
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from hemeroteca.config.settings import BASE, ROLES, WINDOWS_RESOURCES, BACKUP_WORKER, WINDOWS_POWERSHELL
from hemeroteca.database.maintenance import database_guard
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.audit_service import append_event, record_event
from hemeroteca.services.backup_archive import (MAGIC, MAX_DATABASE, derive_key, read_archive,
                                     snapshot, validated_database, write_archive)
from hemeroteca.utils.local_secrets import protect_key, unprotect_key, write_json, private_write
from hemeroteca.utils.security import new_password_version, password_matches
from hemeroteca.utils.timestamps import utc_now


def leer_configuracion(path):
    """Lee un objeto JSON de hasta 64 KiB o devuelve ajustes vacíos si aún no existe el archivo."""
    ruta = path
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    if ruta.stat().st_size > 65536:
        raise ValueError("La configuración de respaldos no es válida.")
    resultado = json.loads(ruta.read_text(encoding='utf-8'))
    if not isinstance(resultado, dict):
        raise ValueError("La configuración de respaldos no es válida.")
    return resultado
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
read_settings = leer_configuracion


def respaldo_nombre(reason):
    """Genera un nombre de respaldo con motivo, fecha, hora y un sufijo aleatorio para evitar colisiones."""
    motivo = reason
    return f'hemeroteca-{motivo}-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}.hmbackup'
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
backup_name = respaldo_nombre


def _guardar_copia(connection, settings, *, reason):
    """Obtiene una instantánea consistente, recupera la clave local y guarda el respaldo cifrado en la carpeta configurada."""
    conexion = connection
    motivo = reason
    configuracion = settings
    directorio = Path(configuracion['directory'])
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / backup_name(motivo)
    write_archive(ruta, snapshot(conexion), unprotect_key(configuracion), bytes.fromhex(configuracion['salt']), reason=motivo)
    return ruta
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
_save_copy = _guardar_copia


class ServicioRespaldos:
    """Administra copias cifradas, programación diaria y restauración exclusiva en la PC principal."""
    def __init__(self, connection, access, database, *, settings_path=None, network_path=None):
        """Conserva conexión, autorización y rutas de base, ajustes de respaldo y configuración de red."""
        red_path = network_path
        configuracion_path = settings_path
        acceso = access
        red_path_local = red_path
        configuracion_path_local = configuracion_path
        conexion = connection
        base_datos = database
        ruta_red = red_path_local
        ruta_ajustes = configuracion_path_local
        self.conn, self.access, self.database = conexion, acceso, Path(base_datos)
        self.settings_path = Path(ruta_ajustes or self.database.parent / 'backup-settings.json')
        self.network_path = Path(ruta_red or self.database.parent / 'network.json')

    def _autorizar(self, actor, password=None):
        """Exige administrador maestro y propiedad local; verifica su contraseña cuando la operación la proporciona."""
        responsable = actor
        contrasena = password
        actual = self.access.require_access(responsable, action='Administrar respaldos', master=True)
        self.access.require_host_write()
        if read_settings(self.network_path).get('mode') == 'client':
            raise AccessDenied("Los respaldos se administran presencialmente en la PC principal.")
        if contrasena is not None and not password_matches(contrasena, actual['password']):
            raise AccessDenied("La contraseña actual del administrador maestro no es correcta.")
        return actual
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _authorize = _autorizar

    def estado(self, actor):
        """Devuelve el estado público de los respaldos y errores de configuración sin exponer claves ni sal."""
        responsable = actor
        self._authorize(responsable)
        try:
            configuracion = read_settings(self.settings_path)
        except (OSError, ValueError):
            configuracion = {'last_error': 'La configuración local no se puede leer. Vuelve a configurar las copias diarias.'}
        # Nunca devuelve la clave cifrada, la sal ni la clave de cifrado local a la interfaz.
        return {nombre: configuracion.get(nombre) for nombre in ('enabled', 'directory', 'time', 'last_success',
                'last_file', 'last_daily_date', 'last_error', 'scheduler', 'scheduler_error')} | {
                    'default_directory': str(self.database.parent / 'respaldos')}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    status = estado

    def configurar(self, actor, master_password, backup_password, directory, at='18:00'):
        'Valida y guarda la configuración requerida por el servicio.'
        respaldo_contrasena_local = backup_password
        maestro_contrasena_local = master_password
        respaldo_contrasena = respaldo_contrasena_local
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        clave_respaldo = respaldo_contrasena
        directorio = directory
        contrasena_maestro = maestro_contrasena
        if not isinstance(directorio, str) or not directorio.strip() or not Path(directorio).is_absolute():
            raise ValueError("Selecciona una carpeta para guardar los respaldos.")
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', at):
            raise ValueError("Escribe la hora en formato de 24 horas, por ejemplo 18:00.")
        sal = secrets.token_bytes(16)
        clave = derive_key(clave_respaldo, sal)
        with database_guard(self.database):
            actual = self._authorize(responsable, contrasena_maestro)
            configuracion = {'version': 1, 'enabled': True, 'directory': str(Path(directorio).resolve()),
                        'time': at, 'salt': sal.hex(), **protect_key(clave), 'scheduler': 'app',
                        'last_error': '', 'scheduler_error': ''}
            ruta = _save_copy(self.conn, configuracion, reason='inicial')
            configuracion.update(last_success=utc_now(), last_file=ruta.name, last_daily_date=date.today().isoformat())
            write_json(self.settings_path, configuracion)
            record_event(self.conn, self.access.actor_label(actual), 'Respaldos diarios configurados y copia inicial creada')
            if os.name == 'nt':
                self._schedule_windows(configuracion)
                write_json(self.settings_path, configuracion)
        return self.status(responsable)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    configure = configurar

    def _programar_windows(self, settings, remove=False):
        """Crea o retira la tarea diaria de Windows; registra la alternativa de ejecución desde la aplicación si falla."""
        configuracion = settings
        task_nombre = 'Hemeroteca-Respaldo-' + hashlib.sha256(str(self.database.resolve()).encode()).hexdigest()[:16]
        arguments = [str(WINDOWS_POWERSHELL), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'RemoteSigned',
                     '-File', str(WINDOWS_RESOURCES / 'Programar_Respaldos_Windows.ps1'), '-TaskName', task_nombre,
                     '-PythonPath', sys.executable, '-WorkerPath', str(BACKUP_WORKER),
                     '-DatabasePath', str(self.database.resolve()), '-SettingsPath', str(self.settings_path.resolve()),
                     '-NetworkPath', str(self.network_path.resolve()), '-At', configuracion.get('time', '18:00')]
        if remove:
            arguments.append('-Remove')
        if getattr(sys, 'frozen', False):
            arguments.append('-EjecutableAutonomo')
        try:
            subprocess.run(arguments, check=True, capture_output=True, timeout=25,  # nosec B603 # argumentos separados sin intérprete de comandos; ejecutable del entorno o ruta local controlada
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            configuracion.update(scheduler='disabled' if remove else 'windows', scheduler_error='')
        except (OSError, subprocess.SubprocessError):
            configuracion.update(scheduler='app', scheduler_error=(
                'Windows no permitió actualizar la tarea diaria. Mientras tanto, las copias se harán '
                'con Hemeroteca abierta. Usa Reintentar programación de Windows o solicita ayuda al responsable de la PC.'))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _schedule_windows = _programar_windows

    def reintentar_programar(self, actor, master_password):
        'Reintenta registrar en Windows la tarea de respaldo previamente configurada.'
        maestro_contrasena_local = master_password
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        with database_guard(self.database):
            self._authorize(responsable, contrasena_maestro)
            configuracion = read_settings(self.settings_path)
            if not configuracion.get('enabled'):
                raise ValueError("Configura primero los respaldos diarios.")
            if os.name != 'nt':
                raise ValueError("La tarea de Windows se configura desde una computadora Windows.")
            self._schedule_windows(configuracion)
            write_json(self.settings_path, configuracion)
        return self.status(responsable)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    retry_schedule = reintentar_programar

    def desactivar(self, actor, master_password):
        """Desactiva copias diarias, retira su tarea de Windows y registra el cambio tras verificar al maestro."""
        maestro_contrasena_local = master_password
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        with database_guard(self.database):
            self._authorize(responsable, contrasena_maestro)
            configuracion = read_settings(self.settings_path)
            configuracion['enabled'] = False
            write_json(self.settings_path, configuracion)  # Un trabajador pendiente ya no puede crear copias.
            if os.name == 'nt':
                self._schedule_windows(configuracion, remove=True)
                write_json(self.settings_path, configuracion)
            record_event(self.conn, self.access.actor_label(responsable), 'Respaldos diarios desactivados')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    disable = desactivar

    def create_ahora(self, actor, master_password):
        """Verifica al maestro, genera un respaldo manual y actualiza los datos de éxito y la auditoría."""
        maestro_contrasena_local = master_password
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        with database_guard(self.database):
            self._authorize(responsable, contrasena_maestro)
            configuracion = read_settings(self.settings_path)
            if not configuracion.get('key'):
                raise ValueError("Configura primero la carpeta y la clave de los respaldos.")
            ruta = _save_copy(self.conn, configuracion, reason='manual')
            configuracion.update(last_success=utc_now(), last_file=ruta.name, last_error='')
            write_json(self.settings_path, configuracion)
            record_event(self.conn, self.access.actor_label(responsable), 'Respaldo manual creado: ' + ruta.name)
            return str(ruta)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    create_now = create_ahora

    def listar_respaldos(self, actor):
        """Lista archivos hmbackup de las carpetas conocidas ordenados por modificación, sin descifrarlos."""
        responsable = actor
        self._authorize(responsable)
        try:
            configuracion = read_settings(self.settings_path)
        except (OSError, ValueError):
            configuracion = {}
        directories = {self.database.parent / 'respaldos'}
        if configuracion.get('directory'):
            directories.add(Path(configuracion['directory']))
        resultado = []
        for directorio in directories:
            if directorio.exists():
                for ruta in directorio.glob('*.hmbackup'):
                    if ruta.is_file():
                        info = ruta.stat()
                        resultado.append({'path': str(ruta.resolve()), 'name': ruta.name,
                                       'size': info.st_size, 'modified': info.st_mtime})
        return sorted(resultado, key=lambda row: row['modified'], reverse=True)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    list_backups = listar_respaldos

    def exportar(self, actor, source, destination):
        """Comprueba que el origen sea un respaldo conocido y lo copia al destino elegido por el maestro."""
        responsable = actor
        destino = destination
        origen = source
        self._authorize(responsable)
        sources = {elemento['path'] for elemento in self.list_backups(responsable)}
        if str(Path(origen).resolve()) not in sources:
            raise ValueError("Selecciona uno de los respaldos disponibles en la lista.")
        destino = Path(destino)
        if destino.suffix.lower() != '.hmbackup':
            raise ValueError("El archivo debe conservar la extensión .hmbackup.")
        with Path(origen).open('rb') as flujo:
            contenido = flujo.read(MAX_DATABASE + 8192)
            if flujo.read(1) or not contenido.startswith(MAGIC):
                raise ValueError("El archivo seleccionado no es un respaldo compatible.")
        private_write(destino, contenido)
        record_event(self.conn, self.access.actor_label(responsable), 'Respaldo copiado para llevar: ' + Path(origen).name)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    export = exportar

    def revision(self, actor, path, backup_password):
        """Autoriza al maestro y usa la clave del respaldo para descifrarlo y devolver metadatos y conteos de su base validada."""
        respaldo_contrasena_local = backup_password
        respaldo_contrasena = respaldo_contrasena_local
        responsable = actor
        clave_respaldo = respaldo_contrasena
        ruta = path
        self._authorize(responsable)
        cabecera, base_datos = read_archive(ruta, clave_respaldo)
        with closing(validated_database(base_datos)) as candidato:
            cabecera['counts'] = {tabla_datos: candidato.execute(f'SELECT count(*) FROM {tabla_datos}').fetchone()[0]  # nosec B608 # SQL estructural interno con tablas/columnas o fragmentos constantes; valores del usuario enlazados con parámetros
                                for tabla_datos in ('issues', 'users', 'absent_dates', 'audit')}
            cabecera['master_document'] = candidato.execute('SELECT document FROM users WHERE role=? AND active=1', (ROLES[0],)).fetchone()[0]
        return cabecera
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    preview = revision

    def restaurar(self, actor, path, backup_password, master_password, expected_digest):
        'Restaura datos validados con exclusión de operaciones y una copia previa.'
        respaldo_contrasena_local = backup_password
        maestro_contrasena_local = master_password
        respaldo_contrasena = respaldo_contrasena_local
        maestro_contrasena = maestro_contrasena_local
        responsable = actor
        clave_respaldo = respaldo_contrasena
        contrasena_maestro = maestro_contrasena
        ruta = path
        with database_guard(self.database):
            actual = self._authorize(responsable, contrasena_maestro)
            etiqueta = self.access.actor_label(actual)
            cabecera, base_datos = read_archive(ruta, clave_respaldo)
            if cabecera['archive_sha256'] != expected_digest:
                raise ValueError("El archivo cambió desde la revisión. Vuelve a seleccionarlo.")
            with closing(validated_database(base_datos)) as candidato:
                # La copia de seguridad anterior a restaurar usa la misma clave que acabas de introducir.
                before = self.database.parent / 'respaldos' / backup_name('antes-de-restaurar')
                sal = secrets.token_bytes(16)
                write_archive(before, snapshot(self.conn), derive_key(clave_respaldo, sal), sal, reason='antes-de-restaurar')
                with candidato:
                    for fila in candidato.execute('SELECT id FROM users').fetchall():
                        candidato.execute('UPDATE users SET password_version=?,recovery_pending=0 WHERE id=?', (new_password_version(), fila[0]))
                    nodo = self.access.node_id or read_settings(self.network_path).get('node_id')
                    if nodo:
                        candidato.execute("INSERT INTO system_settings(key,value) VALUES('active_host_id',?)", (nodo,))
                    # Las sesiones, equipos y traslados no se importan de otra máquina o del pasado.
                    append_event(candidato, etiqueta, 'Base restaurada desde respaldo validado; sesiones cerradas y computadoras retiradas')
                # SQLite confirma la copia como una sola transacción de destino. No se renombra una base abierta.
                candidato.backup(self.conn)
            self.conn.execute('PRAGMA foreign_keys=ON')
            advertencia = ''
            try:
                configuracion = read_settings(self.settings_path)
                if configuracion:
                    configuracion.update(last_daily_date='', last_error='')
                    write_json(self.settings_path, configuracion)
            except (OSError, ValueError):
                advertencia = 'La base ya se restauró. Configura nuevamente las copias diarias porque no se pudo actualizar su configuración local.'
            return {'before': str(before), 'created_at': cabecera['created_at'], 'warning': advertencia}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    restore = restaurar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
BackupService = ServicioRespaldos


def ejecutar_diaria_respaldo(database, settings_path, network_path):
    """Punto de entrada sin sesión ni GUI; solo actúa si el maestro lo configuró."""
    red_path = network_path
    configuracion_path = settings_path
    red_path_local = red_path
    configuracion_path_local = configuracion_path
    base_datos = database
    ruta_red = red_path_local
    ruta_ajustes = configuracion_path_local
    base_datos, ruta_ajustes = Path(base_datos), Path(ruta_ajustes)
    if not base_datos.is_file() or not read_settings(ruta_ajustes).get('enabled'):
        return False
    with database_guard(base_datos):
        configuracion, red = read_settings(ruta_ajustes), read_settings(ruta_red)
        if not configuracion.get('enabled') or red.get('mode') == 'client':
            return False
        ahora = datetime.now()
        try:
            hora, minuto = map(int, configuracion['time'].split(':'))
            destinatario = ahora.date() if (ahora.hour, ahora.minute) >= (hora, minuto) else ahora.date() - timedelta(days=1)
            if configuracion.get('last_daily_date', '') >= destinatario.isoformat():
                return False
            with closing(sqlite3.connect(base_datos.resolve().as_uri() + '?mode=rw', uri=True, timeout=10)) as conexion:
                propietario = conexion.execute("SELECT value FROM system_settings WHERE key='active_host_id'").fetchone()
                if propietario and propietario[0] != red.get('node_id'):
                    return False
                if not conexion.execute('SELECT 1 FROM users WHERE role=? AND active=1', (ROLES[0],)).fetchone():
                    return False
                ruta = _save_copy(conexion, configuracion, reason='diario')
                record_event(conexion, 'Sistema de respaldos', 'Respaldo diario creado: ' + ruta.name)
            # Registrar el día cubierto, no el día de ejecución: recuperar ayer por
            # la mañana no debe omitir la copia de hoy cuando llegue su horario.
            configuracion.update(last_success=utc_now(), last_file=ruta.name, last_daily_date=destinatario.isoformat(), last_error='')
            write_json(ruta_ajustes, configuracion)
            return True
        except (OSError, ValueError, KeyError, sqlite3.Error) as excepcion:
            configuracion.update(last_error='No se creó la copia diaria. Revisa la carpeta, el espacio disponible y la configuración de la clave.',
                            last_attempt=utc_now())
            write_json(ruta_ajustes, configuracion)
            raise ValueError(configuracion['last_error']) from excepcion
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
run_daily_backup = ejecutar_diaria_respaldo


class ProgramadorRespaldos:
    """Respaldo pendiente al abrir y revisión cada minuto mientras el programa está abierto."""
    def __init__(self, database, network_path):
        """Conserva las rutas locales y prepara un hilo de copias diarias con su señal de detención."""
        red_path = network_path
        red_path_local = red_path
        base_datos = database
        ruta_red = red_path_local
        self.database, self.network_path = Path(base_datos), Path(ruta_red)
        self.settings_path = self.database.parent / 'backup-settings.json'
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name='hemeroteca-respaldos')

    def iniciar(self):
        'Inicia el trabajador o servidor y conserva su referencia para el cierre.'
        self.thread.start()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    start = iniciar

    def _ejecutar(self):
        'Ejecuta el ciclo de trabajo hasta recibir la señal de cierre.'
        while not self.stopped.is_set():
            try:
                run_daily_backup(self.database, self.settings_path, self.network_path)
            except (OSError, ValueError, sqlite3.Error):
                pass  # El estado visible del maestro conserva el error; reintenta en un minuto.
            self.stopped.wait(60)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _run = _ejecutar

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        self.stopped.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
BackupScheduler = ProgramadorRespaldos
