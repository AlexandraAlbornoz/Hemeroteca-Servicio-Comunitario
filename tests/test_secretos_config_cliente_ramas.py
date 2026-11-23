"""Claves locales, configuración y respuestas RPC inválidas sin servicios externos."""
import base64
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from hemeroteca.utils import local_secrets as secrets
from hemeroteca.network import configuration as config
from hemeroteca.network.client import RemoteClient,RemoteProxy,RemoteServices
from hemeroteca.services.access_service import AccessDenied


class PruebasSecretosLocales(unittest.TestCase):
    """Nunca usa claves reales del usuario ni modifica permisos fuera del temporal."""

    def test_alternativa_no_windows_roundtrip_y_longitud_invalida(self):
        key=b'k'*32
        with patch.object(secrets.os,'name','posix'):
            settings=secrets.protect_key(key)
            self.assertEqual(settings['protection'],'file-permissions')
            self.assertEqual(secrets.unprotect_key(settings),key)
            with self.assertRaises(ValueError):secrets.unprotect_key(dict(settings,key=base64.b64encode(b'x'*31).decode()))

    def test_configuraciones_corruptas_no_devuelven_clave(self):
        for value in [None,[],{},dict(key='no base64',protection='file-permissions'),dict(key=123,protection='file-permissions'),
                      dict(key=base64.b64encode(b'x'*32).decode(),protection='inventada')]:
            with self.subTest(value=value),self.assertRaises(ValueError):secrets.unprotect_key(value)
        with patch.object(secrets.os,'name','nt'),self.assertRaises(ValueError):
            secrets.unprotect_key(dict(key=base64.b64encode(b'x'*32).decode(),protection='file-permissions'))
        with patch.object(secrets.os,'name','posix'),self.assertRaises(ValueError):
            secrets.unprotect_key(dict(key=base64.b64encode(b'x'*32).decode(),protection='windows-dpapi'))

    def test_fallo_dpapi_proteger_y_abrir_se_informa(self):
        crypt,kernel=Mock(),Mock()
        crypt.CryptProtectData.return_value=False
        crypt.CryptUnprotectData.return_value=False
        for decrypt in [False,True]:
            with patch.object(secrets.ctypes,'WinDLL',side_effect=[crypt,kernel]),self.assertRaisesRegex(ValueError,'Windows'):
                secrets._dpapi(b'bytes ficticios',decrypt=decrypt)
        kernel.LocalFree.assert_not_called()

    def test_fsync_fallido_conserva_archivo_y_retira_temporal(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'privado.json'
            path.write_bytes(b'anterior')
            with patch.object(secrets.os,'fsync',side_effect=OSError('disco ficticio')),self.assertRaises(OSError):
                secrets.private_write(path,b'nuevo')
            self.assertEqual(path.read_bytes(),b'anterior')
            self.assertEqual(list(Path(folder).iterdir()),[path])
            secrets.write_json(path,{'texto':'válido'})
            self.assertIn('válido',path.read_text(encoding='utf-8'))


class PruebasConfiguracionRed(unittest.TestCase):
    """Prueba archivos corruptos, reemplazos fallidos y certificados temporales."""

    def test_configuracion_no_objeto_y_nodo_invalido_se_rechazan(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'network.json'
            for value in [[],None,dict(mode='local',node_id=1),dict(mode='local',node_id=' '),dict(mode='invalido',node_id='fixture')]:
                path.write_text(json.dumps(value),encoding='utf-8')
                with self.subTest(value=value),self.assertRaises(ValueError):config.load_settings(path)

    def test_guardado_fallido_conserva_ajustes_y_no_deja_tmp(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'network.json'
            config.save_settings({'mode':'local','node_id':'fixture'},path)
            before=path.read_bytes()
            with patch.object(Path,'replace',side_effect=OSError('reemplazo ficticio')),self.assertRaises(OSError):
                config.save_settings({'mode':'client','node_id':'fixture'},path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(Path(folder).iterdir()),[path])
            config.save_settings({'mode':'local','node_id':'otro'},path)
            self.assertEqual(config.load_settings(path)['node_id'],'otro')

    def test_direccion_y_huella_tipos_formatos_y_limites(self):
        for value in [None,123,[], 'http://192.168.1.1:8765','https://usuario@192.168.1.1:8765',
                      'https://8.8.8.8:8765','https://servidor:8765','https://0.0.0.0:8765',
                      'https://192.168.1.1:80','https://192.168.1.1:8765/ruta']:
            with self.subTest(value=value),self.assertRaises(ValueError):config.validate_address(value)
        self.assertEqual(config.validate_address(' https://127.0.0.1:8765/ '),'https://127.0.0.1:8765')
        for value in [None,[],123,'abc','g'*64]:
            with self.subTest(value=value),self.assertRaises(ValueError):config.normalize_fingerprint(value)
        self.assertEqual(config.normalize_fingerprint(':'.join(['AA']*32)),'a'*64)

    def test_certificado_vencido_indica_carpeta_real_sin_renovarlo(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            key=ec.generate_private_key(ec.SECP256R1())
            name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Fixture')])
            certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                         .serial_number(1).not_valid_before(datetime(2000,1,1,tzinfo=timezone.utc))
                         .not_valid_after(datetime(2001,1,1,tzinfo=timezone.utc)).sign(key,hashes.SHA256()))
            (path/'server.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            (path/'server.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            before=(path/'server.pem').read_bytes()
            with patch.object(config,'NETWORK_TLS_PATH',path),self.assertRaisesRegex(ValueError,'venció') as error:
                config.ensure_certificate()
            self.assertIn(str(path),str(error.exception))
            self.assertEqual((path/'server.pem').read_bytes(),before)


class PruebasClienteRPC(unittest.TestCase):
    """La respuesta del transporte sigue siendo una entrada que debe validarse."""

    def setUp(self):
        self.settings={'server_url':'https://127.0.0.1:8765','fingerprint':'a'*64}
        self.manager=Mock()
        self.client=RemoteClient(self.settings,self.manager)
        self.client.token='sesion-ficticia'

    def test_logout_borra_token_aunque_servidor_no_responda(self):
        with patch('hemeroteca.network.client.request',side_effect=ValueError('sin conexión')):
            self.client.logout()
        self.assertIsNone(self.client.token)
        self.client.logout()

    def test_operacion_invalida_no_se_envia(self):
        with patch('hemeroteca.network.client.request') as request,self.assertRaises(AccessDenied):self.client.call('users.delete_user')
        request.assert_not_called()

    def test_redireccion_valida_token_y_limite_de_saltos(self):
        moved=dict(moved=True,server_url='https://127.0.0.1:9999',fingerprint='b'*64)
        with patch('hemeroteca.network.client.request',side_effect=[moved,{'result':True,'token':'sesion-nueva'}]) as request:
            self.assertTrue(self.client.call('auth.needs_setup'))
            self.assertEqual(request.call_count,2)
        self.assertEqual(self.client.token,'sesion-nueva')
        self.manager.follow_server.assert_called_once()
        with patch('hemeroteca.network.client.request',return_value=moved),self.assertRaisesRegex(ValueError,'resolver'):
            self.client.call('auth.needs_setup')

    def test_respuesta_malformada_no_contamina_sesion_ni_ajustes(self):
        for result in [None,[],{'moved':True},{'moved':'false'},
                       dict(moved=True,server_url='https://8.8.8.8:8765',fingerprint='b'*64),
                       dict(moved=True,server_url='https://127.0.0.1:9999',fingerprint='incorrecta'),{'token':123,'result':True}]:
            self.client.settings=dict(self.settings)
            with self.subTest(result=result),patch('hemeroteca.network.client.request',return_value=result),self.assertRaises(ValueError):
                self.client.call('auth.needs_setup')
            self.assertEqual(self.client.settings,self.settings)
            self.assertEqual(self.client.token,'sesion-ficticia')
        self.manager.follow_server.assert_not_called()

    def test_proxy_actor_local_tipos_y_timeout_pdf(self):
        fake=Mock()
        proxy=RemoteProxy(fake,'access')
        self.assertEqual(proxy.actor_label(None),'Sin sesión')
        self.assertEqual(proxy.actor_label({'name':'Fixture','identity':'V-12345678'}),'Fixture · V-12345678')
        fake.call.return_value=['Uno']
        self.assertEqual(proxy.permissions({'id':99}),{'Uno'})
        fake.call.assert_called_with('access.permissions')
        RemoteProxy(fake,'audit').record('Fixture','Evento')
        fake.call.return_value={'user_id':4,'recovery_code':'HMR-FICTICIO'}
        self.assertEqual(RemoteProxy(fake,'users').register_user('Nombre').user_id,4)
        with patch('hemeroteca.network.client.request',return_value={'result':{}}) as request:self.client.call('reports.generate')
        self.assertEqual(request.call_args.kwargs['timeout'],120)
        RemoteServices(fake,None).close()
        fake.logout.assert_called_once()
