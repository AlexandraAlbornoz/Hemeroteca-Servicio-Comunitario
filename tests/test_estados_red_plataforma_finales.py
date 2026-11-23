"""Revalidación del servidor, rollback repetido y respaldo sin tarea Windows."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from hemeroteca.network import manager as module
from hemeroteca.network.devices import DeviceIdentity
from hemeroteca.services import backup_service
from hemeroteca.services.access_service import AccessDenied
from tests import test_gestion_red as network
from tests import test_servidor_rpc as server
from tests import test_respaldos_operacion as backups


class PruebasServidorCambioDuranteOferta(unittest.TestCase):
    setUpClass=classmethod(network.PruebasGestionRed.setUpClass.__func__)
    tearDownClass=classmethod(network.PruebasGestionRed.tearDownClass.__func__)
    setUp=network.PruebasGestionRed.setUp
    servidor_guardado=network.PruebasGestionRed.servidor_guardado
    def test_oferta_firmada_no_autoriza_si_deja_de_ser_servidor(self):
        self.servidor_guardado();identity=DeviceIdentity(self.root/'equipo-temporal.key')
        candidate={'url':'https://127.0.0.1:8767','fingerprint':'a'*64,'invitation_id':'invitacion-ficticia','name':'PC ficticia'}
        hello=dict(invitation_id=candidate['invitation_id'],public_key=identity.public_key,nonce='nonce',node_id='cliente')
        def response(url,pin,path,payload=None,**kw):
            if path=='/pair/hello':return hello
            self.manager.settings['mode']='client'
            return {'signature':identity.sign(module.canonical(payload['offer'])),'device_id':identity.device_id}
        with patch.object(module,'request',side_effect=response) as request,patch.object(module,'local_address',return_value='127.0.0.1'):
            with self.assertRaisesRegex(AccessDenied,'ya no es el servidor'):
                self.manager.approve_computer(self.s,self.master,candidate,'ABCDEFGHJKMN',network.CLAVE)
        self.assertEqual(request.call_count,2)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM authorized_devices').fetchone()[0],0)


class PruebasRollbackYaAplicado(unittest.TestCase):
    setUpClass=classmethod(server.PruebasEstadoServidor.setUpClass.__func__)
    tearDownClass=classmethod(server.PruebasEstadoServidor.tearDownClass.__func__)
    setUp=server.PruebasEstadoServidor.setUp
    def test_propietario_local_sin_traslado_no_se_modifica(self):
        with self.services.connection:
            self.services.connection.execute("INSERT INTO system_settings(key,value) VALUES('active_host_id','local') ON CONFLICT(key) DO UPDATE SET value='local'")
        before=dict(self.services.connection.execute('SELECT key,value FROM system_settings'))
        self.s._restore_owner(self.services,'sin-traslado')
        self.s._restore_owner(self.services,'sin-traslado')
        self.assertEqual(dict(self.services.connection.execute('SELECT key,value FROM system_settings')),before)
        self.assertFalse(self.services.connection.in_transaction)


class PruebasRespaldoSinWindows(unittest.TestCase):
    setUpClass=classmethod(backups.PruebasOperacionRespaldos.setUpClass.__func__)
    tearDownClass=classmethod(backups.PruebasOperacionRespaldos.tearDownClass.__func__)
    setUp=backups.PruebasOperacionRespaldos.setUp
    def test_configurar_y_desactivar_no_programa_tarea_windows(self):
        with patch.object(backup_service,'os',SimpleNamespace(name='posix')),patch.object(self.service,'_schedule_windows') as schedule:
            state=self.service.configure(self.master,backups.CLAVE,'RespaldoFicticio#2026',str(self.output),'12:30')
            self.assertTrue(state['enabled']);self.assertEqual(state['scheduler'],'app')
            self.service.disable(self.master,backups.CLAVE)
        schedule.assert_not_called()
        self.assertFalse(backup_service.read_settings(self.service.settings_path)['enabled'])
        self.assertTrue(list(self.output.glob('*.hmbackup')))
