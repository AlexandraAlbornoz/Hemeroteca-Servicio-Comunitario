"""Apertura de la base local y transacciones SQLite."""

import sqlite3
from datetime import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from hemeroteca.config.settings import DB_PATH
from hemeroteca.database.schema import SCHEMA_VERSION, initialize_schema


def conectar_base_datos(path: Path | str = DB_PATH, *, initialize=True) -> sqlite3.Connection:
    """Abre la base y prepara su esquema; no crea cuentas predeterminadas."""
    ruta = path
    if str(ruta) != ":memory:":
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta, timeout=10)
    conexion.row_factory = sqlite3.Row
    from hemeroteca.services.paginacion import plegar_texto, instante_evento, instante_evento_utc
    conexion.create_function('plegar_texto', 1, plegar_texto, deterministic=True)
    conexion.create_function('instante_evento', 1, instante_evento, deterministic=True)
    conexion.create_function('instante_evento_utc', 1, instante_evento_utc, deterministic=True)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 10000")
    if not initialize:
        return conexion
    try:
        if str(ruta) != ":memory:" and conexion.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            if conexion.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
                respaldo_dir = Path(ruta).parent / "backups"
                respaldo_dir.mkdir(exist_ok=True)
                ruta_respaldo = respaldo_dir / f"hemeroteca-pre-v{SCHEMA_VERSION}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
                respaldo = sqlite3.connect(ruta_respaldo)
                try:
                    conexion.backup(respaldo)
                finally:
                    respaldo.close()
        initialize_schema(conexion)
    except BaseException:
        conexion.close()
        raise
    return conexion
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
connect_database = conectar_base_datos


@contextmanager
def transaccion(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Comprueba y guarda cambios bajo una transacción de escritura."""
    conexion = connection
    conexion.execute("BEGIN IMMEDIATE")
    try:
        yield conexion
        conexion.commit()
    except BaseException:
        conexion.rollback()
        raise
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
transaction = transaccion
