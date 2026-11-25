"""Consulta y administración del catálogo de periódicos."""

from __future__ import annotations
from utils.validaciones import validar_numero, validar_edicion
from ui.controles import TextoEditable
from ui.validacion_formularios import preparar_ejemplar
import sqlite3
import customtkinter as ctk
from datetime import date
from tkinter import messagebox
from config.settings import BG, FONT, INK, LINE, MONTHS, RED, REGIONAL, TITLES, ISSUE_STATUSES, RECORD_PERIODS, VIEWS, WHITE, REPORT_ISSUES_PERMISSION, ROLES
from services.access_service import AccessDenied
from config.declaraciones import CAMPOS_IDENTIFICACION, CAMPOS_EJEMPLAR, CAMPOS_AUSENCIA


class VistaPeriodicos:
    """Consulta y administración del catálogo de periódicos.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _consultar_pagina(self):
        'Construye los controles de consultar pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[0], action='Consultar periódicos', view=True):
            return
        self._heading('Colección de periódicos', 'Consulta de hemeroteca', 'Todos los ejemplares, del último registrado al primero. Los periodos se aplican a la fecha de registro.')
        tarjeta = self._card(1)
        for indice in range(3):
            tarjeta.grid_columnconfigure(indice, weight=1, uniform='consult_filters')
        ctk.CTkLabel(tarjeta, text='Filtros de búsqueda', text_color=INK, font=(FONT, 17, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w', padx=20, pady=(18, 12))
        desde_wrap, desde = self._date_entry(tarjeta, 'Publicación desde')
        hasta_wrap, hasta = self._date_entry(tarjeta, 'Publicación hasta')
        desde_wrap.grid(row=1, column=0, sticky='ew', padx=12, pady=12)
        hasta_wrap.grid(row=1, column=1, columnspan=2, sticky='ew', padx=12, pady=12)
        envoltura_titulo, titulo = self._combo(tarjeta, 'Periódico', ['Todos los periódicos'] + TITLES, 'Todos los periódicos')
        envoltura_titulo.grid(row=2, column=0, columnspan=2, sticky='ew', padx=12, pady=(0, 14))
        opciones_extra, tipo = self._combo(tarjeta, 'Tipo de prensa', ['Todos', 'Regional', 'Nacional'], 'Todos')
        opciones_extra.grid(row=2, column=2, sticky='ew', padx=12, pady=(0, 14))
        habilitado = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(tarjeta, text='Filtrar por periodo de registro', variable=habilitado).grid(row=3, column=0, sticky='w', padx=16, pady=12)
        envoltura_periodo, periodo = self._combo(tarjeta, 'Periodo de registro', ['Todos los registros'] + list(RECORD_PERIODS), 'Todos los registros')
        envoltura_periodo.grid(row=3, column=1, columnspan=2, sticky='ew', padx=12, pady=(0, 14))
        acciones = ctk.CTkFrame(tarjeta, fg_color='transparent')
        acciones.grid(row=4, column=0, columnspan=3, sticky='ew', padx=18, pady=(0, 16))
        self._button(acciones, 'Mostrar todos', lambda: reset(), 'secondary', width=145).pack(side='left')
        self._primary(acciones, 'Buscar', lambda: search(), width=115).pack(side='right')
        reporte_filters = {'value': {}}
        if self._can(REPORT_ISSUES_PERMISSION):
            self._button(acciones, 'Guardar resultado en PDF', lambda: self._export_pdf(scope='issues', filters=dict(reporte_filters['value'])), 'secondary', width=230).pack(side='right', padx=8)
        resultados = self._card(2, (0, 28))
        ctk.CTkLabel(resultados, text='Ejemplares registrados · Más recientes primero', text_color=INK, font=(FONT, 18, 'bold')).pack(anchor='w', padx=20, pady=(18, 12))
        contenedor = ctk.CTkFrame(resultados, fg_color=WHITE)
        contenedor.pack(fill='x', pady=(0, 12))
        nota_ausencias = self._paragraph(resultados, '')
        nota_ausencias.pack(fill='x', padx=18)
        def reiniciar():
            'Restablece los filtros iniciales y vuelve a consultar los resultados.'
            tipo.set('Todos')
            desde.delete(0, 'end')
            hasta.delete(0, 'end')
            titulo.set('Todos los periódicos')
            periodo.set('Todos los registros')
            habilitado.set(False)
            search()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        reset = reiniciar
        def search():
            'Obtiene los resultados que corresponden a los filtros elegidos.'
            if not self._require_access(VIEWS[0], action='Buscar periódicos', view=True):
                return
            filtros = {'title': None if titulo.get() == 'Todos los periódicos' else titulo.get(),
                       'kind': None if tipo.get() == 'Todos' else tipo.get(),
                       'desde': self._fecha_iso(desde), 'hasta': self._fecha_iso(hasta),
                       'period': None if periodo.get() == 'Todos los registros' else periodo.get() if habilitado.get() else None}
            self._guardar_estado_vista()
            reporte_filters['value'] = dict(filtros)
            if filtros['desde'] and filtros['desde'] == filtros['hasta']:
                fecha = date.fromisoformat(filtros['desde'])
                titulo_elegido, tipo_elegido = titulo.get(), tipo.get()
                def mostrar_ausencias(datos):
                    """Actualiza la nota sin reconstruir la tabla ni leer filtros posteriores."""
                    ausentes = self._filter_rows(datos[0], titulo_elegido, tipo_elegido)
                    nota_ausencias.configure(text='Sin publicación: ' + ', '.join(f['title'] for f in ausentes) if ausentes else '')
                self._cargar_seccion(resultados, [self.services.consulta('periodicos', 'consult_absent_dates', self.user, fecha.year, fecha.month, fecha.day)], mostrar_ausencias, clave='ausencias')
            else:
                nota_ausencias.configure(text='')
                versiones = getattr(resultados, '_versiones_carga', {})
                versiones['ausencias'] = versiones.get('ausencias', 0) + 1
            def fetch(page):
                """Obtiene del servicio una página de ocho ejemplares utilizando los filtros vigentes de la vista."""
                pagina = page
                return self.services.consulta('periodicos', 'search_issues', self.user, **filtros, page=pagina, page_size=8)
            def row(record):
                """Convierte un ejemplar en las columnas visibles de periódico, fecha, edición, ubicación y estado."""
                registro = record
                return (registro['title'], f"{registro['day']:02d}/{registro['month']:02d}/{registro['year']}",
                        f"{registro['edition'] or '—'} · N.º {registro['number'] or '—'}",
                        f"Estante {registro['shelf'] or '—'} · Gaveta {registro['drawer'] or '—'}", registro['status'])
            self._paged_table(contenedor, fetch, row, [('paper', 'PERIÓDICO', 190), ('date', 'PUBLICACIÓN', 120), ('edition', 'EDICIÓN / N.º', 180), ('location', 'UBICACIÓN FÍSICA', 220), ('status', 'ESTADO', 150)])
        self._registrar_estado_vista('consulta', {'titulo': titulo, 'tipo': tipo, 'desde': desde, 'hasta': hasta, 'periodo': periodo, 'activar_periodo': habilitado})
        periodo.configure(command=lambda valor: (habilitado.set(valor != 'Todos los registros'), search()))
        search()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _consult_page = _consultar_pagina

    def _ejemplar_creacion_permiso(self, permissions=None):
        """Elige el permiso de registro aplicable al administrador regular con Catálogo o el permiso explícito de registrar."""
        permisos = permissions
        if permisos is None:
            permisos = self._permisos_actuales()
        if self.role == ROLES[1] and VIEWS[1] in permisos:
            return VIEWS[1]
        return 'Registrar ejemplares'
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _issue_creation_permission = _ejemplar_creacion_permiso

    def _catalogo_pagina(self):
        'Construye los controles de catalogo pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action="Abrir panel del catálogo"):
            return
        self._heading("Catálogo de periódicos", "Administración de periódicos", "Elige Ejemplares o Fechas sin publicación. Cada sección muestra sus propios filtros, acciones y resultados.")
        seccion = {'actual': getattr(self, '_catalogo_seccion', 'Ejemplares')}
        pestañas = self._card(1)
        selector_seccion = ctk.CTkSegmentedButton(pestañas, values=['Ejemplares', 'Fechas sin publicación'],
                                                 height=40, font=(FONT, 14, 'bold'), text_color=INK,
                                                 fg_color=LINE, selected_color='#BDD8FF', selected_hover_color='#AACCF7',
                                                 unselected_color=WHITE, unselected_hover_color=BG,
                                                 command=lambda valor: cambiar_seccion(valor))
        selector_seccion.set(seccion['actual'])
        selector_seccion.pack(fill='x', padx=12, pady=10)
        seleccion = {"id": None}
        acceso = {"permissions": set(), "read": False}
        operations = self._card(2)
        self._paragraph(operations, "Acciones del catálogo", color=INK).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        botones = ctk.CTkFrame(operations, fg_color="transparent")
        botones.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        for columna in range(2):
            botones.grid_columnconfigure(columna, weight=1, uniform="catalog_actions")
        create = self._primary(botones, "Registrar ejemplar", self._record_form, width=0, state="disabled")
        consult = self._button(botones, "Actualizar catálogo", lambda: render(), "secondary", width=0, state="disabled")
        edit = self._button(botones, "Editar seleccionado", lambda: self._record_form(issue_id=seleccion["id"]), "secondary", width=0, state="disabled")
        delete = self._button(botones, "Eliminar seleccionado", lambda: self._delete_issue(seleccion["id"]), "danger", width=0, state="disabled")
        accion_buttons = (create, consult, edit, delete)
        for indice, boton in enumerate(accion_buttons):
            boton.grid(row=indice // 2, column=indice % 2, sticky="ew", padx=6, pady=5)
        layout = {"columns": 2}
        def ajustar_actions(_event):
            """Reorganiza los botones del catálogo en una o dos columnas solo cuando cambia el ancho efectivo."""
            _evento_local = _event
            _evento = _evento_local
            columnas = 1 if botones._reverse_widget_scaling(botones.winfo_width()) < 360 else 2
            if columnas == layout["columns"]:
                return
            layout["columns"] = columnas
            for columna in range(2):
                botones.grid_columnconfigure(columna, weight=1 if columna < columnas else 0,
                                             uniform="catalog_actions" if columna < columnas else "")
            for indice, boton in enumerate(accion_buttons):
                boton.grid_configure(row=indice // columnas, column=indice % columnas)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        ajustar_actions_local = ajustar_actions
        botones.bind("<Configure>", ajustar_actions_local)
        indicio_permisos = self._paragraph(operations, "")
        indicio_permisos.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 14))
        filtros = self._card(3)
        for indice_breve in range(3):
            filtros.grid_columnconfigure(indice_breve, weight=1, uniform="catalog_filters")
        ctk.CTkLabel(filtros, text="Filtrar catálogo", text_color=INK, font=(FONT, 17, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 12))
        envoltura_titulo, titulo = self._combo(filtros, "Periódico", ["Todos los periódicos"] + TITLES, "Todos los periódicos")
        envoltura_titulo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 14))
        opciones_extra, tipo = self._combo(filtros, "Tipo de prensa", ["Todos", "Regional", "Nacional"], "Todos")
        opciones_extra.grid(row=1, column=2, sticky="ew", padx=12, pady=(0, 14))
        envoltura_anio, anio = self._combo(filtros, "Año", ["Todos"] + [str(anio_breve) for anio_breve in range(date.today().year, 1969, -1)], "Todos")
        envoltura_mes, mes = self._combo(filtros, "Mes", ["Todos"] + MONTHS, "Todos")
        envoltura_dia, dia = self._combo(filtros, "Día", ["Todos"] + [str(dia_breve) for dia_breve in range(1, 32)], "Todos")
        for indice_breve, envoltura in enumerate((envoltura_anio, envoltura_mes, envoltura_dia)):
            envoltura.grid(row=2, column=indice_breve, sticky="ew", padx=12, pady=(0, 14))
        self._connect_date_fields(anio, mes, dia, allow_all=True)
        acciones = ctk.CTkFrame(filtros, fg_color="transparent")
        acciones.grid(row=3, column=0, columnspan=3, sticky="ew", padx=18, pady=(0, 16))
        filtrar_boton = self._primary(acciones, "Filtrar catálogo", lambda: render(), width=155, state="disabled")
        filtrar_boton.pack(side="right")
        reiniciar_boton = self._button(acciones, "Limpiar filtros", lambda: reset(), "secondary", width=135, state="disabled")
        reiniciar_boton.pack(side="right", padx=8)
        reporte_filters = {'value': {}}
        reporte_boton = None
        if self._can(REPORT_ISSUES_PERMISSION):
            reporte_boton = self._button(acciones, 'Guardar resultado en PDF', lambda: self._export_pdf(scope='issues', filters=dict(reporte_filters['value'])), 'secondary', width=230, state="disabled")
            reporte_boton.pack(side='left')
        listing = self._card(4)
        ctk.CTkLabel(listing, text="Ejemplares registrados", text_color=INK, font=(FONT, 18, "bold")).pack(anchor="w", padx=20, pady=(18, 12))
        controles = ctk.CTkFrame(listing, fg_color=BG, corner_radius=8)
        controles.pack(fill="x", padx=18, pady=(0, 12))
        indicacion = self._paragraph(controles, "Selecciona un ejemplar para habilitar Editar o Eliminar si tienes el permiso.")
        indicacion.pack(fill="x", padx=12, pady=10)
        contenedor = ctk.CTkFrame(listing, fg_color=WHITE)
        contenedor.pack(fill="x", pady=(0, 12))
        absent_tarjeta = self._card(5, (0, 24))
        bar = ctk.CTkFrame(absent_tarjeta, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(16, 10))
        self._paragraph(absent_tarjeta, "Fechas sin publicación", color=INK).pack(before=bar, fill="x", padx=20, pady=(16, 0))
        absent_boton = self._button(bar, "Registrar fecha", lambda: self._record_form(absent=True), "primary", width=140, state="disabled")
        absent_boton.pack(side="left", padx=(0, 8))
        filtros_ausencia = ctk.CTkFrame(absent_tarjeta, fg_color='transparent')
        filtros_ausencia.pack(fill='x', padx=20, pady=8)
        filtros_ausencia.grid_columnconfigure((0, 1), weight=1, uniform='filtros_ausencia')
        filtro_ausencia_wrap, filtro_ausencia = self._combo(filtros_ausencia, 'Observaciones', ['Todas', 'Con observación', 'Sin observación'], 'Todas')
        filtro_ausencia_wrap.grid(row=0, column=1, sticky='ew', padx=(8, 0), pady=6)
        filtro_ausencia.configure(command=lambda valor: render())
        aus_desde_wrap, aus_desde = self._date_entry(filtros_ausencia, 'Desde')
        aus_hasta_wrap, aus_hasta = self._date_entry(filtros_ausencia, 'Hasta')
        aus_titulo_wrap, aus_titulo = self._combo(filtros_ausencia, 'Periódico', ['Todos los periódicos'] + TITLES)
        aus_titulo_wrap.grid(row=0, column=0, sticky='ew', padx=(0, 8), pady=6)
        aus_desde_wrap.grid(row=1, column=0, sticky='ew', padx=(0, 8), pady=6)
        aus_hasta_wrap.grid(row=1, column=1, sticky='ew', padx=(8, 0), pady=6)
        self._button(absent_tarjeta, 'Filtrar fechas sin publicación', lambda: render(), 'primary').pack(padx=20, pady=8)
        ausencia_elegida = {'id': None}
        def elegir_ausencia(tabla):
            """Habilita la corrección solo con selección y permiso de registro."""
            seleccion = tabla.selection() if tabla else ()
            ausencia_elegida['id'] = int(seleccion[0]) if seleccion else None
            corregir.configure(state='normal' if seleccion and 'Registrar ejemplares' in acceso['permissions'] else 'disabled')
        def anular_ausencia():
            """Retira una anotación errónea tras confirmación y registra la acción."""
            identificador = ausencia_elegida['id']
            if identificador is None or not self._require_access('Registrar ejemplares', action='Anular fecha sin publicación'):
                return
            if not messagebox.askyesno('Corregir fecha sin publicación', '¿Anular la anotación seleccionada? La acción quedará en auditoría y permitirá registrar ejemplares de esa fecha.', parent=self):
                return
            try:
                self.services.periodicos.corregir_fecha_ausente(self.user, identificador, anular=True)
            except ValueError as error:
                messagebox.showwarning('No se corrigió la anotación', str(error), parent=self)
                return
            render()
        corregir = self._button(bar, 'Anular anotación incorrecta', anular_ausencia, 'primary', width=230, state='disabled')
        corregir.pack(side='left')
        missing_holder = ctk.CTkFrame(absent_tarjeta, fg_color=WHITE)
        missing_holder.pack(fill="x", pady=(0, 12))
        def elegir(tree):
            'Actualiza la selección y habilita las acciones permitidas para la fila.'
            tabla = tree
            seleccionado = tabla.selection() if tabla else ()
            seleccion["id"] = int(seleccionado[0]) if seleccionado else None
            permisos = acceso["permissions"]
            edit.configure(state="normal" if seleccionado and "Editar ejemplares" in permisos else "disabled")
            delete.configure(state="normal" if seleccionado and "Eliminar ejemplares" in permisos else "disabled")
            indicacion.configure(text=f"Ejemplar #{seleccion['id']} seleccionado. Las acciones disponibles dependen de tus permisos." if seleccionado else "Selecciona un ejemplar para habilitar Editar o Eliminar si tienes el permiso.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        choose = elegir
        def actualizar_permisos():
            """Consulta permisos vigentes y actualiza acciones, filtros, exportación y texto explicativo del catálogo."""
            permisos = set(self._permisos_actuales())
            acceso["permissions"] = permisos
            acceso["read"] = VIEWS[1] in permisos or bool(permisos & {"Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"})
            puede_crear = self._issue_creation_permission(permisos) in permisos
            create.configure(state="normal" if puede_crear else "disabled")
            for boton in (consult, filtrar_boton, reiniciar_boton):
                boton.configure(state="normal" if acceso["read"] else "disabled")
            for campo in (titulo, tipo, anio, mes, dia):
                campo.configure(state="readonly" if acceso["read"] else "disabled")
            absent_boton.configure(state="normal" if "Registrar ejemplares" in permisos else "disabled")
            if reporte_boton:
                reporte_boton.configure(state="normal" if acceso["read"] and REPORT_ISSUES_PERMISSION in permisos else "disabled")
            statuses = (("Registrar", puede_crear), ("Consultar", acceso["read"]),
                        ("Editar", "Editar ejemplares" in permisos),
                        ("Eliminar", "Eliminar ejemplares" in permisos))
            indicio_permisos.configure(text=" · ".join(f"{nombre}: {'autorizado' if permitidos else 'sin permiso'}" for nombre, permitidos in statuses)
                                      + ".\nSolicita los accesos que necesitas en Solicitudes de acceso. Las aprobaciones se actualizan automáticamente.")
            choose(None)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        actualizar_permisos_local = actualizar_permisos
        def aplicar_filters(records):
            """Filtra registros en memoria por periódico, tipo y las partes de fecha seleccionadas."""
            registros = records
            registros = self._filter_rows(registros, titulo.get(), tipo.get())
            for nombre, valor in (("year", anio.get()), ("month", mes.get()), ("day", dia.get())):
                if valor != "Todos":
                    numero = MONTHS.index(valor) + 1 if nombre == "month" else int(valor)
                    registros = [registro_breve for registro_breve in registros if registro_breve[nombre] == numero]
            return registros
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        aplicar_filters_local = aplicar_filters
        def reiniciar():
            'Restablece los filtros iniciales y vuelve a consultar los resultados.'
            titulo.set("Todos los periódicos")
            for campo in (tipo, anio, mes, dia):
                campo.set("Todos")
            render()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        reset = reiniciar
        def representar():
            'Aplica los filtros y actualiza el contenido visible de esta pantalla.'
            if not self._require_access(action="Actualizar panel del catálogo"):
                return
            actualizar_permisos_local()
            if not acceso["read"]:
                self._vaciar_contenedor(contenedor)
                self._vaciar_contenedor(missing_holder)
                self._empty(contenedor, "Catálogo pendiente de autorización", "Los botones están deshabilitados porque aún no tienes permisos. Solicita Catálogo de periódicos para consultar y, si eres administrador regular, registrar ejemplares.")
                self._empty(missing_holder, "Se requiere permiso de catálogo", "Registrar fecha requiere además el permiso Registrar ejemplares.")
                return
            if not self._require_access(VIEWS[1], action="Consultar catálogo", view=True):
                return
            self._guardar_estado_vista()
            reporte_filters['value'] = {'title': None if titulo.get() == 'Todos los periódicos' else titulo.get(),
                'kind': None if tipo.get() == 'Todos' else tipo.get(),
                'year': None if anio.get() == 'Todos' else int(anio.get()),
                'month': None if mes.get() == 'Todos' else MONTHS.index(mes.get()) + 1,
                'day': None if dia.get() == 'Todos' else int(dia.get())}
            filtros = dict(reporte_filters['value'])
            if seccion['actual'] == 'Ejemplares':
                def obtener_ejemplares(pagina):
                    """Solicita una página autorizada del catálogo aplicando filtros SQL."""
                    return self.services.consulta('periodicos', 'search_issues', self.user, catalog=True, page=pagina, **filtros)
                def presentar_ejemplar(fila):
                    """Convierte una ficha de servicio en las columnas de la tabla."""
                    return (fila['title'], f"{fila['day']:02d}/{fila['month']:02d}/{fila['year']}",
                            f"{fila['edition'] or 'General'} · {fila['number'] or '—'}",
                            f"Estante {fila['shelf'] or '—'} · Gaveta {fila['drawer'] or '—'}", fila['status'])
                self._paged_table(contenedor, obtener_ejemplares, presentar_ejemplar,
                    [('title', 'PERIÓDICO', 190), ('date', 'FECHA', 120), ('edition', 'EDICIÓN / N.º', 180),
                     ('loc', 'UBICACIÓN', 220), ('status', 'ESTADO', 130)], selected_callback=choose, key='catalogo')
            else:
                def obtener_ausencias(pagina):
                    """Solicita cinco anotaciones sin descargar el historial completo."""
                    return self.services.consulta('periodicos', 'buscar_fechas_ausentes', self.user, page=pagina, observaciones=filtro_ausencia.get(), **dict(filtros, title=None if aus_titulo.get() == 'Todos los periódicos' else aus_titulo.get(), kind=None, year=None, month=None, day=None, desde=self._fecha_iso(aus_desde), hasta=self._fecha_iso(aus_hasta)))
                def presentar_ausencia(fila):
                    """Presenta fecha, periódico y observación sin publicación."""
                    return (fila['title'], f"{fila['day']:02d}/{fila['month']:02d}/{fila['year']}", fila['kind'], fila['note'] or 'Sin observación')
                self._paged_table(missing_holder, obtener_ausencias, presentar_ausencia,
                    [('title', 'PERIÓDICO', 210), ('date', 'FECHA', 130), ('kind', 'TIPO', 120), ('note', 'OBSERVACIÓN', 280)],
                    selected_callback=elegir_ausencia, key='ausencias')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        render = representar

        def cambiar_seccion(valor):
            """Muestra una sola tarea y conserva filtros y páginas de ambas secciones."""
            for recipiente in (contenedor, missing_holder):
                tabla_previa = getattr(recipiente, '_tabla_paginada', None)
                if tabla_previa and tabla_previa['area'].winfo_exists():
                    tabla_previa['nav'].pack_forget()
                    versiones = getattr(tabla_previa['area'], '_versiones_carga', {})
                    versiones['datos'] = versiones.get('datos', 0) + 1
            seccion['actual'] = valor
            self._catalogo_seccion = valor
            for tarjeta in (operations, filtros, listing):
                if valor == 'Ejemplares':
                    tarjeta.grid()
                else:
                    tarjeta.grid_remove()
            if valor == 'Fechas sin publicación':
                absent_tarjeta.grid()
            else:
                absent_tarjeta.grid_remove()
            self.content._parent_canvas.yview_moveto(0)
            render()

        self._registrar_estado_vista('catalogo', {'titulo': titulo, 'tipo': tipo, 'anio': anio, 'mes': mes, 'dia': dia})
        cambiar_seccion(seccion['actual'])
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _catalog_page = _catalogo_pagina

    def _registro_formulario(self, absent=False, issue_id=None):
        'Construye y valida el formulario declarativo de ejemplar o ausencia.'
        ejemplar_id = issue_id
        sin_publicacion = absent
        identificador_ejemplar = ejemplar_id
        permiso = ("Editar ejemplares" if identificador_ejemplar is not None else
                      "Registrar ejemplares" if sin_publicacion else self._issue_creation_permission())
        if not self._require_access(permiso, action=f"Abrir formulario: {permiso}"):
            return
        if sin_publicacion:
            return self._formulario_ausencia()
        existente = self.services.periodicos.get_issue(self.user, identificador_ejemplar, permission=permiso) if identificador_ejemplar is not None else None
        if identificador_ejemplar is not None and existente is None:
            return
        titulo_texto = "Editar ejemplar" if existente else "Registrar fecha sin publicación" if sin_publicacion else "Registrar ejemplar"
        dialogo = self._dialog(titulo_texto, "740x720")
        pie = ctk.CTkFrame(dialogo, fg_color=WHITE, corner_radius=0)
        pie.pack(side="bottom", fill="x")
        panel = self._scrollable(dialogo, fg_color=BG, corner_radius=0)
        panel.pack(fill="both", expand=True, padx=20, pady=18)
        ctk.CTkLabel(panel, text=titulo_texto, text_color=INK, font=(FONT, 26, "bold")).pack(anchor="w", pady=(0, 8))
        self._paragraph(panel, "* Campos obligatorios · Colección de 1970 a 2100 · Indica estante, gaveta o ambos").pack(fill="x", pady=(0, 14))
        tarjeta = ctk.CTkFrame(panel, fg_color=WHITE, corner_radius=12, border_width=1, border_color=LINE)
        tarjeta.pack(fill="x")
        for indice_breve in range(2):
            tarjeta.grid_columnconfigure(indice_breve, weight=1, uniform="record_fields")
        campos = {}
        declaraciones = CAMPOS_IDENTIFICACION + (CAMPOS_AUSENCIA if sin_publicacion else CAMPOS_EJEMPLAR)
        especificaciones = [(campo.etiqueta, campo.tipo, list(campo.opciones) if campo.tipo == 'combo' else campo.opciones) for campo in declaraciones]
        especificaciones = [campo for campo in especificaciones if campo[0] not in ('Año', 'Mes', 'Día')]
        especificaciones.insert(1, ('Fecha de publicación', 'fecha', None))
        for posicion, (nombre, tipo, valores) in enumerate(especificaciones):
            fila, col = divmod(posicion, 2)
            etiqueta = nombre + (" *" if nombre not in ("Observación", "Estante", "Gaveta") else "")
            if tipo == 'fecha':
                envoltura, control = self._date_entry(tarjeta, etiqueta)
            else:
                envoltura, control = self._entry(tarjeta, etiqueta, valores) if tipo == "entry" else self._combo(tarjeta, etiqueta, valores)
            envoltura.grid(row=fila, column=col, sticky="ew", padx=16, pady=12)
            campos[nombre] = control
            if nombre in ("Número", "Estante", "Gaveta"):
                self._solo_numeros(control, 12)
        type_note = self._paragraph(panel, "")
        type_note.pack(fill="x", pady=(12, 0))
        campos["Periódico"].configure(command=lambda value: type_note.configure(text=f"Tipo de prensa: {'Regional' if value in REGIONAL else 'Nacional'} (según el periódico seleccionado)."))
        if existente:
            correspondencias = {"Periódico": existente["title"], "Fecha de publicación": f"{existente['day']:02d}/{existente['month']:02d}/{existente['year']}", "Edición": existente["edition"], "Número": existente["number"], "Estante": existente["shelf"], "Gaveta": existente["drawer"], "Estado": existente["status"]}
            for nombre, valor in correspondencias.items():
                control = campos[nombre]
                if isinstance(control, ctk.CTkComboBox):
                    control.set(valor)
                else:
                    control.insert(0, valor or "")
        type_note.configure(text=f"Tipo de prensa: {'Regional' if campos['Periódico'].get() in REGIONAL else 'Nacional'} (según el periódico seleccionado).")
        aviso_ubicacion = self._paragraph(panel, 'Ubicación obligatoria: completa Estante, Gaveta o ambos con números.', color=RED)
        aviso_ubicacion.pack(fill='x', pady=(8, 0))
        # El motivo del bloqueo permanece visible aunque el formulario esté desplazado.
        error = self._paragraph(pie, "", color=RED)
        error.pack(fill="x", padx=20, pady=(8, 0))
        estado_validacion = {'valores': None, 'valido': None}

        def leer_campos():
            """Obtiene los valores actuales para validar y guardar exactamente los mismos datos."""
            return {nombre: control.get() for nombre, control in campos.items()}

        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            if not self._require_access(permiso, action=f"Guardar registro: {permiso}", parent=dialogo):
                return
            try:
                valores = preparar_ejemplar(leer_campos())
                self.services.periodicos.save_record(self.user, valores, absent=False, issue_id=identificador_ejemplar, expected_revision=existente["revision"] if existente else None)
            except AccessDenied as excepcion:
                self._access_denied(excepcion, parent=dialogo)
                return
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            except sqlite3.IntegrityError:
                error.configure(text="Ya existe un registro con ese periódico, fecha, edición y número.")
                return
            dialogo.destroy()
            self.navigate(self.current_view)
            self._notice("Cambios guardados." if existente else "Registro guardado correctamente.")
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        guardar_boton = self._primary(pie, "Guardar cambios" if existente else "Guardar fecha" if sin_publicacion else "Guardar ejemplar", save, width=170)
        guardar_boton.pack(side="right", padx=(8, 20), pady=14)
        def validar_estado():
            """Actualiza botón y motivo al cambiar datos, sin ocultar errores devueltos al guardar."""
            if not dialogo.winfo_exists():
                return
            pendiente = getattr(dialogo, '_validacion_pendiente', None)
            if pendiente:
                dialogo.after_cancel(pendiente)
                dialogo._validacion_pendiente = None
            valores = leer_campos()
            if valores != estado_validacion['valores']:
                mensaje = ''
                try:
                    preparar_ejemplar(valores)
                except ValueError as excepcion:
                    mensaje = str(excepcion)
                valido = not mensaje
                if valido != estado_validacion['valido']:
                    guardar_boton.configure(state='normal' if valido else 'disabled')
                error.configure(text=mensaje)
                aviso_ubicacion.configure(text='' if valores['Estante'].strip() or valores['Gaveta'].strip() else 'Ubicación obligatoria: completa Estante, Gaveta o ambos con números.')
                estado_validacion.update(valores=valores, valido=valido)
            dialogo._validacion_pendiente = dialogo.after(200, validar_estado)

        def cancelar_validacion(evento):
            """Cancela el temporizador del diálogo al cerrarlo, antes de liberar sus comandos Tcl."""
            if evento.widget is dialogo:
                pendiente = getattr(dialogo, '_validacion_pendiente', None)
                if pendiente:
                    dialogo.after_cancel(pendiente)
                    dialogo._validacion_pendiente = None

        # El temporizador cubre cambios de calendario y selector sin sustituir callbacks.
        for control in campos.values():
            control.bind('<KeyRelease>', lambda evento: validar_estado())
        dialogo.bind('<Destroy>', cancelar_validacion, add='+')
        validar_estado()
        self._button(pie, "Cancelar", dialogo.destroy, "secondary", width=120).pack(side="right", pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _record_form = _registro_formulario

    def _formulario_ausencia(self):
        """Registra una ausencia con un único calendario y observación de varias líneas."""
        dialogo = self._dialog('Registrar fecha sin publicación', '680x650')
        pie = ctk.CTkFrame(dialogo, fg_color=WHITE)
        pie.pack(side='bottom', fill='x')
        panel = self._scrollable(dialogo, fg_color=WHITE)
        panel.pack(fill='both', expand=True, padx=20, pady=18)
        self._paragraph(panel, 'Elige el periódico y una fecha entre 1970 y 2100, ambos incluidos.').pack(fill='x', padx=16, pady=12)
        envoltura, titulo = self._combo(panel, 'Periódico *', TITLES)
        envoltura.pack(fill='x', padx=16, pady=10)
        envoltura, fecha = self._date_entry(panel, 'Fecha sin publicación *')
        envoltura.pack(fill='x', padx=16, pady=10)
        self._label(panel, 'Observaciones (opcionales, máximo 1.000 caracteres)').pack(anchor='w', padx=16, pady=(14, 6))
        nota = TextoEditable(panel, height=160, wrap='word', fg_color=BG, text_color=INK, font=(FONT, 13))
        nota.pack(fill='x', padx=16)
        error = self._paragraph(panel, '', color=RED)
        error.pack(fill='x', padx=16, pady=10)
        def guardar():
            """Valida y delega el alta al mismo servicio autorizado y transaccional."""
            try:
                valor = self._fecha_iso(fecha)
                if not valor:
                    raise ValueError('Selecciona la fecha con el calendario.')
                elegida = date.fromisoformat(valor)
                tipo = 'Regional' if titulo.get() in REGIONAL else 'Nacional'
                valores = (titulo.get(), tipo, elegida.year, elegida.month, elegida.day, nota.get('1.0', 'end-1c').strip())
                self.services.periodicos.save_record(self.user, valores, absent=True)
            except AccessDenied as excepcion:
                self._access_denied(excepcion, parent=dialogo)
                return
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            except sqlite3.IntegrityError:
                error.configure(text='Ya existe una anotación para ese periódico y fecha.')
                return
            dialogo.destroy()
            self.navigate(self.current_view)
            self._notice('Fecha sin publicación registrada.')
        self._primary(pie, 'Guardar fecha', guardar).pack(side='right', padx=16, pady=14)
        self._button(pie, 'Cancelar', dialogo.destroy, 'secondary').pack(side='right', pady=14)

    def _eliminar_ejemplar(self, issue_id):
        """Revalida permiso y ejemplar, solicita confirmación y realiza su retiro lógico antes de actualizar el catálogo."""
        ejemplar_id = issue_id
        identificador_ejemplar = ejemplar_id
        if identificador_ejemplar is None:
            return
        if not self._require_access("Eliminar ejemplares", action=f"Eliminar ejemplar #{identificador_ejemplar}"):
            return
        registro = self.services.periodicos.get_issue(self.user, identificador_ejemplar, permission="Eliminar ejemplares")
        if not registro:
            return
        if not messagebox.askyesno("Eliminar ejemplar", f"¿Enviar {registro['title']} del {registro['day']}/{registro['month']}/{registro['year']} a Registros eliminados?\n\nSolo el administrador maestro podrá restaurarlo.", parent=self):
            return
        try:
            self.services.periodicos.delete_issue(self.user, identificador_ejemplar)
        except AccessDenied as excepcion:
            self._access_denied(excepcion)
            return
        except ValueError as excepcion:
            messagebox.showwarning("Revisar ejemplar", str(excepcion), parent=self)
            return
        self.navigate(VIEWS[1])
        self._notice("Ejemplar enviado a Registros eliminados.")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _delete_issue = _eliminar_ejemplar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
PeriodicosView = VistaPeriodicos
