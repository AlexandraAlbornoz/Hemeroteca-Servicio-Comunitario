"""Entradas hostiles y fallos de recursos en los módulos menos cubiertos."""
import ctypes
import json
import runpy
import unittest
from unittest.mock import Mock, patch
from hemeroteca.network import discovery as d
from hemeroteca.utils import security as s
from hemeroteca.config.settings import SECURITY_QUESTIONS


class PruebasDescubrimientoPendiente(unittest.TestCase):
    """Paquetes, reloj y Winsock controlados sin emitir tráfico UDP."""

    def setUp(self):
        self.enterContext(patch.object(d, '_discovery_interfaces', return_value=('192.168.1.1',)))

    def valid(self, **kw):
        return dict(protocol=d.PROTOCOL,nonce='a'*32,invitation_id='invitacion',name='PC',port=8765,expires_at=2000)|kw

    def make_responder(self, description):
        with patch.object(d.sys, 'platform', 'win32'):
            return d.DiscoveryResponder(description)

    def search(self, packets):
        udp=Mock()
        udp.__enter__=Mock(return_value=udp);udp.__exit__=Mock(return_value=False)
        udp.recvfrom.side_effect=[(p,('192.168.1.3',8766)) for p in packets]+[OSError('fin')]
        # El plazo termina después de procesar cada datagrama.
        ticks=iter([0]+[0]*len(packets)+[10])
        with patch.object(d,'_discovery_socket',return_value=udp),patch.object(d.secrets,'token_hex',return_value='a'*32),patch.object(d.time,'time',return_value=1000),patch.object(d.time,'monotonic',side_effect=lambda:next(ticks)):
            return d.discover_waiting(timeout=1)

    def responder(self, packets, description=None):
        udp=Mock()
        with patch.object(d,'_discovery_socket',return_value=udp):r=self.make_responder(description or (lambda:None))
        pending=iter(packets)
        def receive(size):
            try:return next(pending)
            except StopIteration:
                r.stop.set();raise OSError('fin')
        udp.recvfrom.side_effect=receive
        return r,udp

    def test_descubrimiento_descarta_profundidad_y_puerto_infinito(self):
        packets=[b'['*1800+b']'*1800,json.dumps(self.valid(port=float('inf'))).encode(),json.dumps(self.valid()).encode()]
        result=self.search(packets)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['url'],'https://192.168.1.3:8765')

    def test_responder_tolera_json_profundo_y_sigue_respondiendo(self):
        valid=json.dumps(dict(protocol=d.PROTOCOL,kind='discover',nonce='a'*32)).encode()
        r,udp=self.responder([(b'['*1000+b']'*1000,('192.168.1.3',8766)),(valid,('192.168.1.3',8766))],lambda:{'name':'PC'})
        with patch.object(d.time,'monotonic',return_value=10):r.run()
        self.assertEqual(udp.sendto.call_count,1)
        r.close()

    def test_inicializacion_fallida_libera_socket(self):
        for operation in ['setsockopt','bind','settimeout']:
            with self.subTest(operation=operation):
                udp=Mock();getattr(udp,operation).side_effect=OSError('fallo')
                with patch.object(d,'_discovery_socket',return_value=udp),self.assertRaises(OSError):self.make_responder(lambda:None)
                udp.close.assert_called_once()

    def test_error_preparando_hilo_libera_socket(self):
        udp=Mock()
        with patch.object(d,'_discovery_socket',return_value=udp),patch.object(d.threading,'Thread',side_effect=RuntimeError('sin recursos')),self.assertRaises(RuntimeError):
            self.make_responder(lambda:None)
        udp.close.assert_called_once()

    def test_descubrimiento_descarta_expiracion_infinita_y_deduplica(self):
        packets=[json.dumps(self.valid(expires_at=float('inf'))).encode(),json.dumps(self.valid()).encode(),json.dumps(self.valid(name='Actualizada')).encode()]
        result=self.search(packets)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['name'],'Actualizada')

    def test_winsock_informa_error_sin_perder_socket(self):
        udp=Mock();winsock=Mock();winsock.WSAIoctl.return_value=-1;winsock.WSAGetLastError.return_value=10022
        with patch.object(d.sys,'platform','win32'),patch.object(d.socket,'socket',return_value=udp),patch.object(ctypes,'WinDLL',return_value=winsock),self.assertLogs(d.__name__,level='DEBUG') as logs:
            self.assertIs(d._discovery_socket(),udp)
        self.assertIn('10022',str(logs.output));udp.close.assert_not_called()

    def test_responder_limita_fuentes_y_limpia_historial(self):
        packet=json.dumps(dict(protocol=d.PROTOCOL,kind='discover',nonce='a'*32)).encode()
        packets=[(packet,(f'10.0.{n//250}.{n%250+1}',8766)) for n in range(257)]
        # Se vuelve a aceptar una fuente antigua tras la limpieza acotada.
        packets.append(packets[0])
        r,udp=self.responder(packets,lambda:{'name':'PC'})
        with patch.object(d.time,'monotonic',return_value=10):r.run()
        self.assertEqual(udp.sendto.call_count,258);r.close()

    def test_responder_reinicio_y_error_fatal_se_distinguen(self):
        for error in [ConnectionResetError(10054,'reinicio'),OSError(5,'fatal')]:
            with self.subTest(error=type(error).__name__):
                r,udp=self.responder([])
                calls=iter([error,OSError('fin')])
                def receive(size):
                    exc=next(calls)
                    if str(exc)=='fin':r.stop.set()
                    raise exc
                udp.recvfrom.side_effect=receive
                with patch.object(d.logging.getLogger(d.__name__),'exception') as log:r.run()
                self.assertEqual(log.call_count,0 if isinstance(error,ConnectionResetError) else 1)
                r.close()

    def test_responder_sin_invitacion_no_responde(self):
        packet=json.dumps(dict(protocol=d.PROTOCOL,kind='discover',nonce='a'*32)).encode()
        r,udp=self.responder([(packet,('192.168.1.3',8766))])
        with patch.object(d.time,'monotonic',return_value=10):r.run()
        udp.sendto.assert_not_called();r.close()


class PruebasSeguridadPendiente(unittest.TestCase):
    """Errores de representación y normalización sin cambiar el hashing heredado."""

    def test_hash_guardado_malformado_devuelve_false(self):
        for saved in ['sin separador','zz:00','00:á','0:00']:
            with self.subTest(saved=saved):self.assertFalse(s.password_matches('ejemplo',saved))

    def test_preguntas_fuera_de_catalogo_y_respuesta_expandida(self):
        with self.assertRaisesRegex(ValueError,'lista disponible'):
            s.prepare_security_questions([('Pregunta no incluida','respuesta')]*3)
        with self.assertRaisesRegex(ValueError,'entre 2 y 50'):
            s.prepare_security_questions([(SECURITY_QUESTIONS[0],'ß'*50)]*3)

    def test_estructura_malformada_de_preguntas_error_controlado(self):
        for value in [1,{},[None]*3,[(None,'respuesta')]*3,[('pregunta',None)]*3,[('uno',)]*3]:
            with self.subTest(value=value),self.assertRaises(ValueError):s.prepare_security_questions(value)


class PruebasEntradasDirectas(unittest.TestCase):
    """Invoca los guardas de ejecución con servicios sustituidos."""

    def test_worker_directo_devuelve_codigo_sin_abrir_base(self):
        with patch('sys.argv',['worker']),patch('hemeroteca.services.backup_service.run_daily_backup') as run:
            with self.assertRaises(SystemExit) as result:runpy.run_module('hemeroteca.backup_worker',run_name='__main__')
            self.assertEqual(result.exception.code,0);run.assert_called_once()

    def test_main_directo_cierra_recursos(self):
        with patch('hemeroteca.network.manager.NetworkManager') as manager,patch('hemeroteca.services.backup_service.BackupScheduler') as scheduler,patch('hemeroteca.ui.main_view.HemerotecaApp') as app:
            runpy.run_module('hemeroteca.main',run_name='__main__')
            app.return_value.mainloop.assert_called_once();scheduler.return_value.close.assert_called_once();manager.return_value.close.assert_called_once()
