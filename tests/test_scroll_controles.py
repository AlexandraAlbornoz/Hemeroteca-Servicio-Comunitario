"""Prioridad de rueda entre campos, menús y páginas reales de Tkinter."""
import tkinter as tk
from tkinter import ttk
import unittest
import customtkinter as ctk
from ui.components import UIComponents
from ui.controles import SelectorCompacto


class VentanaScroll(UIComponents, ctk.CTk):
    """Construye las áreas desplazables usadas por los formularios de Hemeroteca."""


class PruebasScrollControles(unittest.TestCase):
    """Cada rueda mueve únicamente el control o contenedor al que corresponde."""

    @classmethod
    def crear_raiz(cls):
        """Prepara una ventana aislada sin servicios ni cuentas."""
        cls.raiz = VentanaScroll()
        cls.raiz.title('Hemeroteca · Prueba aislada de scroll')
        cls.raiz.geometry('640x500+30+30')

    @classmethod
    def cerrar_raiz(cls):
        """Cancela las tareas de CTk y libera el intérprete de prueba."""
        for tarea in cls.raiz.tk.splitlist(cls.raiz.tk.call('after', 'info')):
            cls.raiz.after_cancel(tarea)
        cls.raiz.destroy()

    def setUp(self):
        """Crea una página larga con selector, texto, tabla y un bloque anidado."""
        self.crear_raiz()
        self.errores = []
        self.raiz.report_callback_exception = lambda tipo, error, traza: self.errores.append(str(error))
        self.pagina = self.raiz._scrollable(self.raiz, height=400)
        self.pagina.pack(fill='both', expand=True)
        self.selector = SelectorCompacto(self.pagina, values=[str(n) for n in range(100)], state='readonly')
        self.selector.pack(padx=20, pady=10)
        self.texto = ctk.CTkTextbox(self.pagina, height=90)
        self.texto.pack(fill='x', padx=20, pady=10)
        self.texto.insert('1.0', '\n'.join('Línea de prueba ' + str(n) for n in range(100)))
        self.tabla = ttk.Treeview(self.pagina, columns=['dato'], show='headings', height=4)
        self.tabla.pack(fill='x', padx=20, pady=10)
        for n in range(50):
            self.tabla.insert('', 'end', values=[str(n)])
        self.interior = self.raiz._scrollable(self.pagina, height=100)
        self.interior.pack(fill='x', padx=20, pady=10)
        self.etiqueta_interior = None
        for n in range(30):
            etiqueta = ctk.CTkLabel(self.interior, text='Interior ' + str(n))
            etiqueta.pack()
            if self.etiqueta_interior is None:
                self.etiqueta_interior = etiqueta
        for n in range(30):
            ctk.CTkLabel(self.pagina, text='Página ' + str(n)).pack()
        self.raiz.update()

    def tearDown(self):
        """Cierra cualquier menú de prueba y retira su página."""
        self.pagina.destroy()
        self.raiz.update()
        self.cerrar_raiz()
        self.assertEqual(self.errores, [])

    def rueda(self, control, delta=-120):
        """Emite una rueda sobre el widget con sus coordenadas reales."""
        control.event_generate('<MouseWheel>', delta=delta, x=5, y=5,
                               rootx=control.winfo_rootx() + 5, rooty=control.winfo_rooty() + 5)
        self.raiz.update()

    def test_rueda_selector_cerrado_mueve_pagina_sin_abrir(self):
        """Texto y flecha dejan continuar el scroll sin cambiar el valor ni abrir opciones."""
        valor = self.selector.get()
        for control in (self.selector._entry, self.selector._canvas):
            self.pagina._parent_canvas.yview_moveto(0)
            self.rueda(control)
            self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)
            self.assertIsNone(self.selector._ventana_menu)
            self.assertEqual(self.selector.get(), valor)

    def test_rueda_campo_con_menu_abierto_cierra_y_mueve_pagina(self):
        """Fuera de las opciones, la rueda cierra el menú y desplaza el formulario."""
        self.selector._open_dropdown_menu()
        self.raiz.update()
        self.rueda(self.selector._entry)
        self.assertIsNone(self.selector._ventana_menu)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_rueda_selector_deshabilitado_no_abre(self):
        """Un campo deshabilitado tampoco interrumpe el desplazamiento general."""
        self.selector.configure(state='disabled')
        self.rueda(self.selector._canvas)
        self.assertIsNone(self.selector._ventana_menu)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_rueda_lista_abierta_no_mueve_pagina_incluso_en_limite(self):
        """La rueda se queda en el menú, también al llegar al final de sus opciones."""
        self.selector._open_dropdown_menu()
        self.raiz.update()
        lista = next(hijo for hijo in self.selector._ventana_menu.winfo_children() if isinstance(hijo, tk.Listbox))
        anterior = self.pagina._parent_canvas.yview()
        self.rueda(lista)
        self.assertGreater(lista.yview()[0], 0)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)
        lista.yview_moveto(1)
        self.rueda(lista)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)

    def test_rueda_tabla_mueve_filas_sin_mover_pagina(self):
        """La tabla conserva su desplazamiento propio aunque esté dentro de una página larga."""
        anterior = self.pagina._parent_canvas.yview()
        self.rueda(self.tabla)
        self.assertGreater(self.tabla.yview()[0], 0)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)

    def test_rueda_texto_mueve_solo_su_contenido(self):
        """Los cuadros de varias líneas siguen recibiendo la rueda sin mover su formulario."""
        anterior = self.pagina._parent_canvas.yview()
        self.rueda(self.texto._textbox)
        self.assertGreater(self.texto.yview()[0], 0)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)

    def test_rueda_bloque_anidado_no_mueve_exterior(self):
        """En bloques anidados solo se mueve el contenedor más cercano al cursor."""
        anterior = self.pagina._parent_canvas.yview()
        self.rueda(self.etiqueta_interior._label)
        self.assertGreater(self.interior._parent_canvas.yview()[0], 0)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)

    def test_rueda_fondo_sigue_moviendo_pagina(self):
        """El fondo del formulario conserva su scroll normal."""
        self.rueda(self.pagina._parent_canvas)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_rueda_recorre_tres_lineas_aproximadas(self):
        """Un paso completo recorre noventa píxeles lógicos, sin exigir giros repetidos."""
        lienzo = self.pagina._parent_canvas
        antes = lienzo.canvasy(0)
        self.rueda(lienzo)
        esperado = round(90 * self.raiz._get_window_scaling())
        self.assertAlmostEqual(lienzo.canvasy(0) - antes, esperado, delta=1)

    def test_tabla_al_final_continua_en_pagina(self):
        """Al agotar las filas, la rueda baja el formulario sin atascarse."""
        self.tabla.yview_moveto(1)
        self.raiz.update()
        self.rueda(self.tabla)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_tabla_al_inicio_continua_hacia_arriba(self):
        """La continuidad también funciona al subir desde la primera fila."""
        self.pagina._parent_canvas.yview_moveto(.3)
        self.tabla.yview_moveto(0)
        self.raiz.update()
        antes = self.pagina._parent_canvas.yview()[0]
        self.rueda(self.tabla, 120)
        self.assertLess(self.pagina._parent_canvas.yview()[0], antes)

    def test_tabla_sin_desbordamiento_no_bloquea(self):
        """Una tabla vacía o corta deja pasar la rueda a la página."""
        self.tabla.delete(*self.tabla.get_children())
        self.raiz.update()
        self.rueda(self.tabla)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_texto_al_final_continua_en_pagina(self):
        """Los cuadros de texto entregan la rueda al formulario al llegar al final."""
        self.texto.yview_moveto(1)
        self.raiz.update()
        self.rueda(self.texto._textbox)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_marco_anidado_al_final_continua_en_exterior(self):
        """El desplazamiento atraviesa contenedores interiores sin recorrido restante."""
        self.interior._parent_canvas.yview_moveto(1)
        self.raiz.update()
        self.rueda(self.etiqueta_interior._label)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_panel_tactil_sobre_campos_no_pierde_fracciones(self):
        """Movimientos pequeños sobre distintos hijos se acumulan en la misma página."""
        antes = self.pagina._parent_canvas.yview()[0]
        for control in (self.selector._entry, self.selector._canvas) * 4:
            self.rueda(control, -1)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], antes)
        self.assertIsNone(self.selector._ventana_menu)

    def test_rueda_sobre_boton_y_etiqueta(self):
        """Controles sin desplazamiento propio no interrumpen la rueda general."""
        boton = ctk.CTkButton(self.pagina, text='Prueba')
        boton.pack()
        self.raiz.update()
        self.rueda(boton._text_label)
        self.assertGreater(self.pagina._parent_canvas.yview()[0], 0)

    def test_panel_tactil_acumula_deltas_sin_mover_pagina(self):
        """Dos movimientos pequeños navegan la lista sin saltar al contenedor exterior."""
        anterior = self.pagina._parent_canvas.yview()
        valor = self.selector.get()
        self.selector._open_dropdown_menu()
        self.raiz.update()
        lista = self.selector._lista_menu
        self.rueda(lista, -60)
        self.assertEqual(lista.yview()[0], 0)
        self.rueda(lista, -60)
        self.assertGreater(lista.yview()[0], 0)
        self.assertEqual(self.selector.get(), valor)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)

    def test_rueda_sobre_barra_menu_mueve_lista_no_pagina(self):
        """La barra del desplegable tiene la misma prioridad que sus opciones."""
        self.selector._open_dropdown_menu()
        self.raiz.update()
        barra = next(hijo for hijo in self.selector._ventana_menu.winfo_children() if isinstance(hijo, ttk.Scrollbar))
        anterior = self.pagina._parent_canvas.yview()
        self.rueda(barra)
        self.assertGreater(self.selector._lista_menu.yview()[0], 0)
        self.assertEqual(self.pagina._parent_canvas.yview(), anterior)
