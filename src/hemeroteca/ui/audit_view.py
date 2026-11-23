"""Vista de consulta del historial de auditoría."""

from __future__ import annotations
import customtkinter as ctk
from hemeroteca.config.settings import RED, VIEWS, WHITE
from hemeroteca.utils.dates import parse_filter_date, instante_auditoria_local
from hemeroteca.ui.selector_hora import SelectorHora, usuario_auditoria_valido


class VistaAuditoria:
    """Vista de consulta del historial de auditoría.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _auditoria_pagina(self):
        'Construye los controles de auditoria pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[3], action="Consultar auditoría", view=True):
            return
        self._heading("Seguridad y trazabilidad", "Registro de auditoría", "Combina fecha, hora, acción y usuario para localizar eventos del historial.")
        tarjeta = self._card(1)
        filtros = ctk.CTkFrame(tarjeta, fg_color="transparent")
        filtros.pack(fill="x", padx=20, pady=18)
        filtros.grid_columnconfigure((0, 1), weight=1, uniform="audit_filters")
        fecha_wrap, evento_fecha = self._date_entry(filtros, "Fecha")
        fecha_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        time_wrap = self._marco_campo(filtros, "Hora y minutos · 24 h (opcional)")
        evento_time = SelectorHora(time_wrap)
        evento_time.pack(anchor='w')
        time_wrap.grid(row=0, column=1, sticky="ew")
        usuario_wrap, evento_usuario = self._entry(filtros, "Usuario", "Nombre o parte del nombre")
        evento_usuario.configure(validate='key', validatecommand=(evento_usuario.register(usuario_auditoria_valido), '%P'))
        usuario_wrap.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(12, 0))
        accion_wrap, evento_accion = self._combo(filtros, "Acción", ["Todas"], "Todas")
        accion_wrap.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        resultados = []
        rw, resultado = self._combo(filtros, "Resultado", ["Todos"] + sorted({"Completado", "Acceso denegado"} | set(resultados)), "Todos")
        rw.grid(row=2, column=0, sticky="ew", padx=(0, 12), pady=(12, 0))
        filtrar_error = self._paragraph(tarjeta, "", color=RED)
        acciones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        acciones.pack(fill="x", padx=20, pady=(0, 16))
        self._primary(acciones, "Filtrar historial", lambda: render(), width=155).pack(side="right")
        self._button(acciones, "Limpiar filtros", lambda: reset(), "secondary", width=135).pack(side="right", padx=8)
        contenedor = ctk.CTkFrame(tarjeta, fg_color=WHITE)
        contenedor.pack(fill="x", pady=(0, 12))
        def reiniciar():
            'Restablece los filtros iniciales y vuelve a consultar los resultados.'
            for entrada in (evento_fecha, evento_time, evento_usuario):
                entrada.delete(0, "end")
            resultado.set("Todos")
            evento_accion.set("Todas")
            render()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        reset = reiniciar
        def representar():
            'Aplica los filtros y actualiza el contenido visible de esta pantalla.'
            if not self._require_access(VIEWS[3], action="Filtrar auditoría", view=True):
                return
            try:
                chosen_fecha = parse_filter_date(evento_fecha.get())
            except ValueError as excepcion:
                filtrar_error.configure(text=str(excepcion))
                filtrar_error.pack(after=filtros, fill="x", padx=20)
                evento_fecha.focus_set()
                return
            time_texto = evento_time.get().strip()
            time_parts = time_texto.split(":") if time_texto else []
            if time_parts and (len(time_parts) > 3 or
                               any(not parte.isascii() or not parte.isdigit() or len(parte) > 2 for parte in time_parts) or
                               any(int(parte) > limite for parte, limite in zip(time_parts, (23, 59, 59)))):
                filtrar_error.configure(text="Escribe una hora válida: HH, HH:MM o HH:MM:SS (formato de 24 horas).")
                filtrar_error.pack(after=filtros, fill="x", padx=20)
                evento_time.focus_set()
                return
            filtrar_error.pack_forget()
            time_prefix = ":".join(parte.zfill(2) for parte in time_parts)
            self._guardar_estado_vista()
            def obtener(pagina):
                """Aplica los filtros validados en el servidor y pagina el resultado."""
                return self.services.consulta('audit', 'buscar_eventos', self.user, fecha=chosen_fecha.isoformat() if chosen_fecha else None,
                    hora=time_prefix, usuario=evento_usuario.get(), accion="" if evento_accion.get() == "Todas" else evento_accion.get(), resultado=resultado.get(), pagina=pagina)
            def presentar(fila):
                """Conserva la representación legible de fechas históricas."""
                instante = instante_auditoria_local(fila['at'])
                return (instante.strftime('%d/%m/%Y %H:%M:%S') if instante else fila['at'], fila['user'], fila['action'], fila['result'])
            self._paged_table(contenedor, obtener, presentar, [('at', 'FECHA Y HORA', 180), ('user', 'USUARIO', 180),
                ('action', 'ACCIÓN', 360), ('result', 'RESULTADO', 130)], key='auditoria')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        render = representar
        for entrada in (evento_fecha, evento_time.hora, evento_time.minuto, evento_usuario, evento_accion):
            entrada.bind("<Return>", lambda _e: render())
        resultado.configure(command=lambda _v: render())
        evento_accion.configure(command=lambda _v: render())
        self._registrar_estado_vista('auditoria', {'fecha': evento_fecha, 'hora': evento_time, 'usuario': evento_usuario, 'accion': evento_accion, 'resultado': resultado})
        def opciones(datos):
            """Completa los menús sin borrar filtros que el usuario ya haya elegido."""
            evento_accion.configure(values=['Todas'] + datos[0])
            resultado.configure(values=['Todos'] + sorted({'Completado', 'Acceso denegado'} | set(datos[1])))
        self._cargar_seccion(contenedor, [self.services.consulta('audit', 'acciones_disponibles', self.user),
            self.services.consulta('audit', 'resultados_disponibles', self.user)], opciones, clave='opciones')
        render()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _audit_page = _auditoria_pagina
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
AuditView = VistaAuditoria
