"""Fallos de bloqueo y cupos HTTP sin cambiar la seguridad de Windows."""
import ctypes
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from hemeroteca.database import barrera as module
from hemeroteca.network.http_server import TLSHTTPServer


class PruebasBarreraErrores(unittest.TestCase):
    """Comprueba que los errores no dejen bloqueos o contadores retenidos."""

    def test_reintento_de_bloqueo_real_y_liberacion(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prueba.db'
            original=module.bloquear_archivo
            count=0
            def lock(*args):
                nonlocal count
                count+=1
                if count==1:raise OSError('ocupado ficticio')
                return original(*args)
            with patch.object(module,'bloquear_archivo',side_effect=lock):
                with module.database_guard(path,timeout=1):pass
            self.assertEqual(count,2)
            with module.database_guard(path,timeout=.5):pass

    def test_timeout_no_impide_siguiente_operacion(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prueba.db'
            with patch.object(module,'bloquear_archivo',side_effect=OSError('ocupado')),self.assertRaises(ValueError):
                with module.database_guard(path,timeout=0):pass
            with module.database_guard(path,timeout=.5):pass

    def test_error_de_apertura_o_unlock_libera_barrera_y_archivo(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prueba.db'
            with patch.object(Path,'open',side_effect=OSError('apertura fallida')),self.assertRaises(OSError):
                with module.database_guard(path):pass
            with patch.object(module,'liberar_archivo',side_effect=OSError('unlock fallido')),self.assertRaises(OSError):
                with module.database_guard(path):pass
            with module.database_guard(path,timeout=.5):pass
            self.assertEqual(getattr(module._adquiridos,'rutas',{}),{})

    def test_rama_posix_solo_invoca_flock_sin_simular_windows_real(self):
        fcntl=SimpleNamespace(flock=Mock(),LOCK_EX=2,LOCK_SH=1,LOCK_NB=4,LOCK_UN=8)
        file=Mock()
        file.fileno.return_value=7
        with patch.object(module.os,'name','posix'),patch.dict(sys.modules,{'fcntl':fcntl}):
            self.assertIsNone(module.bloquear_archivo(file,True))
            self.assertIsNone(module.bloquear_archivo(file,False))
            module.liberar_archivo(file,None)
        self.assertEqual(fcntl.flock.call_args_list[-1].args,(7,8))

    def test_errores_nativos_lock_y_unlock_se_propagan(self):
        api=Mock()
        api.LockFileEx.return_value=False
        file=Mock()
        with patch.object(ctypes,'WinDLL',return_value=api),patch('msvcrt.get_osfhandle',return_value=7),patch.object(ctypes,'WinError',return_value=OSError('lock ficticio')),self.assertRaises(OSError):
            module.bloquear_archivo(file,True)
        class Overlapped(ctypes.Structure):_fields_=[('valor',ctypes.c_int)]
        api.UnlockFileEx.return_value=False
        with patch.object(ctypes,'WinError',return_value=OSError('unlock ficticio')),self.assertRaises(OSError):
            module.liberar_archivo(file,(api,7,Overlapped()))


class PruebasCuposHTTP(unittest.TestCase):
    """Ejercita el control de cupos aislado del socket y del sistema de hilos."""

    def setUp(self):
        self.s=TLSHTTPServer.__new__(TLSHTTPServer)
        self.s.connections=threading.BoundedSemaphore(1)
        self.s.shutdown_request=Mock()

    def test_cupo_agotado_cierra_sin_crear_trabajador(self):
        self.s.connections.acquire()
        with patch.object(ThreadingHTTPServer,'process_request') as parent:self.s.process_request(Mock(),('127.0.0.1',1))
        parent.assert_not_called()
        self.s.shutdown_request.assert_called_once()
        self.s.connections.release()

    def test_fallo_al_crear_hilo_restituye_cupo(self):
        with patch.object(ThreadingHTTPServer,'process_request',side_effect=RuntimeError('hilo fallido')),self.assertRaises(RuntimeError):
            self.s.process_request(Mock(),('127.0.0.1',1))
        self.assertTrue(self.s.connections.acquire(blocking=False))
        self.s.connections.release()

    def test_error_inesperado_conserva_registro_del_servidor(self):
        with patch.object(ThreadingHTTPServer,'handle_error') as parent:
            try:raise RuntimeError('error ficticio')
            except RuntimeError:self.s.handle_error(Mock(),('127.0.0.1',1))
        parent.assert_called_once()
