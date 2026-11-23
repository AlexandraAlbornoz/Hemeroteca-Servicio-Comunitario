"""Errores, cancelación y entregas tardías sin reemplazar los controles Tk."""
from collections import namedtuple
from concurrent.futures import Future
import gc
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import customtkinter as ctk
from hemeroteca.config.settings import SECURITY_QUESTIONS
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.container import create_services
from hemeroteca.ui.carga import CargaDeVistas
from hemeroteca.ui.tareas import ServiciosDeInterfaz, materializar


class VentanaLecturas(CargaDeVistas, ctk.CTk):
    """Raíz gráfica auténtica con captura explícita de errores Tcl."""

    def __init__(self):
        super().__init__()
        self.withdraw()
        self.user = {'id': 1, 'password_version': 1}
        self._sync_session = Mock()
        self.errors = []
        self.report_callback_exception = lambda kind,error,trace: self.errors.append(error)
        self.panel = ctk.CTkFrame(self)
        self.panel.pack()

    def clean(self):
        for task in self.tk.splitlist(self.tk.call('after','info')):
            self.tk.call('after','cancel',task)
        self.destroy()
        if self.errors:
            raise AssertionError(self.errors)


class PruebasVigenciaDeCarga(unittest.TestCase):
    """Controla el orden de entrega mediante futuros; no necesita esperas temporales."""

    def setUp(self):
        self.h = VentanaLecturas()
        self.addCleanup(self.h.clean)
        self.calls = []
        def submit(queries, receive, fail):
            f = Future()
            self.calls.append((f,receive,fail))
            return f
        self.h.services = SimpleNamespace(leer_async=submit, access=Mock())
        self.present, self.fail = Mock(), Mock()

    def load(self, **kwargs):
        return self.h._cargar_seccion(self.h.panel, [], self.present, error=self.fail, **kwargs)

    def indicator(self, key='datos'):
        return self.h.panel._indicadores_carga[key]

    def test_error_vigente_se_muestra_y_el_reintento_limpia_indicador(self):
        self.load()
        error = OSError('conexión ficticia interrumpida')
        self.calls[0][2](error)
        self.assertEqual(self.indicator().cget('text'), str(error))
        self.fail.assert_called_once_with(error)
        self.load()
        self.assertEqual(self.indicator().cget('text'), 'Cargando…')
        self.calls[1][1](['resultado nuevo'])
        self.assertEqual(self.indicator().cget('text'), '')
        self.present.assert_called_once_with(['resultado nuevo'])

    def test_error_acceso_agenda_sincronizacion_sin_bloquear(self):
        self.load()
        self.calls[0][2](AccessDenied('permiso revocado'))
        self.h._sync_session.assert_not_called()
        self.h.update_idletasks()
        self.h._sync_session.assert_called_once()

    def test_error_sin_callback_es_visible(self):
        self.h._cargar_seccion(self.h.panel, [], self.present)
        self.calls[0][2](ValueError('filtro inválido'))
        self.assertEqual(self.indicator().cget('text'), 'filtro inválido')

    def test_errores_y_resultados_antiguos_no_pisan_filtro_nuevo(self):
        self.load()
        self.calls[0][0].set_running_or_notify_cancel()
        self.load()
        self.calls[1][1](['último'])
        self.calls[0][2](AccessDenied('error antiguo'))
        self.calls[0][1](['obsoleto'])
        self.h.update_idletasks()
        self.present.assert_called_once_with(['último'])
        self.fail.assert_not_called()
        self.h._sync_session.assert_not_called()

    def test_cambio_de_identidad_version_o_salida_descarta_entregas(self):
        for user in [None, {'id':2,'password_version':1}, {'id':1,'password_version':2}]:
            self.h.user = {'id':1,'password_version':1}
            self.load()
            self.h.user = user
            self.calls[-1][1](['privado'])
            self.calls[-1][2](AccessDenied('obsoleto'))
        self.h.update_idletasks()
        self.present.assert_not_called()
        self.fail.assert_not_called()
        self.h._sync_session.assert_not_called()

    def test_generacion_y_padre_destruido_descartan_resultados_y_errores(self):
        future = self.load()
        self.h._invalidar_cargas()
        self.assertTrue(future.cancelled())
        self.calls[-1][1](['anterior'])
        self.load()
        self.h.panel.destroy()
        self.calls[-1][1](['sin ventana'])
        self.calls[-1][2](ValueError('sin ventana'))
        self.present.assert_not_called()
        self.fail.assert_not_called()

    def test_claves_distintas_no_se_cancelan_y_reutilizan_indicadores(self):
        a = self.load(clave='tabla')
        self.load(clave='resumen')
        indicator = self.indicator('tabla')
        self.assertFalse(a.cancelled())
        self.load(clave='tabla')
        self.assertTrue(a.cancelled())
        self.assertIs(indicator, self.indicator('tabla'))
        self.calls[1][1](['resumen'])
        self.calls[2][1](['tabla'])
        self.assertEqual(self.present.call_count, 2)

    def test_indicador_en_grid_y_recreacion_si_se_destruye(self):
        self.h.panel.pack_forget()
        self.h.panel.grid()
        label = ctk.CTkLabel(self.h.panel, text='Cabecera')
        label.grid(row=0,column=0)
        self.load()
        self.assertEqual(self.indicator().winfo_manager(), 'grid')
        old = self.indicator()
        old.destroy()
        self.load()
        self.assertIsNot(self.indicator(), old)

    def test_futuros_terminados_no_se_acumulan_y_permisos_no_se_cachean(self):
        self.load()
        self.calls[0][0].set_result([])
        self.load()
        self.assertEqual(len(self.h._futuros_vista), 1)
        self.h.services.access.permissions.return_value = ['Uno']
        self.assertEqual(self.h._permisos_actuales(), {'Uno'})
        self.h._contexto_construccion = {'Dos'}
        self.assertEqual(self.h._permisos_actuales(), {'Dos'})

    def test_fallo_al_programar_consulta_no_deja_cargando(self):
        for error in [RuntimeError('ejecutor no disponible'), ValueError('servicios cerrados')]:
            self.h.services.leer_async = Mock(side_effect=error)
            future = self.load()
            self.assertTrue(future.done())
            self.assertIs(future.exception(), error)
            self.assertEqual(self.indicator().cget('text'), str(error))
        self.assertEqual(self.fail.call_count,2)


class PruebasTrabajadoresReales(unittest.TestCase):
    """Usa ejecutores reales, conexiones propias y el bucle Tk sin esperas modales."""

    @classmethod
    def setUpClass(cls):
        cls.seed = create_services(':memory:')
        cls.seed.auth.create_master('Maestra Ficticia', 'V-12345678', 'Prueba#2026',
                                    tuple(zip(SECURITY_QUESTIONS[:3],('Luna','Sol','Mar'))))
        cls.actor = cls.seed.auth.authenticate('V-12345678','Prueba#2026')

    @classmethod
    def tearDownClass(cls):
        cls.seed.close()

    def setUp(self):
        self.initial_gc = gc.isenabled()
        self.temp = tempfile.TemporaryDirectory()
        self.h = VentanaLecturas()
        self.original = create_services(Path(self.temp.name)/'prueba.db')
        self.seed.connection.backup(self.original.connection)
        self.h.user = dict(self.actor)
        self.s = ServiciosDeInterfaz(self.h,self.original)
        self.h.services = self.s
        self.main_thread = threading.get_ident()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        try:
            self.pump(lambda: self.s._trabajos==0)
            self.assertEqual(gc.isenabled(),self.initial_gc)
        finally:
            self.s.close()
            self.h.clean()
            self.temp.cleanup()
            gc.enable() if self.initial_gc else gc.disable()

    def pump(self, condition, timeout=5):
        end = time.monotonic()+timeout
        while not condition() and time.monotonic()<end:
            self.h.update()
            time.sleep(.001)
        self.assertTrue(condition(),'El trabajador no entregó resultado dentro del plazo')

    def query(self):
        return self.s.consulta('periodicos','search_issues',self.h.user)

    def test_resultado_sqlite_y_callback_llegan_en_tk_sin_modal(self):
        received = []
        def receive(data):
            received.append((threading.get_ident(),data))
        with patch('hemeroteca.ui.tareas.tk.Toplevel') as modal:
            self.s.leer_async([self.query()],receive,lambda e:self.fail(str(e)))
            self.pump(lambda: bool(received))
            modal.assert_not_called()
        self.assertEqual(received[0][0],self.main_thread)
        self.assertEqual(received[0][1][0]['total'],0)
        self.assertEqual(self.s._trabajos,0)

    def test_errores_sqlite_red_y_negocio_se_entregan_sin_perder_gc(self):
        for exception in [sqlite3.OperationalError('base ocupada'), OSError('red caída'), ValueError('filtro inválido'), RuntimeError('fallo controlado'), AccessDenied('permiso revocado')]:
            errors = []
            with patch.object(self.s,'_con_servicios',side_effect=exception):
                self.s.leer_async([self.query()],lambda data:self.fail('No debía entregar datos'),lambda e:errors.append((threading.get_ident(),e)))
                self.pump(lambda: bool(errors))
            self.assertEqual(errors,[(self.main_thread,exception)])
            self.assertEqual(self.s._trabajos,0)

    def test_resultados_invertidos_y_error_antiguo_no_reemplazan_actual(self):
        started, release = threading.Event(), threading.Event()
        received = []
        count = 0
        lock = threading.Lock()
        def work(*args):
            nonlocal count
            with lock:
                count+=1
                first = count==1
            if first:
                started.set()
                if not release.wait(4): raise ValueError('plazo de prueba')
                raise AccessDenied('error de filtro anterior')
            return ['resultado actual']
        with patch.object(self.s,'_con_servicios',side_effect=work):
            try:
                self.h._cargar_seccion(self.h.panel,[],received.append)
                self.assertTrue(started.wait(2))
                self.h._cargar_seccion(self.h.panel,[],received.append)
                self.pump(lambda: bool(received))
                release.set()
                self.pump(lambda: self.s._trabajos==0)
            finally:
                release.set()
        self.assertEqual(received,[['resultado actual']])
        self.h._sync_session.assert_not_called()

    def test_cancelacion_en_cola_y_cierre_descartan_entregas(self):
        started, release = threading.Event(), threading.Event()
        def block(*args):
            started.set()
            if not release.wait(4): raise ValueError('plazo de prueba')
            return ['tardío']
        received, errors = [], []
        with patch.object(self.s,'_con_servicios',side_effect=block):
            try:
                self.s.leer_async([],received.append,errors.append)
                self.assertTrue(started.wait(2))
                self.s.leer_async([],received.append,errors.append)
                queued = self.s.leer_async([],received.append,errors.append)
                self.assertTrue(queued.cancel())
                self.s.close()
                release.set()
                self.pump(lambda: self.s._trabajos==0)
            finally:
                release.set()
        self.assertEqual(received,[])
        self.assertEqual(errors,[])

    def test_lane_autorizacion_no_espera_a_dos_lecturas_lentas(self):
        release = threading.Event()
        both = threading.Barrier(3)
        original = self.s._con_servicios
        def work(operation,*args):
            # Las dos primeras tareas no ejecutan SQL; ocupan los lectores.
            if threading.current_thread().name.startswith('hemeroteca-lecturas'):
                both.wait(timeout=3)
                if not release.wait(4): raise ValueError('plazo de prueba')
                return []
            return original(operation,*args)
        results = []
        with patch.object(self.s,'_con_servicios',side_effect=work):
            try:
                for _ in range(2): self.s.leer_async([],lambda d:None,lambda e:self.fail(str(e)))
                both.wait(timeout=3)
                self.s.leer_async([self.s.consulta('access','permissions',self.h.user)],results.append,lambda e:self.fail(str(e)))
                self.pump(lambda: bool(results))
                self.assertFalse(release.is_set())
            finally:
                release.set()
                self.pump(lambda: self.s._trabajos==0)

    def test_rechazo_submit_async_restaura_contador_y_gc(self):
        with patch.object(self.s.lectores,'submit',side_effect=RuntimeError('ejecutor rechazado')):
            with self.assertRaises(RuntimeError):
                self.s.leer_async([],Mock(),Mock())
        self.assertEqual(self.s._trabajos,0)
        self.assertEqual(gc.isenabled(),self.initial_gc)

    def test_rechazo_submit_modal_desbloquea_interfaz(self):
        with patch.object(self.s.ejecutor,'submit',side_effect=RuntimeError('ejecutor rechazado')):
            with self.assertRaises(RuntimeError):
                self.s.ejecutar('periodicos','search_issues',(self.h.user,),{})
        self.assertFalse(self.h._servicios_ocupados)
        self.assertEqual(self.s._trabajos,0)

    def test_consulta_captura_filtros_y_actor_antes_del_hilo(self):
        filters = {'title':'Ficticio','nested':[1]}
        actor = dict(self.h.user)
        descriptor = self.s.consulta('periodicos','search_issues',actor,filters=filters)
        actor['id']=99
        filters['nested'].append(2)
        self.assertEqual(descriptor[2][0]['id'],self.h.user['id'])
        self.assertEqual(descriptor[3]['filters']['nested'],[1])

    def test_materializar_desvincula_filas_y_conserva_namedtuple(self):
        row = self.original.connection.execute('SELECT id,name FROM users').fetchone()
        result = namedtuple('Resultado','row values')(row,[row])
        data = materializar({'tuple':(result,row),'list':[row]})
        self.assertIsInstance(data['tuple'][0],type(result))
        self.assertEqual(data['list'][0]['id'],self.actor['id'])

    def test_servicios_cerrados_y_operacion_ocupada_no_inician_trabajos(self):
        self.h._servicios_ocupados=True
        with self.assertRaises(ValueError): self.s.ejecutar('periodicos','search_issues',(self.h.user,),{})
        self.h._servicios_ocupados=False
        self.s.close()
        with self.assertRaises(ValueError): self.s.leer_async([],Mock(),Mock())
        with self.assertRaises(ValueError): self.s.ejecutar('periodicos','search_issues',(self.h.user,),{})
        self.assertEqual(self.s._trabajos,0)

    def test_atributo_proxy_no_invoca_trabajador(self):
        self.assertIsNone(self.s.access.node_id)

    def test_conexion_temporal_se_cierra_tras_fallo_del_servicio(self):
        from hemeroteca.services import container
        real=container.create_services
        closed=[]
        def create(*args,**kwargs):
            services=real(*args,**kwargs)
            original_close=services.close
            def close():
                closed.append(threading.get_ident())
                original_close()
            services.close=close
            return services
        with patch.object(container,'create_services',side_effect=create):
            with self.assertRaisesRegex(ValueError,'fallo ficticio'):
                self.s._con_servicios(Mock(side_effect=ValueError('fallo ficticio')))
        self.assertEqual(len(closed),1)

    def test_lectura_remota_no_cierra_sesion_ni_sobrescribe_token_actual(self):
        remote=SimpleNamespace(read_only=True,network=Mock(),client=SimpleNamespace(settings={'server_url':'https://127.0.0.1:8888'},token='sesion-original'))
        client=SimpleNamespace(settings=dict(remote.client.settings),token=None)
        services=SimpleNamespace(client=client,close=Mock())
        original=self.s.original
        self.s.original=remote
        try:
            with patch('hemeroteca.network.client.RemoteClient',return_value=client),patch('hemeroteca.network.client.RemoteServices',return_value=services):
                def read(temporary):
                    self.assertEqual(temporary.client.token,'sesion-original')
                    temporary.client.token='token-tardio'
                    return ['lectura']
                self.assertEqual(self.s._con_servicios(read),['lectura'])
            self.assertEqual(remote.client.token,'sesion-original')
            services.close.assert_not_called()
        finally:self.s.original=original

    def test_operacion_remota_actualiza_token_y_destino_incluso_si_falla(self):
        remote=SimpleNamespace(read_only=True,network=Mock(),client=SimpleNamespace(settings={'server_url':'https://127.0.0.1:8888'},token='sesion-original'))
        client=SimpleNamespace(settings=dict(remote.client.settings),token=None)
        services=SimpleNamespace(client=client,close=Mock())
        original=self.s.original
        self.s.original=remote
        try:
            with patch('hemeroteca.network.client.RemoteClient',return_value=client),patch('hemeroteca.network.client.RemoteServices',return_value=services):
                def change(temporary):
                    temporary.client.token='sesion-actualizada'
                    temporary.client.settings={'server_url':'https://127.0.0.1:9999'}
                    raise ValueError('resultado no disponible')
                with self.assertRaises(ValueError):self.s._con_servicios(change,'auth','authenticate')
            self.assertEqual(remote.client.token,'sesion-actualizada')
            self.assertEqual(remote.client.settings['server_url'],'https://127.0.0.1:9999')
            services.close.assert_not_called()
        finally:self.s.original=original

    def test_agrupacion_preserva_gc_previamente_desactivado(self):
        gc.disable()
        try:
            with self.s.agrupar_interfaz():
                self.s._iniciar_trabajo()
                self.s._terminar_trabajo()
            self.assertFalse(gc.isenabled())
        finally:
            if self.initial_gc:gc.enable()
