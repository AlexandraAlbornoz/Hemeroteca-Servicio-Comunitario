"""Contrato TLS y errores de transporte sin enviar credenciales a equipos reales."""
import hashlib
import http.client
import unittest
from unittest.mock import Mock, patch
from hemeroteca.network import transport
from hemeroteca.services.access_service import AccessDenied


class PruebasTransporteRamas(unittest.TestCase):
    """La conexión controlada permite comprobar orden, límites y cierre."""

    def setUp(self):
        self.cert = b'certificado ficticio'
        self.pin = hashlib.sha256(self.cert).hexdigest()
        self.conn = Mock()
        self.conn.sock.getpeercert.return_value = self.cert
        self.response = self.conn.getresponse.return_value
        self.response.status = 200
        self.response.read.return_value = b'{"ok":true}'
        self.factory = patch.object(transport.http.client, 'HTTPSConnection', return_value=self.conn)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def request(self, **kw):
        return transport.request('https://127.0.0.1:8443', self.pin, '/status', **kw)

    def test_pin_incorrecto_no_envia_credenciales_y_cierra(self):
        with self.assertRaisesRegex(ValueError, 'huella'):
            transport.request('https://127.0.0.1:8443', '0'*64, '/rpc', {'password':self.cert.hex()}, 'sesion')
        self.conn.request.assert_not_called()
        self.conn.close.assert_called_once()

    def test_identidad_por_defecto_firma_despues_del_pin(self):
        identity = Mock()
        identity.headers.return_value = {'X-Prueba':'firmado'}
        with patch('hemeroteca.network.devices.DeviceIdentity', return_value=identity):
            result = transport.request('https://127.0.0.1:8443', self.pin, '/rpc', {'dato':'á'}, 'sesion')
        self.assertEqual(result, {'ok':True})
        method,path = self.conn.request.call_args.args
        self.assertEqual((method,path), ('POST','/rpc'))
        body = self.conn.request.call_args.kwargs['body']
        identity.headers.assert_called_once_with('POST','/rpc',body,'sesion',self.pin)
        self.assertEqual(self.conn.request.call_args.kwargs['headers']['Authorization'],'Bearer sesion')
        self.conn.close.assert_called_once()

    def test_respuesta_al_limite_y_exceso_no_se_acepta(self):
        self.assertEqual(self.request(max_response=11), {'ok':True})
        self.response.read.assert_called_with(12)
        with self.assertRaisesRegex(ValueError,'demasiado grande'):
            self.request(max_response=10)

    def test_json_no_objeto_y_estados_de_error(self):
        for value in [b'[]', b'null', b'42']:
            with self.subTest(value=value):
                self.response.read.return_value=value
                with self.assertRaisesRegex(ValueError,'no es válida'): self.request()
        self.response.read.return_value=b'{}'
        self.response.status=401
        with self.assertRaises(AccessDenied): self.request()
        self.response.status=500
        with self.assertRaisesRegex(ValueError,'no pudo completar'): self.request()
        self.response.status=200
        self.response.read.return_value=b'{"error_type":"AccessDenied","error":"rechazado"}'
        with self.assertRaisesRegex(AccessDenied,'rechazado'): self.request()

    def test_fallos_de_red_http_y_json_siempre_cierran(self):
        for error in [OSError('red'),http.client.BadStatusLine('invalido')]:
            with self.subTest(error=type(error).__name__):
                self.conn.connect.side_effect=error
                with self.assertRaises(transport.ErrorConexion): self.request()
        self.conn.connect.side_effect=None
        self.response.read.return_value=b'{'
        with self.assertRaises(transport.ErrorConexion): self.request()
        self.assertEqual(self.conn.close.call_count,3)

    def test_bytes_no_utf8_producen_error_controlado_y_cierran(self):
        self.response.read.return_value=b'\xff'
        with self.assertRaises(transport.ErrorConexion): self.request()
        self.conn.close.assert_called_once()
