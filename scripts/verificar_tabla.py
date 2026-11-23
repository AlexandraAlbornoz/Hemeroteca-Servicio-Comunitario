"""Prueba visual breve en un proceso Tk separado de las pruebas de servicios."""

from tkinter import ttk
import customtkinter as ctk

from hemeroteca.ui.components import UIComponents


def verificar_tabla():
    """Comprueba cinco filas y ausencia de barra vertical en la tabla común."""
    raiz = ctk.CTk()
    raiz.withdraw()
    try:
        envoltura, tabla = UIComponents()._table(
            raiz, [('id', 'N.º', 90)], [(numero,) for numero in range(12)], height=12)
        if len(tabla.get_children()) != 5 or int(tabla.cget('height')) != 5:
            raise RuntimeError('La tabla no conserva cinco filas visibles.')
        if any(isinstance(hijo, ttk.Scrollbar) and str(hijo.cget('orient')) == 'vertical'
               for hijo in envoltura.winfo_children()):
            raise RuntimeError('La tabla contiene una barra vertical inesperada.')
        print('Tabla: cinco filas, sin scrollbar vertical')
    finally:
        raiz.destroy()


if __name__ == '__main__':
    verificar_tabla()
