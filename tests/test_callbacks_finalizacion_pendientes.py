"""Activaciones tardías, pérdida de permiso y finalización del trabajo gráfico."""
from concurrent.futures import Future
import gc
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import customtkinter as ctk
from hemeroteca.ui.tareas import ServiciosDeInterfaz
from hemeroteca.ui import controles
from tests.soporte_catalogo import VentanaCatalogo
from tests import test_pantalla_login as login


class PruebasCallbacksFinalizacion(unittest.TestCase):
    def setUp(self):
        self.h=VentanaCatalogo();self.addCleanup(self.h.close_for_test)

    def test_exportacion_encolada_sin_seleccion_no_abre_destino(self):
        self.h.services.backups.status.return_value={'enabled':False}
        self.h.services.backups.list_backups.return_value=[]
        self.h._backups_page()
        button=self.h.button('Guardar en USB u otra carpeta')
        with patch('hemeroteca.ui.backups_view.filedialog.asksaveasfilename') as destination:
            # Un comando ya encolado puede llegar después de perder la selección.
            button.cget('command')()
        destination.assert_not_called();self.h.services.backups.export.assert_not_called()

    def test_solicitudes_revocadas_no_vuelven_a_consultar(self):
        self.h._requests_page();before=self.h.services.requests.buscar_solicitudes.call_count
        self.h._require_access.return_value=False;self.h.button('Filtrar solicitudes').invoke()
        self.assertEqual(self.h.services.requests.buscar_solicitudes.call_count,before)

    def test_menu_sin_seleccion_conserva_lista_al_confirmar(self):
        combo=controles.SelectorCompacto(self.h.content,values=['Uno','Dos'],state='readonly');combo.pack();self.h.update()
        combo._open_dropdown_menu();self.h.update();menu=combo._ventana_menu;listing=combo._lista_menu
        listing.event_generate('<ButtonPress-1>',x=3,y=3);self.h.update()
        self.assertIs(combo._ventana_menu,menu)
        listing.selection_clear(0,'end');listing.focus_force();self.h.update()
        listing.event_generate('<Return>');self.h.update()
        self.assertIs(combo._ventana_menu,menu);self.assertEqual(listing.curselection(),())
        combo._cerrar_menu()

    def test_validador_ya_entregado_no_reprograma_dialogo_destruido(self):
        callbacks=[];real_after=ctk.CTkToplevel.after
        def schedule(window,ms,func=None,*args):
            if func is not None and func.__name__=='validar_estado':callbacks.append(func)
            return real_after(window,ms,func,*args)
        with patch.object(ctk.CTkToplevel,'after',schedule):self.h._record_form()
        dialog=self.h.dialogs[-1];self.assertTrue(callbacks)
        self.h.write('Estante','1');callbacks[-1]()
        self.assertEqual(self.h.button('Guardar ejemplar').cget('state'),'disabled')
        dialog.destroy();before=set(self.h.tk.splitlist(self.h.tk.call('after','info')))
        callbacks[-1]()
        self.assertEqual(set(self.h.tk.splitlist(self.h.tk.call('after','info'))),before)
        self.h.services.periodicos.save_record.assert_not_called()


class PruebasTrabajoFinalizado(unittest.TestCase):
    def setUp(self):
        self.h=VentanaCatalogo();self.addCleanup(self.h.close_for_test)
        self.services=ServiciosDeInterfaz(self.h,SimpleNamespace(close=Mock()))
        self.addCleanup(self.services.close)

    def test_aviso_ya_entregado_no_abre_progreso_si_futuro_termino(self):
        result=Future();result.set_result('resultado')
        callbacks={};real_after=self.h.after
        def schedule(ms,callback,*args):
            callbacks[callback.__name__]=callback
            return real_after(60000,callback,*args)
        def wait(variable):
            callbacks['mostrar']();callbacks['recibir']()
        with patch.object(self.services.ejecutor,'submit',return_value=result),patch.object(self.h,'after',side_effect=schedule),patch.object(self.h,'wait_variable',side_effect=wait),patch('hemeroteca.ui.tareas.tk.Toplevel') as dialog:
            self.assertEqual(self.services.ejecutar('audit','list',(),{}),'resultado')
        dialog.assert_not_called();self.assertEqual(self.services._trabajos,0)
        self.assertFalse(self.h._servicios_ocupados)

    def test_gc_previamente_deshabilitado_no_se_habilita_al_terminar(self):
        previous=gc.isenabled()
        try:
            gc.disable();self.services._iniciar_trabajo();self.services._terminar_trabajo()
            self.assertFalse(gc.isenabled());self.assertEqual(self.services._trabajos,0)
        finally:
            if previous:gc.enable()


class PruebasContrasenaVisibleEnAcceso(unittest.TestCase):
    def test_mostrar_ocultar_sin_confirmacion_de_registro(self):
        h=login.VentanaLogin();self.addCleanup(h.close_for_test)
        h.show_login();h.login_password.insert(0,'Dato ficticio')
        check=h.text_checkbox('Mostrar contraseña')
        check.toggle();self.assertEqual(h.login_password.cget('show'),'')
        check.toggle();self.assertEqual(h.login_password.cget('show'),'•')
        self.assertEqual(h.login_password.get(),'Dato ficticio')
