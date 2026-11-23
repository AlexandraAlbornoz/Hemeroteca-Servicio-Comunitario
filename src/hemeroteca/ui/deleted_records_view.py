"""Consulta y restauración de ejemplares retirados."""

from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
from hemeroteca.config.settings import ROLES, VIEWS, WHITE
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.utils.dates import display_date


class VistaEliminados:
    """Consulta y restauración de ejemplares retirados.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _eliminados_pagina(self):
        'Construye los controles de eliminados pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[5], action="Consultar registros eliminados", view=True):
            return
        self._heading("Administración", "Registros eliminados", "Consulta los ejemplares retirados. Solo el administrador maestro puede restaurarlos.")
        tarjeta = self._card(1)
        filtros = ctk.CTkFrame(tarjeta, fg_color="transparent")
        filtros.pack(fill="x", padx=20, pady=18)
        filtros.grid_columnconfigure(0, weight=1)
        qw, consulta = self._entry(filtros, "Buscar ejemplar eliminado", "Periódico, número, fecha o responsable")
        qw.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self._primary(filtros, "Filtrar", lambda: render(), width=115).grid(row=0, column=1, sticky="s")
        self._button(filtros, "Limpiar", lambda: reset(), "secondary", width=105).grid(row=0, column=2, sticky="s", padx=(8, 0))
        dw, desde = self._date_entry(filtros, 'Eliminación desde')
        hw, hasta = self._date_entry(filtros, 'Eliminación hasta')
        pw, periodo = self._combo(filtros, 'Eliminados recientemente', ['Todos', '24h', '1 semana', '1 mes'])
        dw.grid(row=1, column=0, sticky='ew', pady=8)
        hw.grid(row=2, column=0, sticky='ew', pady=8)
        pw.grid(row=3, column=0, sticky='ew', pady=8)
        self._paragraph(tarjeta, 'El rango y los atajos usan la fecha de eliminación registrada en auditoría. Los registros sin esa fecha siguen disponibles al quitar los filtros de fecha.').pack(fill='x', padx=20)
        seleccion = {"id": None}
        controles = ctk.CTkFrame(tarjeta, fg_color="transparent")
        controles.pack(fill="x", padx=20, pady=(0, 12))
        indicacion = self._paragraph(controles, "Selecciona un ejemplar para consultar su restauración.")
        indicacion.pack(side="left", fill="x", expand=True)
        restore = self._button(controles, "Restaurar ejemplar", lambda: self._restore_issue(seleccion["id"]), "secondary", width=175, state="disabled")
        if self.role == ROLES[0] and not self.services.read_only:
            restore.pack(side="right")
        contenedor = ctk.CTkFrame(tarjeta, fg_color=WHITE)
        contenedor.pack(fill="x", pady=(0, 12))
        def elegir(tree):
            'Actualiza la selección y habilita las acciones permitidas para la fila.'
            tabla = tree
            identificadores = tabla.selection() if tabla else ()
            seleccion["id"] = int(identificadores[0]) if identificadores else None
            restore.configure(state="normal" if identificadores and self.role == ROLES[0] else "disabled")
            indicacion.configure(text=f"Ejemplar #{seleccion['id']} seleccionado" if identificadores else "Selecciona un ejemplar de la lista.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        choose = elegir
        def reiniciar():
            'Restablece los filtros iniciales y vuelve a consultar los resultados.'
            consulta.delete(0, "end")
            desde.delete(0, "end")
            hasta.delete(0, "end")
            periodo.set("Todos")
            render()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        reset = reiniciar
        def representar():
            'Aplica los filtros y actualiza el contenido visible de esta pantalla.'
            if not self._require_access(VIEWS[5], action="Filtrar registros eliminados", view=True):
                return
            self._guardar_estado_vista()
            def obtener(pagina):
                """Solicita solo una página de ejemplares retirados."""
                return self.services.consulta('periodicos', 'buscar_eliminados', self.user, texto=consulta.get(), pagina=pagina, desde=self._fecha_iso(desde), hasta=self._fecha_iso(hasta), periodo=None if periodo.get() == "Todos" else periodo.get())
            def presentar(fila):
                """Presenta los datos necesarios para elegir una restauración."""
                return (fila['title'], f"{fila['day']:02d}/{fila['month']:02d}/{fila['year']}", fila['edition'] or 'General', fila['shelf'] or '—', display_date(fila['eliminado_el']), 'Retirado')
            self._paged_table(contenedor, obtener, presentar, [('title', 'PERIÓDICO', 210), ('date', 'PUBLICACIÓN', 130),
                ('edition', 'EDICIÓN', 170), ('shelf', 'ESTANTE', 150), ('eliminado_el', 'ELIMINACIÓN', 175), ('status', 'ESTADO', 110)], selected_callback=choose, key='eliminados')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        render = representar
        consulta.bind("<Return>", lambda _e: render())
        espera_busqueda = {'id': None}
        def buscar_al_escribir(_evento=None):
            """Actualiza coincidencias parciales tras una pausa breve al teclear."""
            if espera_busqueda['id'] is not None:
                self.after_cancel(espera_busqueda['id'])
            espera_busqueda['id'] = self.after(
                250, lambda: render() if consulta.winfo_exists() else None)
        consulta.bind('<KeyRelease>', buscar_al_escribir, add='+')
        self._registrar_estado_vista('eliminados', {'texto': consulta})
        periodo.configure(command=lambda valor: render())
        render()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _deleted_page = _eliminados_pagina

    def _restaurar_ejemplar(self, issue_id):
        """Revalida acceso maestro y conflictos de fecha, pide confirmación y restaura el ejemplar seleccionado."""
        ejemplar_id = issue_id
        identificador_ejemplar = ejemplar_id
        if identificador_ejemplar is None:
            return
        if not self._require_access(action=f"Restaurar ejemplar #{identificador_ejemplar}", master=True):
            return
        try:
            registro = self.services.periodicos.get_deleted_issue(self.user, identificador_ejemplar)
            if not registro:
                return
            conflict = self.services.periodicos.has_absent_date(self.user, registro["title"], registro["year"], registro["month"], registro["day"])
        except AccessDenied as excepcion:
            self._access_denied(excepcion)
            return
        except ValueError as excepcion:
            messagebox.showwarning('Revisar ejemplar', str(excepcion), parent=self)
            return
        if conflict:
            messagebox.showwarning("Revisar fecha", "Esta fecha está registrada sin publicación. Revisa esa anotación antes de restaurar el ejemplar.", parent=self)
            return
        if not messagebox.askyesno("Restaurar ejemplar", f"¿Restaurar {registro['title']} del {registro['day']}/{registro['month']}/{registro['year']}?\nVolverá a aparecer en el catálogo de consulta.", parent=self):
            return
        try:
            self.services.periodicos.restore_issue(self.user, identificador_ejemplar)
        except AccessDenied as excepcion:
            self._access_denied(excepcion)
            return
        except ValueError as excepcion:
            messagebox.showwarning("Revisar ejemplar", str(excepcion), parent=self)
            return
        self.navigate(VIEWS[5])
        self._notice("Ejemplar restaurado en el catálogo.")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _restore_issue = _restaurar_ejemplar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
DeletedRecordsView = VistaEliminados
