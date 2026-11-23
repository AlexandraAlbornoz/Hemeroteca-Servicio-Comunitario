"""Respaldos reales aislados: configuración, programación, exportación y ejecución diaria."""
from datetime import datetime
from pathlib import Path
import os
import secrets
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hemeroteca.config.settings import SECURITY_QUESTIONS
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services import backup_service as module
from hemeroteca.services.backup_archive import derive_key, read_archive, MAGIC
from hemeroteca.utils.local_secrets import protect_key, write_json

CLAVE = 'Prueba#2026'  # pragma: allowlist secret -- cuentas ficticias de una base temporal


class PruebasOperacionRespaldos(unittest.TestCase):
    """Usa SQLite, AES-GCM y DPAPI reales; solo simula el programador de Windows."""

    @classmethod
    def setUpClass(cls):
        """Prepara cuentas y clave cifrada reutilizables sin repetir scrypt en cada caso."""
        cls.seed = create_services(':memory:')
        questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        cls.seed.auth.create_master('Maestra Ficticia', 'V-12345678', CLAVE, questions)
        cls.seed.users.register_user('Persona Ficticia', 'V-12345679', CLAVE, questions)
        cls.salt = secrets.token_bytes(16)
        cls.key = derive_key('RespaldoFicticio#2026', cls.salt)
        cls.protected = protect_key(cls.key)

    @classmethod
    def tearDownClass(cls):
        """Cierra la semilla sintética."""
        cls.seed.close()

    def setUp(self):
        """Restaura una colección independiente y evita toda tarea real del sistema."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.s = create_services(self.root / 'hemeroteca.db')
        self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
        self.master = self.s.auth.authenticate('V-12345678', CLAVE)
        self.user = self.s.auth.authenticate('V-12345679', CLAVE)
        self.service = self.s.backups
        self.output = self.root / 'copias'

    def ajustes(self, **changes):
        """Guarda una configuración funcional cuya clave corresponde a la sal indicada."""
        settings = dict(version=1, enabled=True, directory=str(self.output), time='00:00',
                        salt=self.salt.hex(), last_daily_date='', **self.protected)
        settings.update(changes)
        write_json(self.service.settings_path, settings)
        return settings

    def test_configurar_crea_copia_descifrable_y_estado_sin_secretos(self):
        """La configuración inicial guarda un respaldo real sin exponer material de clave."""
        with patch.object(self.service, '_schedule_windows') as scheduler:
            result = self.service.configure(self.master, CLAVE, 'RespaldoFicticio#2026', str(self.output), '12:30')
        self.assertTrue(result['enabled'])
        self.assertEqual(result['time'], '12:30')
        self.assertFalse({'key', 'salt', 'protection'} & result.keys())
        metadata, data = read_archive(self.output / result['last_file'], 'RespaldoFicticio#2026')
        self.assertEqual(metadata['reason'], 'inicial')
        self.assertTrue(data.startswith(b'SQLite format 3\x00'))
        self.assertEqual(scheduler.call_count, int(os.name == 'nt'))

    def test_configuracion_invalida_no_crea_archivos(self):
        """Rechaza rutas relativas y horas imposibles antes de guardar ajustes."""
        for directory, hour in (('', '12:00'), ('relativa', '12:00'), (str(self.output), '24:00'), (str(self.output), '9:00')):
            with self.subTest(directory=directory, hour=hour), self.assertRaises(ValueError):
                self.service.configure(self.master, CLAVE, 'RespaldoFicticio#2026', directory, hour)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.service.settings_path.exists())

    def test_cuenta_regular_y_contrasena_incorrecta_no_pueden_operar(self):
        """La autorización no depende de la pantalla que invoque el servicio."""
        with self.assertRaises(AccessDenied):
            self.service.status(self.user)
        with self.assertRaises(AccessDenied):
            self.service.create_now(self.master, 'Incorrecta#2026')
        write_json(self.service.network_path, {'mode': 'client'})
        with self.assertRaises(AccessDenied):
            self.service.status(self.master)
        self.assertFalse(self.output.exists())

    def test_estado_tolera_json_corrupto_y_lector_rechaza_tamano_y_tipo(self):
        """Un ajuste dañado produce un estado comprensible, no filtración de claves."""
        self.service.settings_path.write_text('{', encoding='utf-8')
        self.assertIn('no se puede leer', self.service.status(self.master)['last_error'])
        self.service.settings_path.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            module.read_settings(self.service.settings_path)
        self.service.settings_path.write_bytes(b'x' * 65537)
        with self.assertRaises(ValueError):
            module.read_settings(self.service.settings_path)

    def test_copia_manual_exportacion_y_listado_reales(self):
        """Exporta bytes idénticos de un respaldo reconocido y registra la copia."""
        self.ajustes()
        source = Path(self.service.create_now(self.master, CLAVE))
        listed = self.service.list_backups(self.master)
        self.assertEqual(len(listed), 1)
        self.assertEqual(Path(listed[0]['path']), source.resolve())
        target = self.root / 'exportada.hmbackup'
        self.service.export(self.master, source, target)
        self.assertEqual(source.read_bytes(), target.read_bytes())
        self.assertEqual(module.read_settings(self.service.settings_path)['last_file'], source.name)

    def test_exportacion_rechaza_origen_ajeno_extension_y_archivo_danado(self):
        """No exporta archivos arbitrarios ni un respaldo reconocido pero alterado."""
        self.ajustes()
        source = Path(self.service.create_now(self.master, CLAVE))
        target = self.root / 'salida.hmbackup'
        for origin, destination in ((self.root / 'ajeno.hmbackup', target), (source, self.root / 'salida.txt')):
            with self.assertRaises(ValueError):
                self.service.export(self.master, origin, destination)
        source.write_bytes(b'archivo ajeno')
        with self.assertRaises(ValueError):
            self.service.export(self.master, source, target)
        self.assertFalse(target.exists())

    def test_exportacion_rechaza_respaldo_que_supera_limite(self):
        """Limita la lectura de archivos conocidos sin cargar tamaños arbitrarios."""
        self.ajustes()
        self.output.mkdir()
        source = self.output / 'grande.hmbackup'
        source.write_bytes(MAGIC + b'x' * 8300)
        with patch.object(module, 'MAX_DATABASE', 1), self.assertRaises(ValueError):
            self.service.export(self.master, source, self.root / 'salida.hmbackup')

    def test_listado_usa_copias_previas_si_configuracion_esta_corrupta(self):
        """Las copias previas siguen siendo visibles aunque fallen ajustes diarios."""
        folder = self.root / 'respaldos'
        folder.mkdir()
        (folder / 'primera.hmbackup').write_bytes(MAGIC)
        (folder / 'directorio.hmbackup').mkdir()
        self.service.settings_path.write_text('{', encoding='utf-8')
        self.assertEqual([item['name'] for item in self.service.list_backups(self.master)], ['primera.hmbackup'])

    def test_manual_sin_clave_no_crea_copia(self):
        """Una configuración ausente obliga a elegir primero clave y directorio."""
        with self.assertRaisesRegex(ValueError, 'Configura primero'):
            self.service.create_now(self.master, CLAVE)

    def test_programacion_windows_argumentos_y_fallo_reversible(self):
        """Construye argumentos separados y conserva el respaldo en app si Windows falla."""
        settings = self.ajustes()
        with patch.object(module.subprocess, 'run') as run:
            self.service._schedule_windows(settings)
            args = run.call_args.args[0]
            self.assertTrue(Path(args[0]).is_absolute())
            self.assertIn(str(self.service.settings_path.resolve()), args)
            self.assertEqual(settings['scheduler'], 'windows')
            self.service._schedule_windows(settings, remove=True)
            self.assertIn('-Remove', run.call_args.args[0])
            self.assertEqual(settings['scheduler'], 'disabled')
        with patch.object(module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ficticio', 25)):
            self.service._schedule_windows(settings)
        self.assertEqual(settings['scheduler'], 'app')
        self.assertTrue(settings['scheduler_error'])

    def test_reintento_y_desactivacion_no_crean_tareas_reales(self):
        """Desactivar impide al trabajador crear copias, incluso si la tarea externa falla."""
        self.ajustes()
        with patch.object(self.service, '_schedule_windows') as schedule:
            if os.name == 'nt':
                self.assertTrue(self.service.retry_schedule(self.master, CLAVE)['enabled'])
            self.service.disable(self.master, CLAVE)
        self.assertFalse(module.read_settings(self.service.settings_path)['enabled'])
        self.assertFalse(module.run_daily_backup(self.service.database, self.service.settings_path, self.service.network_path))
        if os.name == 'nt':
            self.assertTrue(schedule.call_args.kwargs['remove'])

    def test_reintento_sin_configuracion_se_rechaza(self):
        """No registra una tarea sin una configuración habilitada."""
        with self.assertRaisesRegex(ValueError, 'Configura primero'):
            self.service.retry_schedule(self.master, CLAVE)

    def test_reintento_en_otro_sistema_no_intenta_programar_windows(self):
        """La operación específica de Windows informa su límite sin ejecutar procesos."""
        self.ajustes()
        with patch.object(module, 'os', SimpleNamespace(name='posix')), patch.object(module.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Windows'):
                self.service.retry_schedule(self.master, CLAVE)
        run.assert_not_called()

    def test_variante_autonoma_del_programador_incluye_bandera(self):
        """El contrato heredado del trabajador autónomo conserva su argumento explícito."""
        settings = self.ajustes()
        with patch.object(module.sys, 'frozen', True, create=True), patch.object(module.subprocess, 'run') as run:
            self.service._schedule_windows(settings)
        self.assertIn('-EjecutableAutonomo', run.call_args.args[0])

    def test_diaria_real_solo_una_vez_y_registra_auditoria(self):
        """El trabajador cifra una copia y no duplica la misma fecha."""
        self.ajustes()
        arguments = (self.service.database, self.service.settings_path, self.service.network_path)
        self.assertTrue(module.run_daily_backup(*arguments))
        self.assertFalse(module.run_daily_backup(*arguments))
        settings = module.read_settings(self.service.settings_path)
        metadata, _ = read_archive(self.output / settings['last_file'], 'RespaldoFicticio#2026')
        self.assertEqual(metadata['reason'], 'diario')
        self.assertTrue(self.s.connection.execute("SELECT 1 FROM audit WHERE action LIKE 'Respaldo diario creado:%'").fetchone())

    def test_diaria_se_omite_en_cliente_otro_propietario_o_sin_maestro(self):
        """Una réplica y una colección sin administrador no generan copias diarias."""
        self.ajustes()
        args = (self.service.database, self.service.settings_path, self.service.network_path)
        write_json(self.service.network_path, {'mode': 'client'})
        self.assertFalse(module.run_daily_backup(*args))
        write_json(self.service.network_path, {'mode': 'server', 'node_id': 'nodo-local'})
        with self.s.connection:
            self.s.connection.execute("INSERT INTO system_settings(key,value) VALUES('active_host_id','otro-nodo')")
        self.assertFalse(module.run_daily_backup(*args))
        with self.s.connection:
            self.s.connection.execute('DELETE FROM system_settings')
            self.s.connection.execute('UPDATE users SET active=0')
        self.assertFalse(module.run_daily_backup(*args))
        self.assertFalse(self.output.exists())

    def test_diaria_fallo_de_copia_guarda_error_y_permite_reintento(self):
        """Una falta de espacio no se marca como éxito ni bloquea intentos posteriores."""
        self.ajustes()
        args = (self.service.database, self.service.settings_path, self.service.network_path)
        with patch.object(module, '_save_copy', side_effect=OSError('espacio ficticio')):
            with self.assertRaisesRegex(ValueError, 'No se creó'):
                module.run_daily_backup(*args)
        failed = module.read_settings(self.service.settings_path)
        self.assertTrue(failed['last_error'])
        self.assertNotIn('last_success', failed)
        self.assertTrue(module.run_daily_backup(*args))
        self.assertFalse(module.read_settings(self.service.settings_path)['last_error'])

    def test_diaria_antes_de_hora_cubre_dia_anterior(self):
        """Recuperar ayer por la mañana no cancela la copia programada para esta tarde."""
        self.ajustes(time='18:00', last_daily_date='2026-11-14')
        with patch.object(module, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 16, 8, 0)
            self.assertTrue(module.run_daily_backup(self.service.database, self.service.settings_path, self.service.network_path))
            self.assertEqual(module.read_settings(self.service.settings_path)['last_daily_date'], '2026-11-15')
            clock.now.return_value = datetime(2026, 11, 16, 18, 0)
            self.assertTrue(module.run_daily_backup(self.service.database, self.service.settings_path, self.service.network_path))
        self.assertEqual(module.read_settings(self.service.settings_path)['last_daily_date'], '2026-11-16')
        self.assertEqual(len(list(self.output.glob('*.hmbackup'))), 2)

    def test_diaria_omite_archivo_inexistente(self):
        """El trabajador no crea una colección nueva por accidente."""
        self.assertFalse(module.run_daily_backup(self.root / 'ausente.db', self.service.settings_path, self.service.network_path))
        self.assertFalse((self.root / 'ausente.db').exists())

    def test_diaria_revalida_si_se_desactiva_al_adquirir_bloqueo(self):
        """Un trabajador pendiente no ignora que el maestro acaba de desactivar copias."""
        settings = self.ajustes()
        with patch.object(module, 'read_settings', side_effect=[settings, settings | {'enabled': False}, {}]), patch.object(module, '_save_copy') as save:
            self.assertFalse(module.run_daily_backup(self.service.database, self.service.settings_path, self.service.network_path))
        save.assert_not_called()

    def test_diaria_configuracion_incompleta_informa_error_sin_copia(self):
        """Un campo de hora ausente se registra como fallo recuperable."""
        settings = self.ajustes()
        settings.pop('time')
        write_json(self.service.settings_path, settings)
        with self.assertRaisesRegex(ValueError, 'No se creó'):
            module.run_daily_backup(self.service.database, self.service.settings_path, self.service.network_path)
        self.assertTrue(module.read_settings(self.service.settings_path)['last_error'])
        self.assertFalse(self.output.exists())

    def test_hilo_programador_se_detiene_y_tolera_error_del_trabajador(self):
        """El hilo real termina de forma acotada aunque una ejecución diaria falle."""
        scheduler = module.BackupScheduler(self.service.database, self.service.network_path)
        def fail_once(*args):
            """Detiene inmediatamente el hilo de prueba sin esperas de un minuto."""
            scheduler.stopped.set()
            raise ValueError('fallo ficticio')
        with patch.object(module, 'run_daily_backup', side_effect=fail_once) as worker:
            scheduler.start()
            scheduler.thread.join(timeout=5)
            scheduler.close()
        self.assertFalse(scheduler.thread.is_alive())
        worker.assert_called_once()

    def test_cierre_del_hilo_en_espera_no_deja_trabajador_vivo(self):
        """La señal de cierre despierta al trabajador y completa join sin esperas reales largas."""
        scheduler = module.BackupScheduler(self.service.database, self.service.network_path)
        entered = threading.Event()
        def worker(*args):
            """Mantiene el trabajador vivo hasta que close señale su terminación."""
            entered.set()
            scheduler.stopped.wait(timeout=5)
            return False
        with patch.object(module, 'run_daily_backup', side_effect=worker):
            scheduler.start()
            self.assertTrue(entered.wait(timeout=3))
            scheduler.close()
        self.assertFalse(scheduler.thread.is_alive())
        self.assertTrue(scheduler.stopped.is_set())
