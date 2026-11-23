"""Contrato y ciclo de vida del emparejamiento temporal, sin broadcast LAN."""
import base64
from email.message import Message
import hashlib
import http.client
import io
import json
from pathlib import Path
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from hemeroteca.network import pairing as module
from hemeroteca.network import configuration,devices
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.container import create_services


class PruebasRamasEmparejamiento(unittest.TestCase):
    """Conserva HMAC, firma Ed25519 y el manejador HTTP del producto."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.identity=devices.DeviceIdentity(self.root/'device.key')
        self.accept=Mock()
        with patch.object(module,'DeviceIdentity',return_value=self.identity),patch.object(module,'ensure_certificate',return_value=(Mock(),'a'*64)),patch.object(module,'DiscoveryResponder'),patch.object(module,'TLSHTTPServer') as http:
            self.r=module.PairingReceiver('cliente-ficticio',self.accept)
            self.handler=http.call_args.args[1]

    def offer(self,**changes):
        return dict(invitation_id=self.r.invitation_id,nonce=self.r.nonce,public_key=self.identity.public_key,
                    client_pin=self.r.fingerprint,client_node_id=self.r.node_id,server_url='https://127.0.0.1:8765',server_pin='b'*64,**changes)

    def sign(self,key,value):return {key:value,'proof':module.proof(self.r.code,value)}

    def stage(self):
        value=self.offer()
        self.r.accept_offer(self.sign('offer',value))
        return dict(kind='commit',invitation_id=self.r.invitation_id,offer_hash=hashlib.sha256(module.canonical(value)).hexdigest())

    def call(self,payload=None,*,path='/pair/offer',get=False,raw=None,headers=None,ip='127.0.0.1'):
        h=self.handler.__new__(self.handler)
        h.path,h.client_address=path,(ip,1234)
        body=json.dumps(payload if payload is not None else {}).encode() if raw is None else raw
        h.headers=Message()
        for k,v in {'Content-Length':str(len(body)),'Content-Type':'application/json',**(headers or {})}.items():h.headers[k]=v
        h.rfile,h.wfile=io.BytesIO(body),io.BytesIO()
        h.send_response,h.send_header,h.end_headers=Mock(),Mock(),Mock()
        (h.do_GET if get else h.do_POST)()
        return h.send_response.call_args.args[0],json.loads(h.wfile.getvalue()),h

    def test_hello_solo_red_privada_y_estado_vigente(self):
        self.assertEqual(self.call(path='/pair/hello',get=True)[0],200)
        self.assertEqual(self.call(path='/otro',get=True)[0],404)
        self.assertEqual(self.call(path='/pair/hello',get=True,ip='8.8.8.8')[0],404)
        self.r.state='connected'
        self.assertIsNone(self.r.description())
        self.assertEqual(self.call(path='/pair/hello',get=True)[0],400)

    def test_vencimiento_fallos_y_cancelacion_retiran_descripcion(self):
        with patch.object(module.time,'time',return_value=self.r.expires_at):
            self.assertTrue(self.r.expired())
            self.assertIsNone(self.r.description())
            self.assertEqual(self.call()[0],400)
        self.r.failures=5
        self.assertTrue(self.r.expired())
        self.r.failures=0
        self.r.state='cancelled'
        self.assertTrue(self.r.expired())

    def test_pruebas_incorrectas_y_unicode_cuentan_intentos(self):
        for value in [None,123,'incorrecto','é'*64]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.r.check_proof({},value)
        self.assertEqual(self.r.failures,4)

    def test_oferta_firmada_correcta_es_idempotente_y_no_guarda_configuracion(self):
        value=self.offer()
        result=self.r.accept_offer(self.sign('offer',value))
        devices.verify_signature(self.identity.public_key,result['signature'],module.canonical(value))
        self.assertEqual(result['device_id'],self.identity.device_id)
        self.assertEqual(self.r.accept_offer(self.sign('offer',value)),result)
        self.assertEqual(self.r.state,'offered')
        self.accept.assert_not_called()

    def test_oferta_no_corresponde_a_otro_cliente_y_no_reemplaza_pendiente(self):
        for key in ['invitation_id','nonce','public_key','client_pin','client_node_id']:
            value=self.offer()
            value[key]='otro'
            with self.subTest(key=key),self.assertRaises(ValueError):self.r.accept_offer(self.sign('offer',value))
        value=self.offer()
        self.r.accept_offer(self.sign('offer',value))
        other=dict(value,server_url='https://127.0.0.1:9999')
        with self.assertRaises(ValueError):self.r.accept_offer(self.sign('offer',other))
        self.r.state='connected'
        with self.assertRaises(ValueError):self.r.accept_offer(self.sign('offer',value))

    def test_commit_sin_oferta_incorrecto_y_conectado_no_repite_guardado(self):
        with self.assertRaises(ValueError):self.r.commit({})
        value=self.stage()
        with self.assertRaises(ValueError):self.r.commit(self.sign('commit',dict(value,offer_hash='otro')))
        with patch.object(module,'request',return_value={'authorized':True}) as request:
            self.assertEqual(self.r.commit(self.sign('commit',value)),{'connected':True})
            self.assertEqual(self.r.commit(self.sign('commit',value)),{'connected':True})
            request.assert_called_once()
        self.accept.assert_called_once()
        self.assertEqual(self.r.state,'connected')

    def test_commit_error_red_permiso_y_guardado_permiten_reintentar(self):
        value=self.stage()
        payload=self.sign('commit',value)
        for error in [module.ErrorConexion('sin conexión'),AccessDenied('equipo no autorizado'),ValueError('respuesta inválida')]:
            with patch.object(module,'request',side_effect=error),self.assertRaises(ValueError):self.r.commit(payload)
            self.assertEqual(self.r.state,'offered')
            self.assertTrue(self.r.last_error)
        for error in [OSError('disco ficticio'),ValueError('ajustes inválidos')]:
            self.accept.side_effect=error
            with patch.object(module,'request',return_value={'authorized':True}),self.assertRaises(ValueError):self.r.commit(payload)
            self.assertEqual(self.r.state,'offered')
        self.accept.side_effect=None
        with patch.object(module,'request',return_value={'authorized':True}):self.r.commit(payload)
        self.assertEqual(self.r.last_error,'')

    def test_http_payload_tipo_longitud_y_red_invalidos(self):
        for raw,headers in [(b'[]',{}),(b'{',{}),(b'{}',{'Content-Length':'no'}),
                            (b'{}',{'Content-Length':'0'}),(b'{}',{'Content-Length':'8193'}),
                            (b'{}',{'Content-Type':'text/plain'})]:
            with self.subTest(raw=raw,headers=headers):self.assertEqual(self.call(raw=raw,headers=headers)[0],400)
        self.assertEqual(self.call(ip='8.8.8.8')[0],400)
        self.assertEqual(self.call(path='/otra')[0],400)
        self.assertEqual(self.call(self.sign('offer',self.offer()),headers={'Content-Type':'text/plain'})[0],400)

    def test_http_oferta_y_commit_usan_cabeceras_sin_cache(self):
        value=self.offer()
        status,result,h=self.call(self.sign('offer',value))
        self.assertEqual(status,200)
        h.send_header.assert_any_call('Cache-Control','no-store')
        h.send_header.assert_any_call('Content-Length',str(len(h.wfile.getvalue())))
        commit=dict(kind='commit',invitation_id=self.r.invitation_id,offer_hash=hashlib.sha256(module.canonical(value)).hexdigest())
        with patch.object(module,'request',return_value={'authorized':True}):
            self.assertEqual(self.call(self.sign('commit',commit),path='/pair/commit')[0],200)

    def test_http_error_io_no_expone_detalles(self):
        with patch.object(self.r,'accept_offer',side_effect=OSError('ruta privada')):
            status,data,_=self.call({})
        self.assertEqual(status,500)
        self.assertNotIn('ruta privada',data['error'])

    def test_json_muy_anidado_responde_400(self):
        self.assertEqual(self.call(raw=b'['*4000+b'0'+b']'*4000)[0],400)

    def test_cerrar_antes_de_start_no_espera_bucle_inexistente(self):
        self.r.close()
        self.r.httpd.shutdown.assert_not_called()
        self.r.httpd.server_close.assert_called_once()
        self.assertEqual(self.r.state,'cancelled')

    def test_cierre_conectado_preserva_estado_y_espera_al_hilo(self):
        self.r.state='connected'
        self.r.thread=Mock()
        self.r.thread.is_alive.return_value=True
        self.r.close()
        self.assertEqual(self.r.state,'connected')
        self.r.thread.join.assert_called_once()

    def test_fallo_descubrimiento_al_arrancar_libera_servidor(self):
        self.r.thread=Mock()
        self.r.thread.is_alive.return_value=True
        self.r.discovery.start.side_effect=OSError('UDP no disponible')
        with self.assertRaises(OSError):self.r.start()
        self.r.httpd.shutdown.assert_called_once()
        self.r.httpd.server_close.assert_called_once()

    def test_fallo_al_cerrar_descubrimiento_aun_libera_socket(self):
        self.r.discovery.close.side_effect=OSError('fallo de cierre ficticio')
        with self.assertRaises(OSError):self.r.close()
        self.r.httpd.server_close.assert_called_once()

    def test_constructor_fallido_no_deja_servidor_abierto(self):
        with patch.object(module,'DeviceIdentity',return_value=self.identity),patch.object(module,'ensure_certificate',return_value=(Mock(),'a'*64)),patch.object(module,'TLSHTTPServer') as http,patch.object(module,'DiscoveryResponder',side_effect=OSError('UDP ocupado')):
            with self.assertRaises(OSError):module.PairingReceiver('cliente',Mock())
            http.return_value.server_close.assert_called_once()


class PruebasDispositivosFirmados(unittest.TestCase):
    """Firmas reales, antigüedad, replay y revocación de identidad en SQLite."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.identity=devices.DeviceIdentity(self.root/'device.key')
        self.s=create_services(':memory:')
        self.addCleanup(self.s.close)
        with self.s.connection:self.s.connection.execute('INSERT INTO authorized_devices(device_id,public_key,node_id,name,approved_by,approved_at) VALUES(?,?,?,?,?,?)',
            (self.identity.device_id,self.identity.public_key,'cliente','Fixture','Maestra Ficticia','2026-11-19'))
        self.pin='a'*64
        self.body=b'{}'

    def verify(self,headers,body=None):return devices.verify_device(self.s.connection,headers,'POST','/rpc',self.body if body is None else body,self.pin)

    def test_firma_real_replay_cuerpo_alterado_y_equipo_revocado(self):
        headers=self.identity.headers('POST','/rpc',self.body,None,self.pin)
        self.assertEqual(self.verify(headers),self.identity.device_id)
        with self.assertRaises(AccessDenied):self.verify(headers)
        headers=self.identity.headers('POST','/rpc',self.body,None,self.pin)
        with self.assertRaises(AccessDenied):self.verify(headers,b'alterado')
        with self.s.connection:self.s.connection.execute('UPDATE authorized_devices SET active=0')
        with self.assertRaises(AccessDenied):self.verify(headers)

    def test_cabeceras_y_antiguedad_invalidas_no_consumen_nonce(self):
        for changed in [{'X-Hemeroteca-Time':'no'},{'X-Hemeroteca-Time':'1'},{'X-Hemeroteca-Device':'g'*64},{'X-Hemeroteca-Nonce':'corto'}]:
            headers=self.identity.headers('POST','/rpc',self.body,None,self.pin)
            headers.update(changed)
            with self.subTest(changed=changed),self.assertRaises(AccessDenied):self.verify(headers)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM device_nonces').fetchone()[0],0)

    def test_clave_publica_tipo_y_firma_invalidos(self):
        for value in [None,'x','A'*44,base64.b64encode(b'a'*31).decode()]:
            with self.subTest(value=value),self.assertRaises(ValueError):devices.public_key_id(value)
        with self.assertRaises(AccessDenied):devices.verify_signature('inválida','firma',b'{}')
        self.assertEqual(devices.public_key_id(self.identity.public_key),self.identity.device_id)

    def test_revocacion_entre_verificacion_y_transaccion_se_revalida(self):
        headers=self.identity.headers('POST','/rpc',self.body,None,self.pin)
        original=devices.verify_signature
        def revoke(*args):
            original(*args)
            with self.s.connection:self.s.connection.execute('UPDATE authorized_devices SET active=0')
        with patch.object(devices,'verify_signature',side_effect=revoke),self.assertRaises(AccessDenied):self.verify(headers)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM device_nonces').fetchone()[0],0)

    def test_clave_de_otro_algoritmo_no_se_acepta_como_identidad(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        path=self.root/'otra.key'
        key=ec.generate_private_key(ec.SECP256R1())
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        with self.assertRaisesRegex(ValueError,'inválida'):devices.DeviceIdentity(path)

    def test_creacion_concurrente_conserva_la_identidad_que_gano(self):
        path=self.root/'device.key'
        real_exists,real_open=Path.exists,Path.open
        def exists(p):return False if p==path else real_exists(p)
        def open_file(p,mode='r',*args,**kwargs):
            if p==path and mode=='xb':raise FileExistsError('otra instancia creó la clave')
            return real_open(p,mode,*args,**kwargs)
        with patch.object(Path,'exists',exists),patch.object(Path,'open',open_file):
            identity=devices.DeviceIdentity(path)
        self.assertEqual(identity.device_id,self.identity.device_id)


class PruebasReceptorTLSReal(unittest.TestCase):
    """Servidor real solo en loopback; descubrimiento UDP sustituido."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with patch.object(configuration,'NETWORK_TLS_PATH',self.root/'tls'):context,pin=configuration.ensure_certificate()
        self.context=ssl.create_default_context(cafile=str(self.root/'tls/server.pem'))
        self.context.check_hostname=False  # Se confía exclusivamente en el certificado temporal exacto.
        identity=devices.DeviceIdentity(self.root/'device.key')
        from hemeroteca.network.http_server import TLSHTTPServer
        with patch.object(module,'DeviceIdentity',return_value=identity),patch.object(module,'ensure_certificate',return_value=(context,pin)),patch.object(module,'DiscoveryResponder'),patch.object(module,'TLSHTTPServer',side_effect=lambda addr,handler,ctx:TLSHTTPServer(('127.0.0.1',0),handler,ctx)):
            self.r=module.PairingReceiver('cliente',Mock())
        self.addCleanup(self.r.close)

    def test_hello_y_json_anidado_reales_no_interrumpen_servidor(self):
        self.r.start()
        for body,status in [(None,200),(b'['*4000+b'0'+b']'*4000,400),(None,200)]:
            conn=http.client.HTTPSConnection('127.0.0.1',self.r.httpd.server_port,context=self.context,timeout=3)
            try:
                conn.request('GET' if body is None else 'POST','/pair/hello' if body is None else '/pair/offer',body=body,headers={'Content-Type':'application/json'})
                result=conn.getresponse()
                self.assertEqual(result.status,status)
                json.loads(result.read())
            finally:conn.close()

    def test_cierre_real_previo_al_inicio_no_se_bloquea(self):
        worker=threading.Thread(target=self.r.close,daemon=True)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
