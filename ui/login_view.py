"""Inicio de sesión, registro y configuración del administrador."""

from __future__ import annotations
import logging
import sqlite3
import tkinter as tk
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image, ImageOps, ImageTk
from config.settings import ASSETS, BG, BLUE, FONT, INK, MUTED, ROLES, WHITE
from services.access_service import AccessDenied
from utils.identity import DOCUMENT_HELP, normalize_document
from utils.security import validate_password
from utils.validaciones import validar_nombre, validar_documento_nuevo


class VistaAcceso:
    """Inicio de sesión, registro y configuración del administrador.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _cargar_logotipos(self):
        """Carga imágenes institucionales y conserva versiones adaptadas al ingreso y al pie sin distorsionar sus proporciones."""
        self.logo_images = {}
        self.login_logo_sources = {}
        self.footer_logos = {}
        for clave, filename, entrada_size, footer_size in [
            ("gov", "gobernacion.png", (64, 64), (76, 42)),
            ("library", "biblioteca.png", (96, 64), (96, 42)),
        ]:
            ruta = ASSETS / filename
            if ruta.exists():
                try:
                    with Image.open(ruta) as original:
                        origen = original.convert("RGBA")
                    self.login_logo_sources[clave] = origen
                    # Ajusta cada logo al marco máximo sin cambiar su proporción.
                    ratio = origen.width / origen.height
                    max_width, max_height = entrada_size
                    ancho = min(max_width, int(max_height * ratio))
                    alto = min(max_height, int(max_width / ratio))
                    self.logo_images[clave] = ctk.CTkImage(origen, size=(ancho, alto))
                    pie = ImageOps.contain(origen, footer_size)
                    self.footer_logos[clave] = ctk.CTkImage(origen, size=pie.size)
                except (OSError, ValueError):
                    logging.getLogger(__name__).warning("No se pudo cargar el logo %s", ruta, exc_info=True)
        fondo_path = ASSETS / "fondo_biblioteca.png"
        self.login_background_source = None
        if fondo_path.exists():
            try:
                with Image.open(fondo_path) as original:
                    self.login_background_source = original.convert("RGB")
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("No se pudo cargar el fondo %s", fondo_path, exc_info=True)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _load_logos = _cargar_logotipos

    def _redimensionar_entrada_fondo(self, event):
        """Recorta la foto al panel izquierdo si el tamaño de ventana cambia."""
        if event.width < 2 or event.height < 2:
            return
        pendiente = getattr(self, "_login_bg_resize_job", None)
        if pendiente:
            self.after_cancel(pendiente)
        self._login_bg_resize_job = self.after(70, lambda: self._apply_login_background(event.widget))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _resize_login_background = _redimensionar_entrada_fondo

    def _aplicar_entrada_fondo(self, promo):
        """Redimensiona el fondo al panel visible y reconstruye sus elementos gráficos conservando referencias a las imágenes."""
        self._login_bg_resize_job = None
        if not promo.winfo_exists():
            return
        ancho, alto = promo.winfo_width(), promo.winfo_height()
        if ancho < 2 or alto < 2:
            return
        canvas = self.login_promo_canvas
        canvas.delete("all")
        if self.login_background_source is not None:
            cover = ImageOps.fit(
                self.login_background_source,
                (ancho, alto),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            self.login_background_image = ImageTk.PhotoImage(cover, master=canvas)
            canvas.create_image(0, 0, image=self.login_background_image, anchor="nw")

        # El Canvas mantiene la foto y los textos sin fondos rectangulares.
        texts = [
            (40, 156, "HEMEROTECA · RED DE BIBLIOTECAS", "#DCE6FF", 12, "bold", "nw"),
            (ancho * .08, alto * .43, "CONSULTA DE PRENSA HISTÓRICA", "#F3C84B", 12, "bold", "w"),
            (ancho * .08, alto * .53, "La historia también\nse consulta.", WHITE, 38, "bold", "w"),
            (ancho * .08, alto * .72, "Busca ejemplares por fecha, título y ubicación en la colección.", "#E3E9F7", 15, "normal", "w"),
        ]
        for x, anio_breve, texto, color, tamano, weight, anchor in texts:
            opciones_control = dict(text=texto, font=(FONT, -tamano, weight), anchor=anchor,
                           justify="left", width=min(490, int(ancho * .84)))
            # Una sombra discreta mantiene la lectura sobre la fotografía.
            canvas.create_text(x + 1, anio_breve + 1, fill="#18202C", **opciones_control)
            canvas.create_text(x, anio_breve, fill=color, **opciones_control)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _apply_login_background = _aplicar_entrada_fondo

    def _entrada_disposicion(self):
        """Formulario desplazable; la fotografía se oculta en pantallas pequeñas."""
        self._clear()
        self.configure(fg_color=WHITE)
        self.grid_columnconfigure(0, weight=1, minsize=0, uniform='')
        self.grid_columnconfigure(1, weight=0, minsize=0, uniform='')
        self.grid_rowconfigure(0, weight=1)
        layout = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0)
        layout.grid(row=0, column=0, columnspan=2, sticky='nsew')
        layout.grid_rowconfigure(0, weight=1)
        layout.grid_columnconfigure(0, weight=2)
        layout.grid_columnconfigure(1, weight=3)
        promo = ctk.CTkFrame(layout, fg_color='#18202C', corner_radius=0)
        promo.grid(row=0, column=0, sticky='nsew')
        self.login_promo_canvas = tk.Canvas(promo, bg='#18202C', highlightthickness=0, borderwidth=0)
        self.login_promo_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        promo.bind('<Configure>', self._resize_login_background)
        self._login_bg_resize_job = self.after(80, lambda: self._apply_login_background(promo))
        form = ctk.CTkFrame(layout, fg_color=WHITE, corner_radius=0)
        form.grid(row=0, column=1, sticky='nsew')
        form.grid_columnconfigure(0, weight=1)
        form.grid_rowconfigure(1, weight=1)
        logos = ctk.CTkFrame(form, fg_color=WHITE, corner_radius=0)
        logos.grid(row=0, column=0, sticky='e', padx=24, pady=(10, 0))
        for clave in ('gov', 'library'):
            if clave in self.logo_images:
                ctk.CTkLabel(logos, text='', image=self.logo_images[clave], fg_color=WHITE).pack(side='left', padx=(12, 0))
        formulario_body = self._scrollable(form, fg_color=WHITE, corner_radius=0)
        formulario_body.grid(row=1, column=0, sticky='nsew')
        panel = ctk.CTkFrame(formulario_body, fg_color=WHITE, corner_radius=0)
        panel.pack(fill='x', padx=24, pady=(16, 24))
        estado_local = {'compact': None}
        def redimensionar(_event):
            """Oculta el panel promocional en ventanas estrechas y redistribuye el formulario solo si cambia el modo de diseño."""
            _evento_local = _event
            _evento = _evento_local
            compact = layout._reverse_widget_scaling(layout.winfo_width()) < 1100
            if compact == estado_local['compact']:
                return
            estado_local['compact'] = compact
            if compact:
                promo.grid_remove()
                form.grid_configure(column=0, columnspan=2)
                layout.grid_columnconfigure(0, weight=1)
                layout.grid_columnconfigure(1, weight=0)
            else:
                form.grid_configure(column=1, columnspan=1)
                layout.grid_columnconfigure(0, weight=2)
                layout.grid_columnconfigure(1, weight=3)
                promo.grid()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        resize = redimensionar
        layout.bind('<Configure>', resize)
        return panel
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _login_layout = _entrada_disposicion

    def _entrada_encabezado(self, panel, eyebrow, title, detail):
        """Construye el título, subtítulo y explicación del formulario de ingreso con ajuste al ancho."""
        detalle = detail
        titulo = title
        ctk.CTkLabel(panel, text=eyebrow, text_color=BLUE, font=(FONT, 12, 'bold')).pack(anchor='w', pady=(0, 8))
        encabezado = ctk.CTkLabel(panel, text=titulo, text_color=INK, font=(FONT, 30, 'bold'), anchor='w', justify='left', wraplength=520)
        encabezado.pack(fill='x')
        encabezado.bind('<Configure>', lambda _e: self._fit_text(encabezado, encabezado.winfo_width()))
        self._paragraph(panel, detalle).pack(fill='x', pady=(8, 16))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _login_heading = _entrada_encabezado

    def _entrada_accion(self, parent, title, detail, command, *, variant='secondary', manage=True):
        """Botón y explicación alineados, sin una tarjeta adicional alrededor."""
        comando = command
        detalle = detail
        padre = parent
        titulo = title
        tarjeta = ctk.CTkFrame(padre, fg_color='transparent', corner_radius=0)
        if manage:
            tarjeta.pack(fill='x', pady=(14, 0))
        self._button(tarjeta, titulo, comando, variant, height=44).pack(fill='x')
        self._paragraph(tarjeta, detalle).pack(fill='x', pady=(6, 0))
        return tarjeta
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _login_action = _entrada_accion

    def _entrada_accion_grupo(self, parent, actions):
        """Accesos secundarios en una fila; se apilan cuando falta espacio."""
        acciones = actions
        padre = parent
        grupo = ctk.CTkFrame(padre, fg_color='transparent', corner_radius=0)
        grupo.pack(fill='x', pady=(14, 0))
        grupo.grid_columnconfigure((0, 1), weight=1, uniform='login_actions')
        cards = [self._login_action(grupo, titulo, detalle, comando, manage=False)
                 for titulo, detalle, comando in acciones]
        estado_local = {'columns': None}
        def organizar(_event=None):
            """Distribuye las tarjetas de acciones en una o dos columnas según el ancho, evitando recalcular si no cambia."""
            _evento_local = _event
            _evento = _evento_local
            ancho = grupo._reverse_widget_scaling(grupo.winfo_width())
            columnas = 2 if len(cards) > 1 and ancho >= 560 else 1
            if columnas == estado_local['columns']:
                return
            estado_local['columns'] = columnas
            grupo.grid_columnconfigure(0, weight=1, uniform='login_actions' if columnas == 2 else '')
            grupo.grid_columnconfigure(1, weight=1 if columnas == 2 else 0,
                                       uniform='login_actions' if columnas == 2 else '')
            for indice, tarjeta in enumerate(cards):
                fila, columna = divmod(indice, columnas)
                tarjeta.grid(row=fila, column=columna, sticky='new',
                          padx=(0, 7) if columnas == 2 and columna == 0 else ((7, 0) if columnas == 2 else 0),
                          pady=(0 if fila == 0 else 14, 0))
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        arrange = organizar
        grupo.bind('<Configure>', arrange)
        arrange()
        return grupo
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _login_action_group = _entrada_accion_grupo

    def mostrar_entrada(self, register=False):
        'Construye el acceso y las alternativas de registro y recuperación.'
        conservar = getattr(self, '_guardar_estado_vista', None)
        if conservar and getattr(self, 'user', None) is not None:
            conservar()
        self._guardar_estado_vista = lambda: None
        if self.services.read_only and getattr(self, 'user', None) is not None:
            self.services.client.logout()
        self.user = None
        self._session_snapshot = None
        self._authenticated_version = None
        self._account_step = None
        self._showing_recovery_code = False
        error = ''
        try:
            configuracion_inicial = bool(self.services.auth.needs_setup())
        except (ValueError, sqlite3.Error) as excepcion:
            configuracion_inicial, error = False, str(excepcion)
        self._setup_mode = configuracion_inicial and not self.services.read_only
        self._login_enabled = not bool(error)
        panel = self._login_layout()
        if error:
            self._login_heading(panel, 'ACCESO NO DISPONIBLE', 'Necesitamos revisar la conexión',
                                'No pudimos comprobar si la hemeroteca está lista. Pide ayuda al administrador principal.' if not self.services.read_only else
                                'No se pudo conectar con la PC principal. Comprueba que esté encendida, con la aplicación abierta y en la misma red.')
            self._paragraph(panel, error, color='#A83D35').pack(fill='x', pady=(0, 12))
            self._login_action(panel, 'Reintentar', 'Vuelve a comprobar la conexión antes de escribir tus datos.', self.show_login, variant='primary')
            self._login_action(panel, 'Ayuda para entrar', 'Explica los datos de acceso y qué hacer si olvidaste tu contraseña.', self._login_help)
            self._login_admin_options(panel)
            return
        if self._setup_mode:
            register = True
        if self._setup_mode:
            self._login_heading(panel, 'PRIMER INICIO · PASO 1 DE 3', 'Registrar administrador principal',
                                'Esta hemeroteca todavía no tiene un administrador. La persona responsable debe crear su cuenta antes de que puedan entrar los demás usuarios.')
            self._paragraph(panel, '1. Completa los datos del responsable.\n2. Elige tres preguntas y escribe sus respuestas.\n3. Guarda el código de recuperación que se mostrará una sola vez.', color=INK,
                            fg_color=BG, corner_radius=10).pack(fill='x', pady=(0, 16))
            if getattr(self.services, 'network', None):
                self._login_action(panel, 'Preparar PC de consulta', 'Si esta es una computadora adicional, déjala en espera para que el maestro la autorice desde la PC principal.', self._connect_server_form)
        elif register:
            self._login_heading(panel, 'NUEVO USUARIO · PASO 1 DE 3', 'Crear mi cuenta',
                                'Elige Usuario regular o Administrador regular. Tu cuenta se guardará en la PC principal y podrás usarla desde cualquier computadora autorizada.')
        else:
            self._login_heading(panel, 'HEMEROTECA · RED DE BIBLIOTECAS', 'Iniciar sesión',
                                'Escribe el documento y la contraseña de tu cuenta. El sistema reconocerá automáticamente tu perfil y tus permisos.')
            if self.services.read_only:
                estado = 'PC autorizada y conectada. Inicia sesión con tu cuenta o pulsa Crear mi cuenta si todavía no tienes una.'
            else:
                estado = 'Administrador principal ya registrado. El sistema está listo para ingresar.'
            self._paragraph(panel, estado, color=BLUE, fg_color=BG, corner_radius=8).pack(fill='x', pady=(0, 14))
        if register:
            self.reg_name = self._entry(panel, 'Nombre(s) *', 'Escribe tus nombres')
            self.reg_name[0].pack(fill='x', pady=(0, 12))
            self.reg_lastname = self._entry(panel, 'Apellido(s) *', 'Escribe tus apellidos')
            self.reg_lastname[0].pack(fill='x', pady=(0, 12))
            if not self._setup_mode:
                role_wrap, self.reg_role = self._combo(panel, 'Tipo de cuenta *',
                                                       [ROLES[2], ROLES[1]], ROLES[2])
                role_wrap.pack(fill='x', pady=(0, 8))
                self._paragraph(panel, 'El usuario regular solo puede consultar ejemplares. El administrador regular puede solicitar permisos adicionales al administrador maestro.').pack(fill='x', pady=(0, 12))
        self.login_identity_wrap, self.login_identity = self._document_entry(panel, 'Cédula *')
        self.login_identity_wrap.pack(fill='x', pady=(0, 6))
        if not register and getattr(self, '_documento_recordado', None):
            self.login_identity.set(self._documento_recordado)
        self._paragraph(panel, 'Selecciona V o E y escribe solo el número de tu cédula, sin puntos ni espacios. Usa el documento con el que te registraste.').pack(fill='x', pady=(0, 12))
        self.login_password_wrap, self.login_password = self._entry(panel, 'Crea una contraseña *' if register else 'Contraseña *',
                                                                   '8–15 caracteres · Aa, 1 y #' if register else 'Escribe tu contraseña', show='•')
        self.login_password_wrap.pack(fill='x', pady=(0, 6))
        self._paragraph(panel, 'Usa 8 a 15 caracteres: mayúsculas, minúsculas, números y símbolos, sin espacios.' if register else
                        'Usa la contraseña que creaste o la temporal que te entregó el administrador. Respeta mayúsculas y minúsculas.').pack(fill='x', pady=(0, 10))
        if register:
            self.reg_confirm_wrap, self.reg_confirm = self._entry(panel, 'Repite la contraseña *', 'Escribe exactamente la misma contraseña', show='•')
            self.reg_confirm_wrap.pack(fill='x', pady=(0, 10))
        visible = ctk.BooleanVar(value=False)
        def mostrar_contrasena():
            """Muestra u oculta el texto de contraseña y su confirmación sin cambiar el contenido escrito."""
            valor = '' if visible.get() else '•'
            self.login_password.configure(show=valor)
            if register:
                self.reg_confirm.configure(show=valor)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        mostrar_contrasena_local = mostrar_contrasena
        ctk.CTkCheckBox(panel, text='Mostrar contraseña', variable=visible, command=mostrar_contrasena_local,
                        font=(FONT, 12)).pack(anchor='w', pady=(0, 14))
        if register:
            self._primary(panel, 'Continuar: preguntas de seguridad', self.register_user).pack(fill='x')
            self._paragraph(panel, 'Este botón continúa al paso 2. La cuenta se guardará después de responder las tres preguntas; luego deberás guardar tu código de recuperación.').pack(fill='x', pady=(6, 12))
            if not self._setup_mode:
                self._button(panel, 'Ya tengo cuenta: iniciar sesión', self.show_login, 'secondary').pack(fill='x', pady=(0, 8))
        else:
            self._primary(panel, 'Entrar a la hemeroteca', self.login).pack(fill='x')
            self._paragraph(panel, 'Abre la consulta de periódicos y las funciones autorizadas para tu cuenta.').pack(fill='x', pady=(6, 4))
            acciones = [('Crear mi cuenta', 'Elige Usuario regular o Administrador regular y completa tus datos personales. La cuenta se guarda en la PC principal.', lambda: self.show_login(True))]
            acciones.append(('Olvidé mi contraseña', 'Recupera tu acceso con tu código único o respondiendo tus tres preguntas de seguridad.', self.show_master_recovery))
            self._login_action_group(panel, acciones)
        self._login_action(panel, '¿Cómo lleno estos datos?', 'Consulta los requisitos de cédula, contraseña y recuperación.', self._login_help)
        if not self._setup_mode:
            self._login_admin_options(panel)
        self.login_identity.bind('<Return>', lambda _e: self.login_password.focus_set())
        self.login_password.bind('<Return>', lambda _e: self.reg_confirm.focus_set() if register else self.login())
        if register:
            self.reg_confirm.bind('<Return>', lambda _e: self.register_user())
            self.reg_name[1].bind('<Return>', lambda _e: self.login_identity.focus_set())
            self.reg_name[1].focus_set()
        else:
            self.login_identity.focus_set()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    show_login = mostrar_entrada

    def _entrada_administrador_opciones(self, panel, *, setup=False):
        """Añade el panel plegable de conexión de computadoras y recuperación de traslados cuando hay gestor de red."""
        configuracion_inicial = setup
        if not getattr(self.services, 'network', None):
            return
        boton = self._button(panel, 'Conexión de computadoras', lambda: toggle(), 'secondary', height=34)
        boton.pack(fill='x', pady=(18, 4))
        opciones_control = ctk.CTkFrame(panel, fg_color='transparent')
        def alternar():
            """Muestra u oculta las opciones adicionales de conexión y actualiza el texto del botón."""
            if opciones_control.winfo_manager():
                opciones_control.pack_forget()
                boton.configure(text='Conexión de computadoras')
            else:
                opciones_control.pack(fill='x')
                boton.configure(text='Ocultar opciones adicionales')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        toggle = alternar
        if getattr(self.services, 'network', None):
            self._login_action(opciones_control, 'Preparar PC de consulta', 'Muestra el nombre y un código temporal. El maestro completa la conexión desde la PC principal.', self._connect_server_form)
            self._login_action(opciones_control, 'Recuperar un traslado interrumpido', 'Solo el administrador: se utiliza en la PC que era servidor cuando falló un traslado. No es una recuperación de contraseña.', self._recover_transfer_form)
        if not configuracion_inicial:
            self._paragraph(opciones_control, 'El administrador principal se registra una sola vez por hemeroteca. Si ya existe, debe ingresar con su cuenta o recuperar su contraseña.').pack(fill='x', pady=(12, 0))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _login_admin_options = _entrada_administrador_opciones

    def _entrada_ayuda(self):
        """Muestra las instrucciones de registro, ingreso, recuperación y conexión en un diálogo de ayuda."""
        dialogo, cuerpo, pie = self._credential_container('Ayuda para iniciar sesión')
        sections = [
            ('Tipo de cuenta al registrarte', 'Elige Usuario regular o Administrador regular en Crear mi cuenta. El usuario regular solo puede consultar ejemplares. El administrador maestro aprueba los permisos solicitados por administradores regulares. Si eres administrador regular, el permiso Catálogo de periódicos permite registrar ejemplares desde la principal o una PC secundaria autorizada.'),
            ('Si eres usuario regular', '1. Si no tienes cuenta, pulsa Crear mi cuenta en la PC principal o en cualquier PC autorizada. Completa tus datos, responde tres preguntas y guarda tu código de recuperación.\n2. Escribe tu documento y tu contraseña.\n3. Pulsa Entrar a la hemeroteca. La PC principal debe estar encendida y con Hemeroteca abierta para atender a las otras PC.'),
            ('Documento de identidad', DOCUMENT_HELP + '\nEl ejemplo es una guía: escribe tu propio número. No uses correo electrónico, puntos ni espacios internos.'),
            ('Contraseña', 'Al registrarte, crea una contraseña de entre 8 y 15 caracteres y repítela igual. Al entrar, usa esa misma contraseña. Mostrar contraseña permite revisar lo escrito. Si recibiste una temporal, deberás cambiarla al entrar.'),
            ('Olvidé mi contraseña', 'Abre la recuperación con tu documento y el último código que guardaste, o responde tus tres preguntas de seguridad. Debes elegir una contraseña nueva y guardar el nuevo código. Si perdiste ambos, contacta al administrador principal.'),
            ('Primer inicio de una hemeroteca nueva', 'Aparece Registrar administrador principal. Solo la persona responsable completa ese registro, elige tres preguntas y guarda el código de recuperación. Después podrán registrarse los usuarios regulares.'),
            ('Botones de opciones adicionales', 'Preparar PC de consulta deja esta computadora en espera; solo el maestro puede autorizarla desde la PC principal. Recuperar un traslado interrumpido atiende cambios de servidor que fallaron; no sirve para cambiar contraseñas.'),
        ]
        for titulo, detalle in sections:
            self._label(cuerpo, titulo).pack(anchor='w', padx=18, pady=(10, 6))
            self._paragraph(cuerpo, detalle).pack(fill='x', padx=18, pady=(0, 12))
        self._button(pie, 'Entendido: volver', dialogo.destroy, 'secondary', width=180).pack(side='right', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _login_help = _entrada_ayuda

    def registrar_usuario(self):
        'Valida el registro personal de usuario o administrador regular sin otorgar permisos adicionales.'
        nombre = self.reg_name[1].get().strip()
        if hasattr(self, 'reg_lastname'):
            apellido = self.reg_lastname[1].get().strip()
            if not nombre or not apellido:
                messagebox.showwarning('Datos requeridos', 'Completa tus nombres y apellidos.', parent=self)
                return
            nombre += ' ' + apellido
        identidad = self.login_identity.get().strip()
        contrasena = self.login_password.get()
        if not nombre or not identidad or len(contrasena) < 8:
            messagebox.showwarning("Datos requeridos", "Completa todos los campos. La contraseña debe tener al menos 8 caracteres.", parent=self)
            return
        if contrasena != self.reg_confirm.get():
            messagebox.showwarning("Contraseña", "Las contraseñas no coinciden.", parent=self)
            return
        try:
            identidad = validar_documento_nuevo(identidad)
            nombre = validar_nombre(nombre)
            validate_password(contrasena)
        except ValueError as excepcion:
            messagebox.showwarning('Revisar datos', str(excepcion), parent=self)
            return
        perfil = ROLES[0] if self._setup_mode else self.reg_role.get()
        if not self._setup_mode and perfil not in ROLES[1:]:
            messagebox.showwarning('Tipo de cuenta', 'Selecciona Usuario regular o Administrador regular.', parent=self)
            return
        self._security_questions_form(account_data=(nombre, identidad, contrasena, perfil))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    register_user = registrar_usuario

    def entrada(self):
        """Valida que haya documento y contraseña, autentica con el servicio y abre la sesión o informa del rechazo."""
        identidad, contrasena = self.login_identity.get().strip(), self.login_password.get()
        if not identidad or not contrasena:
            messagebox.showwarning('Completa tus datos', 'Escribe el documento de tu cuenta y tu contraseña para entrar.', parent=self)
            (self.login_identity if not identidad else self.login_password).focus_set()
            return
        try:
            usuario = self.services.auth.authenticate(identidad, contrasena)
        except ValueError as excepcion:
            self.login_password.delete(0, "end")
            messagebox.showerror("Acceso denegado", str(excepcion), parent=self)
            self.login_password.focus_set()
            return
        self.user = usuario
        self._authenticated_version = usuario["password_version"]
        self.show_shell("Consulta de periódicos")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    login = entrada

    def _migracion_formulario(self):
        'Construye los controles de migracion formulario y conecta las acciones con los servicios autorizados.'
        try:
            accounts = self.services.auth.migration_accounts()
        except ValueError as excepcion:
            messagebox.showwarning('Conexión', str(excepcion), parent=self)
            return
        if not accounts:
            messagebox.showinfo('Documentos', 'Todas las cuentas activas ya tienen un documento registrado.', parent=self)
            return
        recipiente, cuerpo, pie = self._credential_container('Registrar documento de cuenta anterior')
        self._paragraph(cuerpo, 'Selecciona tu cuenta y confirma la contraseña que ya usabas. Esto conserva tus datos y reemplaza el identificador anterior por tu documento.').pack(fill='x', padx=18, pady=(0, 16))
        choices = {f"{registro_breve['name']} · {registro_breve['role']} · #{registro_breve['id']}": registro_breve['id'] for registro_breve in accounts}
        envoltura, cuenta = self._combo(cuerpo, 'Cuenta *', list(choices))
        envoltura.pack(fill='x', padx=18, pady=(0, 16))
        envoltura, contrasena = self._entry(cuerpo, 'Contraseña actual *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=(0, 16))
        self._paragraph(cuerpo, DOCUMENT_HELP).pack(fill='x', padx=18, pady=(0, 16))
        envoltura, documento = self._entry(cuerpo, 'Documento *', 'V-12345678')
        envoltura.pack(fill='x', padx=18, pady=(0, 16))
        error = self._paragraph(cuerpo, '', color='#A83D35')
        error.pack(fill='x', padx=18, pady=(0, 16))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            try:
                usuario = self.services.auth.migrate_document(choices[cuenta.get()], contrasena.get(), documento.get())
            except sqlite3.IntegrityError:
                error.configure(text='Ese documento ya pertenece a otra cuenta.')
                return
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            recipiente.destroy()
            self.user, self._authenticated_version = usuario, usuario['password_version']
            self.show_shell('Consulta de periódicos')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(pie, 'Guardar documento', save, width=185).pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', recipiente.destroy, 'secondary').pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _migration_form = _migracion_formulario
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
LoginView = VistaAcceso
