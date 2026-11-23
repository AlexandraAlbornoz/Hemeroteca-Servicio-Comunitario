"""El receptor de red se libera si Tk rechaza programar un sondeo."""
from types import SimpleNamespace
from tkinter import TclError
import unittest
from unittest.mock import Mock,patch
import customtkinter as ctk
from tests.soporte_pantallas import VentanaGeneral


class PruebasFalloSondeoRed(unittest.TestCase):
    def setUp(self):
        self.h=VentanaGeneral();self.addCleanup(self.h.close_for_test)
        self.net=self.h.services.network
        self.net.prepare_consultation_pc.return_value=SimpleNamespace(name='PC ficticia',code='ABCD',state='waiting',expired=Mock(return_value=False),last_error='')
        self.warning=patch('hemeroteca.ui.network_view.messagebox.showwarning').start();self.addCleanup(patch.stopall)

    def test_fallo_programacion_inicial_cierra_y_detiene_receptor(self):
        for failure in [RuntimeError('Tk rechazó la programación'),TclError('intérprete sin temporizador')]:
            with self.subTest(error=type(failure).__name__):
                self.net.stop_preparation.reset_mock();self.warning.reset_mock();real=ctk.CTkToplevel.after
                def after(window,ms,func=None,*a):
                    if getattr(func,'__name__','')=='sondear':raise failure
                    return real(window,ms,func,*a)
                with patch.object(ctk.CTkToplevel,'after',after):self.h._connect_server_form()
                self.net.stop_preparation.assert_called_once();self.warning.assert_called_once()
                self.assertFalse(self.h.dialogs[-1].winfo_exists())
                self.assertEqual(self.h.callback_errors,[])

    def test_fallo_reprogramacion_libera_receptor_sin_callback_roto(self):
        for failure in [RuntimeError('Tk rechazó otro sondeo'),TclError('fallo Tcl de prueba')]:
            with self.subTest(error=type(failure).__name__):
                self.net.stop_preparation.reset_mock();self.warning.reset_mock()
                self.h._connect_server_form();dialog=self.h.dialogs[-1]
                job=next(t for t in self.h.tk.splitlist(self.h.tk.call('after','info')) if str(self.h.tk.call('after','info',t)[0]).endswith('sondear'))
                command=self.h.tk.call('after','info',job)[0]
                dialog.tk.call('after','cancel',job);real=dialog.after
                def after(ms,func=None,*a):
                    if getattr(func,'__name__','')=='sondear':raise failure
                    return real(ms,func,*a)
                with patch.object(dialog,'after',side_effect=after):dialog.tk.call(command)
                self.net.stop_preparation.assert_called_once();self.warning.assert_called_once()
                self.assertFalse(dialog.winfo_exists());self.assertEqual(self.h.callback_errors,[])
