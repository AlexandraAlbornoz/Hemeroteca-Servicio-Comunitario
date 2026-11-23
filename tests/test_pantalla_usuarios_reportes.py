"""Administración de usuarios y descarga PDF con formularios y trabajadores reales."""
import base64
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import sqlite3
import customtkinter as ctk

from tests.soporte_pantallas import VentanaGeneral
from hemeroteca.config.settings import ROLES, VIEWS, REPORT_ISSUES_PERMISSION
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.ui import reports_view


class PruebasUsuariosYReportes(unittest.TestCase):
    """Aísla servicios, selectores y mensajes; conserva controles y ejecución de callbacks."""

    def setUp(self):
        """Prepara una cuenta objetivo y un directorio de salida ficticios."""
        self.h = VentanaGeneral()
        self.addCleanup(self.h.close_for_test)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = dict(self.h.user, id=2, role=ROLES[1], name='Otra Persona', identity='V-12345679', document='V-12345679')
        self.h.services.users.grants.return_value = []
        self.h.services.users.get_user.return_value = self.record
        for name in ('showwarning', 'showinfo', 'showerror', 'askyesno'):
            setattr(self, name, patch('hemeroteca.ui.users_view.messagebox.' + name, return_value=True).start())
        self.addCleanup(patch.stopall)

    def test_crear_cuenta_campos_error_duplicado_permiso_y_exito(self):
        """No crea cuentas incompletas y conserva la versión/identidad que muestra al terminar."""
        self.h._admin_user_form()
        self.h.button('Crear cuenta').invoke()
        self.assertTrue(self.h.has_text('obligatorios'))
        self.h.write('Nombre completo *', 'Persona Ficticia')
        self.h.write('Documento de identidad *', 'V-12345679')
        self.h.write('Contraseña temporal *', 'Prueba#2026')
        for error in (AccessDenied('sin permiso ficticio'), ValueError('datos ficticios inválidos'), sqlite3.IntegrityError('duplicada ficticia')):
            self.h.services.users.create_user.side_effect = error
            self.h.button('Crear cuenta').invoke()
            self.assertTrue(self.h.dialogs[-1].winfo_exists())
        self.h.services.users.create_user.side_effect = None
        self.h.services.users.create_user.return_value = SimpleNamespace(recovery_code='HMR-FICTICIO')
        with patch.object(self.h, '_show_recovery_code') as show:
            self.h.button('Crear cuenta').invoke()
            show.assert_called_once_with('HMR-FICTICIO', 'V-12345679')
        self.h.navigate.assert_called_with(VIEWS[4])

    def test_editar_cuenta_propia_actualiza_actor_y_version(self):
        """La edición del maestro mantiene el rol y reconstruye la sesión actualizada."""
        record = dict(self.h.user)
        self.h._admin_user_form(record)
        self.h.write('Tu contraseña actual de maestro *', 'Prueba#2026')
        self.h.services.users.update_user.return_value = dict(record, password_version=2)
        self.h.button('Guardar cambios').invoke()
        self.assertEqual(self.h.user['password_version'], 2)
        self.assertEqual(self.h.services.users.update_user.call_args.kwargs['expected_version'], 1)
        self.h.show_shell.assert_called_with(VIEWS[4])

    def test_eliminar_usuario_exige_clave_confirmacion_y_reintento(self):
        """No borra por pulsación accidental ni cierra el formulario tras un error."""
        self.h._delete_user_form(self.record)
        self.h.button('Eliminar usuario').invoke()
        self.assertTrue(self.h.has_text('Introduce tu contraseña'))
        self.h.write('Tu contraseña actual de maestro *', 'Prueba#2026')
        self.askyesno.return_value = False
        self.h.button('Eliminar usuario').invoke()
        self.h.services.users.delete_user.assert_not_called()
        self.askyesno.return_value = True
        self.h.services.users.delete_user.side_effect = AccessDenied('cuenta ficticia cambió')
        self.h.button('Eliminar usuario').invoke()
        self.assertTrue(self.h.has_text('cambió'))
        self.h.services.users.delete_user.side_effect = None
        self.h.button('Eliminar usuario').invoke()
        self.h.navigate.assert_called_once_with(VIEWS[4])

    def test_permisos_pdf_y_detalle_con_revocacion_y_estado(self):
        """Una revocación necesita confirmación, sesión vigente y versión esperada."""
        self.h.services.users.grants.return_value = [{'permission': REPORT_ISSUES_PERMISSION}]
        self.h._pdf_permissions_form(self.record)
        self.h.services.users.set_report_permissions.side_effect = ValueError('permisos ficticios inválidos')
        self.h.button('Guardar permisos PDF').invoke()
        self.showerror.assert_called_once()
        self.h.services.users.set_report_permissions.side_effect = None
        self.h.button('Guardar permisos PDF').invoke()
        self.h._user_detail(self.record)
        self.askyesno.return_value = False
        self.h.button('Revocar').invoke()
        self.h.services.users.revoke_grant.assert_not_called()
        self.askyesno.return_value = True
        for error in (AccessDenied('sin permiso ficticio'), ValueError('cuenta ficticia cambió')):
            self.h.services.users.revoke_grant.side_effect = error
            self.h.button('Revocar').invoke()
        self.h.services.users.revoke_grant.side_effect = None
        self.h.button('Revocar').invoke()
        self.assertEqual(self.h.services.users.revoke_grant.call_args.kwargs['expected_version'], 1)
        self.h._user_detail(self.record)
        for error in (AccessDenied('sin permiso ficticio'), ValueError('versión ficticia cambió')):
            self.h.services.users.set_user_active.side_effect = error
            self.h.button('Desactivar cuenta').invoke()
        self.h.services.users.set_user_active.side_effect = None
        self.h.button('Desactivar cuenta').invoke()
        self.assertFalse(self.h.services.users.set_user_active.call_args.args[2])

    def test_detalle_cuenta_ausente_maestra_y_lectura_sin_acciones(self):
        """No expone acciones de escritura a un usuario de consulta."""
        self.h._user_detail(None)
        self.h.services.users.get_user.return_value = None
        self.h._user_detail(self.record)
        self.assertEqual(self.h.dialogs, [])
        self.h.services.users.get_user.return_value = dict(self.h.user)
        self.h._user_detail(self.h.user)
        self.assertTrue(self.h.has_text('no tiene permisos adicionales'))
        self.h.dialogs[-1].destroy()
        self.h.services.users.get_user.return_value = dict(self.record, managed_permissions=0)
        self.h.services.read_only = True
        self.h._user_detail(self.record)
        self.assertFalse(any(button.winfo_exists() and button.cget('text') == 'Eliminar usuario' for button in self.h.buttons))

    def test_detalle_enlaza_edicion_permisos_y_recuperacion(self):
        """Cada botón conserva la cuenta que se consultó, no una selección posterior."""
        for text, method in [('Actualizar datos', '_admin_user_form'), ('Regenerar código de recuperación', '_admin_code_form'),
                             ('Restablecer contraseña', '_admin_password_form'), ('Eliminar usuario', '_delete_user_form'),
                             ('Configurar permisos de reportes PDF', '_pdf_permissions_form')]:
            self.h._user_detail(self.record)
            with patch.object(self.h, method) as action:
                self.h.button(text).invoke()
                action.assert_called_once_with(self.record)

    def test_guardas_de_usuarios_y_pdf(self):
        """Los formularios denegados no se construyen ni ejecutan servicios."""
        self.h._require_access.return_value = False
        self.h._admin_user_form()
        self.h._pdf_permissions_form(self.record)
        self.h._user_detail(self.record)
        self.h._delete_user_form(self.record)
        self.h._users_page()
        self.h._reports_page()
        self.h._export_pdf()
        self.assertEqual(self.h.dialogs, [])

    def test_pagina_reportes_filtros_y_documento_general(self):
        """Convierte selectores en valores del servicio y distingue permisos por tipo de reporte."""
        self.h._reports_page()
        with patch.object(self.h, '_export_pdf') as export:
            self.h.button('Guardar PDF de ejemplares').invoke()
            self.assertIsNone(export.call_args.kwargs['filters']['year'])
            self.h.combos['Año de publicación'].set('2020')
            self.h.combos['Mes de publicación'].set('Enero')
            self.h.combos['Día de publicación'].set('1')
            self.h.button('Guardar PDF de ejemplares').invoke()
            self.assertEqual(export.call_args.kwargs['filters']['month'], 1)
            self.h.button('Guardar PDF general').invoke()
            export.assert_called_with(scope='database')

    def run_pdf(self, result, *, error=None, change_session=False, cancel=False, suffix='.pdf'):
        """Conserva un trabajador real y entrega su resultado al callback real de Tk."""
        threads = []
        real_thread = threading.Thread
        def start_thread(**kwargs):
            """Registra el trabajador sin sustituir su ejecución."""
            thread = real_thread(**kwargs)
            threads.append(thread)
            return thread
        temporary = SimpleNamespace(reports=Mock(), close=Mock())
        temporary.reports.generate.side_effect = error
        temporary.reports.generate.return_value = result
        target = self.root / ('salida' + suffix)
        with patch.object(reports_view, 'threading', SimpleNamespace(Thread=start_thread)), patch('hemeroteca.services.container.create_services', return_value=temporary), patch.object(reports_view.filedialog, 'asksaveasfilename', return_value=str(target)):
            self.h._export_pdf()
            threads[0].join(timeout=3)
            self.assertFalse(threads[0].is_alive())
            temporary.close.assert_called_once()
            if change_session:
                self.h.user = None
            if cancel:
                self.h.button('Cancelar descarga').invoke()
            for task in self.h.tk.splitlist(self.h.tk.call('after', 'info')):
                script, kind = self.h.tk.splitlist(self.h.tk.call('after', 'info', task))
                if str(script).endswith('recibir'):
                    self.h.tk.call('after', 'cancel', task)
                    self.h.tk.call(script)
                    break
            else:
                self.fail('No se programó recepción del reporte')
        return target

    def test_pdf_trabajador_real_guarda_bytes_y_revalida_sesion(self):
        """La entrega válida conserva los bytes y una sesión cambiada cancela la escritura."""
        data = b'%PDF-1.4\ncontenido ficticio'
        result = {'content': base64.b64encode(data).decode(), 'records': 2}
        target = self.run_pdf(result)
        self.assertEqual(target.read_bytes(), data)
        target.unlink()
        self.assertFalse(self.run_pdf(result, change_session=True).exists())
        self.showwarning.assert_called_once()

    def test_pdf_error_servidor_archivo_invalido_y_cancelacion(self):
        """Errores y cancelación no guardan contenido recibido fuera de contrato."""
        self.assertFalse(self.run_pdf({}, error=ValueError('fallo ficticio del servidor')).exists())
        self.assertFalse(self.run_pdf({'content': '***', 'records': 0}).exists())
        self.assertFalse(self.run_pdf({'content': base64.b64encode(b'no PDF').decode(), 'records': 0}).exists())
        self.assertFalse(self.run_pdf({'content': base64.b64encode(b'%PDF-ficticio').decode(), 'records': 1}, suffix='.txt').exists())
        self.assertFalse(self.run_pdf({'content': base64.b64encode(b'%PDF-ficticio').decode(), 'records': 1}, cancel=True).exists())

    def test_cancelar_selector_pdf_no_crea_trabajador(self):
        """Cancelar antes de generar no consulta la base ni crea un hilo."""
        with patch.object(reports_view.filedialog, 'asksaveasfilename', return_value=''), patch.object(reports_view.threading, 'Thread') as thread:
            self.h._export_pdf()
        thread.assert_not_called()
