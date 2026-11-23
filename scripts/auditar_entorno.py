"""Audita versiones instaladas de terceros, sin resolver versiones distintas."""
import json
from pathlib import Path
import re
import subprocess  # nosec B404 # subprocess necesario para herramientas locales; sin shell=True
import sys
import tempfile

from packaging.version import Version


def principal():
    """Fija las versiones reales en un temporal y exige una auditoría completa."""
    result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=json',  # nosec B603 # argumentos separados sin intérprete de comandos; ejecutable del entorno o ruta local controlada
                             '--exclude-editable'], capture_output=True, text=True, check=True)
    dependencies = json.loads(result.stdout)
    lines = []
    for item in dependencies:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', item['name']):
            raise ValueError('Nombre de dependencia inválido.')
        lines.append(item['name'] + '==' + str(Version(item['version'])))
    with tempfile.TemporaryDirectory(prefix='hemeroteca-audit-') as temporary:
        requirements = Path(temporary) / 'installed.txt'
        requirements.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        result = subprocess.run([sys.executable, '-m', 'pip_audit', '--strict', '--no-deps',  # nosec B603 # argumentos separados sin intérprete de comandos; ejecutable del entorno o ruta local controlada
                                 '--disable-pip', '-r', str(requirements), *sys.argv[1:]])
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(principal())
