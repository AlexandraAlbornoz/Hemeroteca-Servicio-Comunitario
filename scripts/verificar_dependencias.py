"""Verifica que el entorno real y los metadatos respeten las versiones con hashes."""
from importlib import metadata
from pathlib import Path
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


def principal():
    """Rechaza versiones distintas del lock o requisitos de ejecución incompatibles."""
    root = Path(__file__).resolve().parents[1]
    pins = {}
    for line in (root / 'requirements-lock.txt').read_text(encoding='utf-8').splitlines():
        if re.match(r'^[A-Za-z0-9_.-]+==', line):
            requirement = Requirement(line.rstrip('\\').strip())
            if requirement.marker and not requirement.marker.evaluate():
                continue
            name = canonicalize_name(requirement.name)
            installed = metadata.version(name)
            if not requirement.specifier.contains(installed, prereleases=True):
                raise ValueError(f'{name}: la versión instalada no coincide con el lock.')
            pins[name] = Version(installed)
    for declaration in metadata.requires('hemeroteca') or []:
        requirement = Requirement(declaration)
        if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
            continue
        name = canonicalize_name(requirement.name)
        if name not in pins or not requirement.specifier.contains(pins[name], prereleases=True):
            raise ValueError(f'{name}: regenere el lock para los requisitos actuales.')
    if not pins:
        raise ValueError('No hay versiones de ejecución fijadas.')
    print(f'{len(pins)} versiones de ejecución coinciden con el lock y los metadatos.')
    return 0


if __name__ == '__main__':
    raise SystemExit(principal())
