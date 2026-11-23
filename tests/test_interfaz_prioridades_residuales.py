"""Ramas de límites de ventana, filtros y permisos revocados en interfaz real."""
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
import customtkinter as ctk
from hemeroteca.ui import controles
from hemeroteca.config.settings import TITLES
from tests.soporte_catalogo import VentanaCatalogo
from tests import test_pantalla_login as login


class PruebasInterfazPrioridadesResiduales(unittest.TestCase):
    def setUp(self):
        self.h=VentanaCatalogo();self.addCleanup(self.h.close_for_test)

    def test_rueda_modal_no_se_propaga_a_ventana_principal(self):
        modal=tk.Toplevel(self.h);modal.geometry('300x200');text=tk.Text(modal,height=3);text.pack()
        text.insert('1.0','\n'.join(str(i) for i in range(100)));self.h.update()
        before=text.yview()[0]
        self.assertEqual(controles.desplazar_con_continuidad(SimpleNamespace(widget=text,delta=-120,state=0)),'break')
        self.assertGreater(text.yview()[0],before)

    def test_filtros_compartidos_incluyen_periodico_y_tipo(self):
        frame=ctk.CTkFrame(self.h.content);frame.pack()
        fields=self.h._title_filter_fields(frame,include_type=True)
        self.assertEqual(set(fields),{'Periódico','Tipo'})
        self.assertEqual(fields['Tipo'].get(),'Todos');self.assertEqual(fields['Periódico'].get(),'Todos los periódicos')

    def test_anular_ausencia_revalida_permiso_tras_seleccion(self):
        self.h._catalogo_seccion='Fechas sin publicación'
        row=dict(id=11,title=TITLES[0],kind='Nacional',year=2020,month=1,day=1,reason='Motivo ficticio',created_at='2020-01-01',note='')
        self.h.services.periodicos.buscar_fechas_ausentes.return_value=self.h.page([row])
        self.h._catalog_page();self.h.update()
        tree=self.h.widgets(ttk.Treeview)[0];self.h.select(tree,11)
        self.h._require_access.return_value=False;self.h.button('Anular anotación incorrecta').invoke()
        self.h.services.periodicos.corregir_fecha_ausente.assert_not_called()

    def test_barras_fijas_independientes_no_ocultan_otra_tabla(self):
        holder=ctk.CTkFrame(self.h);holder.pack()
        target=ctk.CTkFrame(holder);target.grid(row=0,column=0);self.h.navegacion_resultados=target
        areas=[ctk.CTkFrame(self.h.content) for _ in range(2)]
        for area in areas:area.pack()
        first,_,_=self.h._barra_resultados(areas[0],'consulta')
        second,_,_=self.h._barra_resultados(areas[1],'backups')
        first.destroy();areas[0].destroy();self.h.update()
        self.assertTrue(second.winfo_exists());self.assertEqual(target.winfo_manager(),'grid')
        areas[1].destroy();self.h.update();self.assertEqual(target.winfo_manager(),'')


class PruebasAltaMaestraSinRed(unittest.TestCase):
    def test_primera_configuracion_sin_gestor_no_ofrece_preparar_pc(self):
        h=login.VentanaLogin();self.addCleanup(h.close_for_test)
        h.services.network=None;h.services.auth.needs_setup.return_value=True
        h.show_login();h.update()
        texts=[b.cget('text') for b in h.widgets(ctk.CTkButton)]
        self.assertNotIn('Preparar PC de consulta',texts)
        self.assertIn('Continuar: preguntas de seguridad',texts)
