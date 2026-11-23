"""Ramas de permisos, compatibilidad UDP y advertencia tras restauración."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from hemeroteca.config.settings import REPORT_ISSUES_PERMISSION
from hemeroteca.network import discovery
from hemeroteca.services import backup_service
from tests import test_usuarios_permisos_ramas as users
from tests import test_recuperacion_fallos as recovery
from tests import test_pantalla_login as login


class PruebasSolicitudMaestra(unittest.TestCase):
    """Usa la misma semilla real sin heredar casos anteriores."""
    setUpClass=classmethod(users.PruebasUsuariosPermisos.setUpClass.__func__)
    tearDownClass=classmethod(users.PruebasUsuariosPermisos.tearDownClass.__func__)
    setUp=users.PruebasUsuariosPermisos.setUp
    def test_maestro_no_puede_solicitar_permisos_para_si(self):
        before=self.s.connection.execute('SELECT count(*) FROM requests').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'administrador regular'):
            self.s.requests.submit_request(self.master,REPORT_ISSUES_PERMISSION,'Motivo ficticio')
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM requests').fetchone()[0],before)


class PruebasDescubrimientoCerrado(unittest.TestCase):
    def test_sin_opcion_exclusiva_y_cerrado_no_recibe_datagramas(self):
        udp=Mock()
        # Simula únicamente la ausencia de una constante específica de Windows.
        with patch.object(discovery,'socket',SimpleNamespace(SOL_SOCKET=1)),patch.object(discovery,'_discovery_socket',return_value=udp):
            responder=discovery.DiscoveryResponder(lambda:None)
            responder.stop.set();responder.run();responder.close()
        udp.setsockopt.assert_not_called();udp.recvfrom.assert_not_called();udp.close.assert_called_once()


class PruebasAdvertenciaTrasRestaurar(unittest.TestCase):
    setUp=recovery.PruebasRecuperacionFallos.setUp
    tearDown=recovery.PruebasRecuperacionFallos.tearDown
    def test_configuracion_diaria_no_guardada_informa_exito_con_advertencia(self):
        self.services.backups.settings_path.write_text('{"version":1,"enabled":false}',encoding='utf-8')
        with patch.object(backup_service,'write_json',side_effect=OSError('disco lleno ficticio')):
            result=self.services.backups.restore(self.actor,self.archive,self.backup_password,'Prueba#2026',self.digest)
        self.assertIn('ya se restauró',result['warning'])
        self.assertEqual(self.services.connection.execute('SELECT count(*) FROM issues').fetchone()[0],0)
        self.assertEqual(self.services.connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        from pathlib import Path
        self.assertTrue(Path(result['before']).is_file())


class PruebasFondoAccesoSinTrabajoPendiente(unittest.TestCase):
    def test_dimension_minima_no_programa_y_dimension_valida_programa(self):
        h=login.VentanaLogin();self.addCleanup(h.close_for_test)
        h._login_bg_resize_job=None
        with patch.object(h,'after',return_value='tarea-ficticia') as after:
            h._resize_login_background(SimpleNamespace(width=1,height=40,widget=h))
            after.assert_not_called()
            h._resize_login_background(SimpleNamespace(width=40,height=40,widget=h))
            after.assert_called_once()
            self.assertEqual(h._login_bg_resize_job,'tarea-ficticia')
        h._login_bg_resize_job=None
