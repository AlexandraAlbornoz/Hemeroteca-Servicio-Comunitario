"""Solicitudes de acceso y revisión de permisos."""

from __future__ import annotations
from hemeroteca.ui.controles import TextoEditable
import customtkinter as ctk
from hemeroteca.config.settings import AMBER, BG, BLUE, FONT, GREEN, INK, LINE, MUTED, PERMISSIONS, RED, ROLES, VIEWS, WHITE
from hemeroteca.utils.dates import display_date, parse_filter_date
from hemeroteca.services.access_service import AccessDenied


class VistaSolicitudes:
    """Solicitudes de acceso y revisión de permisos.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _solicitudes_pagina(self):
        'Construye los controles de solicitudes pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[2], action="Consultar solicitudes", view=True):
            return
        maestro = self.role == ROLES[0]
        encabezado = self._heading("Control de acceso", "Solicitudes de permisos" if maestro else "Mis solicitudes de acceso",
                                "Revisa el motivo y responde cada solicitud. Aprobar activa el permiso para futuras operaciones." if maestro else
                                "Solicita permisos al administrador maestro y consulta aquí sus respuestas.")
        self._button(encabezado, "Actualizar", lambda: self.navigate(VIEWS[2]), "secondary", width=120).pack(side="right", padx=(12, 0))
        resumen = {'acciones': [], 'contadores': {}}
        contadores = {}
        registros = []
        stats = self._card(1)
        for indice, (estado, titulo, color) in enumerate((("Pendiente", "Pendientes", AMBER), ("Aprobada", "Aprobadas", GREEN), ("Declinada", "Rechazadas", RED))):
            stats.grid_columnconfigure(indice, weight=1, uniform="stats")
            tile = ctk.CTkFrame(stats, fg_color="transparent")
            tile.grid(row=0, column=indice, sticky="ew", padx=18, pady=14)
            ctk.CTkLabel(tile, text=titulo, text_color=MUTED, font=(FONT, 12)).pack(anchor="w")
            contadores[estado] = ctk.CTkLabel(tile, text="…", text_color=color, font=(FONT, 28, "bold"))
            contadores[estado].pack(anchor="w")
        if not maestro:
            acceso = self._card(2)
            bar = ctk.CTkFrame(acceso, fg_color="transparent")
            bar.pack(fill="x", padx=20, pady=(16, 8))
            self._label(bar, "Tus permisos activos").pack(side="left")
            available = []
            boton = self._primary(bar, "Solicitar permiso", self._request_form, width=155)
            boton.pack(side="right")
            activo = sorted(self._permisos_actuales())
            self._paragraph(acceso, " · ".join(activo), color=INK).pack(fill="x", padx=20, pady=(0, 8))
            ayuda_permisos = self._paragraph(acceso, "Cada aprobación habilita un permiso. No necesitas pedirlo para cada operación." if available else
                            "Los demás permisos ya están activos o tienen una solicitud pendiente.", color=RED)
            ayuda_permisos.pack(fill="x", padx=20, pady=(0, 16))
        tarjeta = self._card(2 if maestro else 3)
        titulo = "Bandeja de solicitudes" if maestro else "Historial de mis solicitudes"
        ctk.CTkLabel(tarjeta, text=titulo, text_color=INK, font=(FONT, 18, "bold")).pack(anchor="w", padx=20, pady=(18, 10))
        filtros = ctk.CTkFrame(tarjeta, fg_color="transparent")
        filtros.pack(fill="x", padx=20)
        filtros.grid_columnconfigure((0, 1), weight=1, uniform="request_filters")
        filtrar_estado = getattr(self, "_request_filters", {})
        remembered = filtrar_estado.get(self.user["id"], {})
        search_wrap, search = self._entry(filtros, "Usuario", "Nombre o documento")
        if maestro or "Consultar solicitudes de todos" in self._permisos_actuales():
            search_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        search.insert(0, remembered.get("user", "") if maestro or "Consultar solicitudes de todos" in self._permisos_actuales() else "")
        fecha_wrap, sent_fecha = self._date_entry(filtros, "Fecha de solicitud")
        fecha_wrap.grid(row=0, column=1, sticky="ew")
        sent_fecha.insert(0, remembered.get("date", ""))
        accion_values = ["Todas las acciones"] + resumen['acciones']
        if remembered.get('action') and remembered['action'] not in accion_values:
            # Conserva el filtro hasta recibir el resumen autorizado del servidor.
            accion_values.append(remembered['action'])
        chosen_accion = remembered.get("action", accion_values[0])
        accion_wrap, requested_accion = self._combo(filtros, "Acción solicitada", accion_values,
                                                   chosen_accion if chosen_accion in accion_values else accion_values[0])
        accion_wrap.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(12, 0))
        estado_wrap, estado = self._combo(filtros, "Estado", ["Todos", "Pendiente", "Aprobada", "Rechazada"], remembered.get("status", "Pendiente" if maestro else "Todos"))
        estado_wrap.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        filtrar_error = self._paragraph(tarjeta, "", color=RED)
        acciones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        acciones.pack(fill="x", padx=20, pady=(12, 16))
        self._button(acciones, "Limpiar filtros", lambda: reset(), "secondary", width=135).pack(side="left")
        self._primary(acciones, "Filtrar solicitudes", lambda: render(), width=165).pack(side="right")
        selection_bar = ctk.CTkFrame(tarjeta, fg_color=BG, corner_radius=8)
        selection_bar.pack(fill="x", padx=18, pady=(0, 12))
        selection_texto = self._paragraph(selection_bar, "Selecciona una solicitud para ver el motivo completo y la respuesta.")
        selection_texto.pack(side="left", fill="x", expand=True, padx=12, pady=12)
        seleccionado = {"record": None}
        review = self._button(selection_bar, "Revisar solicitud" if maestro else "Ver detalle",
                              lambda: self._request_detail(seleccionado["record"]), "secondary", width=155, state="disabled")
        review.pack(side="right", padx=12, pady=10)
        contenedor = ctk.CTkFrame(tarjeta, fg_color=WHITE)
        contenedor.pack(fill="x", pady=(0, 8))

        def elegir(tree):
            'Actualiza la selección y habilita las acciones permitidas para la fila.'
            tabla = tree
            identificadores = tabla.selection() if tabla else ()
            registro = next((registro_breve for registro_breve in registros if identificadores and str(registro_breve["id"]) == identificadores[0]), None)
            seleccionado["record"] = registro
            review.configure(state="normal" if registro else "disabled")
            selection_texto.configure(text=f"Solicitud #{registro['id']} · {registro['name']}" if registro else "Selecciona una solicitud para ver su detalle.")
            if tabla:
                tabla.bind("<Double-1>", lambda _e: self._request_detail(seleccionado["record"]) if seleccionado["record"] else None)
                tabla.bind("<Return>", lambda _e: self._request_detail(seleccionado["record"]) if seleccionado["record"] else None)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        choose = elegir

        def reiniciar():
            'Restablece los filtros iniciales y vuelve a consultar los resultados.'
            search.delete(0, "end")
            sent_fecha.delete(0, "end")
            requested_accion.set("Todas las acciones")
            estado.set("Todos")
            render()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        reset = reiniciar

        def representar():
            'Aplica los filtros y actualiza el contenido visible de esta pantalla.'
            if not self._require_access(VIEWS[2], action="Filtrar solicitudes", view=True):
                return
            consulta, elegido = search.get().strip().casefold(), estado.get()
            try:
                chosen_fecha = parse_filter_date(sent_fecha.get())
            except ValueError as excepcion:
                filtrar_error.configure(text=str(excepcion))
                filtrar_error.pack(after=filtros, fill="x", padx=20, pady=(6, 0))
                sent_fecha.focus_set()
                return
            filtrar_error.pack_forget()
            self._request_filters = filtrar_estado
            filtrar_estado[self.user["id"]] = {"user": search.get(), "date": sent_fecha.get(),
                                              "action": requested_accion.get(), "status": elegido}
            target_estado = "Declinada" if elegido == "Rechazada" else elegido
            self._guardar_estado_vista()
            def obtener(pagina):
                """Mantiene el detalle de selección de la página actual de solicitudes."""
                datos = self.services.consulta('requests', 'buscar_solicitudes', self.user, texto=search.get(),
                    fecha=chosen_fecha.isoformat() if chosen_fecha else None,
                    permiso=None if requested_accion.get() == 'Todas las acciones' else requested_accion.get(),
                    estado=target_estado, pagina=pagina)
                return datos
            def presentar(fila):
                """Muestra el estado con las mismas etiquetas del flujo anterior."""
                return (f"#{fila['id']}", fila['name'], fila['permission'], display_date(fila['created_at']),
                    'Rechazada' if fila['status'] == 'Declinada' else fila['status'])
            self._paged_table(contenedor, obtener, presentar, [('id', 'N.º', 65), ('user', 'PERSONA', 180),
                ('permission', 'PERMISO', 230), ('date', 'ENVIADA', 175), ('status', 'ESTADO', 120)], selected_callback=choose, key='solicitudes', on_data=lambda datos: registros.__setitem__(slice(None), datos['items']))
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        render = representar
        search.bind("<Return>", lambda _e: render())
        sent_fecha.bind("<Return>", lambda _e: render())
        requested_accion.configure(command=lambda _v: render())
        estado.configure(command=lambda _v: render())
        self._registrar_estado_vista('solicitudes', {'texto': search, 'fecha': sent_fecha, 'permiso': requested_accion, 'estado': estado})
        def resumen_recibido(datos):
            """Rellena contadores y opciones una sola vez con el resumen autorizado."""
            for estado_nombre, etiqueta in contadores.items():
                etiqueta.configure(text=str(datos[0]['contadores'].get(estado_nombre, 0)))
            opciones = ['Todas las acciones'] + datos[0]['acciones']
            requested_accion.configure(values=opciones)
            if requested_accion.get() not in opciones:
                requested_accion.set('Todas las acciones')
                render()
            if not maestro:
                disponibles = datos[1]
                # El formulario vuelve a consultar al servidor al abrirse; dejar
                # el botón activo permite ver de inmediato un permiso revocado.
                ayuda_permisos.configure(text='Cada aprobación habilita un permiso. No necesitas pedirlo para cada operación.' if disponibles else 'No hay permisos nuevos por ahora. Si te revocan uno, vuelve a pulsar Solicitar permiso.')
        consultas = [self.services.consulta('requests', 'resumen_solicitudes', self.user)]
        if not maestro:
            consultas.append(self.services.consulta('requests', 'available_permissions', self.user))
        self._cargar_seccion(stats, consultas, resumen_recibido)
        render()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _requests_page = _solicitudes_pagina

    def _solicitud_opciones(self):
        """Obtiene del servicio los permisos que aún pueden solicitarse sin duplicar pendientes o accesos activos."""
        return self.services.requests.available_permissions(self.user)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _request_options = _solicitud_opciones

    def _solicitud_formulario(self):
        'Construye los controles de solicitud formulario y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[2], action="Abrir solicitud de permiso", view=True):
            return
        try:
            available = self._request_options()
        except AccessDenied as excepcion:
            self._access_denied(excepcion)
            return
        except ValueError as excepcion:
            self._notice(str(excepcion))
            return
        if not available:
            self._notice("No quedan permisos disponibles para solicitar.")
            return
        dialogo = self._dialog("Solicitar un permiso", "650x600")
        pie = ctk.CTkFrame(dialogo, fg_color=WHITE, corner_radius=0)
        pie.pack(side="bottom", fill="x")
        cuerpo = self._scrollable(dialogo, fg_color=WHITE, corner_radius=12)
        cuerpo.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(cuerpo, text="Solicitar un permiso", text_color=INK, font=(FONT, 24, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        self._paragraph(cuerpo, "El administrador maestro revisará el motivo. Podrás consultar su respuesta en Mis solicitudes.").pack(fill="x", padx=18, pady=(0, 16))
        envoltura, permiso = self._combo(cuerpo, "Permiso que necesitas *", available, available[0])
        envoltura.pack(fill="x", padx=18, pady=(0, 8))
        explanation = self._paragraph(cuerpo, PERMISSIONS[available[0]], color=BLUE)
        explanation.pack(fill="x", padx=18, pady=(0, 18))
        permiso.configure(command=lambda value: explanation.configure(text=PERMISSIONS[value]))
        self._label(cuerpo, "Motivo de la solicitud *").pack(anchor="w", padx=18, pady=(0, 6))
        motivo = TextoEditable(cuerpo, height=130, fg_color=BG, text_color=INK, border_color=LINE, border_width=1, corner_radius=8, font=(FONT, 13), wrap="word")
        motivo.pack(fill="x", padx=18)
        counter = self._paragraph(cuerpo, "0 / 1.000 caracteres · Explica qué tarea necesitas realizar.")
        counter.pack(fill="x", padx=18, pady=(6, 0))
        motivo.bind("<KeyRelease>", lambda _e: counter.configure(text=f"{len(motivo.get('1.0', 'end-1c').strip())} / 1.000 caracteres"))
        error = self._paragraph(cuerpo, "", color=RED)
        error.pack(fill="x", padx=18, pady=(4, 12))
        def enviar():
            """Envía permiso y motivo al servicio; conserva el formulario ante errores y actualiza el historial al completar el envío."""
            try:
                identificador_solicitud = self.services.requests.submit_request(self.user, permiso.get(), motivo.get("1.0", "end-1c"))
            except AccessDenied as excepcion:
                self._access_denied(excepcion, parent=dialogo)
                return
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                motivo.focus_set()
                return
            dialogo.destroy()
            self.navigate(VIEWS[2])
            self._notice(f"Solicitud #{identificador_solicitud} enviada al administrador maestro.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        submit = enviar
        self._primary(pie, "Enviar solicitud", submit, width=165).pack(side="right", padx=(8, 20), pady=14)
        self._button(pie, "Cancelar", dialogo.destroy, "secondary", width=120).pack(side="right", pady=14)
        motivo.focus_set()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _request_form = _solicitud_formulario

    def _solicitud_detalle(self, record):
        """Vuelve a consultar la solicitud para mostrar su estado vigente y ofrece decisión únicamente al maestro autorizado."""
        registro = record
        if registro is None:
            return
        if not self._require_access(VIEWS[2], action=f"Abrir solicitud #{registro['id']}", view=True):
            return
        # Volver a leer evita decidir sobre un estado anterior de la lista.
        try:
            req = next((registro_breve for registro_breve in self.services.requests.requests(self.user) if registro_breve["id"] == registro["id"]), None)
        except AccessDenied as excepcion:
            self._access_denied(excepcion)
            return
        except ValueError as excepcion:
            self._notice(str(excepcion))
            return
        if req is None:
            self.services.audit.record(self.services.access.actor_label(self.user), f"Abrir solicitud ajena o no disponible: #{registro['id']}", "Acceso denegado")
            self._notice("Esta solicitud ya no está disponible.")
            return
        editable = self.role == ROLES[0] and not self.services.read_only and req["status"] == "Pendiente"
        dialogo = self._dialog(f"Solicitud #{req['id']}", "680x720")
        pie = ctk.CTkFrame(dialogo, fg_color=WHITE, corner_radius=0)
        pie.pack(side="bottom", fill="x")
        cuerpo = self._scrollable(dialogo, fg_color=WHITE, corner_radius=12)
        cuerpo.pack(fill="both", expand=True, padx=20, pady=20)
        cabecera = ctk.CTkFrame(cuerpo, fg_color="transparent")
        cabecera.pack(fill="x", padx=18, pady=(16, 12))
        ctk.CTkLabel(cabecera, text=f"Solicitud #{req['id']}", text_color=INK, font=(FONT, 24, "bold")).pack(side="left")
        self._badge(cabecera, req["status"]).pack(side="right")
        for texto in (f"{req['name']} · {req['identity']}", f"Enviada el {display_date(req['created_at'])}"):
            self._paragraph(cuerpo, texto).pack(fill="x", padx=18, pady=(0, 5))
        self._label(cuerpo, req["permission"]).pack(anchor="w", padx=18, pady=(14, 5))
        self._paragraph(cuerpo, PERMISSIONS.get(req["permission"], "Permiso registrado en una versión anterior.")).pack(fill="x", padx=18, pady=(0, 14))
        self._label(cuerpo, "Motivo del usuario").pack(anchor="w", padx=18, pady=(0, 6))
        motive = TextoEditable(cuerpo, height=100, fg_color=BG, text_color=INK, font=(FONT, 13), wrap="word", corner_radius=8)
        motive.pack(fill="x", padx=18, pady=(0, 14))
        motive.insert("1.0", req["reason"])
        motive.configure(state="disabled")
        error = self._paragraph(cuerpo, "", color=RED)
        if editable:
            if not req["active"]:
                self._paragraph(cuerpo, "Esta cuenta está inactiva. Puedes rechazar la solicitud; para aprobarla primero debes reactivar la cuenta desde Usuarios.", color=AMBER).pack(fill="x", padx=18, pady=(0, 12))
            self._label(cuerpo, "Respuesta al usuario").pack(anchor="w", padx=18, pady=(0, 6))
            self._paragraph(cuerpo, "Opcional al aprobar; obligatoria al rechazar. Máximo 1.000 caracteres.").pack(fill="x", padx=18, pady=(0, 8))
            respuesta = TextoEditable(cuerpo, height=100, fg_color=WHITE, text_color=INK, border_width=1, border_color=LINE, font=(FONT, 13), wrap="word", corner_radius=8)
            respuesta.pack(fill="x", padx=18)
            error.pack(fill="x", padx=18, pady=(6, 12))
            def decidir(approved):
                """Envía aprobación o rechazo con la versión de cuenta esperada y actualiza el historial si la decisión se acepta."""
                aprobado = approved
                try:
                    self.services.requests.decide_request(self.user, req["id"], aprobado, respuesta.get("1.0", "end-1c"), expected_account_version=req["account_version"])
                except AccessDenied as excepcion:
                    self._access_denied(excepcion, parent=dialogo)
                    return
                except ValueError as excepcion:
                    error.configure(text=str(excepcion))
                    return
                dialogo.destroy()
                self.navigate(VIEWS[2])
                self._notice(f"Solicitud #{req['id']} {'aprobada. Permiso activado.' if aprobado else 'rechazada. Respuesta guardada.'}")
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            decide = decidir
            self._button(pie, "Aprobar permiso", lambda: decide(True), "success", width=160, state="normal" if req["active"] and req["permission"] in PERMISSIONS else "disabled").pack(side="right", padx=(8, 20), pady=14)
            self._button(pie, "Rechazar", lambda: decide(False), "danger", width=110).pack(side="right", padx=8, pady=14)
            self._button(pie, "Volver", dialogo.destroy, "secondary", width=90).pack(side="left", padx=20, pady=14)
        else:
            self._label(cuerpo, "Respuesta del administrador maestro").pack(anchor="w", padx=18, pady=(0, 6))
            reply = req["response"] or ("Tu solicitud está en revisión. Aún no hay una respuesta." if req["status"] == "Pendiente" else "La decisión se registró sin un comentario adicional.")
            self._paragraph(cuerpo, reply, color=INK).pack(fill="x", padx=18, pady=(0, 14))
            if req["decided_at"]:
                self._paragraph(cuerpo, f"{req['decided_by']} · {display_date(req['decided_at'])}").pack(fill="x", padx=18, pady=(0, 12))
            if req["status"] == "Aprobada":
                self._paragraph(cuerpo, "Permiso activo" if self.services.access.has_grant(self.user, req["user_id"], req["permission"]) else "Este permiso fue revocado después de la aprobación.", color=GREEN if self.services.access.has_grant(self.user, req["user_id"], req["permission"]) else AMBER).pack(fill="x", padx=18, pady=(0, 14))
            self._button(pie, "Cerrar detalle", dialogo.destroy, "secondary", width=145).pack(side="right", padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _request_detail = _solicitud_detalle
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RequestsView = VistaSolicitudes
