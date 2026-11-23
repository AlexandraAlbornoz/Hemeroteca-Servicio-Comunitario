"""Controles reales de respaldos: formularios, confirmaciones, selección y errores."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

import customtkinter as ctk
from hemeroteca.ui.backups_view import BackupsView
from hemeroteca.ui.components import UIComponents
from hemeroteca.services.backup_service import BackupService
from hemeroteca.services.container import create_services
from hemeroteca.config.settings import SECURITY_QUESTIONS, NATIONAL, VIEWS


class VentanaRespaldos(BackupsView, UIComponents, ctk.CTk):
    """Contenedor gráfico real con lecturas síncronas para aislar callbacks de la vista."""

    def __init__(self, backups):
        """Conserva botones, entradas y diálogos reales para operar sus comandos públicos."""
        super().__init__()
        self.geometry('900x650')
        self.content = ctk.CTkFrame(self)
        self.content.pack(fill='both', expand=True)
        self.content.grid_columnconfigure(0, weight=1)
        self.user = {'id': 1, 'password_version': 0}
        self.current_view = VIEWS[7]
        self.services = SimpleNamespace(backups=backups, read_only=False)
        self.services.consulta = lambda group, method, actor: lambda: getattr(backups, method)(actor)
        self._require_access = Mock(return_value=True)
        self.navigate = Mock()
        self.show_login = Mock()
        self.buttons, self.entries, self.dialogs, self.paragraphs = [], {}, [], []
        self.callback_errors = []
        self.report_callback_exception = lambda kind, error, trace: self.callback_errors.append(error)

    def _button(self, *args, **kwargs):
        """Construye un botón auténtico y lo conserva para invocarlo en la prueba."""
        result = super()._button(*args, **kwargs)
        self.buttons.append(result)
        return result

    def _entry(self, parent, label, *args, **kwargs):
        """Conserva entradas reales identificadas por la etiqueta que ve el usuario."""
        wrapper, entry = super()._entry(parent, label, *args, **kwargs)
        self.entries[label] = entry
        return wrapper, entry

    def _dialog(self, *args, **kwargs):
        """Usa el diálogo modal compartido sin sustituir sus controles."""
        result = super()._dialog(*args, **kwargs)
        self.dialogs.append(result)
        return result

    def _paragraph(self, *args, **kwargs):
        """Registra etiquetas reales cuyo texto puede cambiar por validaciones."""
        result = super()._paragraph(*args, **kwargs)
        self.paragraphs.append(result)
        return result

    def _cargar_seccion(self, parent, queries, present, **kwargs):
        """Simula solo la frontera de carga asíncrona; la presentación sigue siendo real."""
        present([query() for query in queries])

    def button(self, text):
        """Devuelve un único botón vivo por su texto visible."""
        matches = [button for button in self.buttons if button.winfo_exists() and button.cget('text') == text]
        if len(matches) != 1:
            raise AssertionError(f'Botón no único: {text}')
        return matches[0]

    def write(self, label, text):
        """Edita un campo del formulario por su interfaz de entrada."""
        entry = self.entries[label]
        entry.delete(0, 'end')
        entry.insert(0, text)

    def widgets(self, kind, parent=None):
        """Recorre controles reales incluidos los marcos desplazables."""
        result = []
        for child in (self if parent is None else parent).winfo_children():
            if isinstance(child, kind):
                result.append(child)
            result.extend(self.widgets(kind, child))
        return result

    def has_text(self, fragment):
        """Busca mensajes visibles de validación sin acceder a variables de cierres."""
        return any(label.winfo_exists() and fragment in label.cget('text') for label in self.paragraphs)


class PruebasInterfazRespaldos(unittest.TestCase):
    """Simula servicios y selectores del sistema, nunca los widgets ni sus callbacks."""

    def setUp(self):
        """Prepara la vista, respuestas de servicio y mensajes no bloqueantes."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root_path = Path(self.temp.name)
        self.backups = Mock(spec=BackupService)
        self.backups.status.return_value = {'enabled': False, 'default_directory': str(self.root_path)}
        self.backups.list_backups.return_value = []
        self.backups.configure.return_value = {}
        self.backups.preview.return_value = {'created_at': '2026-11-16', 'counts': dict(issues=1, users=1, absent_dates=0, audit=2),
                                            'master_document': 'V-12345678', 'archive_sha256': 'a' * 64}
        self.backups.restore.return_value = {'before': str(self.root_path / 'previa.hmbackup'), 'warning': ''}
        self.host = VentanaRespaldos(self.backups)
        self.addCleanup(self.close_window)
        for name in ('showerror', 'showinfo', 'showwarning'):
            mocked = patch('hemeroteca.ui.backups_view.messagebox.' + name).start()
            setattr(self, name, mocked)
        self.addCleanup(patch.stopall)

    def close_window(self):
        """Cancela temporizadores de Tk y destruye únicamente la ventana de la prueba."""
        errors = list(self.host.callback_errors)
        for task in self.host.tk.splitlist(self.host.tk.call('after', 'info')):
            # Cancelar el evento sin borrar aquí comandos Tcl pertenecientes a
            # otros widgets: cada dueño los retira durante su propio destroy.
            self.host.tk.call('after', 'cancel', task)
        self.host.destroy()
        self.assertEqual(errors, [])

    def open_restore(self):
        """Abre el diálogo real con una ruta de archivo ficticio seleccionada."""
        with patch('hemeroteca.ui.backups_view.filedialog.askopenfilename', return_value=str(self.root_path / 'copia.hmbackup')):
            self.host._restore_backup_form()
        self.host.write('Clave con la que se creó este respaldo', 'RespaldoFicticio#2026')

    def review(self):
        """Invoca la revisión exactamente como el botón de la interfaz."""
        self.host.button('Revisar respaldo sin cambiar los datos').invoke()

    def test_permisos_y_cliente_impiden_abrir_cualquier_formulario(self):
        """Los accesos denegados no construyen controles ni consultan respaldos."""
        for denied, read_only in ((True, False), (False, True)):
            self.host._require_access.return_value = not denied
            self.host.services.read_only = read_only
            self.host._backups_page()
            self.host._backup_configuration_form()
            self.host._restore_backup_form()
            self.host._backup_master_action('Crear copia', self.backups.create_now)
        self.assertEqual(self.host.dialogs, [])
        self.backups.status.assert_not_called()

    def test_pagina_sin_configuracion_y_estados_habilitados(self):
        """La presentación distingue configuración ausente y errores de programación."""
        self.host._backups_page()
        self.assertEqual(self.host.button('Crear respaldo ahora').cget('state'), 'disabled')
        self.assertTrue(self.host.has_text('Todavía') or self.host.has_text('Configura una carpeta'))
        for widget in self.host.content.winfo_children():
            widget.destroy()
        self.backups.status.return_value = {'enabled': True, 'time': '18:00', 'directory': str(self.root_path),
                                           'scheduler': 'app', 'last_error': 'Error de copia', 'scheduler_error': 'Tarea pendiente'}
        self.host._backups_page()
        self.assertEqual(self.host.button('Reintentar programación de Windows').cget('state'), 'normal')
        self.assertTrue(self.host.has_text('Error de copia\nTarea pendiente'))
        self.assertTrue(self.host.has_text('mientras Hemeroteca esté abierta'))

    def test_exportar_seleccion_cancelacion_error_y_exito(self):
        """La selección real de tabla determina el archivo, nunca una ruta arbitraria."""
        source = str(self.root_path / 'copia.hmbackup')
        self.backups.status.return_value = {'enabled': True, 'time': '18:00', 'directory': str(self.root_path),
                                           'scheduler': 'windows', 'last_success': '2026-11-16'}
        self.backups.list_backups.return_value = [dict(path=source, name='copia.hmbackup', modified=1, size=1024)]
        self.host._backups_page()
        self.assertTrue(self.host.has_text('aunque Hemeroteca esté cerrada'))
        button = self.host.button('Guardar en USB u otra carpeta')
        self.assertEqual(button.cget('state'), 'disabled')
        tree = self.host.widgets(ttk.Treeview)[0]
        tree.selection_set('0')
        tree.event_generate('<<TreeviewSelect>>')
        self.host.update()
        self.assertEqual(button.cget('state'), 'normal')
        with patch('hemeroteca.ui.backups_view.filedialog.asksaveasfilename', return_value=''):
            button.invoke()
        self.backups.export.assert_not_called()
        target = str(self.root_path / 'destino.hmbackup')
        with patch('hemeroteca.ui.backups_view.filedialog.asksaveasfilename', return_value=target):
            self.backups.export.side_effect = OSError('sin espacio ficticio')
            button.invoke()
            self.showerror.assert_called_once()
            self.backups.export.side_effect = None
            button.invoke()
        self.backups.export.assert_called_with(self.host.user, source, target)
        self.showinfo.assert_called_once()
        tree.selection_remove('0')
        tree.event_generate('<<TreeviewSelect>>')
        self.host.update()
        self.assertEqual(button.cget('state'), 'disabled')

    def test_accion_maestra_error_reintento_y_exito(self):
        """Un error mantiene abierto el diálogo; un éxito refresca la vista y muestra la ruta."""
        action = Mock(side_effect=ValueError('credenciales ficticias rechazadas'))
        self.host._backup_master_action('Crear copia', action)
        self.host.write('Tu contraseña de maestro', 'Prueba#2026')
        self.host.button('Confirmar').invoke()
        self.assertTrue(self.host.dialogs[-1].winfo_exists())
        self.host.navigate.assert_not_called()
        action.side_effect = None
        action.return_value = str(self.root_path / 'nueva.hmbackup')
        self.host.button('Confirmar').invoke()
        self.host.navigate.assert_called_with(VIEWS[7])
        self.showinfo.assert_called_once()

    def test_accion_sin_ruta_no_anuncia_copia_creada(self):
        """Desactivar o reprogramar no se presenta erróneamente como archivo creado."""
        self.host._backup_master_action('Desactivar', Mock(return_value=None))
        self.host.button('Confirmar').invoke()
        self.host.navigate.assert_called_once()
        self.showinfo.assert_not_called()

    def test_configuracion_valida_campos_reintenta_y_muestra_advertencia(self):
        """La confirmación de custodia y las claves iguales son requisitos previos al servicio."""
        self.host._backup_configuration_form()
        dialog = self.host.dialogs[-1]
        self.host.write('Clave para abrir los respaldos *', 'RespaldoFicticio#2026')
        self.host.write('Repetir la clave del respaldo *', 'DistintaFicticia#2026')
        self.host.button('Activar y crear primera copia').invoke()
        self.assertTrue(self.host.has_text('no coinciden'))
        self.host.write('Repetir la clave del respaldo *', 'RespaldoFicticio#2026')
        self.host.button('Activar y crear primera copia').invoke()
        self.assertTrue(self.host.has_text('marca la confirmación'))
        self.backups.configure.assert_not_called()
        self.host.widgets(ctk.CTkCheckBox, dialog)[0].select()
        self.host.write('Tu contraseña actual de maestro *', 'Prueba#2026')
        with patch('hemeroteca.ui.backups_view.filedialog.askdirectory', return_value=''):
            self.host.button('Elegir carpeta').invoke()
        chosen = str(self.root_path / 'elegida')
        with patch('hemeroteca.ui.backups_view.filedialog.askdirectory', return_value=chosen):
            self.host.button('Elegir carpeta').invoke()
        self.assertEqual(self.host.entries['Carpeta donde se guardarán las copias'].get(), chosen)
        self.backups.configure.side_effect = ValueError('error ficticio del servicio')
        self.host.button('Activar y crear primera copia').invoke()
        self.assertTrue(self.host.has_text('error ficticio del servicio'))
        self.assertTrue(dialog.winfo_exists())
        self.backups.configure.side_effect = None
        self.backups.configure.return_value = {'scheduler_error': 'Se usará la aplicación'}
        self.host.button('Activar y crear primera copia').invoke()
        self.assertFalse(dialog.winfo_exists())
        self.assertIn('Se usará la aplicación', self.showinfo.call_args.args[1])
        self.backups.configure.assert_called_with(self.host.user, 'Prueba#2026', 'RespaldoFicticio#2026', chosen, '18:00')

    def test_cancelar_selector_de_archivo_no_abre_restauracion(self):
        """Cancelar el selector no modifica datos ni crea un diálogo modal."""
        with patch('hemeroteca.ui.backups_view.filedialog.askopenfilename', return_value=''):
            self.host._restore_backup_form()
        self.assertEqual(self.host.dialogs, [])
        self.backups.preview.assert_not_called()

    def test_revision_fallida_no_habilita_restaurar(self):
        """Una clave o archivo inválidos no crean la confirmación destructiva."""
        self.open_restore()
        self.backups.preview.side_effect = ValueError('archivo ficticio inválido')
        self.review()
        self.showerror.assert_called_once()
        self.assertFalse(any(button.winfo_exists() and button.cget('text') == 'Restaurar y cerrar las sesiones' for button in self.host.buttons))
        self.backups.restore.assert_not_called()

    def test_restauracion_exige_texto_clave_revisada_y_exito_cierra_sesiones(self):
        """No restaura con confirmación ausente o una clave cambiada después de revisar."""
        self.open_restore()
        self.review()
        self.host.button('Restaurar y cerrar las sesiones').invoke()
        self.showwarning.assert_called_once()
        self.host.write('Escribe RESTAURAR para continuar', 'RESTAURAR')
        self.host.write('Clave con la que se creó este respaldo', 'OtraFicticia#2026')
        self.host.button('Restaurar y cerrar las sesiones').invoke()
        self.assertEqual(self.showwarning.call_count, 2)
        self.backups.restore.assert_not_called()
        self.host.write('Clave con la que se creó este respaldo', 'RespaldoFicticio#2026')
        self.host.write('Tu contraseña de maestro actual', 'Prueba#2026')
        self.backups.restore.side_effect = OSError('fallo ficticio de escritura')
        self.host.button('Restaurar y cerrar las sesiones').invoke()
        self.host.show_login.assert_not_called()
        self.backups.restore.side_effect = None
        self.backups.restore.return_value['warning'] = 'Revisar la programación diaria'
        self.host.button('Restaurar y cerrar las sesiones').invoke()
        self.host.show_login.assert_called_once()
        self.assertIn('Revisar la programación diaria', self.showinfo.call_args.args[1])
        self.backups.restore.assert_called_with(self.host.user, str(self.root_path / 'copia.hmbackup'),
                                               'RespaldoFicticio#2026', 'Prueba#2026', 'a' * 64)

    def test_formulario_completo_con_servicio_sqlite_y_cifrado_reales(self):
        """Configura, revisa y restaura un archivo real a través de los botones del formulario."""
        services = create_services(self.root_path / 'hemeroteca.db')
        self.addCleanup(services.close)
        questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        services.auth.create_master('Persona Ficticia', 'V-12345678', 'Prueba#2026', questions)
        self.host.user = services.auth.authenticate('V-12345678', 'Prueba#2026')
        self.host.services.backups = services.backups
        self.host._backup_configuration_form()
        for label in ('Clave para abrir los respaldos *', 'Repetir la clave del respaldo *'):
            self.host.write(label, 'RespaldoFicticio#2026')
        self.host.write('Tu contraseña actual de maestro *', 'Prueba#2026')
        self.host.widgets(ctk.CTkCheckBox, self.host.dialogs[-1])[0].select()
        with patch.object(services.backups, '_schedule_windows'):
            self.host.button('Activar y crear primera copia').invoke()
        status = services.backups.status(self.host.user)
        archive = Path(status['directory']) / status['last_file']
        self.assertTrue(archive.is_file())
        services.periodicos.save_record(self.host.user, (NATIONAL[0], 'Nacional', 'Matutina', 2020, 1, 1, '1', '1', '', 'Disponible'))
        with patch('hemeroteca.ui.backups_view.filedialog.askopenfilename', return_value=str(archive)):
            self.host._restore_backup_form()
        self.host.write('Clave con la que se creó este respaldo', 'RespaldoFicticio#2026')
        self.review()
        self.host.write('Tu contraseña de maestro actual', 'Prueba#2026')
        self.host.write('Escribe RESTAURAR para continuar', 'RESTAURAR')
        self.host.button('Restaurar y cerrar las sesiones').invoke()
        self.host.show_login.assert_called_once()
        self.assertEqual(services.connection.execute('SELECT count(*) FROM issues').fetchone()[0], 0)
        self.assertEqual(services.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.showerror.assert_not_called()
