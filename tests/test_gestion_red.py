"""Gestión de red y traslados: SQLite real y fronteras de red simuladas."""
import base64
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hemeroteca.config.settings import SECURITY_QUESTIONS
from hemeroteca.network import manager as module
from hemeroteca.network.configuration import save_settings, load_settings
from hemeroteca.network.devices import DeviceIdentity
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied

CLAVE = 'Prueba#2026'  # pragma: allowlist secret -- solo una colección sintética


class PruebasGestionRed(unittest.TestCase):
    """Ejercita estados, propiedad y reversión sin enviar tráfico fuera del equipo."""

    @classmethod
    def setUpClass(cls):
        """Construye una semilla autenticable sin datos personales."""
        cls.seed = create_services(':memory:')
        questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        cls.seed.auth.create_master('Maestra Ficticia', 'V-12345678', CLAVE, questions)
        cls.seed.users.register_user('Persona Ficticia', 'V-12345679', CLAVE, questions)

    @classmethod
    def tearDownClass(cls):
        """Cierra la semilla compartida."""
        cls.seed.close()

    def setUp(self):
        """Prepara base y configuración independientes y controla todos los cierres."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = module.NetworkManager(self.root / 'hemeroteca.db', self.root / 'network.json')
        self.addCleanup(self.manager.close)
        self.s = create_services(self.manager.database, node_id=self.manager.settings['node_id'])
        self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
        self.master = self.s.auth.authenticate('V-12345678', CLAVE)
        self.user = self.s.auth.authenticate('V-12345679', CLAVE)

    def servidor_guardado(self, **changes):
        """Guarda un host local ficticio sin abrir puertos."""
        self.manager.settings.update(mode='server', server_url='https://127.0.0.1:8765', fingerprint='a' * 64)
        self.manager.settings.update(changes)
        save_settings(self.manager.settings, self.manager.config_path)

    def snapshot(self, node_id):
        """Produce una instantánea coherente con metadatos de traslado removibles."""
        with closing(sqlite3.connect(':memory:')) as connection:
            self.seed.connection.backup(connection)
            with connection:
                connection.executemany('INSERT INTO system_settings(key,value) VALUES(?,?)',
                                       [('active_host_id', node_id), ('transfer_rollback_hash', 'huella-ficticia'),
                                        ('transfer_cancel_token', 'cancelacion-ficticia')])
            content = connection.serialize()
        return {'database': base64.b64encode(content).decode(), 'sha256': hashlib.sha256(content).hexdigest(),
                'rollback_key': 'reversion-ficticia'}

    def destino(self):
        """Devuelve ajustes válidos para el destino de una promoción."""
        return dict(self.manager.settings, mode='server', server_url='https://127.0.0.1:8766', fingerprint='b' * 64)

    def remoto(self):
        """Simula solo el transporte externo, conservando el gestor real."""
        return SimpleNamespace(read_only=True, client=SimpleNamespace(
            settings={'server_url': 'https://127.0.0.1:8765', 'fingerprint': 'a' * 64}, token='sesion-ficticia'))

    def controlador(self):
        """Controlador sin socket para comprobar activación y cancelación bajo bloqueo."""
        return SimpleNamespace(ready=False, cancelled=False, cancel_token='cancelacion-ficticia',
                               state_lock=threading.RLock(), settings={}, close=Mock())

    def test_servicios_locales_conservan_propietario_y_ruta_respaldos(self):
        """Construye servicios reales y guarda quién puede escribir esta colección."""
        with closing(self.manager.services()) as services:
            self.assertIs(services.network, self.manager)
            self.assertEqual(services.backups.network_path, self.manager.config_path)
            owner = services.connection.execute("SELECT value FROM system_settings WHERE key='active_host_id'").fetchone()[0]
            self.assertEqual(owner, self.manager.settings['node_id'])

    def test_modo_cliente_no_abre_base_local(self):
        """El cliente usa adaptadores remotos sin tocar la conexión SQLite."""
        self.manager.follow_server({'server_url': 'https://127.0.0.1:8765', 'fingerprint': 'a' * 64})
        with patch.object(module, 'create_services', side_effect=AssertionError('no abrir base local')):
            services = self.manager.services()
        self.assertTrue(services.read_only)
        self.assertIs(services.network, self.manager)
        self.assertEqual(services.client.settings['fingerprint'], 'a' * 64)

    def test_coleccion_trasladada_redirige_y_cierra_conexion_local(self):
        """Una copia antigua no se convierte en un segundo host con capacidad de escritura."""
        with self.s.connection:
            self.s.connection.executemany('INSERT INTO system_settings(key,value) VALUES(?,?)',
                [('active_host_id', 'destino'), ('active_host_url', 'https://127.0.0.1:8766'), ('active_host_pin', 'b' * 64)])
        services = self.manager.services()
        self.assertTrue(services.read_only)
        self.assertEqual(load_settings(self.manager.config_path)['mode'], 'client')
        self.assertEqual(services.client.settings['server_url'], 'https://127.0.0.1:8766')

    def test_servidor_vacio_permanece_local(self):
        """No expone por LAN una base que aún no tiene administrador principal."""
        manager = module.NetworkManager(self.root / 'vacia.db', self.root / 'vacia.json')
        self.addCleanup(manager.close)
        manager.settings['mode'] = 'server'
        save_settings(manager.settings, manager.config_path)
        with patch.object(manager, '_start') as start, closing(manager.services()) as services:
            self.assertTrue(services.auth.needs_setup())
        start.assert_not_called()
        self.assertEqual(manager.describe()['mode'], 'local')

    def test_certificado_cambiado_bloquea_inicio_y_cierra_servicios(self):
        """No acepta silenciosamente otra identidad TLS para un servidor configurado."""
        self.servidor_guardado()
        with patch.object(module, 'ensure_certificate', return_value=(object(), 'b' * 64)), patch.object(self.manager, '_start') as start:
            with self.assertRaisesRegex(ValueError, 'certificado cambió'):
                self.manager.services()
        start.assert_not_called()

    def test_servidor_configurado_inicia_solo_si_no_hay_controlador_listo(self):
        """Reabrir servicios no duplica el servidor ya activo."""
        self.servidor_guardado()
        with patch.object(module, 'ensure_certificate', return_value=(object(), 'a' * 64)), patch.object(self.manager, '_start') as start:
            with closing(self.manager.services()):
                start.assert_called_once()
            self.manager.controllers.append(SimpleNamespace(ready=True, close=Mock()))
            with closing(self.manager.services()):
                self.assertEqual(start.call_count, 1)

    def test_inicio_controlador_guarda_referencia_y_listo(self):
        """La vida del servidor queda ligada al gestor y a su cierre."""
        with patch.object(module, 'LANServer') as constructor:
            controller = self.manager._start(self.manager.settings, object(), ready=False)
            controller.start.assert_called_once()
            self.assertIn(controller, self.manager.controllers)
            self.assertFalse(constructor.call_args.kwargs['ready'])
        self.manager.close()
        controller.close.assert_called_once()

    def test_busqueda_y_listado_solo_para_maestro_local(self):
        """El rol regular y un cliente remoto no enumeran equipos autorizados."""
        with patch.object(module, 'discover_waiting', return_value=[{'name': 'PC ficticia'}]):
            self.assertEqual(self.manager.discover_computers(self.s, self.master), [{'name': 'PC ficticia'}])
            with self.assertRaises(AccessDenied):
                self.manager.discover_computers(self.s, self.user)
        self.assertEqual(self.manager.approved_computers(self.s, self.master), [])
        for call in (self.manager.discover_computers, self.manager.approved_computers):
            with self.assertRaises(AccessDenied):
                call(SimpleNamespace(read_only=True), self.master)
        with self.assertRaises(AccessDenied):
            self.manager.connect('https://127.0.0.1:8765')

    def test_revocacion_desactiva_equipo_y_elimina_sus_sesiones(self):
        """Retirar una PC no deja una sesión antigua utilizable."""
        with self.s.connection:
            self.s.connection.execute('''INSERT INTO authorized_devices(device_id,public_key,node_id,name,approved_by,approved_at)
                VALUES('equipo','clave-publica-ficticia','nodo','PC ficticia','Prueba','2026-11-16')''')
            self.s.connection.execute('''INSERT INTO api_sessions(token_hash,user_id,password_version,method,recovery_generation,expires_at,device_id)
                VALUES('sesion',?,?,'password',0,9999999999,'equipo')''', (self.master['id'], self.master['password_version']))
        self.manager.revoke_computer(self.s, self.master, 'equipo', CLAVE)
        self.assertEqual(self.s.connection.execute("SELECT active FROM authorized_devices WHERE device_id='equipo'").fetchone()[0], 0)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM api_sessions').fetchone()[0], 0)
        with self.assertRaises(ValueError):
            self.manager.revoke_computer(self.s, self.master, 'ausente', CLAVE)
        with self.assertRaises(AccessDenied):
            self.manager.revoke_computer(SimpleNamespace(read_only=True), self.master, 'equipo', CLAVE)

    def test_configurar_actualiza_propiedad_y_reemplaza_puerto(self):
        """Un puerto nuevo cierra el controlador anterior y persiste al nuevo propietario."""
        self.servidor_guardado()
        old = SimpleNamespace(ready=True, settings=dict(self.manager.settings), close=Mock())
        self.manager.controllers.append(old)
        with patch.object(module, 'ensure_certificate', return_value=(object(), 'b' * 64)), patch.object(self.manager, '_start') as start:
            target = self.manager.configure_server(self.s, self.master, CLAVE, '127.0.0.1', 8766)
        start.assert_called_once()
        old.close.assert_called_once()
        self.assertNotIn(old, self.manager.controllers)
        self.assertEqual(load_settings(self.manager.config_path)['server_url'], target['server_url'])
        self.assertEqual(dict(self.s.connection.execute('SELECT key,value FROM system_settings'))['active_host_pin'], 'b' * 64)

    def test_mismo_puerto_reutiliza_controlador_y_rechaza_configuracion_invalida(self):
        """No abre otro socket para la misma dirección ni acepta puertos/direcciones inválidos."""
        self.servidor_guardado()
        old = SimpleNamespace(ready=True, settings=dict(self.manager.settings), close=Mock())
        self.manager.controllers.append(old)
        with patch.object(module, 'ensure_certificate', return_value=(object(), 'b' * 64)), patch.object(self.manager, '_start') as start:
            self.manager.configure_server(self.s, self.master, CLAVE, '127.0.0.1', 8765)
            start.assert_not_called()
            old.close.assert_not_called()
            self.assertEqual(old.settings['fingerprint'], 'b' * 64)
        for host, port in (('127.0.0.1', 'abc'), ('127.0.0.1', 80), ('8.8.8.8', 8765)):
            with self.subTest(host=host, port=port), self.assertRaises(ValueError):
                self.manager.configure_server(self.s, self.master, CLAVE, host, port)

    def test_preparacion_cliente_rechaza_coleccion_propia_y_reemplaza_receptor(self):
        """La preparación es temporal y no sobreescribe una hemeroteca ya configurada."""
        with self.assertRaises(AccessDenied):
            self.manager.prepare_consultation_pc(self.s)
        previous = Mock()
        self.manager.receiver = previous
        with patch.object(module, 'PairingReceiver') as receiver:
            actual = self.manager.prepare_consultation_pc(SimpleNamespace(read_only=True))
            previous.close.assert_called_once()
            actual.start.assert_called_once()
            accept = receiver.call_args.args[1]
            accept({'server_url': 'https://127.0.0.1:8765', 'server_pin': 'a' * 64})
        self.assertEqual(self.manager.describe()['mode'], 'client')
        self.manager.stop_preparation()
        actual.close.assert_called_once()
        self.assertIsNone(self.manager.receiver)

    def test_activacion_principal_elige_direccion_local(self):
        """La activación usa la dirección detectada y el puerto previamente elegido."""
        with patch.object(module, 'local_address', return_value='127.0.0.1'), patch.object(self.manager, 'configure_server') as configure:
            self.manager.activate_principal(self.s, self.master, CLAVE)
        self.assertEqual(configure.call_args.args[-2:], ('127.0.0.1', 8765))

    def test_aprobacion_rechaza_rol_modo_codigo_y_preparacion_invalida(self):
        """No registra un equipo si falla cualquier validación previa al intercambio firmado."""
        candidate = {'url': 'https://127.0.0.1:8767', 'fingerprint': 'a' * 64,
                     'invitation_id': 'invitacion-ficticia', 'name': 'PC ficticia'}
        with self.assertRaises(AccessDenied):
            self.manager.approve_computer(SimpleNamespace(read_only=True), self.master, candidate, 'ABCDEFGHJKMN', CLAVE)
        with self.assertRaises(ValueError):
            self.manager.approve_computer(self.s, self.master, candidate, 'ABCDEFGHJKMN', CLAVE)
        self.servidor_guardado()
        for code in ('corto', '!!!!!!!!!!!!'):
            with self.assertRaises(ValueError):
                self.manager.approve_computer(self.s, self.master, candidate, code, CLAVE)
        with self.assertRaises(AccessDenied):
            self.manager.approve_computer(self.s, self.user, candidate, 'ABCDEFGHJKMN', CLAVE)
        for hello in ({'invitation_id': 'otra'}, {'invitation_id': candidate['invitation_id'], 'nonce': 123}):
            with patch.object(module, 'request', return_value=hello), self.assertRaises(ValueError):
                self.manager.approve_computer(self.s, self.master, candidate, 'ABCDEFGHJKMN', CLAVE)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM authorized_devices').fetchone()[0], 0)

    def test_respuesta_firmada_con_identidad_distinta_no_autoriza(self):
        """Incluso una firma válida debe corresponder al equipo anunciado."""
        self.servidor_guardado()
        identity = DeviceIdentity(self.root / 'equipo.key')
        candidate = {'url': 'https://127.0.0.1:8767', 'fingerprint': 'a' * 64,
                     'invitation_id': 'invitacion-ficticia', 'name': 'PC ficticia'}
        hello = dict(invitation_id=candidate['invitation_id'], public_key=identity.public_key, nonce='nonce', node_id='cliente')
        def response(url, fingerprint, path, payload=None, **kwargs):
            """Firma la oferta real pero anuncia otro identificador de equipo."""
            if path == '/pair/hello':
                return hello
            return {'signature': identity.sign(module.canonical(payload['offer'])), 'device_id': 'otro-equipo'}
        with patch.object(module, 'request', side_effect=response), patch.object(module, 'local_address', return_value='127.0.0.1'):
            with self.assertRaisesRegex(AccessDenied, 'identidad'):
                self.manager.approve_computer(self.s, self.master, candidate, 'ABCDEFGHJKMN', CLAVE)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM authorized_devices').fetchone()[0], 0)

    def test_importacion_valida_conserva_copia_y_retira_secretos_traslado(self):
        """Una copia recibida sustituye la base solo después de verificar dueño e integridad."""
        self.s.close()
        received = self.snapshot('destino')
        self.manager._import_snapshot(received, 'destino')
        with closing(sqlite3.connect(self.manager.database)) as connection:
            settings = dict(connection.execute('SELECT key,value FROM system_settings'))
            self.assertEqual(settings, {'active_host_id': 'destino'})
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        backups = list((self.root / 'backups').glob('antes-de-traslado-*.db'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as previous:
            self.assertEqual(previous.execute('SELECT count(*) FROM users').fetchone()[0], 2)
        self.assertFalse(self.manager.database.with_suffix('.incoming.db').exists())

    def test_importacion_corrupta_propietario_ajeno_y_hash_invalido_no_sustituyen_base(self):
        """Toda copia inválida deja intacta la colección y limpia su archivo de entrada."""
        before = self.manager.database.read_bytes()
        wrong_hash = self.snapshot('destino') | {'sha256': '0' * 64}
        wrong_owner = self.snapshot('otro-nodo')
        for received in (wrong_hash, wrong_owner, {'database': base64.b64encode(b'no es SQLite').decode(), 'sha256': '0' * 64}):
            with self.assertRaises(ValueError):
                self.manager._import_snapshot(received, 'destino')
            self.assertEqual(self.manager.database.read_bytes(), before)
            self.assertFalse(self.manager.database.with_suffix('.incoming.db').exists())

    def test_importacion_a_directorio_nuevo_y_fallo_de_reemplazo(self):
        """Una importación nueva funciona; un fallo al confirmar no sustituye la colección anterior."""
        fresh = module.NetworkManager(self.root / 'nueva' / 'base.db', self.root / 'nueva.json')
        self.addCleanup(fresh.close)
        fresh._import_snapshot(self.snapshot('destino'), 'destino')
        with closing(sqlite3.connect(fresh.database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM users').fetchone()[0], 2)
        self.assertFalse((fresh.database.parent / 'backups').exists())
        before = self.manager.database.read_bytes()
        with patch.object(Path, 'replace', side_effect=PermissionError('fallo ficticio')):
            with self.assertRaises(PermissionError):
                self.manager._import_snapshot(self.snapshot('destino'), 'destino')
        self.assertEqual(self.manager.database.read_bytes(), before)
        self.assertFalse(self.manager.database.with_suffix('.incoming.db').exists())

    def test_sqlite_danada_con_hash_correcto_no_sustituye_coleccion(self):
        """Una huella correcta no sustituye la comprobación estructural de SQLite."""
        data = b'SQLite format 3\x00' + b'\x00' * 128
        received = {'database': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}
        before = self.manager.database.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            self.manager._import_snapshot(received, 'destino')
        self.assertEqual(self.manager.database.read_bytes(), before)
        self.assertFalse(self.manager.database.with_suffix('.incoming.db').exists())

    def test_promocion_exitosa_activa_solo_despues_de_importar(self):
        """El destino queda inactivo hasta tener una instantánea válida y configuración persistida."""
        self.s.close()
        target, controller = self.destino(), self.controlador()
        received = self.snapshot(target['node_id'])
        with patch.object(self.manager, '_start', return_value=controller), patch.object(module, 'request', return_value={'result': received}) as request:
            result = self.manager._promote(self.remoto(), self.master, CLAVE, target, object())
        self.assertTrue(controller.ready)
        self.assertEqual(result, load_settings(self.manager.config_path))
        self.assertEqual(request.call_args.args[3]['method'], 'network.transfer')

    def test_promocion_sin_respuesta_y_servidor_movido_no_activan_destino(self):
        """Una respuesta perdida conserva la sonda pendiente para recuperación presencial."""
        for response in (ValueError('red ficticia'), {'moved': True}):
            controller = self.controlador()
            with patch.object(self.manager, '_start', return_value=controller), patch.object(module, 'request') as request:
                if isinstance(response, Exception):
                    request.side_effect = response
                else:
                    request.return_value = response
                with self.assertRaisesRegex(ValueError, 'No se completó'):
                    self.manager._promote(self.remoto(), self.master, CLAVE, self.destino(), object())
            self.assertFalse(controller.ready)
            self.assertTrue(controller.settings['pending'])

    def test_importacion_fallida_pide_reversion_y_fallo_reversion_queda_pendiente(self):
        """No habilita dos servidores cuando falla importar o confirmar la reversión."""
        received = self.snapshot('destino')
        for rollback in ({'result': True}, ValueError('red ficticia')):
            controller = self.controlador()
            with patch.object(self.manager, '_start', return_value=controller), patch.object(self.manager, '_import_snapshot', side_effect=ValueError('copia inválida')), patch.object(module, 'request', side_effect=[{'result': received}, rollback]) as request:
                with self.assertRaises(ValueError) as error:
                    self.manager._promote(self.remoto(), self.master, CLAVE, self.destino(), object())
            self.assertEqual(request.call_args.args[3]['method'], 'network.rollback_transfer')
            self.assertFalse(controller.ready)
            self.assertTrue(controller.settings['pending'])
            if isinstance(rollback, Exception):
                self.assertIn('bloqueado', str(error.exception))

    def test_promocion_cancelada_y_doble_promocion_se_rechazan(self):
        """Una cancelación durante la importación nunca marca el destino como listo."""
        controller = self.controlador()
        controller.cancelled = True
        with patch.object(self.manager, '_start', return_value=controller), patch.object(self.manager, '_import_snapshot'), patch.object(module, 'request', side_effect=[{'result': self.snapshot('destino')}, {'result': True}]):
            with self.assertRaisesRegex(ValueError, 'canceló'):
                self.manager._promote(self.remoto(), self.master, CLAVE, self.destino(), object())
        self.manager.controllers.append(controller)
        with self.assertRaisesRegex(ValueError, 'Reinicia'):
            self.manager._promote(self.remoto(), self.master, CLAVE, self.destino(), object())

    def test_recuperacion_exige_maestro_y_traslado_pendiente(self):
        """No admite recuperar con credenciales falsas ni una operación inexistente."""
        with self.assertRaisesRegex(ValueError, 'credenciales'):
            self.manager.recover_pending_transfer('V-12345678', 'Incorrecta#2026')
        with self.assertRaisesRegex(ValueError, 'No existe'):
            self.manager.recover_pending_transfer('V-12345678', CLAVE)

    def test_recuperacion_no_habilita_host_si_destino_activo_o_sin_sesion_original(self):
        """La recuperación consulta al destino antes de restaurar la propiedad."""
        with self.s.connection:
            self.s.connection.executemany('INSERT INTO system_settings(key,value) VALUES(?,?)',
                [('active_host_id', 'destino'), ('active_host_url', 'https://127.0.0.1:8766'), ('active_host_pin', 'b' * 64),
                 ('transfer_rollback_hash', 'huella-ficticia'), ('transfer_cancel_token', 'cancelacion-ficticia')])
        with self.assertRaisesRegex(ValueError, 'sesión original'):
            self.manager.recover_pending_transfer('V-12345678', CLAVE)
        controller = SimpleNamespace(ready=True, settings=dict(self.manager.settings), _restore_owner=Mock(), close=Mock())
        self.manager.controllers.append(controller)
        with patch.object(module, 'request', return_value={'cancelled': False, 'node_id': 'destino'}):
            with self.assertRaisesRegex(ValueError, 'ya está activo'):
                self.manager.recover_pending_transfer('V-12345678', CLAVE)
        controller._restore_owner.assert_not_called()
        with patch.object(module, 'request', return_value={'cancelled': True, 'node_id': 'destino'}):
            self.manager.recover_pending_transfer('V-12345678', CLAVE)
        self.assertEqual(controller._restore_owner.call_args.args[1], 'huella-ficticia')

    def test_reinicio_tras_formateo_cierra_controladores_y_borra_conexion(self):
        """Volver al modo local no conserva una dirección remota ni receptores abiertos."""
        self.manager.follow_server({'server_url': 'https://127.0.0.1:8765', 'fingerprint': 'a' * 64})
        receiver, controller = Mock(), Mock()
        self.manager.receiver = receiver
        self.manager.controllers.append(controller)
        self.manager.reiniciar_tras_formateo()
        receiver.close.assert_called_once()
        controller.close.assert_called_once()
        self.assertEqual(self.manager.describe()['mode'], 'local')
        self.assertEqual(self.manager.settings['fingerprint'], '')
