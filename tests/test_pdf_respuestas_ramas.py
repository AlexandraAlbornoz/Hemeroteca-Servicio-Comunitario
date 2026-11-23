"""Respuesta PDF malformada y trabajador remoto con controles reales."""
import base64
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from tests.soporte_pantallas import VentanaGeneral
from tests import test_pantalla_usuarios_reportes as support
from hemeroteca.ui import reports_view as module


class PruebasRespuestaPDF(unittest.TestCase):
    """No guarda archivos fuera de un temporal ni invalida sesiones remotas."""

    run_pdf=support.PruebasUsuariosYReportes.run_pdf

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.h=VentanaGeneral()
        self.addCleanup(self.h.close_for_test)
        for name in ['showerror','showwarning','showinfo']:
            setattr(self,name,patch.object(module.messagebox,name).start())
        self.addCleanup(patch.stopall)

    def receive(self):
        for task in self.h.tk.splitlist(self.h.tk.call('after','info')):
            script,kind=self.h.tk.splitlist(self.h.tk.call('after','info',task))
            if str(script).endswith('recibir'):
                self.h.tk.call('after','cancel',task)
                self.h.tk.call(script)
                return
        self.fail('No hay callback de recepción')

    def test_respuestas_malformadas_no_guardan_archivo(self):
        encoded=base64.b64encode(b'%PDF-ficticio').decode()
        for response in [None,[],{},dict(content=None,records=1),dict(content=encoded),dict(content=encoded,records=True),dict(content=encoded,records=-1)]:
            with self.subTest(response=response):
                path=self.run_pdf(response)
                self.assertFalse(path.exists())
                self.assertEqual(self.h.callback_errors,[])

    def test_fallo_interno_del_trabajador_no_muestra_detalles_privados(self):
        path=self.run_pdf({},error=RuntimeError('ruta privada ficticia'))
        self.assertFalse(path.exists())
        self.showerror.assert_called_once()
        self.assertNotIn('ruta privada',str(self.showerror.call_args))

    def test_pdf_remoto_espera_revalida_permiso_y_no_hace_logout(self):
        self.h.services.read_only=True
        self.h.services.client=SimpleNamespace(settings={'server_url':'https://127.0.0.1:8765','fingerprint':'a'*64},token='sesion-ficticia')
        self.h._require_access.side_effect=[True,False]
        started,release=threading.Event(),threading.Event()
        threads=[]
        real_thread=threading.Thread
        def start_thread(**kwargs):
            thread=real_thread(**kwargs)
            threads.append(thread)
            return thread
        remote=Mock()
        def generate(*args,**kwargs):
            started.set()
            if not release.wait(3):raise ValueError('plazo ficticio')
            return dict(content=base64.b64encode(b'%PDF-ficticio').decode(),records=1)
        remote.reports.generate.side_effect=generate
        client=SimpleNamespace(token=None)
        path=self.root/'remoto.pdf'
        with patch.object(module,'threading',SimpleNamespace(Thread=start_thread)),patch('hemeroteca.network.client.RemoteClient',return_value=client),patch('hemeroteca.network.client.RemoteServices',return_value=remote),patch.object(module.filedialog,'asksaveasfilename',return_value=str(path)):
            try:
                self.h._export_pdf()
                self.assertTrue(started.wait(2))
                self.receive()  # La cola vacía debe programar un nuevo sondeo.
                release.set()
                threads[0].join(timeout=3)
                self.assertFalse(threads[0].is_alive())
                self.receive()
            finally:
                release.set()
                for thread in threads:thread.join(timeout=3)
        self.assertFalse(path.exists())
        self.assertEqual(client.token,'sesion-ficticia')
        remote.close.assert_not_called()
