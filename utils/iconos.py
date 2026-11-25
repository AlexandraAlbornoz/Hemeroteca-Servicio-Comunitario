"""Aplica el icono de periódico a la ventana y a los diálogos de Tkinter."""
from config.settings import ASSETS


def aplicar_icono(ventana):
    """Instala los tamaños nativos de Windows o la alternativa PNG de Tk."""
    import sys
    if sys.platform == 'win32':
        ruta = str(ASSETS / 'hemeroteca_periodico.ico')
        ventana.iconbitmap(ruta)
        ventana.iconbitmap(default=ruta)
    else:
        import tkinter as tk
        imagen = tk.PhotoImage(master=ventana, file=str(ASSETS / 'hemeroteca_periodico.png'))
        ventana.iconphoto(True, imagen)
        ventana._imagen_icono_periodico = imagen
