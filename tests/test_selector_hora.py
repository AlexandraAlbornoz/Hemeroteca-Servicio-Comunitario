"""Regresiones de escritura y selección horaria sin acceder a datos personales."""
import unittest
import customtkinter as ctk
from hemeroteca.ui.controles import EntradaEditable
from hemeroteca.ui.selector_hora import SelectorHora, usuario_auditoria_valido


class PruebasFiltrosAuditoria(unittest.TestCase):
    """Ejercita los widgets reales y su contrato de restauración de filtros."""

    def setUp(self):
        """Crea una raíz oculta sin iniciar servicios ni abrir bases de datos."""
        self.raiz = ctk.CTk()
        self.raiz.withdraw()
        self.selector = SelectorHora(self.raiz)

    def tearDown(self):
        """Libera los controles y sus temporizadores después de cada prueba."""
        for identificador in self.raiz.tk.call('after', 'info'):
            self.raiz.after_cancel(identificador)
        self.raiz.destroy()

    def test_nombres_y_pegado(self):
        """Acepta nombres acentuados y rechaza pegados que incluyan otros caracteres."""
        entrada = EntradaEditable(self.raiz)
        entrada.configure(validate='key', validatecommand=(entrada.register(usuario_auditoria_valido), '%P'))
        entrada.insert(0, 'María José Ñúñez')
        self.assertEqual(entrada.get(), 'María José Ñúñez')
        for texto in ('123', '@', '\t', '\n', 'Ana7', '😊'):
            entrada.insert('end', texto)
            self.assertEqual(entrada.get(), 'María José Ñúñez')
        entrada.delete(0, 'end')
        self.assertEqual(entrada.get(), '')
        self.assertTrue(usuario_auditoria_valido('Jose\u0301'))

    def test_limites_y_limpieza(self):
        """Restaura medianoche, fin del día y filtros anteriores sin valores inválidos."""
        self.assertEqual(self.selector.get(), '')
        for valor in ('00:00', '23:59', '08', '08:05:31'):
            self.selector.set(valor)
            self.assertEqual(self.selector.get(), valor)
        self.selector.delete(0, 'end')
        self.assertEqual(self.selector.get(), '')
        for valor in ('24:00', '12:60', 'abc', '-1:00', '12::00', '12:30:00:00'):
            with self.assertRaises(ValueError):
                self.selector.set(valor)

    def test_seleccion_y_solo_lectura(self):
        """Elegir valores completa el reloj y no permite escribir números fuera de rango."""
        self.assertEqual(self.selector.hora.cget('state'), 'readonly')
        self.assertEqual(self.selector.minuto.cget('state'), 'readonly')
        self.selector.hora.set('15')
        self.selector._elegir_hora('15')
        self.assertEqual(self.selector.get(), '15:00')
        self.selector.minuto.set('42')
        self.selector._elegir_minuto('42')
        self.assertEqual(self.selector.get(), '15:42')
        self.selector.delete()
        self.selector.minuto.set('12')
        self.selector._elegir_minuto('12')
        self.assertEqual(self.selector.get(), '00:12')
