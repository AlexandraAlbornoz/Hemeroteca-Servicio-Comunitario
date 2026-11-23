"""Contenedor de pantallas reales con fronteras de servicios y navegación controladas."""
from types import SimpleNamespace
from unittest.mock import Mock
import customtkinter as ctk

from tests.test_interfaz_respaldos import VentanaRespaldos
from hemeroteca.ui.recovery_view import RecoveryView
from hemeroteca.ui.network_view import NetworkView
from hemeroteca.ui.users_view import UsersView
from hemeroteca.ui.reports_view import ReportsView
from hemeroteca.ui.mantenimiento_view import VistaMantenimiento
from hemeroteca.config.settings import ROLES, VIEWS


class VentanaGeneral(RecoveryView, NetworkView, UsersView, ReportsView, VistaMantenimiento, VentanaRespaldos):
    """Reutiliza las fábricas gráficas del producto; solo aísla servicios y shell."""

    def __init__(self):
        """Prepara respuestas mínimas válidas y un usuario ficticio."""
        super().__init__(Mock())
        self.user = dict(id=1, name='Persona Ficticia', identity='V-12345678', document='V-12345678',
                         role=ROLES[0], password_version=1, must_change_password=False, active=True, managed_permissions=1)
        self.combos = {}
        for name in ('auth', 'recovery', 'users', 'reports', 'network', 'access'):
            setattr(self.services, name, Mock())
        self.services.original = SimpleNamespace(network=self.services.network)
        self.services.consulta = lambda group, method, actor, **kwargs: lambda: getattr(getattr(self.services, group), method)(actor, **kwargs)
        self.services.recovery.configured_questions.return_value = ()
        self.services.recovery.needs_configuration.return_value = False
        self.services.recovery.needs_code.return_value = False
        self.services.network.describe.return_value = dict(mode='local', node_id='nodo-ficticio', server_url='', fingerprint='')
        self.services.network.approved_computers.return_value = []
        self.services.network.discover_computers.return_value = []
        self.services.access.node_id = None
        self._can = Mock(return_value=True)
        self._notice = Mock()
        self.show_shell = Mock()
        self._sync_session = Mock()
        self._network_state = Mock(return_value=('local', '', ''))
        self._restart_services = Mock()
        self._access_denied = Mock()
        self._guardar_estado_vista = Mock()
        self._registrar_estado_vista = Mock()
        self._account_step = None
        self._authenticated_version = 1
        self.clipboard_clear = Mock()
        self.clipboard_append = Mock()

    @property
    def role(self):
        """Resuelve el perfil desde el actor ficticio actual."""
        return self.user['role'] if self.user else ''

    def _combo(self, parent, label, *args, **kwargs):
        """Conserva selectores auténticos para cambiar filtros y roles en la prueba."""
        wrapper, combo = super()._combo(parent, label, *args, **kwargs)
        self.combos[label] = combo
        return wrapper, combo

    def _document_entry(self, parent, label):
        """Conserva el selector de documento real con su validación propia."""
        wrapper, entry = super()._document_entry(parent, label)
        self.entries[label] = entry
        return wrapper, entry

    def _clear(self):
        """Retira la pantalla anterior antes de construir un paso obligatorio."""
        for child in list(self.winfo_children()):
            child.destroy()

    def close_for_test(self):
        """Cancela eventos sin borrar comandos de otros widgets antes de su dueño."""
        # ttk difiere ThemeChanged hasta reposo; hay que entregarlo antes de
        # destruir su intérprete para que no alcance la siguiente raíz de prueba.
        self.update_idletasks()
        for task in self.tk.splitlist(self.tk.call('after', 'info')):
            self.tk.call('after', 'cancel', task)
        self.destroy()
        if self.callback_errors:
            raise AssertionError(self.callback_errors)

    def text_checkbox(self, fragment):
        """Busca una casilla visible por su texto, sin acceder a variables privadas."""
        return next(widget for widget in self.widgets(ctk.CTkCheckBox) if fragment in widget.cget('text'))
