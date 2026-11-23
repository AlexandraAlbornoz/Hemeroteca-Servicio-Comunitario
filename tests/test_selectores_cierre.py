"""Regresiones de interacción exterior y geometría real de los desplegables."""
import unittest
import customtkinter as ctk
from hemeroteca.ui.controles import SelectorCompacto, EntradaEditable


class PruebasSelectores(unittest.TestCase):
    """Prueba controles Tk reales sin cuentas ni base de datos."""

    def setUp(self):
        """Monta un formulario aislado con lista larga y entrada exterior."""
        self.raiz = ctk.CTk()
        self.raiz.geometry('700x450+100+100')
        self.selector = SelectorCompacto(self.raiz, width=140, values=[f'Opción larga {n}' for n in range(40)])
        self.selector.pack(pady=20)
        self.entrada = EntradaEditable(self.raiz)
        self.entrada.pack()
        self.raiz.update()

    def tearDown(self):
        """Libera ventanas y callbacks después de cada caso."""
        for pendiente in self.raiz.tk.call('after', 'info'):
            self.raiz.after_cancel(pendiente)
        self.raiz.destroy()

    def abrir(self):
        """Abre y procesa la geometría del menú para medirla."""
        self.selector._open_dropdown_menu()
        self.raiz.update()

    def test_alineado_ancho_y_eje_x(self):
        """El menú tiene exactamente el ancho y borde izquierdo del campo."""
        self.abrir()
        menu = self.selector._ventana_menu
        self.assertEqual(menu.winfo_rootx(), self.selector.winfo_rootx())
        self.assertEqual(menu.winfo_width(), self.selector.winfo_width())
        self.assertEqual(menu.winfo_rooty(), self.selector.winfo_rooty() + self.selector.winfo_height())

    def test_click_exterior_cierra_y_permite_editar(self):
        """El primer clic exterior cierra el menú y activa el campo de destino."""
        self.abrir()
        self.entrada._entry.event_generate('<ButtonPress-1>', x=5, y=5)
        self.raiz.update()
        self.assertIsNone(self.selector._ventana_menu)
        self.assertEqual(self.raiz.focus_get(), self.entrada._entry)

    def test_rueda_exterior_cierra_antes_del_binding(self):
        """Incluso un destino que consume la rueda recibe el menú ya cerrado."""
        estados = []
        self.entrada._entry.bind('<MouseWheel>', lambda e: estados.append(self.selector._ventana_menu) or 'break')
        self.abrir()
        self.entrada._entry.event_generate('<MouseWheel>', delta=-120)
        self.raiz.update()
        self.assertEqual(estados, [None])

    def test_rueda_interior_no_cierra(self):
        """La rueda dentro de las opciones desplaza únicamente la lista."""
        self.abrir()
        lista = self.selector._lista_menu
        antes = lista.yview()
        lista.event_generate('<MouseWheel>', delta=-120)
        self.raiz.update()
        self.assertIsNotNone(self.selector._ventana_menu)
        self.assertGreater(lista.yview()[0], antes[0])

    def test_escape_y_limpieza_de_bindings(self):
        """Abrir y cerrar repetidamente restaura los bindings originales."""
        etiquetas = self.entrada._entry.bindtags()
        for _ in range(4):
            self.abrir()
            self.selector._lista_menu.event_generate('<Escape>')
            self.raiz.update()
            self.assertIsNone(self.selector._ventana_menu)
            self.assertEqual(etiquetas, self.entrada._entry.bindtags())

    def test_conserva_captura_modal(self):
        """El menú no roba ni libera la captura del formulario modal."""
        self.raiz.grab_set()
        self.abrir()
        self.assertEqual(self.raiz.grab_current(), self.raiz)
        self.selector._cerrar_menu()
        self.assertEqual(self.raiz.grab_current(), self.raiz)

    def test_seleccion_ejecuta_comando_una_vez(self):
        """Confirmar una opción conserva el valor y ejecuta su acción una sola vez."""
        seleccionados = []
        self.selector.configure(command=seleccionados.append)
        self.abrir()
        lista = self.selector._lista_menu
        lista.selection_clear(0, 'end')
        lista.selection_set(3)
        lista.event_generate('<Return>')
        self.raiz.update()
        self.assertEqual(seleccionados, ['Opción larga 3'])
        self.assertEqual(self.selector.get(), 'Opción larga 3')
        self.assertIsNone(self.selector._ventana_menu)

    def test_alineacion_con_escalado(self):
        """Las coordenadas físicas permanecen alineadas con escalado de interfaz."""
        try:
            ctk.set_widget_scaling(1.5)
            self.raiz.update()
            self.test_alineado_ancho_y_eje_x()
        finally:
            ctk.set_widget_scaling(1)

