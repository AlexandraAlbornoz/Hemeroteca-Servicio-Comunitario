"""Formato hmbackup: criptografía real, límites, metadatos y reconstrucción SQLite."""
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from hemeroteca.config.settings import SECURITY_QUESTIONS, NATIONAL
from hemeroteca.services.container import create_services
from hemeroteca.services import backup_archive as module


class PruebasFormatoRespaldos(unittest.TestCase):
    """Ataca entradas malformadas sin modificar ninguna colección del usuario."""

    @classmethod
    def setUpClass(cls):
        """Prepara una colección sintética y una clave scrypt real para la batería."""
        cls.seed = create_services(':memory:')
        questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        cls.seed.auth.create_master('Persona Ficticia', 'V-12345678', 'Prueba#2026', questions)
        actor = cls.seed.auth.authenticate('V-12345678', 'Prueba#2026')
        cls.seed.periodicos.save_record(actor, (NATIONAL[0], 'Nacional', 'Matutina', 2020, 1, 1, '1', '1', '', 'Disponible'))
        cls.salt = secrets.token_bytes(16)
        cls.key = module.derive_key('RespaldoFicticio#2026', cls.salt)
        cls.data = module.snapshot(cls.seed.connection)

    @classmethod
    def tearDownClass(cls):
        """Cierra la semilla que solo contiene datos ficticios."""
        cls.seed.close()

    def setUp(self):
        """Asigna archivos nuevos a cada prueba."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'prueba.hmbackup'

    def archivo(self):
        """Escribe un respaldo válido con el escritor real."""
        return module.write_archive(self.path, self.data, self.key, self.salt)

    def sqlite_modificada(self, statements):
        """Aplica mutaciones únicamente a una copia de la semilla en memoria."""
        with closing(sqlite3.connect(':memory:')) as connection:
            self.seed.connection.backup(connection)
            connection.executescript(statements)
            return connection.serialize()

    def cabecera_cruda(self, header):
        """Construye un contenedor sin etiqueta válida para errores previos al descifrado."""
        encoded = header if isinstance(header, bytes) else json.dumps(header).encode()
        self.path.write_bytes(module.MAGIC + struct.pack('>I', len(encoded)) + encoded + b'x' * 16)

    def autenticar_metadatos(self, header, content=None):
        """Cifra de verdad un archivo de prueba con metadatos semánticamente inválidos."""
        encoded = json.dumps(header).encode()
        prefix = module.MAGIC + struct.pack('>I', len(encoded)) + encoded
        self.path.write_bytes(prefix + AESGCM(self.key).encrypt(bytes.fromhex(header['nonce']), self.data if content is None else content, prefix))

    def test_recorrido_completo_y_huella_del_archivo(self):
        """La ida y vuelta conserva bytes, contenido y la huella utilizada para revisar/restaurar."""
        self.archivo()
        metadata, data = module.read_archive(self.path, 'RespaldoFicticio#2026')
        self.assertEqual(data, self.data)
        self.assertEqual(metadata['archive_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        with closing(module.validated_database(data)) as restored:
            self.assertEqual(restored.execute('SELECT count(*) FROM issues').fetchone()[0], 1)

    def test_claves_de_respaldo_fuera_de_limites(self):
        """El KDF rechaza tipos, espacios y longitudes no admitidos."""
        for value in (None, 123, '', ' ' * 12, 'corta', 'x' * 257):
            with self.subTest(tipo=type(value).__name__), self.assertRaises(ValueError):
                module.derive_key(value, self.salt)

    def test_escritor_rechaza_extension_y_base_excesiva(self):
        """Las entradas que no pueden transportarse no crean archivos parciales."""
        with self.assertRaises(ValueError):
            module.write_archive(self.path.with_suffix('.txt'), self.data, self.key, self.salt)
        with patch.object(module, 'MAX_DATABASE', 1), self.assertRaises(ValueError):
            self.archivo()
        self.assertFalse(self.path.exists())

    def test_escritor_rechaza_clave_sal_y_cabecera_que_no_puede_leer(self):
        """Nunca produce AES-128 rotulado AES-256 ni cabeceras que su lector rechace."""
        for key, salt in ((self.key[:16], self.salt), (self.key, self.salt[:-1])):
            with self.subTest(key_length=len(key), salt_length=len(salt)), self.assertRaises(ValueError):
                module.write_archive(self.path, self.data, key, salt)
            self.assertFalse(self.path.exists())
        with self.assertRaises(ValueError):
            module.write_archive(self.path, self.data, self.key, self.salt, reason='x' * module.MAX_HEADER)
        self.assertFalse(self.path.exists())

    def test_instantanea_rechaza_esquema_ajeno_y_limite(self):
        """La copia se interrumpe antes de aceptar otro esquema o una base excesiva."""
        with closing(sqlite3.connect(':memory:')) as connection:
            with self.assertRaises(ValueError):
                module.snapshot(connection)
        with patch.object(module, 'MAX_DATABASE', 1), self.assertRaises(ValueError):
            module.snapshot(self.seed.connection)

    def test_magia_truncamiento_y_longitud_de_cabecera(self):
        """Rechaza prefijos ajenos, tamaño incompleto, cero y cabeceras excesivas."""
        for content in (b'archivo ajeno', module.MAGIC, module.MAGIC + struct.pack('>I', 0),
                        module.MAGIC + struct.pack('>I', module.MAX_HEADER + 1)):
            self.path.write_bytes(content)
            with self.assertRaises(ValueError):
                module.read_archive(self.path, 'RespaldoFicticio#2026')

    def test_limite_del_archivo_antes_de_kdf(self):
        """No ejecuta scrypt para un contenedor que excede el máximo permitido."""
        self.path.write_bytes(module.MAGIC + b'x' * 100)
        with patch.object(module, 'MAX_DATABASE', 1), patch.object(module, 'MAX_HEADER', 1), patch.object(module, 'derive_key') as derive:
            with self.assertRaises(ValueError):
                module.read_archive(self.path, 'RespaldoFicticio#2026')
        derive.assert_not_called()

    def test_json_y_campos_estructurales_se_rechazan_antes_de_kdf(self):
        """El lector no deriva claves para JSON, algoritmo o material binario inválidos."""
        header = self.archivo()
        variants = [b'{', b'\xff', [], header | {'format': 2}, header | {'application': 'otra'},
                    header | {'cipher': 'AES-128-GCM'}, header | {'kdf': 'otro'},
                    header | {'salt': 'xx'}, header | {'salt': '00'}, header | {'nonce': '00'},
                    {key: value for key, value in header.items() if key != 'salt'}]
        for variant in variants:
            self.cabecera_cruda(variant)
            with patch.object(module, 'derive_key') as derive, self.assertRaises(ValueError):
                module.read_archive(self.path, 'RespaldoFicticio#2026')
            derive.assert_not_called()

    def test_clave_incorrecta_y_manipulacion_de_bytes_se_detectan(self):
        """Una clave distinta y cambios en el texto cifrado no producen datos utilizables."""
        self.archivo()
        with self.assertRaisesRegex(ValueError, 'alterado'):
            module.read_archive(self.path, 'OtraClaveFicticia#2026')
        content = bytearray(self.path.read_bytes())
        content[-1] ^= 1
        self.path.write_bytes(content)
        with self.assertRaisesRegex(ValueError, 'alterado'):
            module.read_archive(self.path, 'RespaldoFicticio#2026')

    def test_metadatos_autenticados_aun_deben_ser_consistentes(self):
        """Una etiqueta AES válida no basta para aceptar esquema, tamaño o hash incorrectos."""
        header = self.archivo()
        for changed, data in ((header | {'schema': 999}, None), (header | {'size': 1}, None),
                              (header | {'sha256': '0' * 64}, None),
                              (header | {'size': 3, 'sha256': hashlib.sha256(b'abc').hexdigest()}, b'abc')):
            self.autenticar_metadatos(changed, data)
            with self.assertRaises(ValueError):
                module.read_archive(self.path, 'RespaldoFicticio#2026')

    def test_sqlite_ajena_columnas_vistas_y_datos_corruptos(self):
        """La reconstrucción exige tablas y columnas propias y no acepta vistas externas."""
        mutations = ['PRAGMA user_version=999;', 'CREATE TABLE intrusa(id);',
                     'CREATE VIEW intrusa AS SELECT * FROM users;', 'ALTER TABLE users ADD COLUMN intrusa TEXT;']
        for statements in mutations:
            with self.subTest(sql=statements), self.assertRaises(ValueError):
                module.validated_database(self.sqlite_modificada(statements))
        with self.assertRaises(ValueError):
            module.validated_database(b'no es una base SQLite')

    def test_relaciones_huerfanas_y_maestro_invalido(self):
        """No entrega una colección sin administrador único o con referencias inexistentes."""
        mutations = ["INSERT INTO grants(user_id,permission) VALUES(999,'Auditoría');",
                     'UPDATE users SET active=0;', 'UPDATE users SET document=NULL;',
                     "INSERT INTO users(id,name,identity,password,role,active,created_at,document) SELECT 99,name,'V-87654321',password,role,1,created_at,'V-87654321' FROM users LIMIT 1;"]
        for statements in mutations:
            with self.subTest(sql=statements), self.assertRaises(ValueError):
                module.validated_database(self.sqlite_modificada(statements))

    def test_disparadores_ajenos_no_se_importan_y_sesiones_no_sobreviven(self):
        """Reconstruye datos, no SQL ejecutable ni autorizaciones de una instalación anterior."""
        data = self.sqlite_modificada("""CREATE TRIGGER intruso AFTER INSERT ON issues BEGIN DELETE FROM users; END;
            INSERT INTO system_settings(key,value) VALUES('active_host_id','anterior');
            INSERT INTO auth_failures(identity_hash,failed_attempts,locked_until) VALUES('ficticia',2,0);
            INSERT INTO api_sessions(token_hash,user_id,password_version,method,expires_at) VALUES('ficticio',1,0,'password',9999999999);""")
        with closing(module.validated_database(data)) as clean:
            self.assertEqual(clean.execute('SELECT count(*) FROM users').fetchone()[0], 1)
            self.assertIsNone(clean.execute("SELECT 1 FROM sqlite_master WHERE name='intruso'").fetchone())
            for table in ('api_sessions', 'auth_failures', 'system_settings'):
                self.assertEqual(clean.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_version_tres_recupera_columnas_y_valores_predeterminados(self):
        """Admite el formato heredado sin permisos administrados ni revisiones de edición."""
        data = self.sqlite_modificada('ALTER TABLE users DROP COLUMN managed_permissions; ALTER TABLE issues DROP COLUMN revision; PRAGMA user_version=3;')
        with closing(module.validated_database(data)) as clean:
            self.assertEqual(clean.execute('SELECT managed_permissions FROM users').fetchone()[0], 0)
            self.assertEqual(clean.execute('SELECT revision FROM issues').fetchone()[0], 0)
            self.assertEqual(clean.execute('PRAGMA user_version').fetchone()[0], module.SCHEMA_VERSION)
