"""Inicio de sesión y registro con controles gráficos y callbacks reales."""
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import customtkinter as ctk
from PIL import Image

from hemeroteca.config.settings import ROLES
from hemeroteca.ui.login_view import LoginView
from tests.soporte_pantallas import VentanaGeneral


class VentanaLogin(LoginView, VentanaGeneral):
    """Añade la vista real al contenedor de controles, sin reemplazar sus formularios."""

    def __init__(self):
        super().__init__()
        self.show_login = self.mostrar_entrada
        self.logo_images = {}
        self.login_background_source = None
        self.services.auth.needs_setup.return_value = False
        self.services.auth.migration_accounts.return_value = []


class PruebasPantallaLogin(unittest.TestCase):
    """Opera por los botones visibles; aísla servicios, mensajes y navegación."""

    def setUp(self):
        self.h = VentanaLogin()
        self.addCleanup(self.h.close_for_test)
        for name in ['showerror', 'showwarning', 'showinfo']:
            setattr(self, name, patch('hemeroteca.ui.login_view.messagebox.'+name).start())
        self.addCleanup(patch.stopall)
        self.actor = dict(self.h.user)

    def open(self, register=False):
        self.h.show_login(register)
        self.h.update_idletasks()

    def credentials(self, document='V-12345678', password='Ficticia#2026'):  # pragma: allowlist secret -- entrada sintética del servicio simulado
        self.h.login_identity.set(document)
        self.h.login_password.delete(0, 'end')
        self.h.login_password.insert(0, password)

    def registration(self):
        self.open(True)
        self.h.write('Nombre(s) *', 'Persona')
        self.h.write('Apellido(s) *', 'Ficticia')
        self.credentials()
        self.h.reg_confirm.insert(0, 'Ficticia#2026')

    def test_logout_remoto_limpia_estado_y_recuerda_documento(self):
        self.h.services.read_only = True
        self.h.services.client = Mock()
        self.h._documento_recordado = 'E-12345678'
        save = self.h._guardar_estado_vista
        self.open()
        save.assert_called_once()
        self.h.services.client.logout.assert_called_once()
        self.assertIsNone(self.h.user)
        self.assertIsNone(self.h._authenticated_version)
        self.assertIsNone(self.h._session_snapshot)
        self.assertEqual(self.h.login_identity.get(), 'E-12345678')
        self.assertTrue(self.h.has_text('PC autorizada y conectada'))

    def test_primer_inicio_solo_configura_maestro_local(self):
        self.h.services.auth.needs_setup.return_value = True
        self.open()
        self.assertTrue(self.h._setup_mode)
        self.assertTrue(self.h.has_text('1. Completa'))
        self.h.services.read_only = True
        self.open()
        self.assertFalse(self.h._setup_mode)
        self.h.button('Entrar a la hemeroteca')

    def test_error_preparacion_no_muestra_formulario_y_permite_reintento(self):
        for error in [ValueError('conexión ficticia'), sqlite3.OperationalError('base no disponible')]:
            with self.subTest(error=error):
                self.h.services.auth.needs_setup.side_effect = error
                self.open()
                self.assertFalse(self.h._login_enabled)
                self.h.services.auth.needs_setup.side_effect = None
                self.h.button('Reintentar').invoke()
                self.h.button('Entrar a la hemeroteca')

    def test_ayuda_y_opciones_plegables(self):
        self.open()
        self.h.button('Conexión de computadoras').invoke()
        self.h.button('Ocultar opciones adicionales').invoke()
        self.h.button('¿Cómo lleno estos datos?').invoke()
        self.assertTrue(self.h.has_text('entre 8 y 128'))
        dialog = self.h.dialogs[-1]
        self.h.button('Entendido: volver').invoke()
        self.assertFalse(dialog.winfo_exists())

    def test_sin_gestor_no_hay_opciones_de_red(self):
        self.h.services.network = None
        self.open()
        with self.assertRaises(AssertionError):
            self.h.button('Conexión de computadoras')

    def test_mostrar_contrasena_no_modifica_texto_y_oculta_confirmacion(self):
        self.registration()
        checkbox = self.h.text_checkbox('Mostrar contraseña')
        checkbox.toggle()
        self.assertEqual(self.h.login_password.cget('show'), '')
        self.assertEqual(self.h.reg_confirm.cget('show'), '')
        self.assertEqual(self.h.login_password.get(), 'Ficticia#2026')
        checkbox.toggle()
        self.assertEqual(self.h.reg_confirm.cget('show'), '•')

    def test_credenciales_vacias_no_consultan_servicio(self):
        self.open()
        self.h.button('Entrar a la hemeroteca').invoke()
        self.credentials(password='')
        self.h.button('Entrar a la hemeroteca').invoke()
        self.assertEqual(self.showwarning.call_count, 2)
        self.h.services.auth.authenticate.assert_not_called()

    def test_rechazo_limpia_contrasena_y_no_abre_sesion(self):
        self.open()
        self.credentials()
        self.h.services.auth.authenticate.side_effect = ValueError('credenciales inválidas')
        self.h.button('Entrar a la hemeroteca').invoke()
        self.assertEqual(self.h.login_password.get(), '')
        self.assertIsNone(self.h.user)
        self.h.show_shell.assert_not_called()
        self.showerror.assert_called_once()

    def test_error_sqlite_muestra_aviso_y_permite_reintento(self):
        self.open()
        self.credentials()
        self.h.services.auth.authenticate.side_effect = sqlite3.OperationalError('ruta privada ficticia')
        self.h.button('Entrar a la hemeroteca').invoke()
        self.showerror.assert_called_once()
        self.assertNotIn('ruta privada', str(self.showerror.call_args))
        self.assertIsNone(self.h.user)
        self.h.services.auth.authenticate.side_effect = None
        self.h.services.auth.authenticate.return_value = self.actor
        self.credentials()
        self.h.button('Entrar a la hemeroteca').invoke()
        self.assertEqual(self.h.user, self.actor)
        self.h.show_shell.assert_called_once_with('Consulta de periódicos')

    def test_exito_establece_version_y_sesion(self):
        self.open()
        self.credentials()
        self.h.services.auth.authenticate.return_value = self.actor
        self.h.button('Entrar a la hemeroteca').invoke()
        self.h.services.auth.authenticate.assert_called_once_with('V-12345678', 'Ficticia#2026')
        self.assertEqual(self.h._authenticated_version, self.actor['password_version'])
        self.h.show_shell.assert_called_once()

    def test_registro_exige_nombres_documento_y_confirmacion(self):
        with patch.object(self.h, '_security_questions_form') as questions:
            self.registration()
            for label in ['Nombre(s) *', 'Apellido(s) *']:
                self.h.write(label, '')
                self.h.register_user()
                self.h.write(label, 'Ficticia')
            self.credentials(password='corta')  # pragma: allowlist secret -- valida rechazo de contraseña corta ficticia
            self.h.register_user()
            self.credentials(password='Otra#2026')  # pragma: allowlist secret -- confirma discrepancia de campos ficticios
            self.h.register_user()
            self.assertEqual(self.showwarning.call_count, 4)
            questions.assert_not_called()

    def test_registro_valida_nombre_documento_y_fortaleza(self):
        with patch.object(self.h, '_security_questions_form') as questions:
            self.registration()
            self.h.write('Nombre(s) *', '1234')
            self.h.register_user()
            self.h.write('Nombre(s) *', 'Persona')
            self.credentials(password='aaaaaaaa')  # pragma: allowlist secret -- verifica rechazo de contraseña débil ficticia
            self.h.reg_confirm.delete(0, 'end')
            self.h.reg_confirm.insert(0, 'aaaaaaaa')
            self.h.register_user()
            self.assertEqual(self.showwarning.call_count, 2)
            questions.assert_not_called()

    def test_registro_no_permite_elevar_perfil_a_maestro(self):
        self.registration()
        with patch.object(self.h.reg_role, 'get', return_value=ROLES[0]), patch.object(self.h, '_security_questions_form') as questions:
            self.h.register_user()
            questions.assert_not_called()
        self.showwarning.assert_called_once()

    def test_registro_regular_solo_pasa_datos_validados_a_preguntas(self):
        self.registration()
        with patch.object(self.h, '_security_questions_form') as questions:
            self.h.register_user()
            questions.assert_called_once_with(account_data=('Persona Ficticia', 'V-12345678', 'Ficticia#2026', ROLES[2]))
        self.h.services.users.register_user.assert_not_called()

    def test_registro_inicial_fija_perfil_maestro(self):
        self.h.services.auth.needs_setup.return_value = True
        self.registration()
        with patch.object(self.h, '_security_questions_form') as questions:
            self.h.register_user()
            self.assertEqual(questions.call_args.kwargs['account_data'][-1], ROLES[0])

    def test_migracion_sin_cuentas_y_error_de_conexion(self):
        self.h._migration_form()
        self.showinfo.assert_called_once()
        self.h.services.auth.migration_accounts.side_effect = ValueError('sin conexión')
        self.h._migration_form()
        self.showwarning.assert_called_once()

    def test_migracion_duplicado_error_y_exito(self):
        self.h.services.auth.migration_accounts.return_value = [dict(id=7, name='Anterior Ficticia', role=ROLES[2])]
        self.h._migration_form()
        dialog = self.h.dialogs[-1]
        self.h.write('Contraseña actual *', 'Ficticia#2026')
        self.h.write('Documento *', 'V-12345678')
        for error, text in [(sqlite3.IntegrityError('duplicado'), 'ya pertenece'), (ValueError('dato inválido'), 'dato inválido')]:
            self.h.services.auth.migrate_document.side_effect = error
            self.h.button('Guardar documento').invoke()
            self.assertTrue(self.h.has_text(text))
            self.assertTrue(dialog.winfo_exists())
        self.h.services.auth.migrate_document.side_effect = None
        self.h.services.auth.migrate_document.return_value = self.actor
        self.h.button('Guardar documento').invoke()
        self.assertFalse(dialog.winfo_exists())
        self.assertEqual(self.h.user, self.actor)
        self.h.show_shell.assert_called_once()

    def test_imagenes_ausentes_validas_y_corruptas(self):
        with tempfile.TemporaryDirectory() as folder, patch('hemeroteca.ui.login_view.ASSETS', Path(folder)):
            self.h._load_logos()
            self.assertEqual(self.h.logo_images, {})
            Image.new('RGBA', (30, 80)).save(Path(folder)/'gobernacion.png')
            Image.new('RGB', (80, 30)).save(Path(folder)/'biblioteca.png')
            Image.new('RGB', (80, 80)).save(Path(folder)/'fondo_biblioteca.png')
            self.h._load_logos()
            self.assertEqual(set(self.h.logo_images), {'gov', 'library'})
            self.assertIsNotNone(self.h.login_background_source)
            for p in Path(folder).iterdir():
                p.write_bytes(b'imagen corrupta')
            with self.assertLogs('hemeroteca.ui.login_view', level='WARNING') as logs:
                self.h._load_logos()
            self.assertEqual(len(logs.output), 3)

    def test_fondo_redimensionado_y_widget_destruido(self):
        self.open()
        promo = self.h.login_promo_canvas.master
        self.h.login_background_source = Image.new('RGB', (30, 30))
        self.h._resize_login_background(SimpleNamespace(width=1, height=1, widget=promo))
        self.h._resize_login_background(SimpleNamespace(width=500, height=500, widget=promo))
        self.h._resize_login_background(SimpleNamespace(width=600, height=600, widget=promo))
        self.h._apply_login_background(promo)
        promo.destroy()
        self.h._apply_login_background(promo)

