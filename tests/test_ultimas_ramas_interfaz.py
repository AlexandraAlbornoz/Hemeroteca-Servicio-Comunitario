"""Ramas finales de cierre, foco y contextos opcionales con Tk real."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
import customtkinter as ctk
from hemeroteca.ui import controles
from hemeroteca.ui.main_view import HemerotecaApp
from hemeroteca.config.settings import ROLES,VIEWS
from tests.soporte_catalogo import VentanaCatalogo
from tests import test_pantalla_login as login
from tests import test_ramas_sesion_navegacion as session


class PruebasUltimasRamasInterfaz(unittest.TestCase):
    def setUp(self):
        self.h=VentanaCatalogo();self.addCleanup(self.h.close_for_test)

    def test_clic_en_menu_o_selector_conserva_apertura_y_fuera_cierra(self):
        combo=controles.SelectorCompacto(self.h.content,values=['Uno','Dos']);combo.pack();self.h.update()
        combo._open_dropdown_menu();self.h.update();window=combo._ventana_menu
        for control in [window,combo._lista_menu,combo._entry]:
            control.event_generate('<ButtonPress-1>',x=2,y=2);self.h.update()
            self.assertIs(combo._ventana_menu,window)
        self.h.content.event_generate('<ButtonPress-1>');self.h.update()
        self.assertIsNone(combo._ventana_menu)

    def test_revision_y_programacion_de_foco_ya_entregadas_tras_cerrar(self):
        combo=controles.SelectorCompacto(self.h.content,values=['Uno']);combo.pack();self.h.update()
        callbacks={};real_bind=tk.Toplevel.bind;real_after=combo.after
        def bind(window,sequence=None,func=None,*a,**kw):
            if sequence=='<FocusOut>':callbacks['programar']=func
            return real_bind(window,sequence,func,*a,**kw)
        def after(ms,func=None,*a):
            if getattr(func,'__name__','')=='comprobar_foco':callbacks['comprobar']=func
            return real_after(ms,func,*a)
        with patch.object(tk.Toplevel,'bind',bind),patch.object(combo,'after',side_effect=after):
            combo._open_dropdown_menu();self.h.update();window=combo._ventana_menu
            window.event_generate('<FocusOut>');self.h.update()
        self.assertIn('comprobar',callbacks);combo._cerrar_menu(devolver_foco=False)
        before=set(self.h.tk.splitlist(self.h.tk.call('after','info')))
        callbacks['comprobar']();callbacks['programar'](SimpleNamespace(widget=window))
        self.assertEqual(set(self.h.tk.splitlist(self.h.tk.call('after','info'))),before)
        self.assertIsNone(combo._revision_foco)

    def test_callbacks_de_foco_no_configuran_boton_destruido(self):
        callbacks=[];real_bind=ctk.CTkButton.bind
        def bind(button,sequence=None,command=None,*a,**kw):
            if sequence in ('<FocusIn>','<FocusOut>'):callbacks.append(command)
            return real_bind(button,sequence,command,*a,**kw)
        with patch.object(ctk.CTkButton,'bind',bind):button=self.h._button(self.h.content,'Prueba',lambda:None)
        self.assertEqual(len(callbacks),2);button.destroy()
        for callback in callbacks:callback(SimpleNamespace(widget=button))
        self.assertFalse(button.winfo_exists())

    def test_acercar_resultados_con_canvas_aun_vacio_no_desplaza(self):
        canvas=tk.Canvas(self.h);canvas.pack();area=ctk.CTkFrame(self.h);area.pack()
        with patch.object(self.h,'content',SimpleNamespace(_parent_canvas=canvas)):
            self.h._mostrar_resultados(area)
        self.assertIsNone(canvas.bbox('all'));self.assertEqual(canvas.yview(),(0.0,1.0))

    def test_codigo_confirmado_sin_callback_opcional_cierra(self):
        self.h._show_recovery_code('HMR-FICTICIO','V-12345678')
        dialog=self.h.dialogs[-1]
        self.h.text_checkbox('He guardado').toggle();self.h.button('Ya lo guardé · Continuar').invoke()
        self.assertFalse(dialog.winfo_exists());self.assertFalse(self.h._showing_recovery_code)
        self.h.show_shell.assert_not_called()

    def test_preguntas_opcionales_guardan_sin_reconstruir_shell(self):
        self.h._security_questions_form(required=False)
        dialog=self.h.dialogs[-1];self.h.write('Contraseña actual *','Prueba#2026')
        for i in range(1,4):self.h.write(f'Respuesta {i} *','Respuesta ficticia')
        self.h.button('Guardar preguntas').invoke()
        self.assertFalse(dialog.winfo_exists());self.h.show_shell.assert_not_called()
        self.h.services.recovery.configure_questions.assert_called_once()
        self.h._notice.assert_called_once()

    def test_permiso_incluido_en_perfil_no_ofrece_revocarlo(self):
        record=dict(self.h.user,id=2,role=ROLES[2],name='Persona Ficticia')
        self.h.services.users.get_user.return_value=record
        self.h.services.users.grants.return_value=[{'permission':VIEWS[0]}]
        self.h._user_detail(record)
        self.assertFalse(any(b.cget('text')=='Revocar' for b in self.h.widgets(ctk.CTkButton)))

    def test_cancelar_validacion_dos_veces_no_deja_temporizador(self):
        callbacks=[];real_bind=ctk.CTkToplevel.bind
        def bind(window,sequence=None,command=None,*a,**kw):
            if sequence=='<Destroy>' and getattr(command,'__name__','')=='cancelar_validacion':callbacks.append(command)
            return real_bind(window,sequence,command,*a,**kw)
        with patch.object(ctk.CTkToplevel,'bind',bind):self.h._record_form()
        dialog=self.h.dialogs[-1];self.assertEqual(len(callbacks),1)
        callbacks[0](SimpleNamespace(widget=dialog));callbacks[0](SimpleNamespace(widget=dialog))
        self.assertIsNone(dialog._validacion_pendiente);dialog.destroy()


class PruebasContextoAccesoOpcional(unittest.TestCase):
    def setUp(self):
        self.h=login.VentanaLogin();self.addCleanup(self.h.close_for_test)
    def test_opciones_de_configuracion_no_muestran_aviso_de_cuenta_existente(self):
        panel=ctk.CTkFrame(self.h.content);panel.pack()
        self.h._login_admin_options(panel,setup=True)
        self.assertFalse(self.h.has_text('se registra una sola vez'))
    def test_gestor_retirado_durante_construccion_no_ofrece_sus_acciones(self):
        panel=ctk.CTkFrame(self.h.content);panel.pack();real=self.h._button
        def button(*a,**kw):
            result=real(*a,**kw);self.h.services.network=None;return result
        with patch.object(self.h,'_button',side_effect=button):self.h._login_admin_options(panel)
        texts=[b.cget('text') for b in self.h.widgets(ctk.CTkButton)]
        self.assertNotIn('Preparar PC de consulta',texts)
        self.assertNotIn('Recuperar un traslado interrumpido',texts)


class PruebasPrimeraVistaSinFiltros(unittest.TestCase):
    def test_construir_primera_vista_no_exige_estado_previo(self):
        h=session.VentanaEstado();self.addCleanup(h.clean)
        h.content=h._scrollable(h);h.content.pack()
        h.breadcrumb=ctk.CTkLabel(h,text='');h.breadcrumb.pack();h.sidebar_buttons={}
        h.services.consulta=Mock(return_value=('descriptor',))
        self.assertFalse(hasattr(h,'_guardar_estado_vista'))
        with patch.object(h,'_cargar_seccion') as load:HemerotecaApp._construir_vista(h,VIEWS[0])
        self.assertEqual(h.current_view,VIEWS[0]);self.assertTrue(callable(h._guardar_estado_vista))
        self.assertEqual(h.services.consulta.call_count,2);load.assert_called_once()
