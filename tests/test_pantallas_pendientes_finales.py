"""Ramas de pantallas con menor cobertura y callbacks de filtros diferidos."""
import tkinter as tk
import unittest
from hemeroteca.ui.selector_hora import SelectorHora
from tests import test_eliminados_auditoria_ramas as deleted
from tests import test_pantalla_login as login


class PruebasPantallasPendientes(unittest.TestCase):
    """Usa widgets reales con consultas aisladas y datos ficticios."""

    def setUp(self):
        self.h=deleted.VentanaRevision()
        self.addCleanup(self.h.close_for_test)
        self.h.services.periodicos.buscar_eliminados.return_value=self.h.page([])

    def test_formateo_denegado_o_solo_lectura_no_abre_dialogo(self):
        before=self.h.winfo_children()
        self.h._require_access.return_value=False
        self.h._formatear_aplicacion()
        self.h._require_access.return_value=True
        self.h.services.read_only=True
        self.h._formatear_aplicacion()
        self.assertEqual(self.h.winfo_children(),before)
        self.h.services.users.formatear_aplicacion.assert_not_called()

    def test_selector_hora_restablece_minutos_y_preserva_estado_invalido(self):
        control=SelectorHora(self.h.content);control.pack()
        control.set('12:34:56')
        control.hora.set('Hora');control._elegir_hora('Hora')
        self.assertEqual(control.minuto.get(),'Min.');self.assertEqual(control.get(),'')
        control.hora.set('12');control.minuto.set('30');control._elegir_hora('12')
        self.assertEqual(control.get(),'12:30')
        control._elegir_minuto('Min.')
        self.assertEqual(control.hora.get(),'12')
        for value in ['24','12:60','1:2:60','12:30:00:01','１２','12:','-1']:
            with self.subTest(value=value),self.assertRaises(ValueError):control.set(value)
            self.assertEqual(control.get(),'12:30')

    def test_filtro_eliminados_denegado_conserva_tabla(self):
        self.h._deleted_page()
        calls=self.h.services.periodicos.buscar_eliminados.call_count
        self.h._require_access.return_value=False
        self.h.button('Filtrar').invoke()
        self.assertEqual(self.h.services.periodicos.buscar_eliminados.call_count,calls)

    def test_busqueda_diferida_reprograma_y_no_consulta_al_destruir(self):
        self.h._deleted_page();self.h.update()
        entry=self.h.entries['Buscar ejemplar eliminado']
        entry._entry.focus_force();self.h.update()
        entry._entry.event_generate('<KeyRelease>',keysym='a');self.h.update()
        pending=set(self.h.tk.splitlist(self.h.tk.call('after','info')))
        entry._entry.event_generate('<KeyRelease>',keysym='b');self.h.update()
        current=set(self.h.tk.splitlist(self.h.tk.call('after','info')))
        new=current-pending
        self.assertEqual(len(new),1)
        task=new.pop();script=self.h.tk.call('after','info',task)[0]
        before=self.h.services.periodicos.buscar_eliminados.call_count
        self.h.tk.eval(script);self.h.after_cancel(task)
        self.assertEqual(self.h.services.periodicos.buscar_eliminados.call_count,before+1)
        entry._entry.event_generate('<KeyRelease>',keysym='c');self.h.update()
        tasks=set(self.h.tk.splitlist(self.h.tk.call('after','info')))-current
        task=next(t for t in tasks if 'lambda' in str(self.h.tk.call('after','info',t)))
        script=self.h.tk.call('after','info',task)[0]
        entry.destroy();before=self.h.services.periodicos.buscar_eliminados.call_count
        self.h.tk.eval(script);self.h.after_cancel(task)
        self.assertEqual(self.h.services.periodicos.buscar_eliminados.call_count,before)


class PruebasDisposicionLogin(unittest.TestCase):
    """Redimensiona el formulario real sin crear cuentas ni iniciar sesión."""

    def test_login_alterna_disposicion_y_no_repite_cambios(self):
        h=login.VentanaLogin();self.addCleanup(h.close_for_test)
        h._login_layout()
        h.geometry('1400x800');h.update()
        # El formulario vive dentro del scrollable, junto al panel promocional.
        panel=next(w for w in h.winfo_children() if isinstance(w,tk.Misc) and w.winfo_manager()=='grid')
        promo=h.login_promo_canvas.master
        self.assertEqual(promo.winfo_manager(),'grid')
        self.assertEqual(panel.grid_columnconfigure(1)['weight'],3)
        h.geometry('800x650');h.update()
        self.assertEqual(promo.winfo_manager(),'')
        self.assertEqual(panel.grid_columnconfigure(1)['weight'],0)
        panel.event_generate('<Configure>');h.update()
        h.geometry('1400x800');h.update()
        self.assertEqual(promo.winfo_manager(),'grid')
        self.assertEqual(panel.grid_columnconfigure(1)['weight'],3)
        self.assertEqual(h.callback_errors,[])
