"""Normalización Unicode, cuentas y documentos históricos con SQLite real."""
from contextlib import closing
import unittest
from unittest.mock import patch
from hemeroteca.utils.validaciones import validar_nombre
from hemeroteca.services.container import create_services
from hemeroteca.database.schema import initialize_schema
from hemeroteca.network.client import RemoteClient
from hemeroteca.config.settings import ROLES
from tests import test_usuarios_permisos_ramas as fixtures
from tests import test_modulos_menor_cobertura as legacy


class PruebasNormalizacionMigracion(unittest.TestCase):
    setUpClass=classmethod(fixtures.PruebasUsuariosPermisos.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.PruebasUsuariosPermisos.tearDownClass.__func__)
    setUp=fixtures.PruebasUsuariosPermisos.setUp

    def test_expansion_unicode_no_devuelve_nombre_mayor_del_limite(self):
        name='ßa '*50
        self.assertEqual(len(name),150)
        with self.assertRaisesRegex(ValueError,'150'):validar_nombre(name)

    def test_nombres_unicode_dentro_limite_siguen_validos(self):
        name='ßa '*37
        result=validar_nombre(name)
        self.assertEqual(result,' '.join(['Ssa']*37));self.assertLessEqual(len(result),150)
        self.assertEqual(validar_nombre('  maría   pérez '),'María Pérez')
        self.assertEqual(len(validar_nombre('ßa '*37+'aa')),150)

    def test_nombre_expandido_rechazado_en_alta_edicion_y_maestra(self):
        name='ßa '*50
        before=self.s.connection.execute('SELECT count(*) FROM users').fetchone()[0]
        with self.assertRaises(ValueError):self.s.users.create_user(name,'V-12345681',self.clave,actor=self.master)
        with self.assertRaises(ValueError):self.s.users.update_user(self.master,self.admin['id'],name,self.admin['document'],ROLES[1],self.clave)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM users').fetchone()[0],before)
        with closing(create_services(':memory:')) as empty:
            with self.assertRaises(ValueError):empty.auth.create_master(name,'V-12345681',self.clave,self.questions)
            self.assertEqual(empty.connection.execute('SELECT count(*) FROM users').fetchone()[0],0)

    def test_migracion_no_duplica_documento_ya_asignado(self):
        with closing(legacy.PruebasMigracionDeRamas.legacy(self)) as conn:
            conn.execute("UPDATE users SET identity='temporal' WHERE id=1")
            conn.execute("UPDATE users SET identity=' v-12345678 ' WHERE id=2")
            conn.execute("UPDATE users SET identity='V-12345678' WHERE id=1");conn.commit()
            initialize_schema(conn)
            self.assertEqual(conn.execute('SELECT document FROM users WHERE id=1').fetchone()[0],'V-12345678')
            self.assertIsNone(conn.execute('SELECT document FROM users WHERE id=2').fetchone()[0])
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_cliente_sin_gestor_sigue_redireccion_con_token(self):
        settings={'server_url':'https://127.0.0.1:8765','fingerprint':'a'*64}
        client=RemoteClient(settings)
        responses=[{'moved':True,'server_url':'https://127.0.0.1:8766','fingerprint':'b'*64},{'result':{'ok':True},'token':'sesion-ficticia'}]
        with patch('hemeroteca.network.client.request',side_effect=responses) as request:
            self.assertEqual(client.call('auth.needs_setup'),{'ok':True})
        self.assertEqual(client.token,'sesion-ficticia');self.assertEqual(request.call_args.args[0],'https://127.0.0.1:8766')
