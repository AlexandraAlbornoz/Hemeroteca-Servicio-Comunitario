"""Comprueba el contraste de pares de colores de la paleta compartida."""
import json
from hemeroteca.config import settings


def luminancia(color):
    """Calcula luminancia relativa sRGB con la transferencia lineal del estándar."""
    values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in values]
    return sum(weight * value for weight, value in zip((.2126, .7152, .0722), linear))


def contrastes():
    """Devuelve razones para texto activo, sin afirmar accesibilidad de toda la UI."""
    pairs = [('WHITE', 'BLUE'), ('WHITE', 'BLUE_HOVER'), ('MUTED', 'BG'),
             ('MUTED', 'WHITE'), ('WHITE', 'RED'), ('WHITE', 'GREEN'),
             ('WHITE', 'AMBER'), ('INK', 'SOFT'), ('WHITE', 'SIDEBAR')]
    results = {}
    for foreground, background in pairs:
        values = sorted((luminancia(getattr(settings, foreground)), luminancia(getattr(settings, background))))
        results[foreground + '/' + background] = (values[1] + .05) / (values[0] + .05)
    return results


if __name__ == '__main__':
    ratios = contrastes()
    print(json.dumps({key: round(value, 3) for key, value in ratios.items()}, indent=2))
    raise SystemExit(0 if all(value >= 4.5 for value in ratios.values()) else 1)
