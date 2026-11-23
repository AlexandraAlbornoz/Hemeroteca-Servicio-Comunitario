"""Comprueba registro, código único y recuperación por respuestas sin datos reales."""
import time
import unittest

from hemeroteca.config.settings import ROLES, SECURITY_QUESTIONS
from hemeroteca.main import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.recovery_service import RegistrationResult
from hemeroteca.ui.tareas import materializar


class PruebasRecuperacionSeguridad(unittest.TestCase):
    """Ejercita cada método con los tres perfiles y exige restablecimiento seguro."""

    @classmethod
    def setUpClass(cls):
        """Crea cuentas y códigos artificiales para una semilla independiente."""
        cls.semilla = create_services(':memory:')
        cls.contrasena = 'Inicial!2026'
        cls.respuestas = ('Luna', 'María', 'Pecas')
        cls.preguntas = tuple(zip(SECURITY_QUESTIONS[:3], cls.respuestas))
        cls.registros = [cls.semilla.auth.create_master('Maestro temporal', 'V-700001', cls.contrasena, cls.preguntas)]
        for numero, perfil in ((700002, ROLES[1]), (700003, ROLES[2])):
            cls.registros.append(cls.semilla.users.register_user('Titular temporal', f'V-{numero}', cls.contrasena, cls.preguntas, role=perfil))

    @classmethod
    def tearDownClass(cls):
        """Libera la semilla al finalizar las verificaciones."""
        cls.semilla.close()

    def setUp(self):
        """Copia la semilla para que cada caso empiece con códigos vigentes."""
        self.servicios = create_services(':memory:')
        self.semilla.connection.backup(self.servicios.connection)

    def tearDown(self):
        """Cierra la conexión propia del caso de prueba."""
        self.servicios.close()

    def test_resultado_registro_conserva_codigo_al_cruzar_hilos(self):
        """El coordinador conserva el NamedTuple que utiliza la pantalla del código."""
        original = RegistrationResult(42, 'HMR-CODIGO-ARTIFICIAL')
        recibido = materializar(original)
        self.assertIsInstance(recibido, RegistrationResult)
        self.assertEqual(recibido.recovery_code, original.recovery_code)
        self.assertEqual(materializar([original])[0].user_id, 42)

    def test_preguntas_recuperan_los_tres_perfiles(self):
        """Las respuestas permiten cambiar la contraseña y recibir un código nuevo."""
        for numero, registro in zip((700001, 700002, 700003), self.registros):
            with self.subTest(documento=numero):
                documento = f'V-{numero}'
                usuario = self.servicios.auth.autenticar_con_preguntas(documento, ('  LUNA ', ' MARÍA ', 'Pecas'))
                self.assertTrue(usuario['must_change_password'])
                with self.assertRaises(AccessDenied):
                    self.servicios.periodicos.search_issues(usuario)
                nueva = f'Nueva!{numero}'
                actualizado = self.servicios.auth.change_password(usuario, '', nueva)
                self.assertIn('_new_recovery_code', actualizado)
                self.assertNotEqual(actualizado['_new_recovery_code'], registro.recovery_code)
                self.assertEqual(self.servicios.auth.authenticate(documento, nueva)['id'], registro.user_id)
                with self.assertRaises(AccessDenied):
                    self.servicios.auth.authenticate_with_code(documento, registro.recovery_code)
                recuperado = self.servicios.auth.authenticate_with_code(documento, actualizado['_new_recovery_code'])
                self.assertTrue(recuperado['must_change_password'])

    def test_codigo_sigue_recuperando_sin_respuestas(self):
        """La alternativa por código no obliga a conocer las respuestas de seguridad."""
        registro = self.registros[2]
        usuario = self.servicios.auth.authenticate_with_code('V-700003', registro.recovery_code)
        actualizado = self.servicios.auth.change_password(usuario, '', 'Otra!2026')
        self.assertEqual(self.servicios.auth.authenticate('V-700003', 'Otra!2026')['id'], registro.user_id)
        self.assertTrue(actualizado['_new_recovery_code'].startswith('HMR-'))

    def test_respuesta_incorrecta_no_cambia_credenciales(self):
        """Un fallo conserva la cuenta y no registra respuestas en auditoría."""
        antes = dict(self.servicios.connection.execute("SELECT * FROM users WHERE document='V-700003'").fetchone())
        with self.assertRaises(AccessDenied):
            self.servicios.auth.autenticar_con_preguntas('V-700003', ('Luna', 'NO-REGISTRAR-ESTO', 'Pecas'))
        despues = dict(self.servicios.connection.execute("SELECT * FROM users WHERE document='V-700003'").fetchone())
        self.assertEqual(antes, despues)
        eventos = self.servicios.connection.execute('SELECT action FROM audit').fetchall()
        self.assertFalse(any('NO-REGISTRAR-ESTO' in fila[0] for fila in eventos))

    def test_cinco_fallos_bloquean_preguntas_pero_no_codigo(self):
        """El bloqueo persiste en SQLite y afecta solo al método que recibió los fallos."""
        for _ in range(5):
            with self.assertRaises(AccessDenied):
                self.servicios.auth.autenticar_con_preguntas('V-700003', ('Error', 'Error', 'Error'))
        with self.assertRaisesRegex(AccessDenied, 'quince'):
            self.servicios.auth.autenticar_con_preguntas('V-700003', self.respuestas)
        fila = self.servicios.connection.execute('SELECT locked_until FROM auth_failures').fetchone()
        self.assertGreater(fila[0], int(time.time()))
        usuario = self.servicios.auth.authenticate_with_code('V-700003', self.registros[2].recovery_code)
        self.assertTrue(usuario['must_change_password'])

    def test_preguntas_no_revelan_respuestas(self):
        """El formulario recibe únicamente los textos de las tres preguntas."""
        preguntas = self.servicios.auth.obtener_preguntas_recuperacion('V-700003')
        self.assertEqual(preguntas, list(SECURITY_QUESTIONS[:3]))
        self.assertFalse(any(respuesta in preguntas for respuesta in self.respuestas))

    def test_cuenta_desactivada_no_se_recupera(self):
        """Las respuestas válidas no reactivan una cuenta suspendida."""
        self.servicios.connection.execute("UPDATE users SET active=0 WHERE document='V-700003'")
        self.servicios.connection.commit()
        with self.assertRaises(AccessDenied):
            self.servicios.auth.autenticar_con_preguntas('V-700003', self.respuestas)

    def test_tres_respuestas_obligatorias_y_tildes(self):
        """Rechaza entradas incompletas y no elimina tildes de las respuestas."""
        for respuestas in ([], ['Luna'], ['Luna', 'María', 'Pecas', 'Otra'], ['Luna', '', 'Pecas']):
            with self.assertRaises(ValueError):
                self.servicios.auth.autenticar_con_preguntas('V-700003', respuestas)
        with self.assertRaises(AccessDenied):
            self.servicios.auth.autenticar_con_preguntas('V-700003', ('Luna', 'Maria', 'Pecas'))

    def test_codigo_propio_se_renueva_sin_cambiar_contrasena(self):
        """Un titular que no vio su código puede generar otro confirmando su contraseña."""
        usuario = self.servicios.auth.authenticate('V-700003', self.contrasena)
        with self.assertRaises(AccessDenied):
            self.servicios.recovery.renovar_codigo_propio(usuario, 'Incorrecta')
        codigo = self.servicios.recovery.renovar_codigo_propio(usuario, self.contrasena)
        self.assertNotEqual(codigo, self.registros[2].recovery_code)
        self.assertEqual(self.servicios.auth.authenticate('V-700003', self.contrasena)['id'], usuario['id'])
        self.assertTrue(self.servicios.auth.authenticate_with_code('V-700003', codigo)['must_change_password'])

    def test_api_anterior_recupera_por_preguntas(self):
        """Los nombres anteriores dejan de rechazar siempre y delegan al mismo flujo seguro."""
        self.assertEqual(self.servicios.recovery.questions_for_recovery('V-700003'), list(SECURITY_QUESTIONS[:3]))
        actualizado = self.servicios.recovery.recover_password('V-700003', self.respuestas, 'Legado!2026')
        self.assertIn('_new_recovery_code', actualizado)
        self.assertEqual(self.servicios.auth.authenticate('V-700003', 'Legado!2026')['id'], self.registros[2].user_id)
