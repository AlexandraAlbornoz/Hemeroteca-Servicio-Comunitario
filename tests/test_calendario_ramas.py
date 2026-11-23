"""Calendario, foco y límites de controles con widgets Tk reales."""
from datetime import date
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch
import customtkinter as ctk
from hemeroteca.config.settings import MONTHS
from hemeroteca.ui import controles
from tests.soporte_catalogo import VentanaCatalogo


class PruebasCalendarioRamas(unittest.TestCase):
    """Opera los callbacks de los botones, sin modificar el calendario del sistema."""

    def setUp(self):
        self.h=VentanaCatalogo()
        self.addCleanup(self.h.close_for_test)

    def button(self,parent,text):
        return next(w for w in self.h.widgets(ctk.CTkButton,parent) if w.cget('text')==text)

    def test_calendario_bisiesto_selecciona_y_restaura_modal(self):
        modal=ctk.CTkToplevel(self.h)
        modal.update()
        modal.grab_set()
        results=[]
        calendar=controles.abrir_calendario(modal,results.append,date(2024,2,1))
        self.assertIs(self.h.grab_current(),calendar)
        self.button(calendar,'29').invoke()
        self.assertEqual(results,[date(2024,2,29)])
        self.assertIs(self.h.grab_current(),modal)

    def test_calendario_acota_anios_y_redibuja_dias(self):
        for value,expected in [(date(1950,1,1),'1970'),(date(2200,1,1),'2100')]:
            calendar=controles.abrir_calendario(self.h,lambda d:None,value)
            selectors=self.h.widgets(controles.SelectorCompacto,calendar)
            year,month=selectors
            self.assertEqual(year.get(),expected)
            year.set('2100')
            month.set(MONTHS[1])
            month.cget('command')(MONTHS[1])
            self.button(calendar,'28')
            self.assertFalse(any(w.cget('text')=='29' for w in self.h.widgets(ctk.CTkButton,calendar)))
            self.button(calendar,'Cancelar').invoke()

    def test_calendario_cierra_aunque_modal_anterior_haya_desaparecido(self):
        modal=ctk.CTkToplevel(self.h)
        modal.update()
        modal.grab_set()
        calendar=controles.abrir_calendario(self.h,lambda d:None,date(2020,1,1))
        modal.destroy()
        protocol=calendar.tk.call('wm','protocol',calendar._w,'WM_DELETE_WINDOW')
        calendar.tk.call(protocol)
        self.assertFalse(calendar.winfo_exists())

    def test_entrada_fecha_abre_con_valor_y_entrega_dia_elegido(self):
        entry=controles.EntradaFecha(self.h.content)
        entry.pack()
        entry.set('15/01/2020')
        entry.abrir()
        calendar=self.h.widgets(ctk.CTkToplevel)[0]
        self.button(calendar,'16').invoke()
        self.assertEqual(entry.get(),'16/01/2020')
        entry.delete(0,'end')
        entry.abrir()
        calendar=self.h.widgets(ctk.CTkToplevel)[0]
        self.button(calendar,'Cancelar').invoke()
        self.assertEqual(entry.get(),'')

    def test_rueda_botones_linux_y_fracciones_macos(self):
        target=SimpleNamespace()
        self.assertEqual(controles.pasos_de_rueda(target,SimpleNamespace(num=4)),-1)
        self.assertEqual(controles.pasos_de_rueda(target,SimpleNamespace(num=5)),1)
        with patch.object(controles.sys,'platform','darwin'):
            self.assertEqual(controles.pasos_de_rueda(target,SimpleNamespace(delta=.4)),0)
            self.assertEqual(controles.pasos_de_rueda(target,SimpleNamespace(delta=.7)),-1)
        self.assertAlmostEqual(target._resto_rueda,-.1)

    def test_rueda_vacia_o_menu_nativo_no_interfiere(self):
        self.assertIsNone(controles.desplazar_con_continuidad(SimpleNamespace(widget=self.h,delta=0)))
        self.assertIsNone(controles.desplazar_con_continuidad(SimpleNamespace(widget=self.h,delta=120,state=0)))
        modal=tk.Toplevel(self.h)
        lista=tk.Listbox(modal)
        self.assertIsNone(controles.desplazar_con_continuidad(SimpleNamespace(widget=lista,num=4,state=0)))
        lista._rueda_menu=True
        self.assertIsNone(controles.desplazar_con_continuidad(SimpleNamespace(widget=lista,num=5,state=0)))

    def test_scroll_anidado_rechaza_texto_combo_y_control_ajeno(self):
        page=controles.MarcoDesplazable(self.h.content)
        page.pack()
        text=tk.Text(page)
        combo=ctk.CTkComboBox(page,values=['Uno'])
        self.assertFalse(page._check_if_valid_scroll(text))
        self.assertFalse(page._check_if_valid_scroll(combo))
        self.assertFalse(page._check_if_valid_scroll(self.h))
        child=ctk.CTkLabel(page,text='Hijo')
        self.assertTrue(page._check_if_valid_scroll(child))
        other=controles.MarcoDesplazable(self.h.content)
        self.assertFalse(page._check_if_valid_scroll(other._parent_canvas))
        controles.instalar_rueda_continua(self.h)

    def test_texto_deshabilitado_no_toma_foco_y_selector_vacio_se_cierra(self):
        text=controles.TextoEditable(self.h.content)
        text.pack()
        text.configure(state='disabled')
        with patch.object(text._textbox,'focus_force') as focus:
            text._activar_texto(None)
            focus.assert_not_called()
            text.configure(state='normal')
            text._activar_texto(None)
            focus.assert_called_once()
        combo=controles.SelectorCompacto(self.h.content,values=[],state='readonly')
        combo.pack()
        combo._open_dropdown_menu()
        self.assertEqual(combo._lista_menu.size(),0)
        combo._cerrar_menu()
        self.assertIsNone(combo._ventana_menu)

