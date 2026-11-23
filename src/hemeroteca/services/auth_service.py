"""Acceso por documento, migración de cuentas antiguas y sesión de recuperación."""

from hemeroteca.services.base import ServicioConAcceso

import hashlib
import hmac
import sqlite3
import time

from hemeroteca.config.settings import RECOVERY_LOCK_SECONDS, RECOVERY_MAX_ATTEMPTS, ROLES
from hemeroteca.database.connection import transaction
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.audit_service import append_event, record_event
from hemeroteca.services.recovery_service import RegistrationResult, issue_recovery_code, recovery_digest, store_security_questions
from hemeroteca.utils.identity import normalize_document
from hemeroteca.utils.validaciones import validar_nombre, validar_documento_nuevo
from hemeroteca.utils.security import new_password_version, password_hash, password_matches, prepare_security_questions, validate_password
from hemeroteca.utils.timestamps import utc_now


class ServicioAutenticacion(ServicioConAcceso):
    """Gestiona ingreso, bloqueo de intentos, configuración maestra y recuperación con sesiones restringidas."""

    def obtener_preguntas_recuperacion(self, documento):
        """Devuelve las tres preguntas del titular sin exponer respuestas ni credenciales."""
        identidad = normalize_document(documento)
        clave = self._attempt_key(identidad, 'questions')
        self._check_lock(clave)
        fila = self.conn.execute('''SELECT s.question_1,s.question_2,s.question_3
            FROM user_security s JOIN users u ON u.id=s.user_id
            WHERE u.document=? AND u.active=1''', (identidad,)).fetchone()
        if fila is None:
            self._failure(clave)
            raise AccessDenied('No se pudo iniciar la recuperación. Revisa el documento y el estado de la cuenta.')
        return list(fila)

    def autenticar_con_preguntas(self, documento, respuestas):
        """Verifica las respuestas y permite únicamente el cambio de contraseña obligatorio."""
        from hemeroteca.utils.security import normalize_security_answer
        identidad = normalize_document(documento)
        clave = self._attempt_key(identidad, 'questions')
        self._check_lock(clave)
        if not isinstance(respuestas, (list, tuple)) or len(respuestas) != 3 or any(not isinstance(respuesta, str) or not 1 <= len(respuesta) <= 200 for respuesta in respuestas):
            raise ValueError('Responde las tres preguntas con un máximo de 200 caracteres por respuesta.')
        usuario = self.conn.execute('SELECT * FROM users WHERE document=? AND active=1', (identidad,)).fetchone()
        seguridad = self.conn.execute('SELECT * FROM user_security WHERE user_id=?', (usuario['id'],)).fetchone() if usuario else None
        verificaciones = [password_matches(normalize_security_answer(respuesta), seguridad[f'answer_{indice}'])
                          for indice, respuesta in enumerate(respuestas, 1)] if seguridad else [False, False, False]
        if not all(verificaciones):
            self._failure(clave)
            record_event(self.conn, 'Cuenta indicada: ' + identidad, 'Recuperación por preguntas rechazada', 'Acceso denegado')
            raise AccessDenied('No se pudo verificar la cuenta. Revisa las tres respuestas y el documento.')
        with transaction(self.conn):
            self.access.require_host_write()
            self._check_lock(clave)
            actual = self.conn.execute('SELECT * FROM users WHERE id=? AND active=1', (usuario['id'],)).fetchone()
            preguntas_actuales = self.conn.execute('SELECT * FROM user_security WHERE user_id=?', (usuario['id'],)).fetchone()
            if actual is None or actual['password_version'] != usuario['password_version'] or preguntas_actuales is None or any(preguntas_actuales[f'answer_{indice}'] != seguridad[f'answer_{indice}'] for indice in (1, 2, 3)):
                raise AccessDenied('La cuenta cambió. Inicia nuevamente la recuperación.')
            codigo = self.conn.execute('SELECT generation FROM recovery_codes WHERE user_id=?', (usuario['id'],)).fetchone()
            if codigo is None:
                issue_recovery_code(self.conn, usuario['id'])
                codigo = self.conn.execute('SELECT generation FROM recovery_codes WHERE user_id=?', (usuario['id'],)).fetchone()
            self.conn.execute('UPDATE users SET must_change_password=1,recovery_pending=1,password_version=password_version+1 WHERE id=?', (usuario['id'],))
            self.conn.execute('DELETE FROM api_sessions WHERE user_id=?', (usuario['id'],))
            self.conn.execute('DELETE FROM auth_failures WHERE identity_hash=?', (clave,))
            append_event(self.conn, f"{usuario['name']} · {identidad}", 'Acceso restringido mediante preguntas de seguridad')
            actualizado = dict(self.conn.execute('SELECT * FROM users WHERE id=?', (usuario['id'],)).fetchone())
        actualizado.update(_auth_method='recovery', _recovery_generation=codigo['generation'])
        return actualizado

    def necesita_configuracion(self):
        'Comprueba si falta la cuenta maestra para decidir el flujo del primer inicio.'
        return self.conn.execute('SELECT 1 FROM users WHERE role=? LIMIT 1', (ROLES[0],)).fetchone() is None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    needs_setup = necesita_configuracion

    def migracion_cuentas(self):
        'Lista cuentas activas antiguas que necesitan asociar un documento de identidad.'
        return self.conn.execute('SELECT id,name,role FROM users WHERE document IS NULL AND active=1 ORDER BY name').fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    migration_accounts = migracion_cuentas

    def create_maestro(self, name, identity, password, security_questions=None):
        'Configura la única cuenta maestra y emite sus credenciales de recuperación.'
        seguridad_preguntas_local = security_questions
        seguridad_preguntas = seguridad_preguntas_local
        identidad = identity
        nombre = name
        contrasena = password
        preguntas_seguridad = seguridad_preguntas
        identidad = validar_documento_nuevo(identidad)
        nombre = validar_nombre(nombre)
        validate_password(contrasena)
        nombre = nombre.strip()
        valores = prepare_security_questions(preguntas_seguridad)
        with transaction(self.conn):
            self.access.require_host_write()
            if not self.needs_setup():
                raise ValueError('El administrador maestro ya está configurado.')
            cursor_insercion = self.conn.execute('''INSERT INTO users(name,identity,document,password,role,created_at,password_version)
                VALUES(?,?,?,?,?,?,?)''', (nombre, identidad, identidad, password_hash(contrasena), ROLES[0], utc_now(), new_password_version()))
            store_security_questions(self.conn, cursor_insercion.lastrowid, valores)
            codigo = issue_recovery_code(self.conn, cursor_insercion.lastrowid)
            append_event(self.conn, f'{nombre} · {identidad}', 'Administrador maestro configurado')
            return RegistrationResult(cursor_insercion.lastrowid, codigo)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    create_master = create_maestro

    def _intento_clave(self, identity, method):
        """Deriva un identificador SHA-256 por documento y método para contar intentos sin almacenar el texto original."""
        identidad = identity
        metodo = method
        return hashlib.sha256((metodo + ':' + identidad).encode()).hexdigest()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _attempt_key = _intento_clave

    def _comprobar_bloqueo(self, key):
        """Rechaza el acceso mientras no haya vencido el bloqueo registrado para esa identidad y método."""
        clave = key
        fila = self.conn.execute('SELECT locked_until FROM auth_failures WHERE identity_hash=?', (clave,)).fetchone()
        if fila and fila[0] > int(time.time()):
            raise AccessDenied('Acceso temporalmente bloqueado. Espera quince minutos antes de reintentar.')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _check_lock = _comprobar_bloqueo

    def _fallo(self, key):
        """Incrementa intentos fallidos dentro de una transacción y activa el bloqueo al alcanzar el límite configurado."""
        clave = key
        ahora = int(time.time())
        with transaction(self.conn):
            self.access.require_host_write()
            fila = self.conn.execute('SELECT * FROM auth_failures WHERE identity_hash=?', (clave,)).fetchone()
            cantidad = (fila['failed_attempts'] if fila and not fila['locked_until'] else 0) + 1
            hasta = ahora + RECOVERY_LOCK_SECONDS if cantidad >= RECOVERY_MAX_ATTEMPTS else 0
            self.conn.execute('''INSERT INTO auth_failures(identity_hash,failed_attempts,locked_until) VALUES(?,?,?)
                ON CONFLICT(identity_hash) DO UPDATE SET failed_attempts=excluded.failed_attempts,locked_until=excluded.locked_until''', (clave, cantidad, hasta))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _failure = _fallo

    def autenticar(self, identity, password, chosen_role=None):
        'Verifica las credenciales y el bloqueo de intentos antes de iniciar sesión.'
        identidad = identity
        contrasena = password
        identidad = normalize_document(identidad)
        clave = self._attempt_key(identidad, 'password')
        self._check_lock(clave)
        usuario = self.conn.execute('SELECT * FROM users WHERE document=?', (identidad,)).fetchone()
        if not usuario or not usuario['active'] or not password_matches(contrasena, usuario['password']):
            self._failure(clave)
            record_event(self.conn, 'Cuenta indicada: ' + identidad, 'Inicio de sesión rechazado', 'Acceso denegado')
            raise AccessDenied('No se pudo iniciar sesión. Revisa documento, contraseña y estado de la cuenta.')
        if chosen_role is not None and chosen_role != usuario['role']:
            raise AccessDenied('El tipo de cuenta seleccionado no corresponde a tus credenciales.')
        with transaction(self.conn):
            self.access.require_host_write()
            self.conn.execute('DELETE FROM auth_failures WHERE identity_hash=?', (clave,))
            append_event(self.conn, f'{usuario["name"]} · {identidad}', 'Inicio de sesión')
        return dict(usuario, _auth_method='password')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    authenticate = autenticar

    def autenticar_con_codigo(self, identity, code):
        """Verifica el código vigente, invalida sesiones previas y devuelve un acceso restringido al cambio de contraseña."""
        codigo = code
        identidad = identity
        identidad = normalize_document(identidad)
        clave = self._attempt_key(identidad, 'recovery')
        self._check_lock(clave)
        usuario = self.conn.execute('SELECT * FROM users WHERE document=?', (identidad,)).fetchone()
        recuperacion = self.conn.execute('SELECT * FROM recovery_codes WHERE user_id=?', (usuario['id'],)).fetchone() if usuario else None
        if not usuario or not usuario['active'] or not recuperacion or not hmac.compare_digest(recovery_digest(codigo), recuperacion['code_hash']):
            self._failure(clave)
            record_event(self.conn, 'Cuenta indicada: ' + identidad, 'Código de recuperación rechazado', 'Acceso denegado')
            raise AccessDenied('Documento o código de recuperación incorrectos, o cuenta no disponible.')
        with transaction(self.conn):
            self.access.require_host_write()
            # La comprobación se repite dentro de la transacción para evitar una rotación concurrente.
            actual = self.conn.execute('SELECT * FROM recovery_codes WHERE user_id=?', (usuario['id'],)).fetchone()
            if not actual or not hmac.compare_digest(recovery_digest(codigo), actual['code_hash']):
                raise AccessDenied('El código ya no está vigente.')
            self.conn.execute('UPDATE users SET must_change_password=1,recovery_pending=1,password_version=password_version+1 WHERE id=?', (usuario['id'],))
            self.conn.execute('DELETE FROM api_sessions WHERE user_id=?', (usuario['id'],))
            self.conn.execute('DELETE FROM auth_failures WHERE identity_hash=?', (clave,))
            append_event(self.conn, f'{usuario["name"]} · {identidad}', 'Acceso restringido mediante código de recuperación')
            actualizado = dict(self.conn.execute('SELECT * FROM users WHERE id=?', (usuario['id'],)).fetchone())
        actualizado.update(_auth_method='recovery', _recovery_generation=actual['generation'])
        return actualizado
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    authenticate_with_code = autenticar_con_codigo

    def cambiar_contrasena(self, actor, current_password, new_password):
        'Verifica el acceso, cambia la contraseña e invalida sesiones y códigos cuando corresponde.'
        current_contrasena = current_password
        nueva_contrasena_local_local = new_password
        current_contrasena_local = current_contrasena
        nueva_contrasena_local = nueva_contrasena_local_local
        responsable = actor
        contrasena_actual = current_contrasena_local
        nueva_contrasena = nueva_contrasena_local
        validate_password(nueva_contrasena)
        codigo = None
        with self.access.authorized_write(responsable, action='Cambiar contraseña propia', allow_password_change=True, authentication=True) as actual:
            recuperacion_entrada = actual.get('_auth_method') == 'recovery'
            if not recuperacion_entrada and not password_matches(contrasena_actual, actual['password']):
                raise AccessDenied('La contraseña actual no es correcta.')
            if password_matches(nueva_contrasena, actual['password']):
                raise ValueError('Elige una contraseña distinta de la actual o temporal.')
            if actual['must_change_password'] or recuperacion_entrada:
                codigo = issue_recovery_code(self.conn, actual['id'])
            self.conn.execute('UPDATE users SET password=?,password_version=password_version+1,must_change_password=0,recovery_pending=0 WHERE id=?', (password_hash(nueva_contrasena), actual['id']))
            self.conn.execute('DELETE FROM api_sessions WHERE user_id=?', (actual['id'],))
            append_event(self.conn, self.access.actor_label(actual), 'Contraseña propia actualizada')
            actualizado = dict(self.conn.execute('SELECT * FROM users WHERE id=?', (actual['id'],)).fetchone())
        actualizado['_auth_method'] = 'password'
        if codigo:
            actualizado['_new_recovery_code'] = codigo
        return actualizado
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    change_password = cambiar_contrasena

    def verificar_maestro(self, actor, password):
        """Exige una sesión maestra vigente y verifica su contraseña para autorizar operaciones sensibles de red."""
        responsable = actor
        contrasena = password
        actual = self.access.require_access(responsable, action='Autorizar configuración de red', master=True)
        if not password_matches(contrasena, actual['password']):
            raise AccessDenied('La contraseña del administrador maestro no es correcta.')
        return True
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    verify_master = verificar_maestro

    def migrar_documento(self, account_id, current_password, document):
        """Asocia un documento a una cuenta histórica tras verificar su contraseña y vuelve a autenticarla."""
        cuenta_id_local_local = account_id
        current_contrasena = current_password
        cuenta_id_local = cuenta_id_local_local
        current_contrasena_local = current_contrasena
        documento = document
        cuenta_id = cuenta_id_local
        contrasena_actual = current_contrasena_local
        documento = normalize_document(documento)
        clave = self._attempt_key(str(cuenta_id), 'migration')
        self._check_lock(clave)
        cuenta = self.conn.execute('SELECT * FROM users WHERE id=? AND document IS NULL AND active=1', (cuenta_id,)).fetchone()
        if not cuenta or not password_matches(contrasena_actual, cuenta['password']):
            self._failure(clave)
            raise AccessDenied('No se pudo verificar la cuenta anterior.')
        with transaction(self.conn):
            self.access.require_host_write()
            actual = self.conn.execute('SELECT * FROM users WHERE id=? AND document IS NULL AND active=1', (cuenta_id,)).fetchone()
            if actual is None or actual['password_version'] != cuenta['password_version'] or actual['password'] != cuenta['password']:
                raise AccessDenied('La cuenta cambió. Inicia nuevamente la migración.')
            self.conn.execute('UPDATE users SET document=?,identity=?,password_version=password_version+1 WHERE id=? AND document IS NULL', (documento, documento, cuenta_id))
            self.conn.execute('DELETE FROM auth_failures WHERE identity_hash=?', (clave,))
            append_event(self.conn, f'{cuenta["name"]} · {documento}', 'Documento de cuenta anterior registrado')
        return self.authenticate(documento, contrasena_actual)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    migrate_document = migrar_documento
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
AuthService = ServicioAutenticacion
