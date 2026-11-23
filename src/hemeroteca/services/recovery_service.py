"""Preguntas inmutables y códigos de recuperación aleatorios de un solo ciclo."""

from hemeroteca.services.base import ServicioConAcceso

import hashlib
import secrets
import sqlite3
from typing import NamedTuple

from hemeroteca.config.settings import ROLES
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.audit_service import append_event
from hemeroteca.utils.security import password_matches, prepare_security_questions
from hemeroteca.utils.timestamps import utc_now

ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # pragma: allowlist secret -- alfabeto público, no es una clave


class ResultadoRegistro(NamedTuple):
    """Transporta el identificador de la cuenta y el código de recuperación recién emitido, sin persistirlo en claro."""
    user_id: int
    recovery_code: str
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RegistrationResult = ResultadoRegistro


def recuperacion_digest(code):
    """Normaliza el código de recuperación y devuelve el SHA-256 usado para verificarlo sin guardar su texto."""
    codigo = code
    normalizado = ''.join(str(codigo).upper().split()).replace('-', '')
    return hashlib.sha256(normalizado.encode('ascii', errors='replace')).hexdigest()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
recovery_digest = recuperacion_digest


def emitir_codigo_recuperacion(connection, user_id):
    """Se llama dentro de la transacción; nunca persiste el código en claro."""
    usuario_id_local = user_id
    usuario_id = usuario_id_local
    conexion = connection
    identificador_usuario = usuario_id
    fila = conexion.execute('SELECT generation FROM recovery_codes WHERE user_id=?', (identificador_usuario,)).fetchone()
    generation = fila[0] + 1 if fila else 1
    for _ in range(10):
        grupos = [''.join(secrets.choice(ALPHABET) for _ in range(5)) for _ in range(6)]
        codigo = 'HMR-' + '-'.join(grupos)
        resumen_criptografico = recovery_digest(codigo)
        if conexion.execute('SELECT 1 FROM recovery_code_history WHERE code_hash=?', (resumen_criptografico,)).fetchone():
            continue
        ahora = utc_now()
        conexion.execute('INSERT INTO recovery_code_history(code_hash,user_id,generation,created_at) VALUES(?,?,?,?)', (resumen_criptografico, identificador_usuario, generation, ahora))
        conexion.execute('''INSERT INTO recovery_codes(user_id,code_hash,generation,created_at) VALUES(?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash,generation=excluded.generation,
            created_at=excluded.created_at,failed_attempts=0,locked_until=0''', (identificador_usuario, resumen_criptografico, generation, ahora))
        conexion.execute("DELETE FROM api_sessions WHERE user_id=? AND method='recovery'", (identificador_usuario,))
        return codigo
    raise RuntimeError('No se pudo generar un código único. Vuelve a intentarlo.')
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
issue_recovery_code = emitir_codigo_recuperacion


def almacenar_seguridad_preguntas(connection, user_id, values):
    """Inserta preguntas y respuestas ya preparadas y rechaza reemplazar una configuración existente."""
    usuario_id_local = user_id
    usuario_id = usuario_id_local
    conexion = connection
    identificador_usuario = usuario_id
    valores = values
    if conexion.execute('SELECT 1 FROM user_security WHERE user_id=?', (identificador_usuario,)).fetchone():
        raise ValueError('Las preguntas y respuestas registradas no se pueden modificar.')
    conexion.execute('''INSERT INTO user_security(user_id,question_1,answer_1,question_2,answer_2,question_3,answer_3)
        VALUES(?,?,?,?,?,?,?)''', (identificador_usuario,) + valores)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
store_security_questions = almacenar_seguridad_preguntas


class ServicioRecuperacion(ServicioConAcceso):
    """Configura preguntas inmutables y emite o renueva códigos con autorización y auditoría."""

    def renovar_codigo_propio(self, actor, contrasena_actual):
        """Emite un código nuevo al titular autenticado sin cambiar su contraseña."""
        with self.access.authorized_write(actor, action='Renovar código de recuperación propio', authentication=True) as usuario:
            if not password_matches(contrasena_actual, usuario['password']):
                raise AccessDenied('La contraseña actual no es correcta.')
            codigo = issue_recovery_code(self.conn, usuario['id'])
            append_event(self.conn, self.access.actor_label(usuario), 'Código propio de recuperación renovado')
            return codigo

    def necesita_preguntas(self, actor):
        'Comprueba si la cuenta todavía debe configurar sus preguntas obligatorias.'
        responsable = actor
        actual = self.access.current_user(responsable)
        return actual is not None and self.conn.execute('SELECT 1 FROM user_security WHERE user_id=?', (actual['id'],)).fetchone() is None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    needs_configuration = necesita_preguntas

    def necesita_codigo(self, actor):
        'Comprueba si falta emitir el código de recuperación de la cuenta.'
        responsable = actor
        actual = self.access.current_user(responsable)
        return actual is not None and self.conn.execute('SELECT 1 FROM recovery_codes WHERE user_id=?', (actual['id'],)).fetchone() is None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    needs_code = necesita_codigo

    def configuradas_preguntas(self, actor):
        'Devuelve únicamente las preguntas elegidas; nunca expone respuestas guardadas.'
        responsable = actor
        actual = self.access.require_access(responsable, action='Consultar preguntas propias')
        fila = self.conn.execute('SELECT question_1,question_2,question_3 FROM user_security WHERE user_id=?', (actual['id'],)).fetchone()
        return tuple(fila) if fila else ()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    configured_questions = configuradas_preguntas

    def configurar_preguntas(self, actor, current_password, questions):
        """Valida y prepara hashes de respuestas, verifica la contraseña e inserta la configuración de seguridad una sola vez."""
        current_contrasena = current_password
        current_contrasena_local = current_contrasena
        responsable = actor
        contrasena_actual = current_contrasena_local
        preguntas = questions
        valores = prepare_security_questions(preguntas)
        with self.access.authorized_write(responsable, action='Registrar preguntas de seguridad', authentication=True) as actual:
            if not password_matches(contrasena_actual, actual['password']):
                raise AccessDenied('La contraseña actual no es correcta.')
            store_security_questions(self.conn, actual['id'], valores)
            append_event(self.conn, self.access.actor_label(actual), 'Preguntas de seguridad registradas')
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    configure_questions = configurar_preguntas

    def inscribir_codigo(self, actor):
        """Emite el primer código de una cuenta que aún no tiene uno y registra la operación en auditoría."""
        responsable = actor
        with self.access.authorized_write(responsable, action='Generar código inicial de recuperación', authentication=True) as actual:
            if not self.needs_code(actual):
                raise ValueError('Tu código ya fue emitido. No puede volver a mostrarse.')
            codigo = issue_recovery_code(self.conn, actual['id'])
            append_event(self.conn, self.access.actor_label(actual), 'Código inicial de recuperación emitido')
            return codigo
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    enroll_code = inscribir_codigo

    def regenerar_codigo(self, actor, user_id, master_password, expected_version=None):
        """Permite al maestro renovar el código de otra cuenta tras verificar contraseña y versión esperada."""
        maestro_contrasena_local = master_password
        usuario_id_local = user_id
        maestro_contrasena = maestro_contrasena_local
        usuario_id = usuario_id_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        identificador_usuario = usuario_id
        with self.access.authorized_write(responsable, action=f'Regenerar código de cuenta #{identificador_usuario}', master=True) as actual:
            if not password_matches(contrasena_maestro, actual['password']):
                raise AccessDenied('La contraseña actual del administrador maestro no es correcta.')
            destinatario = self.conn.execute('SELECT * FROM users WHERE id=?', (identificador_usuario,)).fetchone()
            if destinatario is None:
                raise ValueError('La cuenta no existe.')
            if expected_version is not None and destinatario['password_version'] != expected_version:
                raise ValueError('La cuenta cambió. Actualiza la lista.')
            codigo = issue_recovery_code(self.conn, identificador_usuario)
            append_event(self.conn, self.access.actor_label(actual), f'Código de recuperación regenerado: {destinatario["document"] or "Documento pendiente"}')
            return codigo
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    regenerate_code = regenerar_codigo

    def preguntas_for_recuperacion(self, identity):
        """Mantiene el contrato anterior y consulta preguntas sin revelar respuestas."""
        from hemeroteca.services.auth_service import AuthService
        return AuthService(self.conn, self.access).obtener_preguntas_recuperacion(identity)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    questions_for_recovery = preguntas_for_recuperacion

    def recuperar_contrasena(self, identity, answers, new_password=None):
        """Conserva la API anterior para recuperar por preguntas y emitir credenciales nuevas."""
        from hemeroteca.services.auth_service import AuthService
        from hemeroteca.utils.security import validate_password
        if new_password is not None:
            validate_password(new_password)
        autenticacion = AuthService(self.conn, self.access)
        usuario = autenticacion.autenticar_con_preguntas(identity, answers)
        return autenticacion.change_password(usuario, '', new_password) if new_password is not None else usuario
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    recover_password = recuperar_contrasena
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RecoveryService = ServicioRecuperacion
