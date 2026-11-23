"""Formato portable .hmbackup: SQLite cifrado y metadatos autenticados con AES-GCM."""

import hashlib
import json
import secrets
import sqlite3
import struct
from contextlib import closing
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from hemeroteca.database.schema import SCHEMA_VERSION, initialize_schema
from hemeroteca.utils.local_secrets import private_write
from hemeroteca.utils.timestamps import utc_now

MAGIC = b'HEMEROTECA-BACKUP\x01\r\n'
MAX_DATABASE = 256 * 1024 * 1024
MAX_HEADER = 4096
PERSISTENT_TABLES = ('users', 'user_security', 'grants', 'requests', 'issues', 'absent_dates',
                     'audit', 'recovery_codes', 'recovery_code_history')
SUPPORTED_SCHEMAS = (3, 4, 5, 6, SCHEMA_VERSION)


def derivar_clave(password, salt):
    'Deriva una clave de cifrado de respaldo mediante scrypt con sal independiente.'
    contrasena = password
    sal = salt
    if not isinstance(contrasena, str) or not 12 <= len(contrasena) <= 256 or not contrasena.strip():
        raise ValueError("Usa una clave de respaldo de 12 a 256 caracteres. Guárdala fuera de la computadora.")
    return Scrypt(salt=sal, length=32, n=2**17, r=8, p=1).derive(contrasena.encode('utf-8'))
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
derive_key = derivar_clave


def crear_instantanea(connection):
    'Copia un estado consistente de SQLite a una representación transportable.'
    conexion = connection
    if conexion.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
        raise ValueError("Abre la aplicación actualizada para preparar la base antes de generar respaldos.")
    tamano_pagina = conexion.execute('PRAGMA page_size').fetchone()[0]
    with closing(sqlite3.connect(':memory:')) as copy:
        def progreso(status, remaining, total):
            """Interrumpe la instantánea SQLite si su tamaño calculado supera el máximo permitido para respaldos."""
            estado = status
            if total * tamano_pagina > MAX_DATABASE:
                raise ValueError("El respaldo admite bases de hasta 256 MiB.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        progreso_local = progreso
        conexion.backup(copy, pages=256, progress=progreso_local)
        resultado = copy.serialize()
    if len(resultado) > MAX_DATABASE:
        raise ValueError("El respaldo admite bases de hasta 256 MiB.")
    return resultado
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
snapshot = crear_instantanea


def escritura_archivo(path, database, key, salt, *, reason='manual'):
    """Crea un archivo hmbackup con cabecera autenticada y base cifrada mediante AES-256-GCM."""
    base_datos = database
    clave = key
    ruta = path
    motivo = reason
    sal = salt
    ruta = Path(ruta)
    if ruta.suffix.lower() != '.hmbackup':
        raise ValueError("Guarda el archivo con la extensión .hmbackup.")
    if len(base_datos) > MAX_DATABASE:
        raise ValueError("El respaldo admite bases de hasta 256 MiB.")
    if not isinstance(clave, bytes) or len(clave) != 32:
        raise ValueError("La clave de cifrado debe contener 32 bytes para AES-256-GCM.")
    if not isinstance(sal, bytes) or len(sal) != 16:
        raise ValueError("La sal del respaldo debe contener 16 bytes.")
    nonce = secrets.token_bytes(12)
    cabecera = {'format': 1, 'application': 'Hemeroteca', 'schema': SCHEMA_VERSION,
              'created_at': utc_now(), 'reason': motivo, 'cipher': 'AES-256-GCM',
              'kdf': 'scrypt-131072-8-1', 'salt': sal.hex(), 'nonce': nonce.hex(),
              'size': len(base_datos), 'sha256': hashlib.sha256(base_datos).hexdigest()}
    encoded = json.dumps(cabecera, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if len(encoded) > MAX_HEADER:
        raise ValueError("La cabecera del respaldo supera el tamaño permitido.")
    prefix = MAGIC + struct.pack('>I', len(encoded)) + encoded
    private_write(ruta, prefix + AESGCM(clave).encrypt(nonce, base_datos, prefix))
    return cabecera
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
write_archive = escritura_archivo


def leer_archivo(path, password):
    'Valida formato, tamaño e integridad del respaldo antes de devolver sus datos descifrados.'
    contrasena = password
    ruta = path
    ruta = Path(ruta)
    maximo = MAX_DATABASE + MAX_HEADER + len(MAGIC) + 20
    with ruta.open('rb') as flujo:
        contenido = flujo.read(maximo + 1)
    if len(contenido) > maximo or not contenido.startswith(MAGIC):
        raise ValueError("El archivo no es un respaldo válido de Hemeroteca o supera 256 MiB.")
    try:
        tamano = struct.unpack('>I', contenido[len(MAGIC):len(MAGIC) + 4])[0]
        if not 1 <= tamano <= MAX_HEADER:
            raise ValueError
        fin = len(MAGIC) + 4 + tamano
        cabecera = json.loads(contenido[len(MAGIC) + 4:fin])
        if not isinstance(cabecera, dict) or cabecera.get('format') != 1 or cabecera.get('application') != 'Hemeroteca':
            raise ValueError
        if cabecera.get('cipher') != 'AES-256-GCM' or cabecera.get('kdf') != 'scrypt-131072-8-1':
            raise ValueError
        sal, nonce = bytes.fromhex(cabecera['salt']), bytes.fromhex(cabecera['nonce'])
        if len(sal) != 16 or len(nonce) != 12:
            raise ValueError
        clave = derive_key(contrasena, sal)
        base_datos = AESGCM(clave).decrypt(nonce, contenido[fin:], contenido[:fin])
    except InvalidTag as excepcion:
        raise ValueError("La clave no es correcta o el respaldo fue alterado. No se modificó la base de datos.") from excepcion
    except (KeyError, TypeError, ValueError, struct.error, UnicodeError) as excepcion:
        raise ValueError("No se pudo abrir el respaldo. Revisa la clave y que el archivo esté completo.") from excepcion
    if cabecera.get('schema') not in SUPPORTED_SCHEMAS:
        raise ValueError("Este respaldo corresponde a otra versión del esquema. Usa una versión compatible de Hemeroteca.")
    if cabecera.get('size') != len(base_datos) or cabecera.get('sha256') != hashlib.sha256(base_datos).hexdigest() or not base_datos.startswith(b'SQLite format 3\x00'):
        raise ValueError("La integridad del respaldo no es válida. No se modificó la base de datos.")
    cabecera['archive_sha256'] = hashlib.sha256(contenido).hexdigest()
    return cabecera, base_datos
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
read_archive = leer_archivo


def validada_base(content):
    """Reconstruye solo tablas conocidas; nunca ejecuta SQL ni disparadores del archivo."""
    contenido = content
    origen = sqlite3.connect(':memory:')
    try:
        clean = sqlite3.connect(':memory:')
    except BaseException:
        origen.close()
        raise
    try:
        origen.deserialize(contenido)
        origen.execute('PRAGMA trusted_schema=OFF')
        source_version = origen.execute('PRAGMA user_version').fetchone()[0]
        if source_version not in SUPPORTED_SCHEMAS:
            raise ValueError("La versión interna del respaldo no es compatible.")
        initialize_schema(clean)
        esperado = {registro_breve[0] for registro_breve in clean.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        actual = {registro_breve[0] for registro_breve in origen.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if actual != esperado or origen.execute("SELECT 1 FROM sqlite_master WHERE type='view' OR lower(sql) LIKE '%create virtual table%' LIMIT 1").fetchone():
            raise ValueError("El respaldo contiene un esquema inesperado.")
        for tabla_datos in sorted(esperado):
            # Los nombres provienen de nuestro esquema; nunca del archivo o de la interfaz.
            columnas = [registro_breve[1] for registro_breve in clean.execute(f'PRAGMA table_info({tabla_datos})')]
            if source_version == 3 and tabla_datos == 'users':
                columnas.remove('managed_permissions')
            if source_version < 5 and tabla_datos == 'issues':
                columnas.remove('revision')
            source_columns = [registro_breve[1] for registro_breve in origen.execute(f'PRAGMA table_info({tabla_datos})')]
            if len(columnas) != len(source_columns) or set(columnas) != set(source_columns):
                raise ValueError("Las columnas del respaldo no son compatibles.")
        if origen.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError("La base contenida en el respaldo está dañada.")
        # Admite registros antiguos incompletos, igual que la migración original.
        clean.execute('DROP TRIGGER IF EXISTS issues_required_insert')
        clean.execute('DROP TRIGGER IF EXISTS issues_required_update')
        with clean:
            for tabla_datos in PERSISTENT_TABLES:
                columnas = [registro_breve[1] for registro_breve in clean.execute(f'PRAGMA table_info({tabla_datos})')]
                seleccionado = ['0 AS managed_permissions' if source_version == 3 and tabla_datos == 'users'
                            and columna == 'managed_permissions' else '0 AS revision' if source_version < 5 and tabla_datos == 'issues' and columna == 'revision' else columna for columna in columnas]
                cursor = origen.execute('SELECT ' + ','.join(seleccionado) + f' FROM {tabla_datos}')
                while lote := cursor.fetchmany(500):
                    clean.executemany(f"INSERT INTO {tabla_datos} VALUES({','.join('?' for _ in columnas)})", lote)  # nosec B608 # SQL estructural interno con tablas/columnas o fragmentos constantes; valores del usuario enlazados con parámetros
        initialize_schema(clean)
        if clean.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError("El respaldo contiene relaciones de datos inconsistentes.")
        masters = clean.execute("SELECT document FROM users WHERE role='Administrador maestro' AND active=1").fetchall()
        if len(masters) != 1 or not masters[0][0]:
            raise ValueError("El respaldo debe contener un administrador maestro activo con documento de identidad.")
        clean.row_factory = sqlite3.Row
        return clean
    except sqlite3.Error as excepcion:
        clean.close()
        raise ValueError("La base del respaldo está dañada o sus datos no son compatibles.") from excepcion
    except BaseException:
        clean.close()
        raise
    finally:
        origen.close()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
validated_database = validada_base
