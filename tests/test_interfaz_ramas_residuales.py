"""Auditoría, menús, recuperación y disposición de acceso en ramas residuales."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import customtkinter as ctk
from hemeroteca.config.settings import SECURITY_QUESTIONS
from hemeroteca.ui import controles
from tests import test_eliminados_auditoria_ramas as audit
from tests import test_pantalla_login as login


class PruebasInterfazRamasResiduales(unittest.TestCase):
    """Opera controles auténticos con servicios aislados y datos sintéticos."""
    def setUp(self):
        self.h=audit.VentanaRevision();self.addCleanup(self.h.close_for_test)
        self.h.services.audit.buscar_eventos.return_value=self.h.page([])
        self.h.services.audit.acciones_disponibles.return_value=[]
        self.h.services.audit.resultados_disponibles.return_value=[]

    def test_auditoria_denegada_al_filtrar_no_consulta(self):
        self.h._audit_page();before=self.h.services.audit.buscar_eventos.call_count
        self.h._require_access.return_value=False;self.h.button('Filtrar historial').invoke()
        self.assertEqual(self.h.services.audit.buscar_eventos.call_count,before)

    def test_textbox_recibe_rueda_sin_mover_formulario(self):
        text=ctk.CTkTextbox(self.h.content,height=70);text.pack()
        text.insert('1.0','\n'.join(str(n) for n in range(100)))
        self.h.update()
        with patch.object(text._textbox,'yview',return_value=(.1,.9)),patch.object(text._textbox,'yview_scroll') as scroll:
            self.assertEqual(controles.desplazar_con_continuidad(SimpleNamespace(widget=text,delta=-120,state=0)),'break')
        scroll.assert_called_once_with(3,'units')

    def test_cerrar_menu_cancela_revision_de_foco_pendiente(self):
        c=controles.SelectorCompacto(self.h.content,values=['Uno'],state='readonly');c.pack();self.h.update()
        c._open_dropdown_menu();self.h.update()
        c._ventana_menu.event_generate('<FocusOut>');self.h.update()
        task=c._revision_foco;self.assertIsNotNone(task)
        c._cerrar_menu(devolver_foco=False)
        self.assertIsNone(c._revision_foco);self.assertIsNone(c._ventana_menu)
        self.assertNotIn(task,self.h.tk.splitlist(self.h.tk.call('after','info')))

    def test_recuperacion_no_se_abre_si_hay_sesion(self):
        self.h.show_master_recovery()
        self.assertEqual(self.h.dialogs,[])

    def test_recargar_preguntas_retira_entradas_anteriores(self):
        self.h.user=None;self.h.show_master_recovery();self.h.write('Documento *','V-12345678')
        self.h.services.auth.obtener_preguntas_recuperacion.return_value=SECURITY_QUESTIONS[:3]
        self.h.button('Mostrar mis preguntas').invoke()
        old=self.h.entries['1. '+SECURITY_QUESTIONS[0]]
        old.insert(0,'Respuesta ficticia')
        self.h.button('Mostrar mis preguntas').invoke()
        self.assertFalse(old.winfo_exists())
        self.assertEqual(self.h.entries['1. '+SECURITY_QUESTIONS[0]].get(),'')
        self.assertEqual(self.h.callback_errors,[])


class PruebasAccesoDisposicionResidual(unittest.TestCase):
    """El Configure nativo debe conservar el modo al repetir el mismo tamaño."""
    def test_configure_repetido_no_cambia_disposicion(self):
        h=login.VentanaLogin();self.addCleanup(h.close_for_test)
        h._login_layout();h.geometry('1400x800');h.update()
        layout=h.login_promo_canvas.master.master
        before=layout.grid_columnconfigure(1)['weight']
        layout._canvas.event_generate('<Configure>');h.update()
        layout._canvas.event_generate('<Configure>');h.update()
        self.assertEqual(layout.grid_columnconfigure(1)['weight'],before)
        self.assertEqual(h.callback_errors,[])
