"""Consulta, creación y administración de cuentas."""

from __future__ import annotations
import sqlite3
import customtkinter as ctk
from tkinter import messagebox
from hemeroteca.config.settings import BG, FONT, INK, RED, ROLES, ROLE_ACCESS, VIEWS, WHITE, REPORT_PERMISSIONS, PERMISSIONS, LEGACY_ADMIN_ACCESS
from hemeroteca.services.access_service import AccessDenied


class VistaUsuarios:
    """Consulta, creación y administración de cuentas.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _users_pagina(self):
        'Construye los controles de users pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[4], action="Consultar usuarios", view=True):
            return
        maestro = self.role == ROLES[0] and not self.services.read_only
        encabezado = self._heading("Administración", "Usuarios y permisos", "Consulta las cuentas y sus permisos. Solo el administrador maestro puede gestionarlos.")
        if maestro:
            self._primary(encabezado, "Crear cuenta", self._admin_user_form, width=145).pack(side="right", padx=(12, 0))
        tarjeta = self._card(1)
        filtros = ctk.CTkFrame(tarjeta, fg_color="transparent")
        filtros.pack(fill="x", padx=20, pady=18)
        filtros.grid_columnconfigure(0, weight=2)
        filtros.grid_columnconfigure(1, weight=1)
        qw, consulta = self._entry(filtros, "Buscar usuario", "Nombre o documento")
        qw.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        sw, estado = self._combo(filtros, "Estado", ["Todos", "Activo", "Inactivo"], "Todos")
        sw.grid(row=0, column=1, sticky="ew")
        acciones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        acciones.pack(fill="x", padx=20, pady=(0, 16))
        self._primary(acciones, "Filtrar usuarios", lambda: render(), width=155).pack(side="right")
        self._button(acciones, "Limpiar filtros", lambda: reset(), "secondary", width=135).pack(side="right", padx=8)
        seleccionado = {"record": None}
        details = self._button(acciones, "Gestionar cuenta" if maestro else "Ver permisos", lambda: self._user_detail(seleccionado["record"]), "secondary", width=160, state="disabled")
        details.pack(side="left")
        contenedor = ctk.CTkFrame(tarjeta, fg_color=WHITE)
        contenedor.pack(fill="x", pady=(0, 12))
        usuarios = []
        def elegir(tree):
            'Actualiza la selección y habilita las acciones permitidas para la fila.'
            tabla = tree
            identificadores = tabla.selection() if tabla else ()
            seleccionado["record"] = next((registro_breve for registro_breve in usuarios if identificadores and str(registro_breve["id"]) == identificadores[0]), None)
            details.configure(state="normal" if seleccionado["record"] else "disabled")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        choose = elegir
        def reiniciar():
            'Restablece los filtros iniciales y vuelve a consultar los resultados.'
            consulta.delete(0, "end")
            estado.set("Todos")
            render()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        reset = reiniciar
        def representar():
            'Aplica los filtros y actualiza el contenido visible de esta pantalla.'
            if not self._require_access(VIEWS[4], action="Filtrar usuarios", view=True):
                return
            self._guardar_estado_vista()
            def obtener(pagina):
                """Mantiene en memoria solo las cuentas de la página visible."""
                resultado = self.services.consulta('users', 'buscar_usuarios', self.user, texto=consulta.get(), estado=estado.get(), pagina=pagina)
                return resultado
            def presentar(fila):
                """Presenta datos públicos de cuenta y su estado actual."""
                return (fila['name'], fila['identity'], fila['role'], 'Activo' if fila['active'] else 'Inactivo')
            self._paged_table(contenedor, obtener, presentar, [('name', 'PERSONA', 200), ('identity', 'DOCUMENTO', 230),
                ('role', 'TIPO DE CUENTA', 210), ('status', 'ESTADO', 120)], selected_callback=choose, key='usuarios', on_data=lambda datos: usuarios.__setitem__(slice(None), datos['items']))
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        render = representar
        consulta.bind("<Return>", lambda _e: render())
        estado.configure(command=lambda _v: render())
        self._registrar_estado_vista('usuarios', {'texto': consulta, 'estado': estado})
        render()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _users_page = _users_pagina

    def _usuario_detalle(self, record):
        """Consulta la cuenta vigente y muestra sus permisos de perfil y concedidos con las acciones autorizadas."""
        registro = record
        if registro is None:
            return
        if not self._require_access(VIEWS[4], action="Consultar permisos de una cuenta", view=True):
            return
        registro = self.services.users.get_user(self.user, registro["id"])
        if registro is None:
            return
        dialogo = self._dialog("Cuenta y permisos", "650x620")
        pie = ctk.CTkFrame(dialogo, fg_color=WHITE, corner_radius=0)
        pie.pack(side="bottom", fill="x")
        cuerpo = self._scrollable(dialogo, fg_color=WHITE, corner_radius=12)
        cuerpo.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(cuerpo, text=registro["name"], text_color=INK, font=(FONT, 24, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        self._paragraph(cuerpo, f"{registro['identity']}\n{registro['role']} · {'Activo' if registro['active'] else 'Inactivo'}").pack(fill="x", padx=18, pady=(0, 14))
        self._label(cuerpo, "Permisos incluidos en el perfil").pack(anchor="w", padx=18, pady=(0, 6))
        base = set(ROLE_ACCESS[registro["role"]])
        if registro["role"] == ROLES[0]:
            base.update(("Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"))
        elif registro['role'] == ROLES[1] and not registro['managed_permissions']:
            base.update(LEGACY_ADMIN_ACCESS)
        self._paragraph(cuerpo, " · ".join(sorted(base))).pack(fill="x", padx=18, pady=(0, 20))
        self._label(cuerpo, "Permisos adicionales aprobados").pack(anchor="w", padx=18, pady=(0, 10))
        grants = self.services.users.grants(self.user, registro["id"])
        editable = self.role == ROLES[0] and not self.services.read_only and registro["role"] != ROLES[0]
        def revocar(permission):
            """Confirma la retirada de un permiso y envía la versión esperada para evitar cambios sobre una cuenta desactualizada."""
            permiso = permission
            if not self._require_access(action=f"Revocar permiso: {permiso}", master=True, parent=dialogo):
                return
            if not messagebox.askyesno("Revocar permiso", f"¿Revocar «{permiso}» a {registro['name']}?\nLas solicitudes anteriores conservarán su historial.", parent=dialogo):
                return
            try:
                self.services.users.revoke_grant(self.user, registro["id"], permiso, expected_version=registro["password_version"])
            except AccessDenied as excepcion:
                self._access_denied(excepcion, parent=dialogo)
                return
            except ValueError as excepcion:
                messagebox.showwarning("Revisar cuenta", str(excepcion), parent=dialogo)
                return
            dialogo.destroy()
            self.navigate(VIEWS[4])
            self._notice("Permiso revocado. El historial se conserva.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        revoke = revocar
        for grant in grants:
            fila = ctk.CTkFrame(cuerpo, fg_color=BG, corner_radius=8)
            fila.pack(fill="x", padx=18, pady=(0, 8))
            self._paragraph(fila, grant["permission"], color=INK).pack(side="left", fill="x", expand=True, padx=12, pady=12)
            if editable and grant["permission"] not in base:
                self._button(fila, "Revocar", lambda permission=grant["permission"]: revoke(permission), "danger", width=95, height=36).pack(side="right", padx=12, pady=8)
        if not grants:
            self._paragraph(cuerpo, "Esta cuenta no tiene permisos adicionales.").pack(fill="x", padx=18, pady=(0, 18))
        if editable and registro['active']:
            def edit_pdf_permisos():
                """Cierra el detalle y abre el formulario de permisos PDF de la cuenta seleccionada."""
                dialogo.destroy()
                self._pdf_permissions_form(registro)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            edit_pdf_permisos_local = edit_pdf_permisos
            self._button(cuerpo, 'Configurar permisos de reportes PDF', edit_pdf_permisos_local, 'secondary', width=290).pack(anchor='w', padx=18, pady=(0, 18))
        if self.role == ROLES[0] and not self.services.read_only:
            def edit_usuario():
                """Cierra el detalle y abre la edición administrativa de la cuenta seleccionada."""
                dialogo.destroy()
                self._admin_user_form(registro)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            edit_usuario_local = edit_usuario

            self._button(cuerpo, "Actualizar datos", edit_usuario_local, "secondary", width=185).pack(anchor="w", padx=18, pady=(0, 20))
        if self.role == ROLES[0] and not self.services.read_only:
            self._button(cuerpo, 'Regenerar código de recuperación', lambda: (dialogo.destroy(), self._admin_code_form(registro)), 'secondary', width=270).pack(anchor='w', padx=18, pady=(0, 16))
            self._label(cuerpo, "Contraseña de la cuenta").pack(anchor="w", padx=18, pady=(0, 6))
            self._paragraph(cuerpo, "Cambio de contraseña temporal pendiente." if registro["must_change_password"] else
                            "Puedes asignar una contraseña temporal si su titular perdió el acceso.").pack(fill="x", padx=18, pady=(0, 12))

            def reiniciar_contrasena():
                'Emite una contraseña temporal y exige al titular sustituirla antes de continuar.'
                dialogo.destroy()
                self._admin_password_form(registro)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            reiniciar_contrasena_local = reiniciar_contrasena

            self._button(cuerpo, "Restablecer contraseña", reiniciar_contrasena_local, "secondary", width=210).pack(anchor="w", padx=18, pady=(0, 20))

            def eliminar_usuario():
                """Cierra el detalle y abre el formulario de confirmación para eliminar la cuenta seleccionada."""
                dialogo.destroy()
                self._delete_user_form(registro)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            eliminar_usuario_local = eliminar_usuario

            if editable:
                self._button(cuerpo, "Eliminar usuario", eliminar_usuario_local, "danger", width=185).pack(anchor="w", padx=18, pady=(0, 20))
        def alternar():
            """Confirma activar o desactivar la cuenta y actualiza el listado tras la operación autorizada."""
            accion = "Desactivar" if registro["active"] else "Activar"
            if not self._require_access(action=f"{accion} cuenta", master=True, parent=dialogo):
                return
            if not messagebox.askyesno(f"{accion} cuenta", f"¿{accion.lower()} el acceso de {registro['name']}?\nLa cuenta y su historial se conservarán.", parent=dialogo):
                return
            try:
                self.services.users.set_user_active(self.user, registro["id"], not registro["active"], expected_version=registro["password_version"])
            except AccessDenied as excepcion:
                self._access_denied(excepcion, parent=dialogo)
                return
            except ValueError as excepcion:
                messagebox.showwarning("Revisar cuenta", str(excepcion), parent=dialogo)
                return
            dialogo.destroy()
            self.navigate(VIEWS[4])
            self._notice("Estado de la cuenta actualizado.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        toggle = alternar
        if editable:
            self._button(pie, "Desactivar cuenta" if registro["active"] else "Activar cuenta", toggle, "danger" if registro["active"] else "success", width=170).pack(side="left", padx=20, pady=14)
        self._button(pie, "Cerrar", dialogo.destroy, "secondary", width=110).pack(side="right", padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _user_detail = _usuario_detalle

    def _pdf_permisos_formulario(self, record):
        'Construye los controles de pdf permisos formulario y conecta las acciones con los servicios autorizados.'
        registro = record
        if not self._require_access(action='Configurar permisos PDF', master=True) or self.services.read_only:
            return
        dialogo = self._dialog('Permisos de reportes PDF', '630x520')
        cuerpo = self._scrollable(dialogo, fg_color=WHITE)
        cuerpo.pack(fill='both', expand=True, padx=20, pady=20)
        self._label(cuerpo, f"Reportes de {registro['name']}").pack(anchor='w', padx=12, pady=(12, 10))
        self._paragraph(cuerpo, 'Marca los documentos que esta persona puede generar. Los permisos se aplican tanto en la PC principal como en las computadoras de consulta autorizadas.').pack(fill='x', padx=12, pady=(0, 14))
        granted = {fila['permission'] for fila in self.services.users.grants(self.user, registro['id'])}
        campos = {}
        for permiso in sorted(REPORT_PERMISSIONS):
            seleccionado = ctk.BooleanVar(value=permiso in granted)
            campos[permiso] = seleccionado
            ctk.CTkCheckBox(cuerpo, text=permiso, variable=seleccionado, font=(FONT, 12)).pack(anchor='w', padx=12, pady=(8, 8))
            self._paragraph(cuerpo, PERMISSIONS[permiso]).pack(fill='x', padx=12, pady=(0, 12))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            try:
                self.services.users.set_report_permissions(self.user, registro['id'], [p for p, campo in campos.items() if campo.get()], expected_version=registro['password_version'])
            except ValueError as excepcion:
                messagebox.showerror('No se guardaron los permisos', str(excepcion), parent=dialogo)
                return
            dialogo.destroy()
            self.navigate(VIEWS[4])
            self._notice('Permisos PDF actualizados.')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(cuerpo, 'Guardar permisos PDF', save, width=220).pack(anchor='e', padx=12, pady=(6, 16))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _pdf_permissions_form = _pdf_permisos_formulario

    def _administrador_usuario_formulario(self, record=None):
        'Construye los controles de administrador usuario formulario y conecta las acciones con los servicios autorizados.'
        registro = record
        editing = registro is not None
        if not self._require_access(action="Abrir edición de cuenta" if editing else "Abrir creación de cuenta", master=True):
            return
        titulo = "Actualizar datos" if editing else "Crear cuenta"
        dialogo = self._dialog(titulo, "600x680")
        pie = ctk.CTkFrame(dialogo, fg_color=WHITE, corner_radius=0)
        pie.pack(side="bottom", fill="x")
        tarjeta = self._scrollable(dialogo, fg_color=WHITE, corner_radius=12)
        tarjeta.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(tarjeta, text=titulo, text_color=INK, font=(FONT, 24, "bold")).pack(anchor="w", padx=18, pady=(18, 8))
        self._paragraph(tarjeta, "Todos los campos son obligatorios. Las cuentas nuevas comienzan con consulta y solicitudes; el maestro habilita los permisos adicionales.").pack(fill="x", padx=18, pady=(0, 16))
        nw, nombre = self._entry(tarjeta, "Nombre completo *", "Nombre y apellido")
        nw.pack(fill="x", padx=18, pady=(0, 14))
        iw, identidad = self._document_entry(tarjeta, "Documento de identidad *")
        iw.pack(fill="x", padx=18, pady=(0, 14))
        envoltura_periodo, contrasena = self._entry(tarjeta, "Tu contraseña actual de maestro *" if editing else "Contraseña temporal *",
                                   "" if editing else "Mínimo 8 caracteres", show="•")
        envoltura_periodo.pack(fill="x", padx=18, pady=(0, 14))
        if not editing:
            self._paragraph(tarjeta, "La persona deberá cambiar la contraseña temporal y responder sus tres preguntas de seguridad al iniciar sesión.").pack(fill="x", padx=18, pady=(0, 14))
        roles = [ROLES[0]] if editing and registro["role"] == ROLES[0] else ROLES[1:]
        rw, perfil = self._combo(tarjeta, "Tipo de cuenta *", roles, registro["role"] if editing else ROLES[1])
        rw.pack(fill="x", padx=18, pady=(0, 14))
        if editing:
            nombre.insert(0, registro["name"])
            identidad.insert(0, registro["document"] or "")
        error = self._paragraph(tarjeta, "", color=RED)
        error.pack(fill="x", padx=18, pady=(0, 12))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            if not self._require_access(action="Actualizar cuenta" if editing else "Crear cuenta", master=True, parent=dialogo):
                return
            if not nombre.get().strip() or not identidad.get().strip() or not contrasena.get():
                error.configure(text="Completa todos los campos obligatorios.")
                return
            try:
                if editing:
                    actualizado = self.services.users.update_user(self.user, registro["id"], nombre.get(), identidad.get(), perfil.get(),
                                                               contrasena.get(), expected_version=registro["password_version"])
                else:
                    creado = self.services.users.create_user(nombre.get().strip(), identidad.get().strip(), contrasena.get(), perfil.get(), actor=self.user)
            except AccessDenied as excepcion:
                self._access_denied(excepcion, parent=dialogo)
                return
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            except sqlite3.IntegrityError:
                error.configure(text="Ya existe una cuenta con ese documento.")
                return
            created_documento = identidad.get().strip().upper()
            dialogo.destroy()
            if editing and actualizado["id"] == self.user["id"]:
                self.user = actualizado
                self._authenticated_version = actualizado["password_version"]
                self.show_shell(VIEWS[4])
            else:
                self.navigate(VIEWS[4])
            self._notice("Datos actualizados." if editing else "Cuenta creada correctamente.")
            if not editing:
                self._show_recovery_code(creado.recovery_code, created_documento)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(pie, "Guardar cambios" if editing else "Crear cuenta", save, width=160).pack(side="right", padx=(8, 20), pady=14)
        self._button(pie, "Cancelar", dialogo.destroy, "secondary", width=120).pack(side="right", pady=14)
        nombre.focus_set()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _admin_user_form = _administrador_usuario_formulario

    def _eliminar_usuario_formulario(self, record):
        'Construye los controles de eliminar usuario formulario y conecta las acciones con los servicios autorizados.'
        registro = record
        if not self._require_access(action="Abrir eliminación de usuario", master=True):
            return
        recipiente, cuerpo, pie = self._credential_container("Eliminar usuario")
        self._paragraph(cuerpo, f"Cuenta: {registro['name']} · {registro['identity']}", color=INK).pack(fill="x", padx=18, pady=(0, 14))
        self._paragraph(cuerpo, "La eliminación es definitiva: se borrarán la cuenta, sus permisos, preguntas de seguridad y solicitudes. Los ejemplares registrados y la auditoría se conservan.").pack(fill="x", padx=18, pady=(0, 18))
        envoltura, contrasena = self._entry(cuerpo, "Tu contraseña actual de maestro *", "", show="•")
        envoltura.pack(fill="x", padx=18, pady=(0, 14))
        error = self._paragraph(cuerpo, "", color=RED)
        error.pack(fill="x", padx=18, pady=(0, 14))

        def eliminar():
            """Pide confirmación definitiva y contraseña maestra para eliminar la cuenta; mantiene el formulario si la operación falla."""
            if not contrasena.get():
                error.configure(text="Introduce tu contraseña actual para confirmar.")
                return
            if not messagebox.askyesno("Eliminar usuario", f"¿Eliminar definitivamente la cuenta de {registro['name']} ({registro['identity']}) y sus solicitudes?", parent=recipiente):
                return
            try:
                self.services.users.delete_user(self.user, registro["id"], contrasena.get(), expected_version=registro["password_version"])
            except (AccessDenied, ValueError) as excepcion:
                self._credential_error(excepcion, error)
                return
            recipiente.destroy()
            self.navigate(VIEWS[4])
            self._notice("Usuario eliminado. Los ejemplares y la auditoría se conservan.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        delete = eliminar

        self._button(pie, "Eliminar usuario", delete, "danger", width=180).pack(side="right", padx=(8, 20), pady=14)
        self._button(pie, "Cancelar", recipiente.destroy, "secondary", width=120).pack(side="left", padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _delete_user_form = _eliminar_usuario_formulario
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
UsersView = VistaUsuarios
