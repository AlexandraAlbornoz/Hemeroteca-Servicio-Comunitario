"""Importa una copia validada de datos anteriores sin sobrescribir instalaciones."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile

from config.settings import DB_PATH
from database.maintenance import database_guard
from services.backup_archive import validated_database


def importar(origen, destino=DB_PATH):
    """Reconstruye datos conocidos en un destino nuevo y elimina sesiones y equipos."""
    origen, destino = Path(origen).resolve(), Path(destino).resolve()
    if origen == destino:
        raise ValueError('El origen y el destino deben ser distintos.')
    if not origen.is_file():
        raise ValueError(f'No se encontró la base anterior: {origen}')
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    with database_guard(destino):
        if destino.exists():
            raise ValueError('Hemeroteca ya tiene una base. Usa el flujo de respaldos o una carpeta nueva; no se sobrescribió ningún dato.')
        try:
            with closing(sqlite3.connect(origen.as_uri() + '?mode=ro', uri=True)) as conexion_origen, closing(sqlite3.connect(':memory:')) as copia:
                conexion_origen.backup(copia)
                with closing(validated_database(copia.serialize())) as validada:
                    descriptor, nombre = tempfile.mkstemp(prefix='importacion-', suffix='.db', dir=destino.parent)
                    os.close(descriptor)
                    temporal = Path(nombre)
                    with closing(sqlite3.connect(temporal)) as conexion_destino:
                        validada.backup(conexion_destino)
            if os.name == 'nt':
                temporal.rename(destino)  # Windows rechaza reemplazar un destino existente.
            else:
                os.link(temporal, destino)
                temporal.unlink()
            return destino
        finally:
            if temporal is not None and temporal.exists():
                temporal.unlink()


def principal():
    """Lee las rutas de importación y muestra un resultado comprensible en consola."""
    analizador = argparse.ArgumentParser(description='Copiar datos anteriores a una instalación nueva de Hemeroteca.')
    anterior = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'Hemeroteca-Perri/data/hemeroteca.db'
    analizador.add_argument('--origen', type=Path, default=anterior)
    analizador.add_argument('--destino', type=Path, default=DB_PATH)
    argumentos = analizador.parse_args()
    try:
        destino = importar(argumentos.origen, argumentos.destino)
    except (ValueError, OSError, sqlite3.Error) as error:
        print('No se importaron datos:', error)
        return 1
    print('Copia importada:', destino)
    print('Conserva tus cuentas. Las computadoras de consulta deben autorizarse de nuevo.')
    return 0


if __name__ == '__main__':
    raise SystemExit(principal())
