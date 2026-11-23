"""Contrato HTTP y sesiones del servidor, con SQLite real y transporte controlado."""
import base64
from collections import deque
from email.message import Message
import hashlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from hemeroteca.config.settings import SECURITY_QUESTIONS
from hemeroteca.network import server as module
from hemeroteca.network import configuration
from hemeroteca.network.devices import DeviceIdentity
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.container import create_services


class PruebasContratoHTTP(unittest.TestCase):
    """Ejecuta el manejador real sin sockets; no sustituye validación ni serialización."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.object(module, 'TLSHTTPServer') as http, patch.object(module, 'DeviceIdentity'):
            self.s = module.LANServer(self.root/'test.db', dict(bind='127.0.0.1', port=0, node_id='local', fingerprint='a'*64), Mock())
            self.handler = http.call_args.args[1]
        self.services = Mock()
        self.services.connection = Mock()
        self.services.connection.__enter__ = Mock()
        self.services.connection.__exit__ = Mock()
        self.actor = dict(id=1, password_version=1)
        self.services.auth.authenticate.return_value = self.actor
        self.services.periodicos.search_issues.return_value = {'items': [], 'total': 0}
        self.guard = Mock()
        self.guard.__enter__ = Mock()
        self.guard.__exit__ = Mock()
        for name, value in [('create_services', self.services), ('database_guard', self.guard), ('verify_device', 'device')]:
            mocked = patch.object(module, name, return_value=value).start()
            setattr(self, name, mocked)
        self.addCleanup(patch.stopall)
        self.redirect = patch.object(self.s, 'redirect', return_value=None).start()
        self.session = patch.object(self.s, 'actor_from_token', return_value=self.actor).start()
        self.new = patch.object(self.s, 'new_session', return_value='sesion-ficticia').start()

    def call(self, payload=None, *, path='/rpc', raw=None, headers=None, get=False):
        h = self.handler.__new__(self.handler)
        h.path, h.client_address = path, ('127.0.0.1', 12345)
        body = json.dumps(payload if payload is not None else {'method': 'auth.needs_setup'}).encode() if raw is None else raw
        h.headers = Message()
        for k, v in {'Content-Length': str(len(body)), 'Content-Type': 'application/json', 'Authorization': 'Bearer '+('t'*48), **(headers or {})}.items():
            h.headers[k] = v
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h.send_response, h.send_header, h.end_headers = Mock(), Mock(), Mock()
        (h.do_GET if get else h.do_POST)()
        return h.send_response.call_args.args[0], json.loads(h.wfile.getvalue()), h

    def test_health_y_ruta_desconocida(self):
        self.assertEqual(self.call(path='/health', get=True)[:2], (200, {'node_id': 'local', 'ready': True}))
        self.assertEqual(self.call(path='/otro', get=True)[0], 404)
        self.assertEqual(self.call(path='/otro')[0], 503)
        self.s.ready = False
        self.assertEqual(self.call()[0], 503)
        self.create_services.assert_not_called()

    def test_cabeceras_sin_cache_y_datos_secretos_no_salen(self):
        self.services.auth.authenticate.return_value = dict(self.actor, password='privado', nested={'answer_1': 'privado', 'ok': [1]})
        status, data, h = self.call({'method': 'auth.authenticate', 'args': ['V-12345678', 'Ficticia#2026']})
        self.assertEqual(status, 200)
        self.assertNotIn('password', data['result'])
        self.assertEqual(data['result']['nested'], {'ok': [1]})
        self.assertEqual(data['token'], 'sesion-ficticia')
        h.send_header.assert_any_call('Cache-Control', 'no-store')
        h.send_header.assert_any_call('Content-Length', str(len(h.wfile.getvalue())))
        self.services.close.assert_called_once()
        self.guard.__exit__.assert_called_once()

    def test_json_longitud_tipo_y_estructura_invalidos(self):
        cases = [(b'[]', {}), (b'{', {}), (b'{}', {'Content-Length': 'no'}), (b'{}', {'Content-Length': '0'}),
                 (b'{}', {'Content-Length': str(module.MAX_REQUEST+1)}), (b'{}', {'Content-Type': 'text/plain'}),
                 (b'\xff', {})]
        for raw, headers in cases:
            with self.subTest(raw=raw, headers=headers):
                self.assertEqual(self.call(raw=raw, headers=headers)[0], 400)
        self.create_services.assert_not_called()
        self.assertTrue(self.s._slots.acquire(blocking=False))
        self.s._slots.release()

    def test_no_admite_metodos_ni_argumentos_privados(self):
        for payload, status in [({'method': 'auth.create_master'}, 401), ({'method': 'auth.needs_setup', 'args': {}}, 401),
                                ({'method': 'auth.needs_setup', 'kwargs': []}, 401),
                                ({'method': 'auth.needs_setup', 'kwargs': {'actor': {}}}, 400),
                                ({'method': 'auth.needs_setup', 'kwargs': {'_internal': True}}, 400),
                                ({'method': []}, 400)]:
            with self.subTest(payload=payload):
                self.assertEqual(self.call(payload)[0], status)
        self.services.auth.needs_setup.assert_not_called()

    def test_preparacion_remota_siempre_falsa(self):
        self.assertEqual(self.call()[:2], (200, {'result': False}))
        self.session.assert_not_called()

    def test_equipo_firma_y_redireccion(self):
        self.assertEqual(self.call(path='/device/verify')[:2], (200, {'authorized': True}))
        self.redirect.return_value = {'moved': True, 'server_url': 'https://127.0.0.1:8888'}
        self.assertEqual(self.call()[1], self.redirect.return_value)
        self.assertEqual(self.call(path='/device/verify')[0], 401)
        self.verify_device.side_effect = AccessDenied('firma inválida')
        self.assertEqual(self.call()[0], 401)

    def test_limite_general_y_cupos_no_abren_servicios(self):
        with patch.object(self.s, 'allow_request', return_value=False):
            self.assertEqual(self.call()[0], 429)
        for _ in range(12):
            self.assertTrue(self.s._slots.acquire(blocking=False))
        self.assertEqual(self.call()[0], 429)
        for _ in range(12):
            self.s._slots.release()
        self.create_services.assert_not_called()

    def test_limite_registro_por_dispositivo(self):
        with patch.object(self.s, 'allow_request', side_effect=[True, False]) as limit:
            self.assertEqual(self.call({'method': 'users.register_user'})[0], 429)
            self.assertEqual(limit.call_args.kwargs['group'], 'registration')
        self.services.users.register_user.assert_not_called()

    def test_autorizacion_distingue_sesion_de_permisos(self):
        self.session.side_effect = AccessDenied('sesión vencida')
        self.assertEqual(self.call({'method': 'periodicos.search_issues'})[0], 401)
        self.session.side_effect = None
        self.services.periodicos.search_issues.side_effect = AccessDenied('sin permiso')
        self.assertEqual(self.call({'method': 'periodicos.search_issues'})[0], 403)

    def test_errores_de_datos_y_servidor_limpian_recursos(self):
        for error, status in [(ValueError('dato inválido'), 400), (TypeError('detalle interno'), 400),
                              (sqlite3.IntegrityError('tabla interna'), 400), (sqlite3.OperationalError('ruta privada'), 500),
                              (OSError('ruta privada'), 500), (RuntimeError('interno'), 500)]:
            with self.subTest(error=error):
                self.services.close.reset_mock()
                self.guard.__exit__.reset_mock()
                self.services.periodicos.search_issues.side_effect = error
                code, data, _ = self.call({'method': 'periodicos.search_issues'})
                self.assertEqual(code, status)
                self.assertNotIn('privada', data['error'])
                self.services.close.assert_called_once()
                self.guard.__exit__.assert_called_once()

    def test_reporte_libera_bloqueo_antes_del_trabajo(self):
        def generate(actor):
            self.guard.__exit__.assert_called_once()
            return {'content': 'pdf-ficticio'}
        self.services.reports.generate.side_effect = generate
        self.assertEqual(self.call({'method': 'reports.generate'})[0], 200)
        self.guard.__exit__.assert_called_once()

    def test_logout_borra_hash_y_no_token_en_claro(self):
        self.assertEqual(self.call({'method': 'auth.logout'})[1], {'result': True})
        args = self.services.connection.execute.call_args.args
        self.assertEqual(args[1], (hashlib.sha256(('t'*48).encode()).hexdigest(),))

    def test_alias_traslado_y_reversion_enrutan_control(self):
        for method, attr in [('network.transfer', 'transfer'), ('hemeroteca.network.transfer', 'transfer'),
                             ('network.rollback_transfer', 'rollback_transfer'), ('hemeroteca.network.rollback_transfer', 'rollback_transfer')]:
            with self.subTest(method=method), patch.object(self.s, attr, return_value=True) as operation:
                self.assertEqual(self.call({'method': method, 'args': ['dato']})[1], {'result': True})
                operation.assert_called_once_with(self.services, self.actor, 'dato')
                self.assertTrue(self.database_guard.call_args.kwargs['exclusive'])

    def test_cancelacion_valida_invalida_y_carga_malformada(self):
        self.s.ready = False
        self.assertEqual(self.call({'token': self.s.cancel_token}, path='/cancel-transfer')[1]['cancelled'], True)
        for payload in [[], {'token': 'incorrecto'}, {'token': 123}]:
            self.assertEqual(self.call(payload, path='/cancel-transfer')[0], 400)
        self.assertEqual(self.call(path='/cancel-transfer', raw=b'{')[0], 400)
        self.assertEqual(self.call(path='/cancel-transfer', headers={'Content-Length': '0'})[0], 400)
        self.s.ready = True
        self.assertFalse(self.call({'token': self.s.cancel_token}, path='/cancel-transfer')[1]['cancelled'])

    def test_json_muy_anidado_se_rechaza_tambien_al_cancelar(self):
        raw = b'['*15000+b'0'+b']'*15000
        for path in ['/rpc', '/cancel-transfer']:
            with self.subTest(path=path):
                self.assertEqual(self.call(path=path, raw=raw)[0], 400)

    def test_cerrar_sin_iniciar_no_llama_shutdown_bloqueante(self):
        self.s.close()
        self.s.httpd.shutdown.assert_not_called()
        self.s.httpd.server_close.assert_called_once()

    def test_cierre_iniciado_espera_al_hilo_y_es_repetible(self):
        self.s.thread = Mock()
        self.s.thread.is_alive.side_effect = [True, False]
        self.s.close()
        self.s.close()
        self.s.httpd.shutdown.assert_called_once()
        self.s.thread.join.assert_called_once()


class PruebasEstadoServidor(unittest.TestCase):
    """Sesiones y traslados con permisos y transacciones del producto."""

    @classmethod
    def setUpClass(cls):
        cls.seed = create_services(':memory:')
        cls.clave = 'Prueba#2026'
        cls.seed.auth.create_master('Maestra Ficticia', 'V-12345678', cls.clave,
                                    tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'Sol', 'Mar'))))

    @classmethod
    def tearDownClass(cls):
        cls.seed.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'hemeroteca.db'
        self.services = create_services(self.db, node_id='local')
        self.addCleanup(self.services.close)
        self.seed.connection.backup(self.services.connection)
        self.actor = self.services.auth.authenticate('V-12345678', self.clave)
        self.settings = dict(bind='127.0.0.1', port=0, node_id='local', mode='server',
                             server_url='https://127.0.0.1:8888', fingerprint='a'*64)
        with patch.object(module, 'TLSHTTPServer'), patch.object(module, 'DeviceIdentity', return_value=DeviceIdentity(self.root/'device.key')):
            self.s = module.LANServer(self.db, self.settings, Mock(), config_path=self.root/'network.json')

    def values(self):
        return dict(self.services.connection.execute('SELECT key,value FROM system_settings'))

    def test_sesion_guarda_hash_expira_y_se_liga_al_equipo(self):
        with patch.object(module.time, 'time', return_value=1000):
            token = self.s.new_session(self.services, self.actor, 'equipo')
            row = self.services.connection.execute('SELECT * FROM api_sessions').fetchone()
            self.assertEqual(row['token_hash'], hashlib.sha256(token.encode()).hexdigest())
            self.assertEqual(row['expires_at'], 1000+module.SESSION_SECONDS)
            self.assertEqual(self.s.actor_from_token(self.services, 'Bearer '+token, 'equipo')['id'], self.actor['id'])
            with self.assertRaises(AccessDenied):
                self.s.actor_from_token(self.services, 'Bearer '+token, 'otro')
        with patch.object(module.time, 'time', return_value=1000+module.SESSION_SECONDS):
            with self.assertRaises(AccessDenied):
                self.s.actor_from_token(self.services, 'Bearer '+token, 'equipo')
            self.s.new_session(self.services, self.actor, 'equipo')
            self.assertEqual(self.services.connection.execute('SELECT count(*) FROM api_sessions').fetchone()[0], 1)

    def test_token_formato_cuenta_desactivada_y_version_cambiada(self):
        for value in ['', 'Basic abc', 'Bearer corto', 'Bearer '+'x'*257, 'Bearer '+'x'*48]:
            with self.subTest(value=value), self.assertRaises(AccessDenied):
                self.s.actor_from_token(self.services, value, 'equipo')
        token = self.s.new_session(self.services, self.actor, 'equipo')
        for sql in ['UPDATE users SET active=0', 'UPDATE users SET active=1,password_version=password_version+1']:
            with self.services.connection:
                self.services.connection.execute(sql)
            with self.assertRaises(AccessDenied):
                self.s.actor_from_token(self.services, 'Bearer '+token, 'equipo')

    def test_sesion_recuperacion_exige_generacion_vigente(self):
        actor = dict(self.actor, _auth_method='recovery', _recovery_generation=1)
        token = self.s.new_session(self.services, actor, 'equipo')
        with patch.object(self.services.access, '_recovery_valid', return_value=True):
            self.assertEqual(self.s.actor_from_token(self.services, 'Bearer '+token, 'equipo')['_recovery_generation'], 1)
        with patch.object(self.services.access, '_recovery_valid', return_value=False), self.assertRaises(AccessDenied):
            self.s.actor_from_token(self.services, 'Bearer '+token, 'equipo')

    def test_limites_por_grupo_expiran_y_limpian_origenes_antiguos(self):
        with patch.object(module.time, 'monotonic', return_value=100):
            self.assertTrue(self.s.allow_request('ip', limit=1))
            self.assertFalse(self.s.allow_request('ip', limit=1))
            self.assertTrue(self.s.allow_request('ip', group='registro', limit=1))
        self.s._rates.update({('requests', str(i)): deque([0]) for i in range(260)})
        with patch.object(module.time, 'monotonic', return_value=161):
            self.assertTrue(self.s.allow_request('ip', limit=1))
            self.assertEqual(len(self.s._rates), 1)
        self.s._rates[('requests', 'ip')] = deque([100])
        with patch.object(module.time, 'monotonic', return_value=161):
            self.assertTrue(self.s.allow_request('ip', limit=1))

    def test_public_value_limpia_filas_listas_y_registro(self):
        row = self.services.connection.execute('SELECT * FROM users').fetchone()
        data = module.public_value([row, (1, 2), {3}])
        self.assertNotIn('password', data[0])
        result = module.RegistrationResult(10, 'HMR-FICTICIO')
        self.assertEqual(module.public_value(result), {'user_id': 10, 'recovery_code': 'HMR-FICTICIO'})

    def transfer(self):
        with patch.object(module, 'request', return_value={'node_id': 'nuevo', 'ready': False}):
            return self.s.transfer(self.services, self.actor, 'https://127.0.0.1:9999', 'b'*64, 'nuevo', self.clave, 'c'*48)

    def test_traslado_exporta_sqlite_y_redirige_las_consultas(self):
        self.assertIsNone(self.s.redirect(self.services))
        result = self.transfer()
        content = base64.b64decode(result['database'])
        self.assertTrue(content.startswith(b'SQLite format 3'))
        self.assertEqual(result['sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(self.s.redirect(self.services)['server_url'], 'https://127.0.0.1:9999')
        self.assertEqual(self.values()['transfer_rollback_hash'], hashlib.sha256(result['rollback_key'].encode()).hexdigest())
        self.assertEqual(json.loads((self.root/'network.json').read_text())['mode'], 'client')

    def test_traslado_rechaza_destino_token_y_estado(self):
        for node, token in [('local', 'c'*48), (None, 'c'*48), ('x'*101, 'c'*48), ('nuevo', 'corto')]:
            with self.subTest(node=node), self.assertRaises(ValueError):
                self.s.transfer(self.services, self.actor, 'https://127.0.0.1:9999', 'b'*64, node, self.clave, token)
        for remote in [{'node_id': 'otro', 'ready': False}, {'node_id': 'nuevo', 'ready': True}]:
            with patch.object(module, 'request', return_value=remote), self.assertRaises(ValueError):
                self.s.transfer(self.services, self.actor, 'https://127.0.0.1:9999', 'b'*64, 'nuevo', self.clave, 'c'*48)
        self.assertNotIn('transfer_rollback_hash', self.values())

    def test_fallo_snapshot_restaura_propietario(self):
        with patch.object(module, 'MAX_DATABASE', 1), self.assertRaisesRegex(ValueError, '64 MiB'):
            self.transfer()
        self.assertEqual(self.values()['active_host_id'], 'local')
        self.assertNotIn('transfer_rollback_hash', self.values())

    def test_reversion_exige_clave_y_cancelacion_del_destino(self):
        result = self.transfer()
        with self.assertRaises(AccessDenied):
            self.s.rollback_transfer(self.services, self.actor, self.clave, 'equivocada')
        with patch.object(module, 'request', return_value={'node_id': 'nuevo', 'cancelled': False}), self.assertRaises(AccessDenied):
            self.s.rollback_transfer(self.services, self.actor, self.clave, result['rollback_key'])
        with patch.object(module, 'request', return_value={'node_id': 'nuevo', 'cancelled': True}):
            self.assertTrue(self.s.rollback_transfer(self.services, self.actor, self.clave, result['rollback_key']))
        self.assertEqual(self.values()['active_host_id'], 'local')
        self.assertNotIn('transfer_cancel_token', self.values())
        self.assertTrue(self.s.rollback_transfer(self.services, self.actor, self.clave, result['rollback_key']))

    def test_reversion_no_sobrescribe_otro_traslado(self):
        self.transfer()
        with self.assertRaises(AccessDenied):
            self.s._restore_owner(self.services, 'otro-hash')
        self.assertEqual(self.values()['active_host_id'], 'nuevo')


class PruebasHTTPSTransporte(unittest.TestCase):
    """Comprueba el protocolo y el cierre con TLS real solamente en loopback."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.object(configuration, 'NETWORK_TLS_PATH', self.root/'tls'):
            context, fingerprint = configuration.ensure_certificate()
        with patch.object(module, 'DeviceIdentity', return_value=DeviceIdentity(self.root/'device.key')):
            self.s = module.LANServer(self.root/'test.db', dict(bind='127.0.0.1', port=0, node_id='tls-local', fingerprint=fingerprint), context)
        self.addCleanup(self.s.close)
        self.context = ssl.create_default_context(cafile=str(self.root/'tls/server.pem'))
        # El certificado LAN no declara DNS; se confía solo en la CA temporal exacta.
        self.context.check_hostname = False

    def call(self, path, body=None):
        conn = http.client.HTTPSConnection('127.0.0.1', self.s.httpd.server_port, context=self.context, timeout=3)
        try:
            conn.request('GET' if body is None else 'POST', path, body=body, headers={'Content-Type': 'application/json'})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_health_real_y_cierre_sin_hilos_pendientes(self):
        self.s.start()
        self.assertEqual(self.call('/health'), (200, {'node_id': 'tls-local', 'ready': True}))
        self.s.close()
        self.assertFalse(self.s.thread.is_alive())

    def test_json_anidado_real_responde_400_y_sigue_atendiendo(self):
        self.s.start()
        for path in ['/rpc', '/cancel-transfer']:
            self.assertEqual(self.call(path, b'['*15000+b'0'+b']'*15000)[0], 400)
        self.assertEqual(self.call('/health')[0], 200)

    def test_cierre_real_antes_de_start_no_se_bloquea(self):
        worker = threading.Thread(target=self.s.close, daemon=True)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive(), 'El cierre previo a start quedó bloqueado')

