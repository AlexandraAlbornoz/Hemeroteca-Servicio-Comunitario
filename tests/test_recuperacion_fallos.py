"""Restauración cifrada bajo corrupción, cambios de archivo y fallos de disco."""
from contextlib import closing
from pathlib import Path
import hashlib
import secrets
import tempfile
import unittest
from unittest.mock import patch

from hemeroteca.config.settings import SECURITY_QUESTIONS, NATIONAL
from hemeroteca.services.container import create_services
from hemeroteca.services.backup_archive import derive_key, snapshot, write_archive


class PruebasRecuperacionFallos(unittest.TestCase):
    """Garantiza que un fallo anterior a restaurar conserve el catálogo vigente."""

    def setUp(self):
        """Crea una colección ficticia, un respaldo y un cambio posterior distinguible."""
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.services = create_services(self.folder / 'hemeroteca.db')
        questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        self.services.auth.create_master('Persona Ficticia', 'V-12345678', 'Prueba#2026', questions)
        self.actor = self.services.auth.authenticate('V-12345678', 'Prueba#2026')
        self.archive = self.folder / 'prueba.hmbackup'
        salt = secrets.token_bytes(16)
        self.backup_password = 'RespaldoDePrueba#2026'  # pragma: allowlist secret -- solo datos ficticios temporales
        write_archive(self.archive, snapshot(self.services.connection), derive_key(self.backup_password, salt), salt)
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.services.periodicos.save_record(self.actor, (NATIONAL[0], 'Nacional', 'Matutina', 2020, 1, 1, '42', '1', '', 'Disponible'))

    def tearDown(self):
        """Cierra SQLite y retira únicamente los datos temporales de la prueba."""
        self.services.close()
        self.temporary.cleanup()

    def comprobar_catalogo_conservado(self):
        """Confirma integridad y presencia del ejemplar posterior al respaldo."""
        self.assertEqual(self.services.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.services.connection.execute('SELECT count(*) FROM issues').fetchone()[0], 1)

    def test_respaldo_alterado_no_modifica_base(self):
        """La autenticación AES-GCM detecta una alteración antes de escribir SQLite."""
        data = bytearray(self.archive.read_bytes())
        data[-1] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaises(ValueError):
            self.services.backups.restore(self.actor, self.archive, self.backup_password, 'Prueba#2026', self.digest)
        self.comprobar_catalogo_conservado()

    def test_sin_espacio_para_copia_previa_no_restaurar(self):
        """Si no puede guardarse la copia de seguridad previa, no se aplica el respaldo."""
        with patch('hemeroteca.services.backup_service.write_archive', side_effect=OSError('disco lleno ficticio')):
            with self.assertRaises(OSError):
                self.services.backups.restore(self.actor, self.archive, self.backup_password, 'Prueba#2026', self.digest)
        self.comprobar_catalogo_conservado()

    def test_archivo_distinto_del_revisado_se_rechaza(self):
        """Un digest distinto exige repetir la revisión en lugar de restaurar otro archivo."""
        with self.assertRaisesRegex(ValueError, 'cambió'):
            self.services.backups.restore(self.actor, self.archive, self.backup_password, 'Prueba#2026', '0' * 64)
        self.comprobar_catalogo_conservado()

    def test_restauracion_exitosa_conserva_copia_anterior(self):
        """El catálogo vuelve al respaldo y la copia anterior conserva el ejemplar reciente."""
        result = self.services.backups.restore(self.actor, self.archive, self.backup_password, 'Prueba#2026', self.digest)
        self.assertEqual(self.services.connection.execute('SELECT count(*) FROM issues').fetchone()[0], 0)
        self.assertTrue(Path(result['before']).is_file())
        from hemeroteca.services.backup_archive import read_archive, validated_database
        _, data = read_archive(result['before'], self.backup_password)
        with closing(validated_database(data)) as previous:
            self.assertEqual(previous.execute('SELECT count(*) FROM issues').fetchone()[0], 1)
        self.assertEqual(self.services.connection.execute('SELECT count(*) FROM api_sessions').fetchone()[0], 0)
