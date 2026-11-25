"""Regresiones de clic sobre controles reales de Tkinter, sin cuentas del usuario."""
import tkinter as tk
import unittest
import customtkinter as ctk
from ui.controles import EntradaDocumento


class PruebasSelectorCedula(unittest.TestCase):
    """Verifica texto, flecha y selección dentro de diálogos con captura de foco."""

    @classmethod
    def setUpClass(cls):
        """Comparte un único intérprete Tk para no mezclar temporizadores de CTk."""
        cls.raiz = ctk.CTk()
        cls.raiz.title('Hemeroteca · Prueba aislada del selector')
        cls.raiz.geometry('420x220+40+40')

    @classmethod
    def tearDownClass(cls):
        """Cancela las tareas de la ventana de prueba antes de destruir Tk."""
        for tarea in cls.raiz.tk.splitlist(cls.raiz.tk.call('after', 'info')):
            cls.raiz.after_cancel(tarea)
        cls.raiz.destroy()

    def setUp(self):
        """Crea controles aislados sin abrir bases de datos ni servicios."""
        self.errores = []
        self.raiz.report_callback_exception = lambda tipo, error, traza: self.errores.append(str(error))
        self.documento = EntradaDocumento(self.raiz)
        self.documento.pack(padx=20, pady=20, fill='x')
        self.raiz.update()

    def tearDown(self):
        """Libera las ventanas y exige que no existan errores de callbacks."""
        self.documento.destroy()
        self.assertEqual(self.errores, [])

    def pulsar(self, control, x=8, y=8):
        """Emite presión y liberación sobre el widget real, con coordenadas coherentes."""
        opciones = dict(x=x, y=y, rootx=control.winfo_rootx() + x, rooty=control.winfo_rooty() + y)
        control.event_generate('<Motion>', **opciones)
        control.event_generate('<ButtonPress-1>', **opciones)
        self.raiz.update()
        if control.winfo_exists():
            control.event_generate('<ButtonRelease-1>', **opciones)
            self.raiz.update()

    def elegir_extranjero(self, selector):
        """Selecciona E con el ratón y comprueba que el menú se cierre."""
        ventana = selector._ventana_menu
        self.assertIsNotNone(ventana)
        self.assertTrue(ventana.winfo_viewable())
        lista = next(hijo for hijo in ventana.winfo_children() if isinstance(hijo, tk.Listbox))
        x, y, ancho, alto = lista.bbox(1)
        self.pulsar(lista, x + 4, y + alto // 2)
        self.assertEqual(selector.get(), 'E')
        self.assertIsNone(selector._ventana_menu)

    def test_clic_en_texto_abre_y_permite_elegir_e(self):
        """El clic sobre V abre el menú sin exigir acertar sobre la flecha."""
        self.pulsar(self.documento.tipo._entry)
        self.elegir_extranjero(self.documento.tipo)
        self.documento.numero.insert(0, '1234567')
        self.assertEqual(self.documento.get(), 'E-1234567')

    def test_clic_en_flecha_abre_y_permite_elegir_e(self):
        """La flecha conserva su clic y usa el mismo menú visible que el texto."""
        canvas = self.documento.tipo._canvas
        self.pulsar(canvas, canvas.winfo_width() - 10, canvas.winfo_height() // 2)
        self.elegir_extranjero(self.documento.tipo)

    def test_restaura_captura_de_dialogo(self):
        """Al elegir una opción se devuelve la captura al formulario que la tenía."""
        dialogo = ctk.CTkToplevel(self.raiz)
        documento = EntradaDocumento(dialogo)
        documento.pack(padx=20, pady=20)
        dialogo.grab_set()
        self.raiz.update()
        self.pulsar(documento.tipo._entry)
        self.elegir_extranjero(documento.tipo)
        self.assertEqual(self.raiz.grab_current(), dialogo)
        dialogo.destroy()

    def test_selector_deshabilitado_no_abre(self):
        """Un control deshabilitado no permite cambiar el tipo por clic."""
        self.documento.tipo.configure(state='disabled')
        self.pulsar(self.documento.tipo._entry)
        self.assertIsNone(self.documento.tipo._ventana_menu)
