"""Controles reutilizables, tablas, filtros y paginación."""

from __future__ import annotations
import calendar
import customtkinter as ctk
from datetime import date
from tkinter import ttk
from ui.controles import EntradaEditable, MarcoDesplazable, SelectorCompacto, EntradaDocumento, EntradaFecha, abrir_calendario
from config.settings import BG, BLUE, BLUE_HOVER, FONT, GREEN, INK, LINE, MONTHS, MUTED, SOFT, TITLES, WHITE


class ComponentesInterfaz:
    """Controles reutilizables, tablas, filtros y paginación.

    Comparte el controlador Tkinter y los servicios de HemerotecaApp.
    """

    def _marco_campo(self, padre, etiqueta):
        """Crea el contenedor y la etiqueta comunes a entradas, fechas y selectores.

        El llamador añade el control y decide dónde colocar el contenedor;
        así se conservan el orden de tabulación y la distribución de cada vista.
        """
        caja = ctk.CTkFrame(padre, fg_color='transparent')
        self._label(caja, etiqueta).pack(anchor='w', pady=(0, 6))
        return caja

    def _vaciar_contenedor(self, contenedor):
        """Destruye los hijos directos y ejecuta sus enlaces de limpieza habituales.

        Debe llamarse desde Tk. Conserva el propio contenedor y sus opciones
        geométricas; las tablas retiradas liberan también su barra de paginación.
        """
        for hijo in contenedor.winfo_children():
            hijo.destroy()

    def _preparar_estilo_tablas(self, padre):
        """Configura el estilo una vez por intérprete Tk y lo repone si cambia el tema.

        Evita emitir cambios globales de tema al paginar o abrir otra tabla.
        La marca pertenece a la raíz de Tk, no al proceso: dos ventanas raíz
        independientes reciben cada una su propia configuración.
        """
        raiz = padre._root()
        estilo = ttk.Style(master=padre)
        if getattr(raiz, '_estilo_tablas_preparado', False) and estilo.theme_use() == 'clam':
            return
        estilo.theme_use('clam')
        estilo.configure('Hemeroteca.Treeview', background=WHITE, foreground=INK, fieldbackground=WHITE,
                         rowheight=42, borderwidth=0, font=(FONT, 11))
        estilo.configure('Hemeroteca.Treeview.Heading', background='#F5F7FB', foreground=MUTED,
                         relief='flat', padding=(10, 10), font=(FONT, 10, 'bold'))
        estilo.map('Hemeroteca.Treeview', background=[('selected', SOFT)], foreground=[('selected', INK)])
        raiz._estilo_tablas_preparado = True

    def _etiqueta(self, parent, text, **kwargs):
        """Crea una etiqueta con tipografía y color comunes y permite añadir opciones de presentación."""
        opciones = kwargs
        padre = parent
        texto = text
        return ctk.CTkLabel(padre, text=texto, text_color=INK, font=(FONT, 12, "bold"), **opciones)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _label = _etiqueta

    def _entrada(self, parent, label, placeholder="", show=None):
        """Devuelve contenedor y entrada editable con etiqueta, texto de ayuda y resaltado del foco; admite máscara de contraseña."""
        etiqueta = label
        padre = parent
        caja = self._marco_campo(padre, etiqueta)
        entrada = EntradaEditable(caja, height=44, corner_radius=8, border_width=1, border_color=LINE, fg_color=WHITE,
                             text_color=INK, placeholder_text=placeholder, font=(FONT, 13), show=show or "")
        entrada.pack(fill="x")
        entrada.bind("<FocusIn>", lambda _e: entrada.configure(border_color=BLUE))
        entrada.bind("<FocusOut>", lambda _e: entrada.configure(border_color=LINE))
        return caja, entrada
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _entry = _entrada

    def _document_entry(self, padre, etiqueta):
        """Construye una cédula con tipo separado y número validado al escribir."""
        caja = self._marco_campo(padre, etiqueta)
        control = EntradaDocumento(caja)
        control.pack(fill='x')
        return caja, control

    def _fecha_iso(self, control):
        """Convierte el calendario opcional al formato que validan los servicios."""
        from utils.dates import parse_filter_date
        fecha = parse_filter_date(control.get())
        return fecha.isoformat() if fecha else None

    def _date_entry(self, padre, etiqueta):
        """Construye una fecha de calendario sin entrada manual."""
        caja = self._marco_campo(padre, etiqueta)
        control = EntradaFecha(caja)
        control.pack(fill='x')
        return caja, control

    def _solo_numeros(self, control, maximo):
        """Bloquea letras, espacios y símbolos incluso al pegar texto."""
        control.configure(validate='key', validatecommand=(control.register(
            lambda valor: len(valor) <= maximo and (not valor or valor.isascii() and valor.isdigit())), '%P'))

    def _selector_control(self, parent, values, default=None, command=None, **kwargs):
        """Crea un selector compacto de solo lectura con opciones, valor inicial y callback, respetando ajustes del llamador."""
        comando = command
        predeterminado = default
        opciones = kwargs
        padre = parent
        valores = values
        opciones_control = dict(values=valores, height=44, width=140, corner_radius=8,
                       border_width=1, border_color=LINE, fg_color=WHITE,
                       text_color=INK, text_color_disabled=MUTED, button_color=SOFT,
                       button_hover_color="#DCE9FC", dropdown_fg_color=WHITE,
                       dropdown_hover_color=SOFT, dropdown_text_color=INK,
                       font=(FONT, 13), dropdown_font=(FONT, 13), state="readonly",
                       command=comando)
        opciones_control.update(opciones)
        selector = SelectorCompacto(padre, **opciones_control)
        selector.set(predeterminado if predeterminado is not None else (valores[0] if valores else "Sin opciones"))
        return selector
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _combo_control = _selector_control

    def _selector(self, parent, label, values, default=None):
        """Devuelve el contenedor etiquetado y el selector compacto para que la vista decida su colocación."""
        predeterminado = default
        etiqueta = label
        padre = parent
        valores = values
        caja = self._marco_campo(padre, etiqueta)
        selector = self._combo_control(caja, valores, predeterminado)
        selector.pack(fill="x")
        if predeterminado:
            selector.set(predeterminado)
        return caja, selector
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _combo = _selector

    def _principal(self, parent, text, command, **kw):
        """Crea un botón de acción principal reutilizando la fábrica común de botones."""
        comando = command
        opciones_extra = kw
        padre = parent
        texto = text
        return self._button(padre, texto, comando, **opciones_extra)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _primary = _principal

    def _boton(self, parent, text, command, variant="primary", **kwargs):
        """Construye un botón con la paleta de su variante y permite sobrescribir dimensiones y estado."""
        comando = command
        opciones = kwargs
        padre = parent
        texto = text
        palette = {
            "primary": (BLUE, BLUE_HOVER, WHITE, BLUE),
            "secondary": (WHITE, SOFT, INK, LINE),
            "danger": ("#FFF1F0", "#FBE2DF", "#A83D35", "#EDC7C3"),
            "success": ("#E9F6EF", "#D5EDDF", "#126B49", "#BBDECD"),
        }
        color, resaltado, texto_color, borde = palette[variant]
        opciones_control = dict(height=44, width=140, corner_radius=8, border_width=1,
                       fg_color=color, hover_color=resaltado, text_color=texto_color,
                       border_color=borde, text_color_disabled="#94A3B8",
                       font=(FONT, 13, "bold"))
        opciones_control.update(opciones)
        return ctk.CTkButton(padre, text=texto, command=comando, **opciones_control)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _button = _boton

    def _vacio(self, parent, title, detail=""):
        """Muestra una tarjeta de ausencia de resultados con título y detalle adaptado al ancho disponible."""
        detalle = detail
        padre = parent
        titulo = title
        caja = ctk.CTkFrame(padre, fg_color=BG, corner_radius=10)
        caja.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(caja, text=titulo, text_color=INK, font=(FONT, 16, "bold")).pack(padx=16, pady=(22, 5))
        if detalle:
            etiqueta = ctk.CTkLabel(caja, text=detalle, text_color=MUTED, font=(FONT, 12), wraplength=500, justify="center")
            etiqueta.pack(fill="x", padx=16, pady=(0, 20))
            caja.bind("<Configure>", lambda e: etiqueta.configure(wraplength=max(200, e.width - 40)))
        return caja
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _empty = _vacio

    def _aviso(self, text):
        """Actualiza el mensaje de estado si la etiqueta de la pantalla sigue existiendo."""
        texto = text
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.configure(text=texto, text_color=GREEN)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _notice = _aviso

    def _dialogo(self, title, geometry="650x620"):
        """Abre un diálogo modal ajustado a la pantalla con cierre mediante Escape y foco diferido."""
        titulo = title
        dialogo = ctk.CTkToplevel(self)
        dialogo.title(titulo)
        requested_width, requested_height = (int(valor) for valor in geometry.split('x'))
        disponibles_width = max(440, self._reverse_window_scaling(self.winfo_screenwidth()) - 64)
        disponibles_height = max(360, self._reverse_window_scaling(self.winfo_screenheight()) - 100)
        ancho, alto = min(requested_width, disponibles_width), min(requested_height, disponibles_height)
        dialogo.geometry(f'{ancho}x{alto}')
        dialogo.minsize(min(500, ancho), min(400, alto))
        dialogo.configure(fg_color=BG)
        dialogo.transient(self)
        dialogo.grab_set()
        dialogo.bind("<Escape>", lambda _e: dialogo.destroy())
        dialogo.after(80, dialogo.focus_force)
        return dialogo
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _dialog = _dialogo

    def _desplazable(self, parent, **kwargs):
        """Crea un marco desplazable con barra condicional y navegación por páginas mediante teclado."""
        opciones = kwargs
        padre = parent
        marco = MarcoDesplazable(padre, **opciones)
        # Actualiza solo los rangos que cambian para evitar redibujos innecesarios
        # de la barra mientras se ajusta el tamaño del contenido.
        def actualizar_barra(start, end):
            """Actualiza el rango solo cuando cambia y oculta la barra si todo el contenido cabe en el marco."""
            fin = end
            inicio = start
            valores = float(inicio), float(fin)
            if any(abs(a - b) > 0.000001 for a, b in zip(valores, marco._scrollbar.get())):
                marco._scrollbar.set(*valores)
            if valores[1] - valores[0] >= .999999:
                marco._scrollbar.grid_remove()
            else:
                marco._scrollbar.grid()
        for tecla, unidades in (('<Next>', 1), ('<Prior>', -1)):
            marco._parent_canvas.bind(tecla, lambda evento, unidades=unidades: marco._parent_canvas.yview_scroll(unidades, 'pages'))
        marco._parent_canvas.bind('<Home>', lambda evento: marco._parent_canvas.yview_moveto(0))
        marco._parent_canvas.bind('<End>', lambda evento: marco._parent_canvas.yview_moveto(1))
        marco._parent_canvas.configure(takefocus=True)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        actualizar_barra_local = actualizar_barra
        marco._parent_canvas.configure(yscrollcommand=actualizar_barra_local)
        return marco
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _scrollable = _desplazable

    def _parrafo(self, parent, text, color=MUTED, **kwargs):
        """Crea una etiqueta de texto multilínea que ajusta su envoltura al ancho de su contenedor."""
        opciones = kwargs
        padre = parent
        texto = text
        etiqueta = ctk.CTkLabel(padre, text=texto, text_color=color, font=(FONT, 12),
                             justify="left", anchor="w", wraplength=420, **opciones)
        # CTkLabel emite eventos de su texto interno y de su Canvas. Medir siempre
        # el contenedor exterior evita alternar entre dos anchos diferentes.
        etiqueta.bind("<Configure>", lambda _e: self._fit_text(etiqueta, etiqueta.winfo_width()))
        return etiqueta
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _paragraph = _parrafo

    @staticmethod
    def _ajustar_texto(label, width):
        # Configure se emite también después de cambiar el texto. No redibujar
        # si el ancho sigue igual evita ciclos de ajuste con el área desplazable.
        """Recalcula la envoltura según el escalado y evita redibujar si el ancho efectivo sigue igual."""
        etiqueta = label
        ancho = width
        envoltura = max(180, int(etiqueta._reverse_widget_scaling(ancho)) - 8)
        if etiqueta.cget("wraplength") != envoltura:
            etiqueta.configure(wraplength=envoltura)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _fit_text = _ajustar_texto

    def _insignia(self, parent, text):
        """Representa el estado de una solicitud con colores y traduce el valor interno Declinada a Rechazada."""
        padre = parent
        texto = text
        color, fondo = {
            "Pendiente": ("#946008", "#FFF5D8"),
            "Aprobada": (GREEN, "#E9F6EF"),
            "Declinada": ("#A83D35", "#FFF1F0"),
        }.get(texto, (MUTED, BG))
        return ctk.CTkLabel(padre, text="Rechazada" if texto == "Declinada" else texto,
                            text_color=color, fg_color=fondo, corner_radius=14,
                            height=30, width=108, font=(FONT, 12, "bold"))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _badge = _insignia

    def _encabezado(self, eyebrow, title, subtitle):
        """Crea el título y la descripción de una vista y adapta sus textos al ancho disponible."""
        titulo = title
        caja = ctk.CTkFrame(self.content, fg_color="transparent")
        caja.grid(row=0, column=0, sticky="ew", padx=34, pady=(24, 16))
        copy = ctk.CTkFrame(caja, fg_color="transparent")
        copy.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(copy, text=eyebrow.upper(), text_color=BLUE, font=(FONT, 10, "bold")).pack(anchor="w")
        titulo_etiqueta = ctk.CTkLabel(copy, text=titulo, text_color=INK, font=(FONT, 28, "bold"), anchor="w", justify="left")
        titulo_etiqueta.pack(fill="x", pady=(5, 2))
        subtitle_etiqueta = ctk.CTkLabel(copy, text=subtitle, text_color=MUTED, font=(FONT, 12), anchor="w", justify="left")
        subtitle_etiqueta.pack(fill="x")
        copy.bind("<Configure>", lambda e: [self._fit_text(label, e.width) for label in (titulo_etiqueta, subtitle_etiqueta)])
        return caja
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _heading = _encabezado

    def _tarjeta(self, row, pady=(0, 18)):
        """Añade una tarjeta de contenido en la fila indicada con márgenes, borde y columna expansible comunes."""
        fila = row
        tarjeta = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=12, border_width=1, border_color=LINE)
        tarjeta.grid(row=fila, column=0, sticky="ew", padx=34, pady=pady)
        tarjeta.grid_columnconfigure(0, weight=1)
        return tarjeta
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _card = _tarjeta

    def _tabla(self, parent, columns, rows, height=6, row_ids=None):
        """Construye una tabla de selección única con columnas, filas e identificadores y barras visibles solo cuando hacen falta."""
        columnas = columns
        identificadores_filas = row_ids
        alto = height
        padre = parent
        filas = rows
        self._preparar_estilo_tablas(padre)
        envoltura = ctk.CTkFrame(padre, fg_color=WHITE, height=alto * 42 + 62)
        envoltura.grid_propagate(False)
        envoltura.grid_columnconfigure(0, weight=1)
        envoltura.grid_rowconfigure(0, weight=1)
        claves = [col[0] for col in columnas]
        tabla = ttk.Treeview(envoltura, columns=claves, show="headings", height=alto, selectmode="browse", style="Hemeroteca.Treeview")
        for clave, titulo, ancho in columnas:
            tabla.heading(clave, text=titulo, anchor="w")
            tabla.column(clave, width=ancho, minwidth=min(ancho, 110), anchor="w", stretch=True)
        tabla.tag_configure("alternate", background="#F8FAFD")
        for indice_breve, fila in enumerate(filas):
            tabla.insert("", "end", iid=str(identificadores_filas[indice_breve]) if identificadores_filas else None, values=fila, tags=("alternate",) if indice_breve % 2 else ())
        horizontal = ttk.Scrollbar(envoltura, orient="horizontal", command=tabla.xview)
        def actualizar_horizontal(inicio, fin):
            """Muestra desplazamiento únicamente si las columnas exceden el ancho."""
            horizontal.set(inicio, fin)
            if float(fin) - float(inicio) >= .999999:
                horizontal.grid_remove()
            else:
                horizontal.grid(row=1, column=0, sticky='ew')
        vertical = ttk.Scrollbar(envoltura, orient='vertical', command=tabla.yview)
        vertical._destino_rueda = tabla
        horizontal._destino_rueda = tabla
        def actualizar_vertical(inicio, fin):
            """Conserva acceso a todas las filas cuando la tabla reduce su altura."""
            vertical.set(inicio, fin)
            if float(fin) - float(inicio) >= .999999:
                vertical.grid_remove()
            else:
                vertical.grid(row=0, column=1, sticky='ns')
        tabla.configure(xscrollcommand=actualizar_horizontal, yscrollcommand=actualizar_vertical)
        tabla.grid(row=0, column=0, sticky="nsew")
        horizontal.grid(row=1, column=0, sticky="ew")
        return envoltura, tabla
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _table = _tabla

    def _barra_resultados(self, area, clave):
        """Fija la navegación fuera del scroll e identifica cada conjunto de resultados."""
        destino = getattr(self, 'navegacion_resultados', None)
        fija = destino is not None and destino.winfo_exists()
        nav = ctk.CTkFrame(destino if fija else area, fg_color=WHITE, border_width=1, border_color=LINE)
        nav.pack(fill='x', padx=12, pady=4)
        titulos = {'consulta': 'Resultados', 'catalogo': 'Ejemplares', 'ausencias': 'Fechas sin publicación',
                   'solicitudes': 'Solicitudes', 'auditoria': 'Auditoría', 'usuarios': 'Usuarios', 'eliminados': 'Registros eliminados', 'backups': 'Respaldos'}
        nav._titulo_resultados = titulos.get(clave, 'Resultados')
        encabezado = ctk.CTkFrame(nav, fg_color='transparent')
        encabezado.pack(fill='x', padx=10, pady=(5, 0))
        self._label(encabezado, nav._titulo_resultados).pack(side='left')
        resumen = self._paragraph(encabezado, '')
        resumen.pack(side='right')
        controles = ctk.CTkFrame(nav, fg_color='transparent')
        controles.pack(fill='x', padx=6, pady=(4, 6))
        if fija:
            destino.grid()
            if clave != 'backups':
                self._button(controles, 'Ir a filtros', lambda: self.content._parent_canvas.yview_moveto(0), 'secondary', width=100, height=36).pack(side='left', padx=4)
                self._button(controles, 'Ver resultados', lambda: self._mostrar_resultados(area), 'secondary', width=120, height=36).pack(side='left', padx=4)
            def retirar(evento):
                """Retira únicamente la barra de la tabla que se destruyó al filtrar o navegar."""
                if nav.winfo_exists():
                    nav.destroy()
                if destino.winfo_exists() and not destino.winfo_children():
                    destino.grid_remove()
            area.bind('<Destroy>', retirar, add='+')
        return nav, resumen, controles

    def _mostrar_resultados(self, area):
        """Acerca la tabla a la zona visible sin alterar sus filtros ni selección."""
        if not area.winfo_exists() or not hasattr(self, 'content'):
            return
        self.update_idletasks()
        lienzo = self.content._parent_canvas
        limites = lienzo.bbox('all')
        if limites and limites[3] > limites[1]:
            posicion = area.winfo_rooty() - lienzo.winfo_rooty() + lienzo.canvasy(0) - 8
            lienzo.yview_moveto(max(0, posicion) / (limites[3] - limites[1]))

    def _paginar(self, parent, rows, columns, key, page_size=8, selected_callback=None, row_ids=None):
        'Construye los controles de paginar y conecta las acciones con los servicios autorizados.'
        columnas = columns
        pagina_size = page_size
        identificadores_filas = row_ids
        selected_retrollamada_local = selected_callback
        clave = key
        tamano_pagina = pagina_size
        padre = parent
        filas = rows
        selected_retrollamada = selected_retrollamada_local
        estado_local = {"page": 0}
        area = ctk.CTkFrame(padre, fg_color=WHITE)
        area.pack(fill="x", padx=18, pady=(0, 8))
        tabla_holder = ctk.CTkFrame(area, fg_color=WHITE)
        tabla_holder.pack(fill="x")
        nav, izquierda, botones = self._barra_resultados(area, clave)
        def dibujar():
            'Actualiza la tabla y sus controles según la página actual.'
            for w in tabla_holder.winfo_children():
                w.destroy()
            total = len(filas)
            paginas = max(1, (total + tamano_pagina - 1) // tamano_pagina)
            estado_local["page"] = max(0, min(estado_local["page"], paginas - 1))
            lote = filas[estado_local["page"] * tamano_pagina:(estado_local["page"] + 1) * tamano_pagina]
            batch_ids = identificadores_filas[estado_local["page"] * tamano_pagina:(estado_local["page"] + 1) * tamano_pagina] if identificadores_filas else None
            if selected_retrollamada:
                selected_retrollamada(None)
            wrapped, tabla = self._table(tabla_holder, columnas, lote, height=min(tamano_pagina, max(2, len(lote))), row_ids=batch_ids)
            wrapped.pack(fill="x")
            if selected_retrollamada:
                tabla.bind("<<TreeviewSelect>>", lambda _e: selected_retrollamada(tabla))
            inicio = estado_local["page"] * tamano_pagina + 1 if total else 0
            fin = min((estado_local["page"] + 1) * tamano_pagina, total)
            izquierda.configure(text=f"{inicio}–{fin} de {total} registros · Página {estado_local['page'] + 1} de {paginas}")
            prev.configure(state="normal" if estado_local["page"] > 0 else "disabled", fg_color=BLUE if estado_local['page'] > 0 else SOFT)
            nxt.configure(state="normal" if estado_local["page"] < paginas - 1 else "disabled", fg_color=BLUE if estado_local['page'] < paginas - 1 else SOFT)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        draw = dibujar
        prev = self._button(botones, "Anterior", lambda: change(-1), "primary", width=100, height=36)
        nxt = self._button(botones, "Siguiente", lambda: change(1), "primary", width=100, height=36)
        nxt.pack(side="right", padx=4); prev.pack(side="right", padx=4)
        def cambiar(amount):
            """Comprueba acceso antes de cambiar la página en memoria y desplaza la vista hacia sus resultados."""
            if not self._require_access(self.current_view, action=f"Cambiar página: {self.current_view}", view=True):
                return
            estado_local["page"] += amount
            draw()
            self._mostrar_resultados(area)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        change = cambiar
        draw()
        return area
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _paginate = _paginar

    def _registrar_estado_vista(self, clave, controles):
        """Restaura filtros del mismo usuario y guarda cambios antes de navegar."""
        memoria = getattr(self, '_filtros_recordados', {})
        self._filtros_recordados = memoria
        identificador = (self.user['id'], clave)
        guardado = memoria.get(identificador, {})
        for nombre, control in controles.items():
            if nombre in guardado:
                if hasattr(control, 'set'):
                    control.set(guardado[nombre])
                else:
                    control.delete(0, 'end')
                    control.insert(0, guardado[nombre])
        def conservar():
            """Guarda valores simples y reinicia páginas únicamente si cambian filtros."""
            valores = {nombre: control.get() for nombre, control in controles.items()}
            if memoria.get(identificador, valores) != valores:
                paginas = getattr(self, '_paginas_recordadas', {})
                for llave in list(paginas):
                    if llave[:2] == (self.user['id'], self.current_view):
                        paginas.pop(llave)
            memoria[identificador] = valores
        conservar()
        self._guardar_estado_vista = conservar

    def _paginada_tabla(self, parent, fetch_page, format_row, columns, *, selected_callback=None, key='consulta', on_data=None):
        """Reutiliza tabla y paginación; consulta datos sin bloquear la navegación."""
        identificador = (self.user['id'], self.current_view, key)
        paginas = getattr(self, '_paginas_recordadas', {})
        self._paginas_recordadas = paginas
        selecciones = getattr(self, '_selecciones_recordadas', {})
        self._selecciones_recordadas = selecciones
        estado = getattr(parent, '_tabla_paginada', None)
        if estado is None or not estado['area'].winfo_exists():
            area = ctk.CTkFrame(parent, fg_color=WHITE)
            area.pack(fill='x', padx=18, pady=(0, 8))
            mensaje = self._paragraph(area, '')
            mensaje.pack(fill='x')
            envoltura, tabla = self._table(area, columns, [], height=2)
            envoltura.pack(fill='x')
            nav, etiqueta, controles = self._barra_resultados(area, key)
            estado = {'area': area, 'nav': nav, 'tabla': tabla, 'mensaje': mensaje, 'etiqueta': etiqueta,
                      'page': 1, 'pages': 1, 'recibir': None, 'seleccionar': None}
            parent._tabla_paginada = estado

            def elegir(_evento=None):
                """Restaura detalles únicamente con la selección de la tabla vigente."""
                seleccion = tabla.selection()
                if seleccion:
                    selecciones[identificador] = seleccion[0]
                if estado['seleccionar']:
                    estado['seleccionar'](tabla)
            tabla.bind('<<TreeviewSelect>>', elegir)

            def cambiar(desplazamiento):
                """Solicita la página elegida conservando la tabla y la barra de navegación."""
                estado['dibujar'](estado['page'] + desplazamiento)
                self._mostrar_resultados(area)
            anterior = self._button(controles, 'Anterior', lambda: cambiar(-1), 'primary', width=100, height=36)
            siguiente = self._button(controles, 'Siguiente', lambda: cambiar(1), 'primary', width=100, height=36)
            siguiente.pack(side='right', padx=4)
            anterior.pack(side='right', padx=4)
            estado.update(anterior=anterior, siguiente=siguiente)
        estado['nav'].pack(fill='x', padx=12, pady=4)
        estado['seleccionar'] = selected_callback

        def dibujar(pagina):
            """Captura filtros en Tk y entrega al trabajador solo valores serializables."""
            estado['anterior'].configure(state='disabled')
            estado['siguiente'].configure(state='disabled')
            estado['etiqueta'].configure(text='Cargando resultados…')
            tabla = estado['tabla']
            tabla.delete(*tabla.get_children())
            if selected_callback:
                selected_callback(None)

            def presentar(datos):
                """Reemplaza filas sin destruir el Treeview, los botones ni las barras."""
                resultado = datos[0]
                if on_data:
                    on_data(resultado)
                estado.update(page=resultado['page'], pages=resultado['pages'])
                paginas[identificador] = resultado['page']
                filas = resultado['items']
                tabla.configure(height=min(8, max(2, len(filas))))
                for fila in filas:
                    tabla.insert('', 'end', iid=str(fila['id']), values=format_row(fila))
                estado['mensaje'].configure(text='' if filas else 'No hay registros para estos filtros. Limpia los filtros para ampliar la búsqueda.')
                seleccion = selecciones.get(identificador)
                if seleccion and tabla.exists(seleccion):
                    tabla.selection_set(seleccion)
                    if selected_callback:
                        selected_callback(tabla)
                estado['etiqueta'].configure(text=f"{resultado['total']} registros · Página {resultado['page']} de {resultado['pages']}")
                for boton, disponible in ((estado['anterior'], resultado['page'] > 1),
                                          (estado['siguiente'], resultado['page'] < resultado['pages'])):
                    boton.configure(state='normal' if disponible else 'disabled', fg_color=BLUE if disponible else SOFT)

            def fallo(excepcion):
                """Deja el error visible y permite repetir la búsqueda con los filtros."""
                estado['etiqueta'].configure(text='No se pudieron cargar los resultados')
            try:
                consulta = fetch_page(pagina)
            except ValueError as excepcion:
                estado['mensaje'].configure(text=str(excepcion))
                fallo(excepcion)
                return
            self._cargar_seccion(estado['area'], [consulta], presentar, error=fallo)
        estado['dibujar'] = dibujar
        dibujar(paginas.get(identificador, 1))
        return estado['area']

    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _paged_table = _paginada_tabla

    def _titulo_filtrar_campos(self, parent, start_col=0, include_type=True):
        """Crea selectores de periódico y tipo opcional y devuelve los controles indexados por su etiqueta."""
        iniciar_col_local = start_col
        padre = parent
        iniciar_col = iniciar_col_local
        campos = {}
        opciones_control = [("Periódico", ["Todos los periódicos"] + TITLES, "Todos los periódicos")]
        if include_type:
            opciones_control.append(("Tipo", ["Todos", "Regional", "Nacional"], "Todos"))
        for indice_breve, (etiqueta, valores, predeterminado) in enumerate(opciones_control, iniciar_col):
            envoltura, selector = self._combo(padre, etiqueta, valores, predeterminado)
            envoltura.grid(row=2, column=indice_breve, sticky="ew", padx=7, pady=(0, 16))
            campos[etiqueta] = selector
        return campos
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _title_filter_fields = _titulo_filtrar_campos

    def _filtrar_filas(self, rows, title, kind):
        """Filtra registros en memoria por periódico y tipo, respetando las opciones que significan todos."""
        tipo = kind
        filas = rows
        titulo = title
        if titulo and titulo != "Todos los periódicos":
            filas = [registro_breve for registro_breve in filas if registro_breve["title"] == titulo]
        if tipo and tipo != "Todos":
            filas = [registro_breve for registro_breve in filas if registro_breve["kind"] == tipo]
        return filas
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _filter_rows = _filtrar_filas

    def _conectar_fecha_campos(self, year, month, day, allow_all=False):
        """Sincroniza los selectores históricos de año, mes y día con su calendario y mantiene días válidos."""
        permitir_all_local = allow_all
        permitir_all = permitir_all_local
        dia = day
        mes = month
        anio = year
        # El calendario añade altura a Año; los tres campos conservan la misma
        # alineación superior y siguen admitiendo búsquedas parciales por mes/año.
        for control in (anio, mes, dia):
            if control.master.winfo_manager() == 'grid':
                control.master.grid_configure(sticky='new')
        def ajustar(_value=None):
            """Actualiza las opciones de día según el mes y año y corrige la selección si dejó de existir."""
            try:
                anio_breve = date.today().year if anio.get() == "Todos" else int(anio.get())
                maximo = 31 if mes.get() == "Todos" else calendar.monthrange(anio_breve, MONTHS.index(mes.get()) + 1)[1]
            except (ValueError, IndexError):
                return
            valores = (["Todos"] if permitir_all else []) + [str(dia_breve) for dia_breve in range(1, maximo + 1)]
            actual = dia.get()
            dia.configure(values=valores)
            if actual not in valores:
                dia.set("Todos" if permitir_all else str(maximo))
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        adjust = ajustar
        mes.configure(command=adjust)
        if isinstance(anio, ctk.CTkComboBox):
            anio.configure(command=adjust)
        else:
            anio.bind("<KeyRelease>", adjust)
        adjust()
        def elegir_fecha(fecha):
            """Actualiza los tres filtros conservando las búsquedas por mes o año."""
            anio.set(str(fecha.year))
            mes.set(MONTHS[fecha.month - 1])
            adjust()
            dia.set(str(fecha.day))
        def calendario():
            """Abre un calendario junto a los filtros históricos existentes."""
            try:
                actual = date(int(anio.get()), MONTHS.index(mes.get()) + 1, int(dia.get()))
            except (ValueError, IndexError):
                actual = date.today()
            abrir_calendario(anio, elegir_fecha, actual)
        self._button(anio.master, 'Calendario', calendario, 'secondary', height=30).pack(fill='x', pady=(4, 0))
        return adjust
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _connect_date_fields = _conectar_fecha_campos
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
UIComponents = ComponentesInterfaz
