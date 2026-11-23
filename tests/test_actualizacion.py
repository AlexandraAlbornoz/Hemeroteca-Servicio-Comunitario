"""Límites nuevos, compatibilidad de cuentas, privacidad y formateo protegido."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hemeroteca.config.settings import NATIONAL, ROLES, SECURITY_QUESTIONS
from hemeroteca.main import create_services
from hemeroteca.network.configuration import load_settings, save_settings
from hemeroteca.network.manager import NetworkManager
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.utils.security import validate_password, prepare_security_questions, password_hash, password_matches
from hemeroteca.utils.validaciones import validar_nombre, validar_documento_nuevo, validar_numero, validar_edicion


class PruebasActualizacion(unittest.TestCase):
    """Comprueba límites y rechazos sin abrir una base de datos del usuario."""

    @classmethod
    def setUpClass(cls):
        """Prepara cuentas artificiales compatibles con las reglas nuevas."""
        cls.semilla = create_services(':memory:')
        cls.clave = 'Clave#2026'
        cls.preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('María', 'José', 'Caracas')))
        cls.semilla.auth.create_master('Responsable Prueba', 'V-100000', cls.clave, cls.preguntas)
        cls.semilla.users.register_user('Persona Prueba', 'E-1000000', cls.clave, cls.preguntas)

    @classmethod
    def tearDownClass(cls):
        """Libera la semilla después de todos los escenarios."""
        cls.semilla.close()

    def setUp(self):
        """Restaura un estado aislado con maestro y usuario regular."""
        self.s = create_services(':memory:')
        self.semilla.connection.backup(self.s.connection)
        self.maestro = self.s.auth.authenticate('V-100000', self.clave)
        self.usuario = self.s.auth.authenticate('E-1000000', self.clave)

    def tearDown(self):
        """Cierra únicamente la base de prueba."""
        self.s.close()

    def test_limites_cedula(self):
        """Verifica ambos tipos, longitudes y bloqueo de pasaportes e inyecciones."""
        for valor in ('V-123456', 'V-12345678', 'E-1234567', 'E-12345678', 'V-000001'):
            self.assertEqual(validar_documento_nuevo(valor), valor)
        for valor in ('V-12345', 'E-123456', 'V-123456789', 'V-123 456', 'V-12A456', ' V-123456', 'P-CO-AB12345', "V-' OR 1=1", 'V-１２３４５６'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                validar_documento_nuevo(valor)

    def test_limites_contrasena(self):
        """Comprueba 8–128 caracteres y cada categoría obligatoria."""
        for valor in ('Abcd#123', 'Hemeroteca#2026', 'Abcdefghi#12345', 'Abcdefghij#123456', 'A#1' + 'b' * 125):
            self.assertEqual(validate_password(valor), valor)
        for valor in ('Ab#1234', 'A#1' + 'b' * 126, 'abcdefgh#123', 'ABCDEFGH#123', 'Abcdefgh123', 'Abcdefgh###', 'Abcd# 123', 'Abcd#123\n'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                validate_password(valor)

    def test_nombre_y_normalizacion(self):
        """Normaliza tildes e iniciales y rechaza números, controles y nombres incompletos."""
        self.assertEqual(validar_nombre('  maría   péREZ  '), 'María Pérez')
        for nombre in ('', 'Ana', 'A Pérez', 'Ana P3rez', 'Ana <Pérez>', 'Ana\nPérez'):
            with self.subTest(nombre=nombre), self.assertRaises(ValueError):
                validar_nombre(nombre)

    def test_respuestas_limites_hash_y_sal(self):
        """Las respuestas nuevas tienen hasta 50 caracteres y hashes con sales distintas."""
        preparado = prepare_security_questions(self.preguntas)
        otro = prepare_security_questions(self.preguntas)
        self.assertTrue(password_matches('maría', preparado[1]))
        self.assertNotEqual(preparado[1], otro[1])
        for respuesta in ('', ' ', 'a', '!!', 'x' * 51, 'hola\x00mundo'):
            with self.subTest(respuesta=respuesta), self.assertRaises(ValueError):
                prepare_security_questions(((SECURITY_QUESTIONS[0], respuesta),) + self.preguntas[1:])

    def valores(self, estante='1', gaveta=''):
        """Construye un ejemplar con ubicación variable."""
        return (NATIONAL[0], 'Nacional', 'Matutina', 2020, 2, 29, '1', estante, gaveta, 'Disponible')

    def test_ubicacion_alternativa(self):
        """Permite solo estante, solo gaveta o ambos y rechaza ubicaciones vacías."""
        for estante, gaveta in (('1', ''), ('', '2'), ('1', '2')):
            self.s.periodicos.save_record(self.maestro, self.valores(estante, gaveta))
            self.s.connection.execute('DELETE FROM issues')
            self.s.connection.commit()
        for estante, gaveta in (('', ''), ('A', '2'), ('1', 'G-2'), (' ', '2')):
            with self.subTest(estante=estante, gaveta=gaveta), self.assertRaises(ValueError):
                self.s.periodicos.save_record(self.maestro, self.valores(estante, gaveta))

    def test_edicion_y_numero(self):
        """No admite código arbitrario ni símbolos como número de ejemplar."""
        for valor in ('Matutina', 'Edición Especial', 'Edición 2'):
            validar_edicion(valor)
        for valor in ('', '<script>', 'A', 'x' * 51):
            with self.assertRaises(ValueError):
                validar_edicion(valor)
        for valor in ('-2', '2.5', 'A2', '２', '1 2'):
            with self.assertRaises(ValueError):
                validar_numero(valor, 'Número')

    def test_contrasena_y_respuestas_antiguas_siguen_funcionando(self):
        """No bloquea contraseñas largas ni respuestas antiguas al autenticar."""
        anterior = 'Clave antigua larga 2025'
        self.s.connection.execute('UPDATE users SET password=? WHERE id=?', (password_hash(anterior), self.usuario['id']))
        self.s.connection.execute('UPDATE user_security SET answer_1=? WHERE user_id=?', (password_hash('x' * 100), self.usuario['id']))
        self.s.connection.commit()
        self.assertEqual(self.s.auth.authenticate('E-1000000', anterior)['id'], self.usuario['id'])
        self.assertTrue(self.s.auth.autenticar_con_preguntas('E-1000000', ('x' * 100, 'josé', 'caracas'))['must_change_password'])

    def test_solicitudes_rechazadas_se_pueden_reenviar(self):
        """Una rechazada permite reenviar; pendiente o activa no duplica avisos."""
        self.s.connection.execute('UPDATE users SET role=?,managed_permissions=1 WHERE id=?', (ROLES[1], self.usuario['id']))
        self.s.connection.commit()
        numero = self.s.requests.submit_request(self.usuario, 'Editar ejemplares', 'Trabajo de archivo')
        with self.assertRaises(ValueError):
            self.s.requests.submit_request(self.usuario, 'Editar ejemplares', 'Otra vez')
        self.s.requests.decide_request(self.maestro, numero, False, 'Revisar motivo')
        numero = self.s.requests.submit_request(self.usuario, 'Editar ejemplares', 'Motivo revisado')
        self.s.requests.decide_request(self.maestro, numero, True)
        with self.assertRaises(ValueError):
            self.s.requests.submit_request(self.usuario, 'Editar ejemplares', 'Ya activo')

    def test_solicitudes_globales_exigen_permiso_explicito(self):
        """El usuario regular no accede a solicitudes ni con un grant heredado."""
        self.s.connection.execute("INSERT INTO requests(user_id,permission,reason,created_at) VALUES(?,?,?,?)", (self.maestro['id'], 'Auditoría', 'Ejemplo ajeno', '2026-10-28'))
        self.s.connection.commit()
        with self.assertRaises(AccessDenied):
            self.s.requests.buscar_solicitudes(self.usuario)
        self.s.connection.execute('INSERT INTO grants VALUES(?,?)', (self.usuario['id'], 'Consultar solicitudes de todos'))
        self.s.connection.commit()
        with self.assertRaises(AccessDenied):
            self.s.requests.buscar_solicitudes(self.usuario)
        with self.assertRaises(AccessDenied):
            self.s.requests.decide_request(self.usuario, 1, True)

    def test_formateo_protegido_y_respaldo(self):
        """Exige al maestro, respalda y deja vacías las cuentas, datos y autorizaciones."""
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / 'prueba.db'
            configuracion = Path(temporal) / 'network.json'
            servicios = create_services(ruta)
            try:
                self.semilla.connection.backup(servicios.connection)
                maestro = servicios.auth.authenticate('V-100000', self.clave)
                usuario = servicios.auth.authenticate('E-1000000', self.clave)
                servicios.periodicos.save_record(maestro, self.valores())
                servicios.connection.execute("INSERT INTO authorized_devices VALUES(?,?,?,?,?,?,?)",
                                            ('cliente-ficticio', 'clave-ficticia', 'nodo-ficticio',
                                             'PC de prueba', 1, 'Maestro', '2026-11-03'))
                servicios.connection.execute("INSERT INTO device_nonces VALUES(?,?,?)",
                                            ('cliente-ficticio', 'nonce-ficticio', 100))
                servicios.connection.execute("INSERT INTO system_settings VALUES(?,?)",
                                            ('active_host_id', 'nodo-principal'))
                servicios.connection.commit()
                gestor = NetworkManager(ruta, configuracion)
                ajustes = dict(gestor.settings, mode='server', server_url='https://127.0.0.1:8765',
                               fingerprint='f' * 64)
                save_settings(ajustes, configuracion)
                gestor.settings = ajustes
                for actor, clave, confirmacion in ((usuario, self.clave, 'FORMATEAR HEMEROTECA'), (maestro, 'Incorrecta', 'FORMATEAR HEMEROTECA'), (maestro, self.clave, 'NO')):
                    with self.assertRaises(ValueError):
                        servicios.users.formatear_aplicacion(actor, clave, confirmacion)
                self.assertEqual(servicios.connection.execute('SELECT count(*) FROM issues').fetchone()[0], 1)
                copia = servicios.users.formatear_aplicacion(maestro, self.clave, 'FORMATEAR HEMEROTECA')
                gestor.reiniciar_tras_formateo()
                with closing(sqlite3.connect(copia)) as respaldo:
                    self.assertEqual(respaldo.execute('SELECT count(*) FROM users').fetchone()[0], 2)
                    self.assertEqual(respaldo.execute('SELECT count(*) FROM issues').fetchone()[0], 1)
                    self.assertEqual(respaldo.execute('SELECT count(*) FROM authorized_devices').fetchone()[0], 1)
                tablas = [fila[0] for fila in servicios.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for tabla in tablas:
                    with self.subTest(tabla=tabla):
                        self.assertEqual(servicios.connection.execute('SELECT count(*) FROM ' + tabla).fetchone()[0], 0)
                self.assertEqual(list(servicios.connection.execute('PRAGMA foreign_key_check')), [])
                self.assertTrue(servicios.auth.needs_setup())
                self.assertEqual(load_settings(configuracion)['mode'], 'local')
                self.assertEqual(load_settings(configuracion)['server_url'], '')
                reiniciado = gestor.services()
                try:
                    self.assertTrue(reiniciado.auth.needs_setup())
                    self.assertEqual(gestor.settings['mode'], 'local')
                finally:
                    reiniciado.close()
            finally:
                servicios.close()
