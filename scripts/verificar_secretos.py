"""Comprueba archivos fuente contra una línea base revisada, sin verificar claves por red."""
from pathlib import Path
import os
import subprocess  # nosec B404 # subprocess necesario para herramientas locales; sin shell=True
import sys


def principal():
    """Ejecuta el hook oficial por lotes y falla ante secretos nuevos o errores."""
    root = Path(__file__).resolve().parents[1]
    executable = Path(sys.executable).parent / ('detect-secrets-hook.exe' if os.name == 'nt' else 'detect-secrets-hook')
    if not executable.is_file():
        print('Instale primero: python -m pip install -e ".[security]"', file=sys.stderr)
        return 2
    ignored = {'.git', '.venv', '__pycache__', 'datos', 'datos-demo', '.pruebas_temporales', 'build', 'dist', 'quality-reports', '.ruff_cache'}
    paths = []
    for current, folders, names in os.walk(root):
        folders[:] = [name for name in folders if name not in ignored and not name.endswith('.egg-info')]
        paths.extend((Path(current) / name).relative_to(root).as_posix() for name in names if name != '.secrets.baseline')
    for start in range(0, len(paths), 20):
        result = subprocess.run([str(executable), '--baseline', '.secrets.baseline', *paths[start:start + 20]], cwd=root)  # nosec B603 # argumentos separados sin intérprete de comandos; ejecutable del entorno o ruta local controlada
        if result.returncode:
            return result.returncode
    print('Sin secretos nuevos respecto a la línea base revisada.')
    return 0


if __name__ == '__main__':
    raise SystemExit(principal())
