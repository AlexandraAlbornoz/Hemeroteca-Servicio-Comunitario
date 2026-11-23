"""Recuperación de cuentas y mantenimiento con widgets reales y respuestas aisladas."""
from types import SimpleNamespace
import sqlite3
import unittest
from unittest.mock import Mock, patch
import customtkinter as ctk

from tests.soporte_pantallas import VentanaGeneral
from hemeroteca.config.settings import ROLES, SECURITY_QUESTIONS, VIEWS
from hemeroteca.services.access_service import AccessDenied


class PruebasPantallaRecuperacion(unittest.TestCase):
    """Prueba validación, reintento y secuencias obligatorias, sin tocar el portapapeles."""

    def setUp(self):
        """Crea una raíz y sustituye únicamente mensajes bloqueantes del sistema."""
        self.h = VentanaGeneral()
        self.addCleanup(self.h.close_for_test)
        for name in ('showwarning', 'showinfo', 'askyesno'):
            value = patch('hemeroteca.ui.recovery_view.messagebox.' + name, return_value=True).start()
            setattr(self, name, value)
        self.addCleanup(patch.stopall)

    def test_codigo_exige_guardado_copia_solo_dato_ficticio_y_continua(self):
        """Cerrar sin confirmación no avanza; el código se copia solo al doble de prueba."""
        resume = Mock()
        self.h._show_recovery_code('HMR-CODIGO-FICTICIO', 'V-12345678', resume, registration=True)
        dialog = self.h.dialogs[-1]
        callback = dialog.tk.call('wm', 'protocol', dialog._w, 'WM_DELETE_WINDOW')
        dialog.tk.call(callback)
        self.showwarning.assert_called_once()
        self.assertTrue(dialog.winfo_exists())
        self.h.button('Copiar código').invoke()
        self.h.clipboard_append.assert_called_once_with('HMR-CODIGO-FICTICIO')
        self.h.text_checkbox('He guardado').toggle()
        self.h.button('Ya lo guardé · Continuar').invoke()
        resume.assert_called_once()
        self.assertFalse(self.h._showing_recovery_code)

    def test_requisitos_obligatorios_en_orden(self):
        """No repite formularios ya abiertos y prioriza contraseña antes de preguntas/código."""
        actor = dict(self.h.user)
        self.h.user = None
        self.assertFalse(self.h._enforce_account_requirements())
        self.h.user = actor
        self.h._account_step = 'code'
        self.assertTrue(self.h._enforce_account_requirements())
        self.h._account_step = None
        with patch.object(self.h, '_password_form') as password, patch.object(self.h, '_security_questions_form') as questions, patch.object(self.h, '_show_recovery_code') as show:
            self.h.user['must_change_password'] = True
            self.assertTrue(self.h._enforce_account_requirements())
            password.assert_called_once_with(required=True)
            self.h._account_step = 'password'
            self.h._enforce_account_requirements()
            self.assertEqual(password.call_count, 1)
            self.h.user['must_change_password'] = False
            self.h._account_step = None
            self.h.services.recovery.needs_configuration.return_value = True
            self.assertTrue(self.h._enforce_account_requirements())
            questions.assert_called_once_with(required=True)
            self.h._account_step = 'questions'
            self.h._enforce_account_requirements()
            self.assertEqual(questions.call_count, 1)
            self.h.services.recovery.needs_configuration.return_value = False
            self.h.services.recovery.needs_code.return_value = True
            self.h.services.recovery.enroll_code.return_value = 'HMR-FICTICIO'
            self.assertTrue(self.h._enforce_account_requirements())
            show.call_args.args[2]()
            self.h.show_shell.assert_called_with(VIEWS[0])
            self.h.services.recovery.needs_code.return_value = False
            self.assertFalse(self.h._enforce_account_requirements())

    def test_cambio_contrasena_diferencias_error_y_codigo_nuevo(self):
        """Un error conserva el formulario y un éxito actualiza la sesión tras guardar el código."""
        self.h._password_form()
        self.h.write('Nueva contraseña *', 'NuevaFicticia#2026')
        self.h.button('Guardar contraseña').invoke()
        self.assertTrue(self.h.has_text('no coinciden'))
        self.h.write('Confirmar nueva contraseña *', 'NuevaFicticia#2026')
        self.h.write('Contraseña actual o temporal *', 'Prueba#2026')
        self.h.services.auth.change_password.side_effect = AccessDenied('sesión ficticia caducada')
        self.h.button('Guardar contraseña').invoke()
        self.h.update_idletasks()
        self.h._sync_session.assert_called_once()
        self.h.services.auth.change_password.side_effect = None
        self.h.services.auth.change_password.return_value = dict(self.h.user, password_version=2, _new_recovery_code='HMR-FICTICIO')
        with patch.object(self.h, '_show_recovery_code') as show:
            self.h.button('Guardar contraseña').invoke()
            show.call_args.args[2]()
        self.assertEqual(self.h.user['password_version'], 2)
        self.h.show_shell.assert_called_once()

    def test_cambio_obligatorio_recuperado_sin_clave_anterior(self):
        """El acceso recuperado envía una clave anterior vacía y no solicita ese campo."""
        self.h.user['_auth_method'] = 'recovery'
        self.h.services.auth.change_password.return_value = dict(self.h.user, password_version=2)
        self.h._password_form(required=True)
        for label in ('Nueva contraseña *', 'Confirmar nueva contraseña *'):
            self.h.write(label, 'NuevaFicticia#2026')
        self.h.button('Guardar contraseña').invoke()
        self.assertEqual(self.h.services.auth.change_password.call_args.args[1], '')
        self.assertIsNone(self.h._account_step)

    def test_preguntas_existentes_no_muestran_respuestas(self):
        """La vista permanente ofrece renovar código sin editar respuestas guardadas."""
        self.h.services.recovery.configured_questions.return_value = SECURITY_QUESTIONS[:3]
        self.h._security_questions_form()
        self.assertTrue(self.h.has_text('no se muestran'))
        with patch.object(self.h, '_renovar_codigo_propio'):
            self.assertTrue(self.h.button('Generar nuevo código de recuperación').winfo_exists())

    def test_preguntas_propias_error_y_guardado_obligatorio(self):
        """Las tres respuestas viajan al servicio y el error no avanza de paso."""
        self.h._security_questions_form(required=True)
        self.h.write('Contraseña actual *', 'Prueba#2026')
        for index in range(1, 4):
            self.h.write(f'Respuesta {index} *', 'Respuesta ficticia')
        self.h.services.recovery.configure_questions.side_effect = ValueError('preguntas ficticias inválidas')
        self.h.button('Guardar preguntas').invoke()
        self.assertTrue(self.h.has_text('preguntas ficticias inválidas'))
        self.h.services.recovery.configure_questions.side_effect = None
        self.h.button('Guardar preguntas').invoke()
        self.h.show_shell.assert_called_with(VIEWS[0])
        self.assertEqual(len(self.h.services.recovery.configure_questions.call_args.args[2]), 3)

    def test_registro_inicial_maestro_y_usuario_con_codigo(self):
        """Los dos perfiles invocan su operación de registro y vuelven a ingreso al guardar código."""
        for role in (ROLES[0], ROLES[2]):
            self.h._security_questions_form(('Persona Ficticia', 'V-12345678', 'Prueba#2026', role))
            for index in range(1, 4):
                self.h.write(f'Respuesta {index} *', 'Respuesta ficticia')
            operation = self.h.services.auth.create_master if role == ROLES[0] else self.h.services.users.register_user
            operation.return_value = SimpleNamespace(recovery_code='HMR-FICTICIO')
            text = 'Crear administrador principal' if role == ROLES[0] else 'Crear mi cuenta'
            operation.side_effect = sqlite3.IntegrityError('duplicado ficticio')
            self.h.button(text).invoke()
            self.assertTrue(self.h.has_text('Ya existe'))
            operation.side_effect = None
            with patch.object(self.h, '_show_recovery_code') as show:
                self.h.button(text).invoke()
                show.call_args.args[2]()
            self.assertEqual(self.h._documento_recordado, 'V-12345678')

    def test_recuperacion_administrativa_temporal_y_solo_codigo(self):
        """Respeta versión esperada y cierra sesión si el maestro cambia su propia clave."""
        record = dict(self.h.user)
        for reset in (True, False):
            self.h._admin_recovery_form(record, reset_password=reset)
            self.h.write('Tu contraseña actual de maestro *', 'Prueba#2026')
            if reset:
                self.h.write('Contraseña temporal *', 'TemporalFicticia#2026')
                self.h.button('Guardar y mostrar código').invoke()
                self.assertTrue(self.h.has_text('no coinciden'))
                self.h.write('Confirmar contraseña temporal *', 'TemporalFicticia#2026')
            operation = self.h.services.users.reset_password if reset else self.h.services.recovery.regenerate_code
            operation.side_effect = ValueError('versión ficticia desactualizada')
            self.h.button('Guardar y mostrar código').invoke()
            self.assertTrue(self.h.has_text('desactualizada'))
            operation.side_effect = None
            operation.return_value = 'HMR-FICTICIO'
            with patch.object(self.h, '_show_recovery_code') as show:
                self.h.button('Guardar y mostrar código').invoke()
                show.call_args.args[2]()
            self.assertEqual(operation.call_args.kwargs['expected_version'], 1)
        self.h.show_login.assert_called_once()
        self.h.navigate.assert_called_with(VIEWS[4])

    def test_renovar_codigo_propietario_error_y_exito(self):
        """No muestra un código si la contraseña actual no se acepta."""
        self.h._renovar_codigo_propio()
        self.h.write('Contraseña actual *', 'Prueba#2026')
        self.h.services.recovery.renovar_codigo_propio.side_effect = ValueError('clave ficticia incorrecta')
        self.h.button('Generar y mostrar código').invoke()
        self.assertTrue(self.h.has_text('incorrecta'))
        self.h.services.recovery.renovar_codigo_propio.side_effect = None
        self.h.services.recovery.renovar_codigo_propio.return_value = 'HMR-FICTICIO'
        with patch.object(self.h, '_show_recovery_code') as show:
            self.h.button('Generar y mostrar código').invoke()
            show.assert_called_once_with('HMR-FICTICIO', self.h.user['identity'])

    def test_recuperar_por_codigo_error_limpieza_y_exito(self):
        """Un intento fallido limpia el código; uno válido conserva la versión autenticada."""
        self.h.user = None
        self.h.show_master_recovery()
        self.h.write('Documento *', 'V-12345678')
        self.h.write('Código de recuperación *', 'hmr-ficticio')
        self.assertEqual(self.h.entries['Código de recuperación *'].get(), 'HMR-FICTICIO')
        self.h.services.auth.authenticate_with_code.side_effect = ValueError('código ficticio inválido')
        self.h.button('Recuperar acceso').invoke()
        self.assertEqual(self.h.entries['Código de recuperación *'].get(), '')
        self.h.services.auth.authenticate_with_code.side_effect = None
        self.h.services.auth.authenticate_with_code.return_value = dict(id=1, password_version=2)
        self.h.write('Código de recuperación *', 'hmr-otro')
        self.h.button('Recuperar acceso').invoke()
        self.h.show_shell.assert_called_with(VIEWS[0])

    def test_recuperar_preguntas_exige_cargar_documento_y_limpia_error(self):
        """El método de preguntas no usa respuestas de otro documento."""
        self.h.user = None
        self.h.show_master_recovery()
        self.h.write('Documento *', 'V-12345678')
        self.h.widgets(ctk.CTkTabview)[0].set('Con mis preguntas')
        self.h.button('Recuperar acceso').invoke()
        self.assertTrue(self.h.has_text('Pulsa Mostrar'))
        self.h.services.auth.obtener_preguntas_recuperacion.side_effect = ValueError('cuenta ficticia no encontrada')
        self.h.button('Mostrar mis preguntas').invoke()
        self.assertTrue(self.h.has_text('no encontrada'))
        self.h.services.auth.obtener_preguntas_recuperacion.side_effect = None
        self.h.services.auth.obtener_preguntas_recuperacion.return_value = SECURITY_QUESTIONS[:3]
        self.h.button('Mostrar mis preguntas').invoke()
        self.h.services.auth.autenticar_con_preguntas.side_effect = ValueError('respuestas ficticias incorrectas')
        for index, question in enumerate(SECURITY_QUESTIONS[:3], 1):
            self.h.write(f'{index}. {question}', 'Ficticia')
        self.h.button('Recuperar acceso').invoke()
        self.assertEqual(self.h.entries['1. ' + SECURITY_QUESTIONS[0]].get(), '')
        self.h.services.auth.autenticar_con_preguntas.side_effect = None
        self.h.services.auth.autenticar_con_preguntas.return_value = dict(id=1, password_version=2)
        self.h.button('Recuperar acceso').invoke()
        self.h.show_shell.assert_called_once()

    def test_permisos_impiden_cambio_preguntas_regeneracion_y_admin(self):
        """Los formularios protegidos no se abren si el guardián deniega acceso."""
        self.h._require_access.return_value = False
        self.h._password_form()
        self.h._security_questions_form()
        self.h._admin_password_form(self.h.user)
        self.h._admin_code_form(self.h.user)
        self.h._renovar_codigo_propio()
        self.assertEqual(self.h.dialogs, [])

    def test_formateo_confirmacion_cancelacion_fallo_y_exito(self):
        """No reinicia red ni datos antes de validar texto, confirmación y operación."""
        self.h._formatear_aplicacion()
        self.h.button('Formatear aplicación').invoke()
        self.assertTrue(self.h.has_text('exactamente'))
        self.h.write('Escribe FORMATEAR HEMEROTECA para confirmar', 'FORMATEAR HEMEROTECA')
        self.askyesno.return_value = False
        self.h.button('Formatear aplicación').invoke()
        self.h.services.users.formatear_aplicacion.assert_not_called()
        self.askyesno.return_value = True
        self.h.services.users.formatear_aplicacion.side_effect = ValueError('fallo ficticio')
        self.h.button('Formatear aplicación').invoke()
        self.assertTrue(self.h.has_text('fallo ficticio'))
        self.h.services.users.formatear_aplicacion.side_effect = None
        self.h.services.users.formatear_aplicacion.return_value = 'copia-ficticia.db'
        self.h.button('Formatear aplicación').invoke()
        self.h.services.original.network.reiniciar_tras_formateo.assert_called_once()
        self.h._restart_services.assert_called_once()
