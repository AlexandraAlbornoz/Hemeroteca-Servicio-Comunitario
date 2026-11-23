"""Edición con eventos reales en las entradas compartidas por los formularios."""
import unittest
import tempfile
from pathlib import Path
import customtkinter as ctk
from hemeroteca.ui.components import UIComponents
from hemeroteca.ui.controles import EntradaDocumento


class FormularioPrueba(UIComponents, ctk.CTk):
    """Usa las mismas entradas que el registro y los módulos internos, sin base de datos."""


class PruebasEdicionCampos(unittest.TestCase):
    """Comprueba reingreso, selección y sustitución por ratón y teclado."""

    @classmethod
    def setUpClass(cls):
        """Crea una única ventana de prueba ajena a las cuentas reales."""
        cls.raiz = FormularioPrueba()
        cls.raiz.title('Hemeroteca · Prueba aislada de edición')
        cls.raiz.geometry('600x420+30+30')

    @classmethod
    def tearDownClass(cls):
        """Cancela temporizadores propios de CTk antes de cerrar el intérprete."""
        for tarea in cls.raiz.tk.splitlist(cls.raiz.tk.call('after', 'info')):
            cls.raiz.after_cancel(tarea)
        cls.raiz.destroy()

    def setUp(self):
        """Crea entradas normales, de contraseña y de documento."""
        self.panel = ctk.CTkFrame(self.raiz)
        self.panel.pack(fill='both', expand=True)
        self.campos = []
        for etiqueta, mascara in (('Nombre', None), ('Apellido', None), ('Contraseña', '•')):
            caja, entrada = self.raiz._entry(self.panel, etiqueta, show=mascara)
            caja.pack(fill='x', padx=20, pady=6)
            self.campos.append(entrada)
        self.documento = EntradaDocumento(self.panel)
        self.documento.pack(fill='x', padx=20, pady=6)
        self.raiz.update()

    def tearDown(self):
        """Retira únicamente los controles de este caso."""
        self.panel.destroy()

    def pulsar_borde(self, campo):
        """Pulsa el área visible del campo por encima del texto interno."""
        canvas = campo._canvas
        opciones = dict(x=12, y=3, rootx=canvas.winfo_rootx() + 12, rooty=canvas.winfo_rooty() + 3)
        canvas.event_generate('<ButtonPress-1>', **opciones)
        canvas.event_generate('<ButtonRelease-1>', **opciones)
        self.raiz.update()

    def reemplazar_teclado(self, campo, texto):
        """Selecciona con Ctrl+A y escribe mediante eventos de teclado de Tk."""
        campo._entry.event_generate('<Control-a>')
        for letra in texto:
            campo._entry.event_generate('<KeyPress>', keysym=letra)
        self.raiz.update()

    def test_clic_en_campo_relleno_devuelve_foco_para_corregir(self):
        """Todo el rectángulo editable recibe el cursor, incluso tras visitar otro campo."""
        for campo in self.campos:
            with self.subTest(campo=campo):
                campo.insert(0, 'Incorrecto')
                self.documento.numero.focus_force()
                self.raiz.update()
                self.pulsar_borde(campo)
                self.assertEqual(self.raiz.focus_get(), campo._entry)
                self.reemplazar_teclado(campo, 'Correcto')
                self.assertEqual(campo.get(), 'Correcto')

    def test_clic_sobre_texto_recupera_teclado_al_salir_y_volver(self):
        """El clic en el texto debe recuperar el teclado, no solo el clic en el borde."""
        campo = self.campos[2]
        campo.insert(0, 'Abcd#1234')
        for vuelta in range(3):
            self.campos[0].focus_force()
            self.raiz.update()
            entrada = campo._entry
            x, y = entrada.winfo_width() // 2, entrada.winfo_height() // 2
            opciones = dict(x=x, y=y, rootx=entrada.winfo_rootx() + x, rooty=entrada.winfo_rooty() + y)
            entrada.event_generate('<ButtonPress-1>', **opciones)
            entrada.event_generate('<ButtonRelease-1>', **opciones)
            self.raiz.update()
            self.assertEqual(self.raiz.focus_get(), entrada)
            self.reemplazar_teclado(campo, 'Corregida' + str(vuelta))
            self.assertEqual(campo.get(), 'Corregida' + str(vuelta))

    def test_cedula_reemplaza_numero_completo_y_conserva_validacion(self):
        """Corrige un número ya escrito y sigue rechazando letras."""
        campo = self.documento.numero
        campo.insert(0, '12345678')
        self.campos[0].focus_force()
        self.raiz.update()
        self.pulsar_borde(campo)
        self.assertEqual(self.raiz.focus_get(), campo._entry)
        self.reemplazar_teclado(campo, '87654321')
        self.assertEqual(campo.get(), '87654321')
        campo.insert('end', 'A')
        self.assertEqual(campo.get(), '87654321')

    def test_contrasena_oculta_se_corrige_en_medio(self):
        """Corrige un carácter interno usando cursor, Retroceso y Suprimir."""
        campo = self.campos[2]
        campo.insert(0, 'Abcd#1234')
        campo.focus_force()
        self.raiz.update()
        campo._entry.icursor(3)
        campo._entry.event_generate('<BackSpace>')
        campo._entry.event_generate('<KeyPress>', keysym='Z')
        self.raiz.update()
        self.assertEqual(campo.get(), 'AbZd#1234')
        campo._entry.icursor(3)
        campo._entry.event_generate('<Delete>')
        campo._entry.event_generate('<KeyPress>', keysym='Q')
        self.raiz.update()
        self.assertEqual(campo.get(), 'AbZQ#1234')

    def test_contrasena_sigue_editable_al_mostrar_y_ocultar(self):
        """Mostrar contraseña conserva contenido y permite volver a borrar y escribir."""
        campo = self.campos[2]
        campo.insert(0, 'Abcd#1234')
        for mascara in ('', '•', '', '•'):
            with self.subTest(mascara=mascara):
                campo.configure(show=mascara)
                self.documento.numero.focus_force()
                self.raiz.update()
                self.pulsar_borde(campo)
                self.reemplazar_teclado(campo, 'Nueva123')
                self.assertEqual(campo.get(), 'Nueva123')

    def test_texto_contrasena_no_queda_cubierto_al_redibujar(self):
        """El control nativo debe permanecer visible sobre el decorado después del foco."""
        campo = self.campos[2]
        campo.insert(0, 'Abcd#1234')
        for operacion in (lambda: campo.configure(border_color='#0080FF'),
                          lambda: campo.configure(font=('Segoe UI', 15)),
                          lambda: campo.configure(show='')):
            operacion()
            self.raiz.update()
            # Consulta el orden local de las capas de Tk, independiente de que
            # Windows minimice u oculte la ventana de prueba durante la ejecución.
            capas = campo.tk.splitlist(campo.tk.call('winfo', 'children', str(campo)))
            self.assertGreater(capas.index(str(campo._entry)), capas.index(str(campo._canvas)))

    def test_consulta_periodica_no_roba_foco_a_contrasena(self):
        """La comprobación de red en segundo plano no debe sacar el cursor del campo."""
        from hemeroteca.services.container import create_services
        from hemeroteca.ui.tareas import ServiciosDeInterfaz

        class RedDePrueba:
            """Describe una red artificial estable sin abrir puertos."""

            def describe(self):
                """Devuelve el estado que la ventana real consulta cada cinco segundos."""
                import time
                time.sleep(.4)
                return {'mode': 'main'}

        with tempfile.TemporaryDirectory() as temporal:
            servicios = create_services(Path(temporal) / 'prueba.db')
            servicios.network = RedDePrueba()
            coordinador = ServiciosDeInterfaz(self.raiz, servicios)
            try:
                campo = self.campos[2]
                campo.insert(0, 'Abcd#1234')
                campo.focus_force()
                self.raiz.update()
                self.assertEqual(self.raiz.focus_get(), campo._entry)
                coordinador.network.describe()
                self.raiz.update()
                self.assertEqual(self.raiz.focus_get(), campo._entry)
            finally:
                coordinador.close()
