"""Verifica que la optimización conserve resultados, errores y ventanas modales."""
import gc
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from services.container import create_services
from ui.tareas import ServiciosDeInterfaz


class RedPrueba:
    """Simula consultas rápidas, lentas y fallidas sin acceso a la red."""

    def consultar(self, demora=0, fallar=False):
        """Devuelve un resultado controlado o reproduce un error de servicio."""
        time.sleep(demora)
        if fallar:
            raise ValueError('Error de prueba')
        return {'resultado': 'vigente'}


class PruebasRendimientoInterfaz(unittest.TestCase):
    """Ejercita el coordinador real sobre una base temporal independiente."""

    def setUp(self):
        """Prepara Tk y servicios aislados de la instalación del usuario."""
        self.temporal = tempfile.TemporaryDirectory()
        self.raiz = tk.Tk()
        self.raiz.withdraw()
        servicios = create_services(Path(self.temporal.name) / 'prueba.db')
        servicios.network = RedPrueba()
        self.servicios = ServiciosDeInterfaz(self.raiz, servicios)

    def tearDown(self):
        """Libera servicios, temporizadores y archivos sintéticos."""
        self.servicios.close()
        for tarea in self.raiz.tk.splitlist(self.raiz.tk.call('after', 'info')):
            self.raiz.after_cancel(tarea)
        self.raiz.destroy()
        self.temporal.cleanup()

    def test_agrupacion_anidada_restaura_memoria_tras_error(self):
        """Un error no deja desactivada la recolección ni niveles pendientes."""
        estado = gc.isenabled()
        with patch('ui.tareas.gc.collect', wraps=gc.collect) as recolectar:
            with self.assertRaisesRegex(ValueError, 'Error de prueba'):
                with self.servicios.agrupar_interfaz():
                    with self.servicios.agrupar_interfaz():
                        self.assertFalse(gc.isenabled())
                        self.servicios.network.consultar(fallar=True)
            self.assertEqual(recolectar.call_count, 2)
        self.assertEqual(gc.isenabled(), estado)
        self.assertEqual(self.servicios._nivel_interfaz, 0)
        self.assertFalse(self.raiz._servicios_ocupados)
        self.assertEqual(self.servicios.network.consultar(), {'resultado': 'vigente'})

    def test_operacion_rapida_no_crea_ventana(self):
        """Las consultas rápidas conservan su resultado sin crear diálogos ocultos."""
        with patch('ui.tareas.tk.Toplevel', wraps=tk.Toplevel) as ventana:
            self.assertEqual(self.servicios.network.consultar(), {'resultado': 'vigente'})
            ventana.assert_not_called()

    def test_operacion_lenta_muestra_progreso_y_restaura_modal(self):
        """Una tarea larga muestra progreso y devuelve la captura al diálogo previo."""
        modal = tk.Toplevel(self.raiz)
        modal.update()
        modal.grab_set()
        with patch('ui.tareas.tk.Toplevel', wraps=tk.Toplevel) as ventana:
            self.assertEqual(self.servicios.network.consultar(demora=.4), {'resultado': 'vigente'})
            self.assertEqual(ventana.call_count, 1)
        self.assertEqual(self.raiz.grab_current(), modal)
        self.assertFalse(self.raiz._servicios_ocupados)
        modal.destroy()
