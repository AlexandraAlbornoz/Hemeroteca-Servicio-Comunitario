"""Contratos de recursos y configuración de la distribución fuente."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hemeroteca.config.settings import ASSETS, WINDOWS_RESOURCES, BACKUP_WORKER


class PruebasEstructura(unittest.TestCase):
    """Comprueba rutas que cambian al reorganizar el proyecto."""

    def test_recursos_operativos_disponibles(self):
        """Imágenes, programador y trabajador existen junto al paquete."""
        self.assertTrue((ASSETS / 'hemeroteca_periodico.ico').is_file())
        self.assertTrue((WINDOWS_RESOURCES / 'Configurar_Red_Windows.ps1').is_file())
        self.assertTrue((WINDOWS_RESOURCES / 'Programar_Respaldos_Windows.ps1').is_file())
        result = subprocess.run([sys.executable, str(BACKUP_WORKER), '--help'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_directorio_configurable_sin_crear_datos_al_importar(self):
        """Un proceso nuevo toma la ruta elegida sin crear una base al importar."""
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / 'coleccion'
            result = subprocess.run(
                [sys.executable, '-c',
                 'from hemeroteca.config.settings import DB_PATH; print(DB_PATH)'],
                env=dict(os.environ, HEMEROTECA_DATA_DIR=str(data)),
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), (data / 'hemeroteca.db').resolve())
            self.assertFalse(data.exists())
