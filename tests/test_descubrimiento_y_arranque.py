"""UDP sin tráfico externo y entradas del programa con recursos controlados."""
from itertools import count
import json
from pathlib import Path
import socket
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch

from hemeroteca.network import discovery as module
from hemeroteca import backup_worker
from hemeroteca import main as entry


class PruebasDescubrimiento(unittest.TestCase):
    """Usa paquetes sintéticos y dobles de socket, sin broadcast en la LAN."""

    def setUp(self):
        self.enterContext(patch.object(module, '_discovery_interfaces', return_value=('192.168.1.1',)))

    def make_responder(self, description):
        with patch.object(module.sys, 'platform', 'win32'):
            return module.DiscoveryResponder(description)

    def test_ips_y_direccion_local_sin_red_real(self):
        """Distingue rutas privadas válidas de bucle local, públicas e indisponibles."""
        for address, expected in (('192.168.1.2', True), ('127.0.0.1', True), ('0.0.0.0', False),
                                  ('224.0.0.1', False), ('8.8.8.8', False), ('no-ip', False)):
            self.assertEqual(module.private_ip(address), expected)
        with patch.object(module.socket, 'socket') as constructor:
            route = constructor.return_value.__enter__.return_value
            route.getsockname.return_value = ('192.168.1.2', 0)
            self.assertEqual(module.local_address('192.168.1.3'), '192.168.1.2')
            route.getsockname.return_value = ('127.0.0.1', 0)
            with self.assertRaises(ValueError):
                module.local_address()
            route.connect.side_effect = OSError('sin ruta ficticia')
            with self.assertRaises(ValueError):
                module.local_address()

    def test_socket_windows_y_proveedor_sin_control_io(self):
        """Abrir el socket y consultar Winsock no envía ninguna datagrama."""
        with module._discovery_socket() as udp:
            self.assertEqual(udp.type, socket.SOCK_DGRAM)
        with patch.object(module, 'sys', SimpleNamespace(platform='linux')):
            with module._discovery_socket() as udp:
                self.assertNotEqual(udp.fileno(), -1)
        if module.sys.platform == 'win32':
            with patch('ctypes.WinDLL', side_effect=OSError('proveedor ficticio no compatible')):
                with module._discovery_socket() as udp:
                    self.assertNotEqual(udp.fileno(), -1)

    def test_busqueda_valida_limpia_nombres_y_descarta_paquetes_ajenos(self):
        """No acepta otro nonce, IP pública, puerto inválido ni invitaciones vencidas."""
        nonce = 'a' * 32
        valid = dict(protocol=module.PROTOCOL, nonce=nonce, invitation_id='ficticia', name='PC\nFicticia', port=8767, expires_at=2000)
        values = [b'{', b'[' * 1000 + b']' * 1000, [], valid | {'nonce': 'otro'}, valid | {'port': 80}, valid | {'expires_at': 1},
                  valid | {'invitation_id': None}, valid | {'name': None}, valid]
        packets = [(value if isinstance(value, bytes) else json.dumps(value).encode(), ('192.168.1.2', 8766)) for value in values]
        packets.insert(0, (json.dumps(valid).encode(), ('8.8.8.8', 8766)))
        udp = MagicMock()
        udp.__enter__.return_value = udp
        udp.recvfrom.side_effect = packets + [socket.timeout()] * 30
        ticks = count()
        with patch.object(module, '_discovery_socket', return_value=udp), patch.object(module.secrets, 'token_hex', return_value=nonce), patch.object(module.time, 'monotonic', side_effect=lambda: next(ticks)), patch.object(module.time, 'time', return_value=1000):
            result = module.discover_waiting(timeout=20)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'PCFicticia')
        self.assertEqual(result[0]['url'], 'https://192.168.1.2:8767')
        udp.bind.assert_called_once_with(('192.168.1.1', 0))
        udp.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        udp.sendto.assert_called_once()
        self.assertEqual(udp.sendto.call_args.args[1], (module.DISCOVERY_GROUP, module.DISCOVERY_PORT))

    def test_busqueda_directa_ignora_respuestas_de_otra_ip(self):
        udp = MagicMock()
        udp.__enter__.return_value = udp
        packet = json.dumps(dict(protocol=module.PROTOCOL, nonce='a' * 32, invitation_id='ficticia',
                                 name='PC', port=8767, expires_at=2000)).encode()
        udp.recvfrom.side_effect = [(packet, ('192.168.1.9', 8766)), (packet, ('192.168.1.2', 8766))]
        with (patch.object(module, '_discovery_socket', return_value=udp),
              patch.object(module, 'local_address', return_value='192.168.1.1'),
              patch.object(module.secrets, 'token_hex', return_value='a' * 32),
              patch.object(module.time, 'time', return_value=1000),
              patch.object(module.time, 'monotonic', side_effect=count())):
            found = module.discover_waiting(timeout=3, address='192.168.1.2')
        self.assertEqual([entry['url'] for entry in found], ['https://192.168.1.2:8767'])
        self.assertEqual(udp.sendto.call_args.args[1], ('192.168.1.2', module.DISCOVERY_PORT))
        udp.setsockopt.assert_not_called()
        with self.assertRaises(ValueError):
            module.discover_waiting(address='8.8.8.8')

    def test_respaldo_udp_consulta_solo_la_subred_conectada(self):
        wifi, other = Mock(), Mock()
        network = module.ipaddress.IPv4Network('192.168.1.0/29')
        sockets = {'192.168.1.2': wifi, '10.0.0.2': other}
        found = {}

        def collect(_sockets, _nonce, results, timeout, _address):
            if timeout == 1.2:
                results['pc'] = {'url': 'https://192.168.1.3:8767'}

        with (patch.object(module, '_windows_ipv4_subnets', return_value={'192.168.1.2': network}),
              patch.object(module, '_collect_invitations', side_effect=collect)):
            module._discover_without_multicast(sockets, b'consulta', 'a' * 32, found)
        self.assertEqual(found['pc']['url'], 'https://192.168.1.3:8767')
        self.assertEqual([call.args[1] for call in wifi.sendto.call_args_list],
                         [(f'192.168.1.{host}', module.DISCOVERY_PORT) for host in (2, 1, 3, 4, 5, 6)])
        other.sendto.assert_not_called()

    def test_reinicios_udp_se_toleran_y_otros_errores_se_propagan(self):
        """Un puerto sin receptor no se confunde con un fallo general de red."""
        self.assertTrue(module._is_udp_reset(ConnectionResetError()))
        self.assertTrue(module._is_udp_reset(OSError(10054, 'ficticio')))
        self.assertFalse(module._is_udp_reset(OSError(5, 'ficticio')))
        udp = MagicMock()
        udp.__enter__.return_value = udp
        udp.sendto.side_effect = [ConnectionResetError(), None]
        udp.recvfrom.side_effect = [ConnectionResetError(), socket.timeout(), socket.timeout()]
        ticks = count()
        with patch.object(module, '_discovery_socket', return_value=udp), patch.object(module.time, 'monotonic', side_effect=lambda: next(ticks)):
            self.assertEqual(module.discover_waiting(timeout=3), [])
        for stage in ('sendto', 'recvfrom'):
            udp.sendto.side_effect = None
            udp.recvfrom.side_effect = socket.timeout()
            getattr(udp, stage).side_effect = OSError(5, 'fallo ficticio')
            ticks = count()
            with patch.object(module, '_discovery_socket', return_value=udp), patch.object(module.time, 'monotonic', side_effect=lambda: next(ticks)), self.assertRaises(OSError):
                module.discover_waiting(timeout=3)

    def test_busqueda_tiene_limite_de_equipos_y_nombre_alternativo(self):
        """El límite de 32 resultados no depende de cuántos paquetes envíe un emisor."""
        udp = MagicMock()
        udp.__enter__.return_value = udp
        udp.recvfrom.side_effect = [(json.dumps(dict(protocol=module.PROTOCOL, nonce='a' * 32, invitation_id=str(index), name='\n', port=8767, expires_at=2000)).encode(), ('192.168.1.2', 0)) for index in range(40)]
        ticks = count()
        with patch.object(module, '_discovery_socket', return_value=udp), patch.object(module.secrets, 'token_hex', return_value='a' * 32), patch.object(module.time, 'monotonic', side_effect=lambda: next(ticks)), patch.object(module.time, 'time', return_value=1000):
            result = module.discover_waiting(timeout=100)
        self.assertEqual(len(result), 32)
        self.assertEqual(result[0]['name'], 'PC de consulta')

    def test_receptor_acota_la_escucha_a_la_interfaz_o_al_grupo(self):
        """Comprueba los enlaces y la membresía en Windows y Linux."""
        interface = '192.168.1.1'
        group = socket.inet_aton(module.DISCOVERY_GROUP) + socket.inet_aton(interface)
        for platform, address in (('win32', interface), ('linux', module.DISCOVERY_GROUP)):
            with self.subTest(platform=platform):
                lan, multicast, local = Mock(), Mock(), Mock()
                sockets = [lan, local] if platform == 'win32' else [lan, multicast, local]
                with (patch.object(module.sys, 'platform', platform),
                      patch.object(module, '_discovery_interfaces', return_value=(interface, module.LOOPBACK)),
                      patch.object(module, '_discovery_socket', side_effect=sockets)):
                    responder = module.DiscoveryResponder(lambda: None)
                self.addCleanup(responder.close)
                lan.bind.assert_called_once_with((interface, module.DISCOVERY_PORT))
                receiver = lan if platform == 'win32' else multicast
                receiver.bind.assert_called_once_with((address, module.DISCOVERY_PORT))
                receiver.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group)
                local.bind.assert_called_once_with((module.LOOPBACK, module.DISCOVERY_PORT))

    def test_responder_descarta_entradas_y_limita_frecuencia(self):
        """El receptor responde solo a consultas válidas y evita amplificar ráfagas."""
        udp = Mock()
        valid = dict(protocol=module.PROTOCOL, kind='discover', nonce='a' * 32)
        packets = [b'{', b'[' * 1000 + b']' * 1000, b'[]', json.dumps(valid | {'kind': 'otra'}).encode(), json.dumps(valid | {'nonce': 1}).encode(),
                   json.dumps(valid).encode(), json.dumps(valid).encode()]
        with patch.object(module, '_discovery_socket', return_value=udp):
            responder = self.make_responder(lambda: {'name': 'Ficticia'})
        pending = iter(packets)
        def receive(size):
            """Finaliza el bucle cuando se agotan los paquetes sintéticos."""
            try:
                return next(pending), ('192.168.1.2', 8766)
            except StopIteration:
                responder.stop.set()
                raise OSError('fin ficticio')
        udp.recvfrom.side_effect = receive
        with patch.object(module.time, 'monotonic', side_effect=[10, 10, 10.1]):
            responder.run()
        self.assertEqual(udp.sendto.call_count, 1)
        self.assertEqual(json.loads(udp.sendto.call_args.args[0])['nonce'], 'a' * 32)

    def test_cierre_sin_arranque_es_seguro_y_repetible(self):
        """Limpiar una preparación fallida no exige haber podido iniciar el hilo."""
        with patch.object(module, '_discovery_socket', return_value=Mock()):
            responder = self.make_responder(lambda: None)
        responder.close()
        responder.close()
        self.assertTrue(responder.stop.is_set())

    def test_hilo_responder_arranca_y_cierra_sin_trafico(self):
        """El cierre desbloquea al hilo real sin dejar un trabajador activo."""
        udp = Mock()
        entered, released = threading.Event(), threading.Event()
        def receive(size):
            """Simula recepción bloqueada hasta cerrar el socket."""
            entered.set()
            released.wait(timeout=3)
            raise OSError('socket cerrado ficticio')
        udp.recvfrom.side_effect = receive
        udp.close.side_effect = released.set
        with patch.object(module, '_discovery_socket', return_value=udp):
            responder = self.make_responder(lambda: None)
        responder.start()
        self.assertTrue(entered.wait(timeout=2))
        responder.close()
        self.assertFalse(responder.thread.is_alive())


class PruebasEntradasPrograma(unittest.TestCase):
    """Las entradas coordinan recursos, sin abrir una base o ventana reales."""

    def test_worker_argumentos_y_error_no_abren_interfaz(self):
        """La ejecución diaria usa las rutas de CLI y devuelve códigos de salida claros."""
        args = ['backup_worker', '--database', 'ficticia.db', '--settings', 'ajustes.json', '--network', 'red.json']
        with patch.object(backup_worker.sys, 'argv', args), patch.object(backup_worker, 'run_daily_backup') as run:
            self.assertEqual(backup_worker.main(), 0)
            run.assert_called_once_with(Path('ficticia.db'), Path('ajustes.json'), Path('red.json'))
            run.side_effect = OSError('fallo ficticio')
            self.assertEqual(backup_worker.main(), 1)

    def test_arranque_normal_y_error_cierran_recursos(self):
        """Un fallo al abrir la ventana no deja gestor, conexión o programador activos."""
        with patch('hemeroteca.network.manager.NetworkManager') as manager, patch('hemeroteca.services.backup_service.BackupScheduler') as scheduler, patch('hemeroteca.ui.main_view.HemerotecaApp') as app:
            entry.main()
            app.return_value.mainloop.assert_called_once()
            app.return_value.services.close.assert_called_once()
            scheduler.return_value.close.assert_called_once()
            manager.return_value.close.assert_called_once()
        with patch('hemeroteca.network.manager.NetworkManager') as manager, patch('hemeroteca.services.backup_service.BackupScheduler') as scheduler, patch('hemeroteca.ui.main_view.HemerotecaApp', side_effect=ValueError('ventana ficticia fallida')):
            with self.assertRaises(ValueError):
                entry.main()
            manager.return_value.services.return_value.close.assert_called_once()
            scheduler.return_value.close.assert_called_once()
            manager.return_value.close.assert_called_once()

    def test_fallo_al_obtener_servicios_cierra_programador_y_gestor(self):
        """Incluso sin conexión creada se ejecuta el cierre de la infraestructura."""
        with patch('hemeroteca.network.manager.NetworkManager') as manager, patch('hemeroteca.services.backup_service.BackupScheduler') as scheduler:
            manager.return_value.services.side_effect = ValueError('servicios ficticios fallidos')
            with self.assertRaises(ValueError):
                entry.main()
            scheduler.return_value.close.assert_called_once()
            manager.return_value.close.assert_called_once()
