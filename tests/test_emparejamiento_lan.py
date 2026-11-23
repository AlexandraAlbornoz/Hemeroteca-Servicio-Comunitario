"""Reproduce dos PC ficticias y el emparejamiento TLS sin tocar datos reales."""

import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hemeroteca.config.settings import ROLES, SECURITY_QUESTIONS
from hemeroteca.network import configuration
from hemeroteca.network.configuration import load_settings
from hemeroteca.network.devices import DeviceIdentity
from hemeroteca.network.manager import NetworkManager
from hemeroteca.network.server import LANServer
from hemeroteca.network.transport import request
from hemeroteca.services.container import create_services
from hemeroteca.ui.tareas import ServiciosDeInterfaz


class DescubrimientoFicticio:
    """Evita enviar paquetes UDP fuera de la prueba; el par real usa HTTPS."""

    def __init__(self, description):
        self.description = description

    def start(self):
        pass

    def close(self):
        pass


def puerto_libre():
    """Reserva brevemente un puerto local para cada servidor ficticio."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conexion:
        conexion.bind(('127.0.0.1', 0))
        return conexion.getsockname()[1]


def certificado_en(carpeta):
    """Emite un certificado temporal propio para cada PC simulada."""
    with patch.object(configuration, 'NETWORK_TLS_PATH', carpeta):
        return configuration.ensure_certificate()


class PruebasEmparejamientoLAN(unittest.TestCase):
    """Ejercita oferta, autorización, fallo de retorno y reintento completo."""

    def setUp(self):
        """Crea dos configuraciones y dos bases aisladas en una carpeta temporal."""
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        raiz = Path(self.temporal.name)
        self.servidor_contexto, self.servidor_huella = certificado_en(raiz / 'tls-servidor')
        cliente_contexto, cliente_huella = certificado_en(raiz / 'tls-cliente')
        self.cliente_huella = cliente_huella
        self.identidad_cliente = DeviceIdentity(raiz / 'cliente.key')
        self.identidad_servidor = DeviceIdentity(raiz / 'servidor.key')
        self.puerto_servidor, self.puerto_cliente = puerto_libre(), puerto_libre()
        self.base_servidor, self.base_cliente = raiz / 'principal.db', raiz / 'cliente.db'
        self.config_servidor, self.config_cliente = raiz / 'principal.json', raiz / 'cliente.json'
        self.gestor_servidor = NetworkManager(self.base_servidor, self.config_servidor)
        self.servicios_servidor = create_services(self.base_servidor, node_id=self.gestor_servidor.settings['node_id'])
        self.addCleanup(self.servicios_servidor.close)
        preguntas = tuple(zip(SECURITY_QUESTIONS, ('Luna', 'María', 'Pecas')))
        self.contrasena = 'Prueba#2026'  # pragma: allowlist secret -- cuenta ficticia creada solo en esta prueba
        self.servicios_servidor.auth.create_master('Maestra ficticia', 'V-12345678', self.contrasena, preguntas)
        self.maestra = self.servicios_servidor.auth.authenticate('V-12345678', self.contrasena, ROLES[0])
        self.gestor_servidor.settings.update(mode='server', bind='127.0.0.1', port=self.puerto_servidor,
                                             server_url=f'https://127.0.0.1:{self.puerto_servidor}',
                                             fingerprint=self.servidor_huella)
        with patch('hemeroteca.network.server.DeviceIdentity', return_value=self.identidad_servidor):
            self.servidor = LANServer(self.base_servidor, self.gestor_servidor.settings,
                                     self.servidor_contexto, config_path=self.config_servidor)
        self.addCleanup(self.servidor.httpd.server_close)
        self.gestor_cliente = NetworkManager(self.base_cliente, self.config_cliente)
        self.servicios_cliente = create_services(self.base_cliente, node_id=self.gestor_cliente.settings['node_id'])
        self.addCleanup(self.servicios_cliente.close)
        with (patch('hemeroteca.network.pairing.DeviceIdentity', return_value=self.identidad_cliente),
              patch('hemeroteca.network.pairing.ensure_certificate', return_value=(cliente_contexto, cliente_huella)),
              patch('hemeroteca.network.pairing.DiscoveryResponder', DescubrimientoFicticio),
              patch('hemeroteca.network.pairing.PAIRING_PORT', self.puerto_cliente)):
            self.receptor = self.gestor_cliente.prepare_consultation_pc(self.servicios_cliente)
        self.addCleanup(self.receptor.close)
        self.candidato = dict(self.receptor.description(), url=f'https://127.0.0.1:{self.puerto_cliente}')

    def test_fallo_de_retorno_y_reintento_conectan_ambas_pc(self):
        """El cliente queda esperando sin TCP; al activarlo, el mismo código completa la conexión."""
        with patch('hemeroteca.network.manager.local_address', return_value='127.0.0.1'):
            with self.assertRaisesRegex(ValueError, 'PC principal') as fallo:
                self.gestor_servidor.approve_computer(self.servicios_servidor, self.maestra,
                                                       self.candidato, self.receptor.code, self.contrasena)
            self.assertIn('Motivo:', str(fallo.exception))
            self.assertEqual(self.receptor.state, 'offered')
            self.assertIn('no pudo comunicarse', self.receptor.last_error, str(fallo.exception))
            self.assertEqual(load_settings(self.config_cliente)['mode'], 'local')
            self.servidor.start()
            self.addCleanup(self.servidor.close)
            dispositivo = self.gestor_servidor.approve_computer(self.servicios_servidor, self.maestra,
                                                                  self.candidato, self.receptor.code, self.contrasena)
        self.assertEqual(dispositivo, self.identidad_cliente.device_id)
        self.assertEqual(self.receptor.state, 'connected')
        self.assertEqual(self.receptor.last_error, '')
        configuracion = load_settings(self.config_cliente)
        self.assertEqual(configuracion['mode'], 'client')
        self.assertEqual(configuracion['fingerprint'], self.servidor_huella)
        respuesta = request(configuracion['server_url'], configuracion['fingerprint'],
                            '/device/verify', {}, identity=self.identidad_cliente)
        self.assertTrue(respuesta['authorized'])

    def test_fallo_de_guardado_se_muestra_y_se_puede_reintentar(self):
        """Un error local en la PC cliente deja el código vigente y explica el bloqueo."""
        self.servidor.start()
        self.addCleanup(self.servidor.close)
        with patch('hemeroteca.network.manager.local_address', return_value='127.0.0.1'):
            with patch.object(self.receptor, 'on_accept', side_effect=OSError('disco temporal')):
                with self.assertRaisesRegex(ValueError, 'No se pudo guardar'):
                    self.gestor_servidor.approve_computer(self.servicios_servidor, self.maestra,
                                                           self.candidato, self.receptor.code, self.contrasena)
            self.assertEqual(self.receptor.state, 'offered')
            self.assertIn('No se pudo guardar', self.receptor.last_error)
            self.assertEqual(load_settings(self.config_cliente)['mode'], 'local')
            self.gestor_servidor.approve_computer(self.servicios_servidor, self.maestra,
                                                   self.candidato, self.receptor.code, self.contrasena)
        self.assertEqual(self.receptor.state, 'connected')
        self.assertEqual(load_settings(self.config_cliente)['mode'], 'client')

    def test_autorizacion_desde_interfaz_no_bloquea_verificacion_del_cliente(self):
        """La aprobación desde Tk libera la lectura que requiere la verificación HTTPS del cliente."""
        self.servidor.start()
        self.addCleanup(self.servidor.close)
        self.servicios_servidor.network = self.gestor_servidor
        coordinador = SimpleNamespace(original=self.servicios_servidor)

        def solicitud_rapida(*args, **kwargs):
            """Acorta solo la espera de esta prueba para detectar el bloqueo sin demorarla."""
            if args[2] == '/device/verify':
                kwargs['timeout'] = .7
            return request(*args, **kwargs)

        with (patch('hemeroteca.network.manager.local_address', return_value='127.0.0.1'),
              patch('hemeroteca.network.pairing.request', side_effect=solicitud_rapida)):
            dispositivo = ServiciosDeInterfaz._con_servicios(
                coordinador,
                lambda servicios: servicios.network.approve_computer(
                    servicios, self.maestra, self.candidato, self.receptor.code, self.contrasena),
                'network', 'approve_computer')

        self.assertEqual(dispositivo, self.identidad_cliente.device_id)
        self.assertEqual(self.receptor.state, 'connected')


if __name__ == '__main__':
    unittest.main()
