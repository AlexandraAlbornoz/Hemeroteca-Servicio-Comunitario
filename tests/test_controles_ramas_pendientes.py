"""Cierre de selectores y rueda en rutas de foco y destrucción pendientes."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
from hemeroteca.ui import controles
from tests.soporte_catalogo import VentanaCatalogo


class PruebasControlesPendientes(unittest.TestCase):
    """Los menús y entradas se operan sobre un intérprete Tk aislado."""

    def setUp(self):
        self.h=VentanaCatalogo()
        self.addCleanup(self.h.close_for_test)

    def combo(self):
        c=controles.SelectorCompacto(self.h.content,values=['Uno','Dos'],state='readonly')
        c.pack();self.h.update()
        return c

    def test_selector_reapertura_rueda_y_confirmacion_sin_comando(self):
        c=self.combo()
        c._abrir_con_raton(None);win=c._ventana_menu
        c._clicked();self.assertIs(c._ventana_menu,win)
        c._lista_menu.selection_clear(0,'end')
        c._lista_menu.event_generate('<Return>');self.h.update()
        self.assertIs(c._ventana_menu,win)
        c._lista_menu.selection_set(1)
        c._lista_menu.event_generate('<Return>');self.h.update()
        self.assertEqual(c.get(),'Dos');self.assertIsNone(c._ventana_menu)
        self.assertEqual(c._rueda_lista(SimpleNamespace(delta=-120)), 'break')
        c.configure(state='disabled');c._abrir_con_teclado(None)
        self.assertIsNone(c._ventana_menu)

    def test_selector_rueda_cierra_y_lista_acumula_fracciones(self):
        c=self.combo();c._abrir_con_teclado(None)
        c._rueda_lista(SimpleNamespace(delta=-1))
        self.assertIsNotNone(c._ventana_menu)
        c._rueda_selector(None)
        self.assertIsNone(c._ventana_menu)
        controles.desplazar_con_continuidad(SimpleNamespace(widget=c,delta=-120,state=0))

    def test_menu_clic_propio_conserva_y_clic_exterior_cierra(self):
        c=self.combo();c._open_dropdown_menu();self.h.update()
        c._entry.event_generate('<ButtonPress-1>');self.h.update()
        self.assertIsNotNone(c._ventana_menu)
        self.h.content.event_generate('<ButtonPress-1>');self.h.update()
        self.assertIsNone(c._ventana_menu)

    def test_revision_foco_reprogramada_cierra_al_salir_y_destruir(self):
        c=self.combo();c._open_dropdown_menu();self.h.update()
        win=c._ventana_menu
        win.event_generate('<FocusOut>');self.h.update()
        first=c._revision_foco
        win.event_generate('<FocusOut>');self.h.update()
        self.assertNotEqual(first,c._revision_foco)
        script=c.tk.call('after','info',c._revision_foco)[0]
        with patch.object(win,'focus_get',return_value=None):c.tk.eval(script)
        self.assertIsNone(c._ventana_menu)
        c._open_dropdown_menu();self.h.update()
        c.destroy();self.h.update()
        self.assertFalse(win.winfo_exists())

    def test_revision_foco_interior_conserva_menu(self):
        c=self.combo();c._open_dropdown_menu();self.h.update()
        win=c._ventana_menu
        win.event_generate('<FocusOut>');self.h.update()
        script=c.tk.call('after','info',c._revision_foco)[0]
        with patch.object(win,'focus_get',return_value=c._lista_menu):c.tk.eval(script)
        self.assertIs(c._ventana_menu,win)
        c._cerrar_menu(devolver_foco=False)

    def test_entradas_deshabilitadas_y_control_a_no_cambian_seleccion(self):
        c=controles.EntradaEditable(self.h.content);c.pack();c.insert(0,'texto')
        self.h.update();c._seleccionar_todo(None)
        self.assertTrue(c._entry.selection_present())
        c._entry.selection_clear();c.configure(state='disabled')
        c._seleccionar_todo(None)
        self.assertFalse(c._entry.selection_present())
        with patch.object(c._entry,'focus_force') as focus:
            c._enfocar_texto(None);c._enfocar_desde_fondo(SimpleNamespace(x_root=0))
            focus.assert_not_called()

    def test_rueda_destino_sin_desplazamiento_y_en_limite(self):
        target=Mock(spec=['yview','yview_scroll'])
        target.yview.return_value=(0,1)
        widget=SimpleNamespace(_destino_rueda=target,master=None)
        event=SimpleNamespace(widget=widget,delta=-120,state=0)
        self.assertEqual(controles.desplazar_con_continuidad(event),'break')
        target.yview_scroll.assert_not_called()
        target.yview.return_value=(.1,.9)
        with patch.object(controles.sys,'platform','darwin'):
            self.assertEqual(controles.desplazar_con_continuidad(event),'break')
        target.yview_scroll.assert_called_once_with(360,'units')

    def test_marco_rueda_valida_y_ajena(self):
        page=controles.MarcoDesplazable(self.h.content);page.pack()
        with patch('customtkinter.CTkScrollableFrame._mouse_wheel_all') as wheel:
            self.assertEqual(page._mouse_wheel_all(SimpleNamespace(widget=page._parent_canvas)),'break')
            wheel.assert_called_once()
            self.assertIsNone(page._mouse_wheel_all(SimpleNamespace(widget=self.h)))

    def test_destruccion_limpia_temporizador_y_ventana_huerfanos(self):
        c=self.combo()
        orphan=tk.Toplevel(c)
        c._ventana_menu=orphan
        c._revision_foco=c.after(10000,lambda:None)
        c._destruir_selector(None)
        self.assertIsNone(c._revision_foco)
        self.assertIsNone(c._ventana_menu)
        self.assertFalse(orphan.winfo_exists())

    def test_menu_encima_del_control_y_cierra_antes_de_rueda(self):
        c=self.combo()
        with patch.object(c,'winfo_screenheight',return_value=0):c._open_dropdown_menu()
        self.h.update()
        self.assertLessEqual(c._ventana_menu.winfo_y(),c.winfo_rooty())
        self.assertEqual(controles.desplazar_con_continuidad(SimpleNamespace(widget=c,delta=-120,state=0)),'break')
        self.assertIsNone(c._ventana_menu)
