"""Trabajador diario de Windows; no abre ventanas ni utiliza credenciales de usuarios."""

import argparse
import sys
from pathlib import Path

from hemeroteca.config.settings import DB_PATH, NETWORK_CONFIG_PATH
from hemeroteca.services.backup_service import run_daily_backup


def principal():
    'Lee rutas y ejecuta el respaldo diario configurado sin abrir ventanas ni iniciar sesión.'
    parser = argparse.ArgumentParser(description='Crear el respaldo diario configurado por el maestro.')
    parser.add_argument('--database', type=Path, default=DB_PATH)
    parser.add_argument('--settings', type=Path, default=DB_PATH.parent / 'backup-settings.json')
    parser.add_argument('--network', type=Path, default=NETWORK_CONFIG_PATH)
    arguments = parser.parse_args()
    try:
        run_daily_backup(arguments.database, arguments.settings, arguments.network)
    except (OSError, ValueError):
        return 1
    return 0
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
main = principal


if __name__ == '__main__':
    sys.exit(main())
