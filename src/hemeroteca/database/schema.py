"""Esquema y migraciones: perfiles con permisos otorgados por el maestro (versión 7)."""

import sqlite3
from datetime import datetime, timezone
from hemeroteca.config.settings import ISSUE_STATUSES
from hemeroteca.utils.identity import normalize_document

SCHEMA_VERSION = 7


def inicializar_esquema(connection: sqlite3.Connection) -> None:
    'Crea o migra tablas, revisiones, índices y restricciones sin crear cuentas predeterminadas.'
    conexion = connection
    old_version = conexion.execute('PRAGMA user_version').fetchone()[0]
    if old_version > SCHEMA_VERSION:
        raise ValueError('La base pertenece a una versión más reciente. Usa una versión compatible de Hemeroteca.')
    conexion.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, identity TEXT NOT NULL UNIQUE,
      password TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, password_version INTEGER NOT NULL DEFAULT 0,
      must_change_password INTEGER NOT NULL DEFAULT 0, document TEXT,
      recovery_pending INTEGER NOT NULL DEFAULT 0,
      managed_permissions INTEGER NOT NULL DEFAULT 0 CHECK(managed_permissions IN (0,1)));
    CREATE TABLE IF NOT EXISTS user_security(
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      question_1 TEXT NOT NULL, answer_1 TEXT NOT NULL,
      question_2 TEXT NOT NULL, answer_2 TEXT NOT NULL,
      question_3 TEXT NOT NULL, answer_3 TEXT NOT NULL,
      failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS grants(
      user_id INTEGER NOT NULL REFERENCES users(id), permission TEXT NOT NULL,
      PRIMARY KEY(user_id, permission));
    CREATE TABLE IF NOT EXISTS requests(
      id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
      permission TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pendiente',
      created_at TEXT NOT NULL, decided_by TEXT, decided_at TEXT, response TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS issues(
      id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL, edition TEXT,
      year INTEGER NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
      number TEXT, shelf TEXT, drawer TEXT, status TEXT NOT NULL DEFAULT 'Disponible',
      deleted INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
      UNIQUE(title, year, month, day, edition, number));
    CREATE TABLE IF NOT EXISTS absent_dates(
      id INTEGER PRIMARY KEY, title TEXT NOT NULL, kind TEXT NOT NULL,
      year INTEGER NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
      note TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
      UNIQUE(title, year, month, day));
    CREATE TABLE IF NOT EXISTS audit(
      id INTEGER PRIMARY KEY, at TEXT NOT NULL, user TEXT NOT NULL, action TEXT NOT NULL, result TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS recovery_codes(
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      code_hash TEXT NOT NULL UNIQUE, generation INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0,
      locked_until INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS recovery_code_history(
      code_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      generation INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS auth_failures(
      identity_hash TEXT PRIMARY KEY, failed_attempts INTEGER NOT NULL DEFAULT 0,
      locked_until INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS system_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS authorized_devices(
      device_id TEXT PRIMARY KEY, public_key TEXT NOT NULL UNIQUE, node_id TEXT NOT NULL,
      name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
      approved_by TEXT NOT NULL, approved_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS device_nonces(
      device_id TEXT NOT NULL REFERENCES authorized_devices(device_id) ON DELETE CASCADE,
      nonce TEXT NOT NULL, expires_at INTEGER NOT NULL,
      PRIMARY KEY(device_id,nonce));
    CREATE TABLE IF NOT EXISTS api_sessions(
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      password_version INTEGER NOT NULL, method TEXT NOT NULL,
      recovery_generation INTEGER, expires_at INTEGER NOT NULL, device_id TEXT NOT NULL DEFAULT '');
    ''')
    conexion.execute('BEGIN IMMEDIATE')
    try:
        usuario_columns = {fila_local[1] for fila_local in conexion.execute('PRAGMA table_info(users)')}
        for columna, definition in (
            ('password_version', 'INTEGER NOT NULL DEFAULT 0'),
            ('must_change_password', 'INTEGER NOT NULL DEFAULT 0'),
            ('document', 'TEXT'), ('recovery_pending', 'INTEGER NOT NULL DEFAULT 0'),
            ('managed_permissions', 'INTEGER NOT NULL DEFAULT 0 CHECK(managed_permissions IN (0,1))'),
        ):
            if columna not in usuario_columns:
                conexion.execute(f'ALTER TABLE users ADD COLUMN {columna} {definition}')
        sesion_columns = {fila_local[1] for fila_local in conexion.execute('PRAGMA table_info(api_sessions)')}
        if 'device_id' not in sesion_columns:
            conexion.execute("ALTER TABLE api_sessions ADD COLUMN device_id TEXT NOT NULL DEFAULT ''")
        if old_version < 3:
            conexion.execute('DELETE FROM api_sessions')
        conexion.execute('CREATE INDEX IF NOT EXISTS device_nonces_expiration ON device_nonces(expires_at)')
        columnas = {fila_local[1] for fila_local in conexion.execute('PRAGMA table_info(requests)')}
        if 'response' not in columnas:
            conexion.execute("ALTER TABLE requests ADD COLUMN response TEXT NOT NULL DEFAULT ''")
        if conexion.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='master_recovery'").fetchone():
            conexion.execute('''INSERT OR IGNORE INTO user_security
              (user_id,question_1,answer_1,question_2,answer_2,question_3,answer_3,failed_attempts,locked_until)
              SELECT user_id,question_1,answer_1,question_2,answer_2,question_3,answer_3,failed_attempts,locked_until FROM master_recovery''')
            conexion.execute('DROP TABLE master_recovery')
        conexion.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_document_unique ON users(document) WHERE document IS NOT NULL')
        if old_version < 2:
            for identificador_usuario, identidad in conexion.execute('SELECT id,identity FROM users WHERE document IS NULL').fetchall():
                try:
                    documento = normalize_document(identidad)
                except ValueError:
                    continue
                if not conexion.execute('SELECT 1 FROM users WHERE document=?', (documento,)).fetchone():
                    try:
                        conexion.execute('UPDATE users SET document=?,identity=? WHERE id=?', (documento, documento, identificador_usuario))
                    except sqlite3.IntegrityError:
                        pass  # Identificador antiguo duplicado: se completa desde la pantalla de migración.
            for tabla_datos in ('issues', 'absent_dates'):
                for registro_id, valor in conexion.execute(f'SELECT id,created_at FROM {tabla_datos}').fetchall():  # nosec B608 # SQL estructural interno con tablas/columnas o fragmentos constantes; valores del usuario enlazados con parámetros
                    try:
                        parsed = datetime.fromisoformat(valor)
                        valor = parsed.astimezone(timezone.utc).isoformat(timespec='seconds')
                    except (TypeError, ValueError):
                        continue
                    conexion.execute(f'UPDATE {tabla_datos} SET created_at=? WHERE id=?', (valor, registro_id))  # nosec B608 # SQL estructural interno con tablas/columnas o fragmentos constantes; valores del usuario enlazados con parámetros
        columnas_ejemplares = {fila[1] for fila in conexion.execute('PRAGMA table_info(issues)')}
        if 'revision' not in columnas_ejemplares:
            conexion.execute('ALTER TABLE issues ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
        # Metadatos opcionales: los formularios existentes conservan su contrato.
        for columna, definicion in (('section', 'TEXT'), ('page_count', 'INTEGER'), ('physical_condition', 'TEXT')):
            if columna not in columnas_ejemplares:
                conexion.execute(f'ALTER TABLE issues ADD COLUMN {columna} {definicion}')
        conexion.execute('CREATE INDEX IF NOT EXISTS issues_active_date ON issues(year,month,day,id DESC) WHERE deleted=0')
        conexion.execute('CREATE INDEX IF NOT EXISTS issues_active_id ON issues(id DESC) WHERE deleted=0')
        conexion.execute('CREATE INDEX IF NOT EXISTS issues_recent_dates ON issues(datetime(created_at),id DESC) WHERE deleted=0')
        conexion.execute('CREATE INDEX IF NOT EXISTS requests_user_status ON requests(user_id,status,id DESC)')
        conexion.execute('CREATE INDEX IF NOT EXISTS issues_created_at ON issues(created_at)')
        conexion.execute('CREATE INDEX IF NOT EXISTS api_sessions_expiration ON api_sessions(expires_at)')
        conexion.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')
        conexion.commit()
    except BaseException:
        conexion.rollback()
        raise
    required = ('title', 'kind', 'edition', 'number', 'status')
    condition = ' OR '.join(f"trim(coalesce(NEW.{campo},''))=''" for campo in required)
    condition += " OR (trim(coalesce(NEW.shelf,''))='' AND trim(coalesce(NEW.drawer,''))='')"
    condition += " OR coalesce(NEW.shelf,'') GLOB '*[^0-9]*' OR coalesce(NEW.drawer,'') GLOB '*[^0-9]*' OR NEW.number GLOB '*[^0-9]*'"
    states = ','.join("'" + valor.replace("'", "''") + "'" for valor in ISSUE_STATUSES)
    conexion.executescript(f'''
    DROP TRIGGER IF EXISTS issues_required_insert;
    DROP TRIGGER IF EXISTS issues_required_update;
    CREATE INDEX IF NOT EXISTS audit_action_id ON audit(action,id DESC);
    CREATE TRIGGER issues_required_insert BEFORE INSERT ON issues
    WHEN {condition} OR NEW.status NOT IN ({states})
    BEGIN SELECT RAISE(ABORT, 'Completa todos los campos y selecciona un estado válido.'); END;
    CREATE TRIGGER issues_required_update BEFORE UPDATE OF title,kind,edition,number,shelf,drawer,status ON issues
    WHEN {condition} OR NEW.status NOT IN ({states})
    BEGIN SELECT RAISE(ABORT, 'Completa todos los campos y selecciona un estado válido.'); END;
    ''')
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
initialize_schema = inicializar_esquema
