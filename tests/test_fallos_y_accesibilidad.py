"""Regresiones de escritura atómica, protocolo RPC y teclado/contraste."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import tkinter as tk
import customtkinter as ctk

from hemeroteca.network.client import RemoteClient
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.ui.components import UIComponents
from hemeroteca.utils.local_secrets import private_write
from scripts.comprobar_contraste import contrastes


class PruebasFallosYContrato(unittest.TestCase):
    """Comprueba preservación de datos y nombres de operaciones publicados."""

    def test_fallo_de_reemplazo_conserva_archivo_y_limpia_temporal(self):
        """Una falta de permisos al confirmar no destruye la configuración previa."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'settings.json'
            path.write_bytes(b'estado anterior')
            with patch('hemeroteca.utils.local_secrets.os.replace', side_effect=PermissionError('fallo ficticio')):
                with self.assertRaises(PermissionError):
                    private_write(path, b'estado nuevo')
            self.assertEqual(path.read_bytes(), b'estado anterior')
            self.assertEqual([p.name for p in path.parent.iterdir()], ['settings.json'])

    def test_rpcs_de_control_conservan_nombres_anteriores(self):
        """El empaquetado Python no cambia los nombres públicos del protocolo."""
        client = RemoteClient({'server_url': 'https://127.0.0.1', 'fingerprint': 'a' * 64})
        with patch('hemeroteca.network.client.request', return_value={'result': {'ok': True}}) as request:
            for method in ('network.transfer', 'network.rollback_transfer',
                           'hemeroteca.network.transfer', 'hemeroteca.network.rollback_transfer'):
                self.assertEqual(client.call(method), {'ok': True})
                self.assertEqual(request.call_args.args[3]['method'], method)
            with self.assertRaises(AccessDenied):
                client.call('network.ejecutar_codigo')
            self.assertEqual(request.call_count, 4)

    def test_contraste_de_texto_en_paleta_compartida(self):
        """Los pares activos auditados alcanzan como mínimo una razón de 4,5:1."""
        for name, ratio in contrastes().items():
            with self.subTest(par=name):
                self.assertGreaterEqual(ratio, 4.5)


class PruebasBotonesTeclado(unittest.TestCase):
    """Ejercita botones reales con eventos de teclado en una ventana temporal."""

    def setUp(self):
        """Crea una raíz gráfica independiente."""
        self.root = ctk.CTk()
        self.root.geometry('320x180')
        self.callbacks = []
        self.button = UIComponents()._button(self.root, 'Acción de prueba', lambda: self.callbacks.append('ok'))
        self.button.pack()
        self.root.update()

    def tearDown(self):
        """Libera temporizadores y ventana de prueba."""
        for task in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            self.root.after_cancel(task)
        self.root.destroy()

    def test_enter_espacio_y_foco_visible(self):
        """El botón es tabulable, muestra foco e invoca una vez por tecla."""
        self.button._canvas.focus_force()
        self.root.update()
        self.assertEqual(self.button.cget('border_width'), 2)
        for key in ('Return', 'space'):
            self.button._canvas.event_generate('<KeyPress-' + key + '>')
            self.root.update()
        self.assertEqual(self.callbacks, ['ok', 'ok'])

    def test_boton_deshabilitado_no_ejecuta_comando(self):
        """Un botón desactivado conserva su restricción incluso mediante teclado."""
        self.button.configure(state='disabled')
        self.button._canvas.focus_force()
        self.root.update()
        self.button._canvas.event_generate('<KeyPress-Return>')
        self.root.update()
        self.assertEqual(self.callbacks, [])
