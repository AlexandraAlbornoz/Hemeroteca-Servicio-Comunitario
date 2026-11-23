"""Destrucción externa de menús, reportes sin permisos y sondeos ya cerrados."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
import customtkinter as ctk
from hemeroteca.config.settings import REPORT_DATABASE_PERMISSION,REPORT_ISSUES_PERMISSION
from hemeroteca.ui import controles
from tests.soporte_pantallas import VentanaGeneral


class PruebasMenusPermisosRestantes(unittest.TestCase):
    """Conserva widgets y comandos Tcl auténticos, aislando los servicios."""
    def setUp(self):
        self.h=VentanaGeneral();self.addCleanup(self.h.close_for_test)

    def test_destruir_menu_externamente_limpia_estado_y_bindings(self):
        combo=controles.SelectorCompacto(self.h.content,values=['Uno','Dos'],state='readonly');combo.pack();self.h.update()
        combo._open_dropdown_menu();self.h.update()
        win=combo._ventana_menu
        tag=next(t for t in self.h.bindtags() if t.startswith('SelectorAbierto'))
        win.event_generate('<FocusOut>');self.h.update();task=combo._revision_foco
        win.destroy();self.h.update()
        self.assertIsNone(combo._ventana_menu);self.assertIsNone(combo._lista_menu)
        self.assertIsNone(combo._cerrar_menu);self.assertIsNone(combo._revision_foco)
        self.assertNotIn(tag,self.h.bindtags())
        self.assertNotIn(task,self.h.tk.splitlist(self.h.tk.call('after','info')))
        combo._open_dropdown_menu();self.h.update()
        self.assertIsNotNone(combo._ventana_menu);combo._cerrar_menu()
        self.assertEqual(self.h.callback_errors,[])

    def test_cierre_repetido_y_rueda_sin_menu_son_idempotentes(self):
        combo=controles.SelectorCompacto(self.h.content,values=['Uno'],state='readonly');combo.pack();self.h.update()
        combo._open_dropdown_menu();close=combo._cerrar_menu
        close();close();self.assertIsNone(combo._ventana_menu)
        combo._rueda_selector(None)
        self.assertEqual(combo._rueda_lista(SimpleNamespace(delta=0)),'break')
        self.assertEqual(self.h.callback_errors,[])

    def test_texto_tk_nativo_desplaza_solo_su_contenido(self):
        text=tk.Text(self.h.content,height=3);text.pack()
        text.insert('1.0','\n'.join(str(i) for i in range(100)));self.h.update()
        before=text.yview()[0]
        self.assertEqual(controles.desplazar_con_continuidad(SimpleNamespace(widget=text,delta=-120,state=0)),'break')
        self.assertGreater(text.yview()[0],before)

    def test_reportes_sin_permisos_no_muestran_exportacion(self):
        self.h._can=Mock(return_value=False);self.h._reports_page()
        texts=[b.cget('text') for b in self.h.widgets(ctk.CTkButton)]
        self.assertNotIn('Guardar PDF de ejemplares',texts);self.assertNotIn('Guardar PDF general',texts)
        self.h.services.reports.generate.assert_not_called()

    def test_reportes_solo_general_no_muestra_exportacion_ejemplares(self):
        self.h._can=Mock(side_effect=lambda permission:permission==REPORT_DATABASE_PERMISSION)
        self.h._reports_page()
        texts=[b.cget('text') for b in self.h.widgets(ctk.CTkButton)]
        self.assertNotIn('Guardar PDF de ejemplares',texts);self.assertIn('Guardar PDF general',texts)

    def test_sondeo_no_se_repite_despues_de_cancelar_preparacion(self):
        receiver=SimpleNamespace(name='PC ficticia',code='ABCD',state='waiting',expired=Mock(return_value=False),last_error='')
        self.h.services.network.prepare_consultation_pc.return_value=receiver
        self.h._connect_server_form();dialog=self.h.dialogs[-1]
        task=next(t for t in self.h.tk.splitlist(self.h.tk.call('after','info')) if str(self.h.tk.call('after','info',t)[0]).endswith('sondear'))
        script=self.h.tk.call('after','info',task)[0]
        # Conserva el comando encolado para reproducir su entrega tras marcar cerrado.
        with patch.object(dialog,'destroy'),patch.object(dialog,'after_cancel'):
            self.h.button('Cancelar preparación').invoke()
            dialog.tk.call(script)
        dialog.after_cancel(task);dialog.destroy()
        self.assertFalse(dialog.winfo_exists())
        self.h.services.network.stop_preparation.assert_called_once()
