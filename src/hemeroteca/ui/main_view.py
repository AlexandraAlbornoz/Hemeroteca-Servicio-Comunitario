"""Ventana principal y navegación entre las pantallas de la aplicación."""

from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
from hemeroteca.config.settings import BG, BLUE, FONT, GREEN, INK, MUTED, ROLES, SIDEBAR, SOFT, VIEWS, WHITE, REPORT_PERMISSIONS, AMBER, RED
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.ui.tareas import ServiciosDeInterfaz
from hemeroteca.ui.carga import CargaDeVistas
from hemeroteca.config.declaraciones import PAGINAS
from hemeroteca.network.transport import ErrorConexion
from hemeroteca.utils.iconos import aplicar_icono
from hemeroteca.ui.components import UIComponents
from hemeroteca.ui.login_view import LoginView
from hemeroteca.ui.periodicos_view import PeriodicosView
from hemeroteca.ui.requests_view import RequestsView
from hemeroteca.ui.audit_view import AuditView
from hemeroteca.ui.users_view import UsersView
from hemeroteca.ui.deleted_records_view import DeletedRecordsView
from hemeroteca.ui.recovery_view import RecoveryView
from hemeroteca.ui.network_view import NetworkView
from hemeroteca.ui.reports_view import ReportsView
from hemeroteca.ui.backups_view import BackupsView
from hemeroteca.ui.mantenimiento_view import VistaMantenimiento


class AplicacionHemeroteca(
    CargaDeVistas,
    UIComponents,
    LoginView,
    PeriodicosView,
    RequestsView,
    AuditView,
    UsersView,
    DeletedRecordsView,
    RecoveryView,
    NetworkView,
    ReportsView,
    BackupsView,
    VistaMantenimiento,
    ctk.CTk,
):
    """Ventana principal, navegación y vigilancia de la sesión activa."""

    def __init__(self, services):
        """Crea la ventana principal, adapta servicios al hilo gráfico y prepara estado de sesión, recursos y vigilancia periódica."""
        servicios = services
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.title("Hemeroteca · Red de Bibliotecas")
        aplicar_icono(self)
        # Dimensiones lógicas: respeta el escalado de pantalla de Windows.
        disponibles_width = max(640, self._reverse_window_scaling(self.winfo_screenwidth()) - 48)
        disponibles_height = max(480, self._reverse_window_scaling(self.winfo_screenheight()) - 100)
        ancho, alto = min(1440, disponibles_width), min(900, disponibles_height)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(min(900, ancho), min(600, alto))
        self.configure(fg_color=BG)
        self.services = ServiciosDeInterfaz(self, servicios)
        self._network_signature = self._network_state()
        self.user = None
        self.current_view = ""
        self.sidebar_buttons = {}
        self._load_logos()
        self.show_login()
        self._session_watch_job = self.after(5000, self._watch_session)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _red_estado(self):
        """Obtiene modo, dirección y huella de red para detectar cambios que requieren reconstruir los servicios."""
        if not getattr(self.services, 'network', None):
            return None
        configuracion = self.services.network.describe()
        return (configuracion['mode'], configuracion.get('server_url'), configuracion.get('fingerprint'))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _network_state = _red_estado

    def _cerrar(self):
        'Cierra la aplicación cuando no hay una operación de datos pendiente.'
        if getattr(self, '_servicios_ocupados', False):
            return
        self._invalidar_cargas()
        self._cancelar_navegacion_pendiente()
        if self.services._trabajos:
            # No se destruye Tcl mientras un lector puede devolver objetos de Python.
            self.withdraw()
            self.after(25, self._close)
            return
        self.after_cancel(self._session_watch_job)
        self.services.close()
        self.destroy()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _close = _cerrar

    @property
    def activo_nombre(self):
        """Devuelve el nombre del usuario en sesión o texto vacío si no hay sesión."""
        return self.user["name"] if self.user else ""
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    active_name = activo_nombre

    @property
    def perfil(self):
        """Devuelve el rol del usuario en sesión o texto vacío si no hay sesión."""
        return self.user["role"] if self.user else ""
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    role = perfil

    def _limpiar(self):
        'Conserva los filtros y libera los widgets de la pantalla anterior.'
        self._invalidar_cargas()
        self._cancelar_navegacion_pendiente()
        conservar = getattr(self, '_guardar_estado_vista', None)
        if conservar and self.user is not None:
            conservar()
        self._guardar_estado_vista = lambda: None
        pendiente = getattr(self, "_login_bg_resize_job", None)
        if pendiente:
            self.after_cancel(pendiente)
            self._login_bg_resize_job = None
        self._vaciar_contenedor(self)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _clear = _limpiar

    def _puede(self, permission):
        """Consulta permisos vigentes para indicar si el usuario actual puede realizar la operación solicitada."""
        permiso = permission
        return self.user is not None and permiso in self._permisos_actuales()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _can = _puede

    def _exigir_acceso(self, permission=None, *, action=None, master=False, view=False,
                        parent=None, allow_password_change=False):
        """Revalida identidad y autorización, actualiza el usuario de sesión y presenta errores sin ejecutar la acción denegada."""
        permitir_contrasena_cambiar_local = allow_password_change
        accion = action
        permitir_contrasena_cambiar = permitir_contrasena_cambiar_local
        maestro = master
        padre = parent
        permiso = permission
        vista = view
        if getattr(self, '_contexto_construccion', None) is not None:
            return True
        try:
            self.user = self.services.access.require_access(self.user, permiso, action=accion or f"Acceder a {permiso}", master=maestro, view=vista,
                                                          allow_password_change=permitir_contrasena_cambiar)
            return True
        except AccessDenied as excepcion:
            self._access_denied(excepcion, parent=padre)
            return False
        except (ValueError, OSError) as excepcion:
            messagebox.showwarning('No se completó la operación', str(excepcion), parent=padre or self)
            return False
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _require_access = _exigir_acceso

    def _acceso_denegado(self, error, parent=None):
        """Muestra el rechazo de acceso y agenda una sincronización de sesión cuando Tk quede libre."""
        padre = parent
        messagebox.showwarning("Acceso denegado", str(error), parent=padre or self)
        self.after_idle(self._sync_session)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _access_denied = _acceso_denegado

    def informar_error_callback(self, exception_type, error, traceback):
        """Muestra también las denegaciones detectadas por los servicios."""
        excepcion_type_local = exception_type
        traza = traceback
        excepcion_type = excepcion_type_local
        if isinstance(error, AccessDenied):
            self._access_denied(error)
            return
        if isinstance(error, (ValueError, OSError)):
            messagebox.showwarning('No se completó la operación', str(error), parent=self)
            return
        super().report_callback_exception(excepcion_type, error, traza)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    report_callback_exception = informar_error_callback

    def _vigilar_sesion(self):
        'Revisa periódicamente la sesión sin interrumpir una operación pendiente.'
        try:
            if getattr(self, '_servicios_ocupados', False):
                return
            if not getattr(self, '_showing_recovery_code', False) and self._network_state() != self._network_signature:
                self._restart_services()
            self._sync_session()
        except AccessDenied:
            self.show_login()
        except (ValueError, OSError):
            self._notice('Conexión temporalmente no disponible. Se volverá a comprobar la sesión.')
        finally:
            self._session_watch_job = self.after(5000, self._watch_session)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _watch_session = _vigilar_sesion

    def _sincronizar_sesion(self):
        'Sincroniza la cuenta y permisos conservando borradores ante fallos transitorios.'
        if self.user is None or getattr(self, '_showing_recovery_code', False):
            return
        try:
            estado = self.services.access.estado_sesion(self.user)
            actual = estado['usuario']
        except AccessDenied:
            self.show_login()
            return
        except (ValueError, OSError):
            self._notice('Sin conexión con la principal; se conservan los datos de la pantalla.')
            return
        if actual is None or not actual["active"]:
            self.services.audit.record(self.services.access.actor_label(self.user), "Sesión invalidada: cuenta desactivada o retirada", "Acceso denegado")
            self.show_login()
            messagebox.showwarning("Sesión finalizada", "Tu cuenta ya no tiene acceso. Contacta al administrador maestro.", parent=self)
            return
        if actual["password_version"] != self._authenticated_version:
            self.services.audit.record(self.services.access.actor_label(self.user), "Sesión invalidada: datos de acceso o contraseña modificados", "Acceso denegado")
            self.show_login()
            messagebox.showwarning("Sesión finalizada", "Tus datos de acceso o contraseña cambiaron. Vuelve a iniciar sesión.", parent=self)
            return
        self.user = actual
        if estado['requiere_configuracion'] and self._enforce_account_requirements():
            return
        instantanea = (actual["role"], frozenset(estado['permisos']))
        if instantanea != getattr(self, "_session_snapshot", None):
            vista = self.current_view if self.current_view in self._allowed_views() else VIEWS[0]
            # Cada guardado revalida permisos: se conserva el formulario hasta cerrarlo.
            if any(isinstance(hijo, ctk.CTkToplevel) for hijo in self.winfo_children()):
                self._notice('Tus permisos cambiaron. Se actualizará el menú al cerrar el formulario.')
                return
            self.show_shell(vista)
            self._notice("Tus permisos se actualizaron. Vuelve a abrir la acción que necesitas.")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _sync_session = _sincronizar_sesion

    def mostrar_shell(self, first_view=None):
        'Construye la navegación y abre la vista permitida para la sesión.'
        vista_inicial = first_view
        if self._enforce_account_requirements():
            return
        if not self._require_access(action="Abrir sesión de Hemeroteca"):
            return
        self._account_step = None
        self._session_snapshot = (self.role, frozenset(self.services.access.permissions(self.user)))
        self._clear()
        self.configure(fg_color=BG)
        self.grid_columnconfigure(0, weight=0, minsize=260, uniform="")
        self.grid_columnconfigure(1, weight=1, minsize=0, uniform="")
        self.grid_rowconfigure(0, weight=1)
        menu_lateral = ctk.CTkFrame(self, width=260, fg_color=SIDEBAR, corner_radius=0)
        menu_lateral.grid(row=0, column=0, sticky="nsew")
        menu_lateral.grid_propagate(False)
        ctk.CTkLabel(menu_lateral, text="HEMEROTECA", text_color=WHITE, font=(FONT, 20, "bold")).pack(anchor="w", padx=30, pady=(16, 0))
        ctk.CTkLabel(menu_lateral, text="RED DE BIBLIOTECAS", text_color="#D9E3FA", font=(FONT, 11, "bold")).pack(anchor="w", padx=30, pady=(2, 8))
        ctk.CTkFrame(menu_lateral, height=1, fg_color="#5270B4").pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkLabel(menu_lateral, text="MENÚ PRINCIPAL", text_color="#C6D3F0", font=(FONT, 10, "bold")).pack(anchor="w", padx=28, pady=(0, 4))
        navegacion = self._scrollable(menu_lateral, fg_color=SIDEBAR, corner_radius=0, width=240)
        navegacion.pack(fill='both', expand=True, padx=4)
        if self.role == ROLES[0] and getattr(self.services, 'network', None):
            self._button(navegacion, 'Computadoras conectadas', self._network_form, 'secondary', height=38).pack(fill='x', padx=10, pady=(0, 12))
        permitidos = self._allowed_views()
        self.sidebar_buttons = {}
        for vista in VIEWS:
            if vista not in permitidos:
                continue
            boton = ctk.CTkButton(navegacion, text=vista, anchor="w", height=34, corner_radius=8, fg_color="transparent", hover_color="#3558A5", text_color="#E9EEFA", font=(FONT, 12), command=lambda elegida=vista: self.navigate(elegida))
            boton.pack(fill="x", padx=8, pady=2)
            self.sidebar_buttons[vista] = boton
        if self.role == ROLES[0] and not self.services.read_only:
            self._button(menu_lateral, "Formatear aplicación", self._formatear_aplicacion, "danger", height=36).pack(fill="x", padx=18, pady=(8, 0))
        self._button(menu_lateral, "Cambiar mi contraseña", self._password_form, "secondary", height=36).pack(fill="x", padx=18, pady=(8, 0))
        self._button(menu_lateral, "Preguntas de seguridad", self._security_questions_form, "secondary", height=36).pack(fill="x", padx=18, pady=(8, 0))
        acciones_remotas = (self.services.read_only and
                          (bool(self._session_snapshot[1] & {"Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"})
                           or (self.role == ROLES[1] and VIEWS[1] in self._session_snapshot[1])))
        etiqueta_modo = ('Cliente · Acciones autorizadas' if acciones_remotas else
                      'Cliente · Solo consultas' if self.services.read_only else
                      'Servidor LAN' if self.services.network and self.services.network.describe()['mode'] == 'server' else 'Aplicación local')
        ctk.CTkLabel(menu_lateral, text='●  ' + etiqueta_modo, text_color=WHITE, fg_color="#3558A5", corner_radius=8, height=28, font=(FONT, 11, "bold")).pack(fill="x", padx=18, pady=10)
        self.main_area = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(1, weight=1)
        cabecera = ctk.CTkFrame(self.main_area, fg_color=WHITE, corner_radius=0, height=62)
        cabecera.grid(row=0, column=0, sticky="ew")
        cabecera.grid_columnconfigure(0, weight=1)
        self.breadcrumb = ctk.CTkLabel(cabecera, text="Hemeroteca / Consulta", text_color=MUTED, font=(FONT, 13))
        self.breadcrumb.grid(row=0, column=0, sticky="w", padx=30, pady=16)
        derecha = ctk.CTkFrame(cabecera, fg_color="transparent")
        derecha.grid(row=0, column=1, sticky="e", padx=24)
        system_insignia = ctk.CTkLabel(derecha, text="SEGÚN PERMISOS" if acciones_remotas else "SOLO CONSULTAS" if self.services.read_only else "HEMEROTECA", text_color=GREEN, fg_color="#E9F6EF", corner_radius=16, width=120, height=30, font=(FONT, 10, "bold"))
        system_insignia.pack(side="left", padx=(0, 12))
        iniciales = "".join(word[0] for word in self.active_name.split()[:2]).upper()
        avatar = ctk.CTkLabel(derecha, text=iniciales, text_color=BLUE, fg_color=SOFT, corner_radius=18, width=36, height=36, font=(FONT, 11, "bold"))
        avatar.pack(side="left", padx=(0, 8))
        short_nombre = self.active_name if len(self.active_name) <= 24 else self.active_name[:23] + "…"
        ctk.CTkLabel(derecha, text=f"{short_nombre}\n{self.role}", width=145, wraplength=145, justify="left", text_color=INK, font=(FONT, 11)).pack(side="left")
        self._button(derecha, "Cerrar sesión", self.show_login, "secondary", width=110, height=36).pack(side="left", padx=(14, 0))
        def ajustar_header(_event):
            """Oculta la insignia del sistema cuando la cabecera es estrecha y la repone al recuperar espacio."""
            _evento_local = _event
            _evento = _evento_local
            compact = cabecera._reverse_widget_scaling(cabecera.winfo_width()) < 980
            if compact and system_insignia.winfo_manager():
                system_insignia.pack_forget()
            elif not compact and not system_insignia.winfo_manager():
                system_insignia.pack(side="left", before=avatar, padx=(0, 12))
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        ajustar_header_local = ajustar_header
        cabecera.bind("<Configure>", ajustar_header_local)
        self.content = self._scrollable(self.main_area, fg_color=BG, corner_radius=0)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.main_area._destino_rueda = self.content._parent_canvas
        self.navegacion_resultados = ctk.CTkFrame(self.main_area, fg_color=WHITE, corner_radius=0)
        self.navegacion_resultados.grid(row=2, column=0, sticky='ew')
        self.navegacion_resultados.grid_remove()
        pie = ctk.CTkFrame(self.main_area, fg_color=BG, height=48)
        pie.grid(row=3, column=0, sticky="ew")
        pie.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(pie, text="Las acciones autorizadas se guardan en el servidor." if acciones_remotas else "Consultas al servidor de la red local." if self.services.read_only else "Los cambios se guardan en este equipo.", text_color=MUTED, font=(FONT, 11), anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=24)
        fila_logotipos = ctk.CTkFrame(pie, fg_color=BG)
        fila_logotipos.grid(row=0, column=1, sticky="e", padx=18, pady=3)
        for clave in ("gov", "library"):
            if clave in self.footer_logos:
                ctk.CTkLabel(fila_logotipos, text="", image=self.footer_logos[clave], fg_color=BG).pack(side="left", padx=5)
        self.navigate(vista_inicial or "Consulta de periódicos")
        # El estado detallado de las copias se consulta al abrir Respaldos,
        # evitando repetir trabajo en cada reconstrucción del marco principal.
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    show_shell = mostrar_shell

    def _permitidas_vistas(self):
        """Calcula las vistas visibles según rol, permisos y modo local o remoto, incluidas las excepciones de catálogo y PDF."""
        permisos = self.services.access.permissions(self.user) if self.user else set()
        permitidos = set(VIEWS) & permisos
        # El administrador regular ve las acciones bloqueadas antes de solicitarlas.
        if self.role == ROLES[1] or permisos & {"Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"}:
            permitidos.add("Catálogo de periódicos")
        if permisos & REPORT_PERMISSIONS:
            permitidos.add(VIEWS[6])
        if self.services.read_only or self.role != ROLES[0]:
            permitidos.discard(VIEWS[7])
        return permitidos
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _allowed_views = _permitidas_vistas

    def navegar(self, view):
        """Conserva el último destino solicitado mientras termina la operación activa."""
        if getattr(self, '_servicios_ocupados', False) or getattr(self, '_navegando', False):
            self._destino_pendiente = (view, self.user['id'], self.user['password_version']) if self.user else None
            if self._destino_pendiente and getattr(self, '_navegacion_pendiente', None) is None:
                self._navegacion_pendiente = self.after(50, self._reanudar_navegacion)
            return
        self._cancelar_navegacion_pendiente()
        self._navegando = True
        try:
            with self.services.agrupar_interfaz():
                self._construir_vista(view)
        finally:
            self._navegando = False

    def _cancelar_navegacion_pendiente(self):
        """Descarta cambios pendientes al limpiar la sesión o elegir otro destino."""
        pendiente = getattr(self, '_navegacion_pendiente', None)
        if pendiente is not None:
            self.after_cancel(pendiente)
        self._navegacion_pendiente = None
        self._destino_pendiente = None

    def _reanudar_navegacion(self):
        """Espera sin alertas y revalida el acceso cuando la misma sesión puede navegar."""
        self._navegacion_pendiente = None
        destino = getattr(self, '_destino_pendiente', None)
        if not destino:
            return
        vista, usuario, version = destino
        if not self.user or (self.user['id'], self.user['password_version']) != (usuario, version):
            self._destino_pendiente = None
            return
        if getattr(self, '_servicios_ocupados', False) or getattr(self, '_navegando', False):
            self._navegacion_pendiente = self.after(50, self._reanudar_navegacion)
            return
        self._destino_pendiente = None
        self.navigate(vista)

    def _construir_vista(self, view):
        """Pinta el destino, autoriza en segundo plano y construye controles sin consultas."""
        vista = view
        if hasattr(self, '_guardar_estado_vista'):
            self._guardar_estado_vista()
        self._invalidar_cargas()
        self.current_view = vista
        self._guardar_estado_vista = lambda: None
        for clave, boton in self.sidebar_buttons.items():
            boton.configure(fg_color="#3558A5" if clave == vista else "transparent")
        self.breadcrumb.configure(text=f"Hemeroteca / {vista}")
        self._vaciar_contenedor(self.content)
        self.content._parent_canvas.yview_moveto(0)
        tarjeta = self._card(0)
        self._label(tarjeta, vista).pack(anchor='w', padx=20, pady=12)
        permiso = None if vista == VIEWS[1] and self.role == ROLES[1] else vista
        consultas = [self.services.consulta('access', 'require_access', self.user,
                        permiso, action=f'Abrir vista: {vista}', view=True),
                     self.services.consulta('access', 'permissions', self.user)]
        def construir(datos):
            """Usa la autorización vigente solo para dibujar; los servicios validan cada acción."""
            self.user, permisos = datos
            self._contexto_construccion = set(permisos)
            self._navegando = True
            try:
                self._vaciar_contenedor(self.content)
                with self.services.agrupar_interfaz():
                    getattr(self, PAGINAS[vista])()
            finally:
                self._contexto_construccion = None
                self._navegando = False
        self._cargar_seccion(tarjeta, consultas, construir)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    navigate = navegar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
HemerotecaApp = AplicacionHemeroteca
