"""Controles accesibles de documento, calendario y listas con desplazamiento."""
import calendar
import sys
from datetime import date, datetime
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from hemeroteca.config.settings import BLUE, FONT, WHITE


def pasos_de_rueda(control, evento):
    """Normaliza la rueda y acumula movimientos pequeños del panel táctil."""
    numero = getattr(evento, 'num', None)
    if numero in (4, 5):
        return -1 if numero == 4 else 1
    delta = getattr(evento, 'delta', 0)
    cantidad = -delta if sys.platform == 'darwin' else -delta / 120
    acumulado = getattr(control, '_resto_rueda', 0) + cantidad
    pasos = int(acumulado)
    control._resto_rueda = acumulado - pasos
    return pasos


def desplazar_con_continuidad(evento):
    """Entrega cada rueda al control con espacio y continúa por sus contenedores."""
    numero = getattr(evento, 'num', None)
    delta = -120 if numero == 5 else 120 if numero == 4 else getattr(evento, 'delta', 0)
    if not delta:
        return
    horizontal = bool(getattr(evento, 'state', 0) & 1)
    eje = 'x' if horizontal else 'y'
    actual = evento.widget
    candidatos = []
    while actual is not None:
        # Los menús flotantes conservan su rueda, incluso en sus extremos.
        if getattr(actual, '_rueda_menu', False):
            return
        if isinstance(actual, tk.Listbox) and isinstance(actual.master, tk.Toplevel):
            return
        if isinstance(actual, SelectorCompacto) and actual._cerrar_menu is not None:
            actual._cerrar_menu(devolver_foco=False)
        destino = getattr(actual, '_destino_rueda', None)
        propietario = getattr(actual, '_propietario_rueda', None)
        if destino is None and propietario is not None:
            destino = propietario._parent_canvas
        if destino is None and isinstance(actual, ctk.CTkScrollableFrame):
            destino = actual._parent_canvas
        if destino is None and isinstance(actual, ctk.CTkTextbox):
            destino = actual._textbox
        if destino is None and isinstance(actual, (tk.Text, tk.Listbox, ttk.Treeview)):
            destino = actual
        if destino is not None and destino not in candidatos:
            candidatos.append(destino)
        if isinstance(actual, tk.Toplevel):
            break
        actual = getattr(actual, 'master', None)
    for destino in candidatos:
        vista = getattr(destino, eje + 'view')()
        if len(vista) != 2 or vista[1] - vista[0] >= .999999:
            continue
        if delta < 0 and vista[1] >= .999999 or delta > 0 and vista[0] <= .000001:
            continue
        # Acumula fracciones por destino y eje: pasar por distintos hijos no
        # descarta los movimientos pequeños del panel táctil.
        # Un paso de rueda debe recorrer aproximadamente tres líneas de texto,
        # no los veinte píxeles que obligaban a girar repetidamente la rueda.
        factor = 3
        if isinstance(destino, tk.Canvas):
            escala = getattr(destino._root(), '_get_window_scaling', lambda: 1)()
            factor = round(90 * escala)
        cantidad = -delta * factor / (1 if sys.platform == 'darwin' else 120)
        atributo = '_resto_continuo_' + eje
        acumulado = getattr(destino, atributo, 0) + cantidad
        pasos = int(acumulado)
        setattr(destino, atributo, acumulado - pasos)
        if pasos:
            getattr(destino, eje + 'view_scroll')(pasos, 'units')
        return 'break'
    if candidatos:
        return 'break'


def instalar_rueda_continua(raiz):
    """Intercepta la rueda antes de los bindings nativos sin reemplazar otros eventos."""
    if getattr(raiz, '_rueda_continua_instalada', False):
        return
    raiz._rueda_continua_instalada = True
    etiqueta = 'HemerotecaRuedaContinua'
    def conectar(control, descendientes=True):
        """Añade prioridad de rueda a cada control, incluidos los creados después."""
        etiquetas = control.bindtags()
        if etiqueta not in etiquetas:
            control.bindtags((etiqueta,) + etiquetas)
        if descendientes:
            for hijo in control.winfo_children():
                conectar(hijo)
    def al_mostrar(evento):
        """Conecta los controles nuevos cuando Tk los incorpora a la pantalla."""
        # Cada hijo recibe su propio Map: recorrer el subárbol en cada evento
        # repetía el trabajo al construir o mostrar formularios grandes.
        conectar(evento.widget, descendientes=False)
    for secuencia in ('<MouseWheel>', '<Shift-MouseWheel>', '<Button-4>', '<Button-5>'):
        raiz.bind_class(etiqueta, secuencia, desplazar_con_continuidad)
    raiz.bind_all('<Map>', al_mostrar, add='+')
    conectar(raiz)


class MarcoDesplazable(ctk.CTkScrollableFrame):
    """Entrega la rueda únicamente al contenedor más cercano que la necesita."""

    def __init__(self, padre, **opciones):
        """Identifica el propietario del fondo y de las barras de este contenedor."""
        super().__init__(padre, **opciones)
        for control in (self._parent_frame, self._parent_canvas, self._scrollbar):
            control._propietario_rueda = self
        instalar_rueda_continua(self._root())

    def _check_if_valid_scroll(self, widget):
        """Evita que listas, tablas, texto o marcos interiores arrastren la página."""
        actual = widget
        while actual is not None:
            if isinstance(actual, (tk.Text, tk.Listbox, ttk.Treeview, ctk.CTkTextbox)):
                return False
            if isinstance(actual, ctk.CTkComboBox) and not isinstance(actual, SelectorCompacto):
                return False
            propietario = getattr(actual, '_propietario_rueda', None)
            if propietario is not None:
                return propietario is self
            if isinstance(actual, ctk.CTkScrollableFrame):
                return actual is self
            actual = getattr(actual, 'master', None)
        return False

    def _mouse_wheel_all(self, evento):
        """Consume la rueda del marco local sin mover también un marco exterior."""
        if self._check_if_valid_scroll(evento.widget):
            super()._mouse_wheel_all(evento)
            return 'break'


class TextoEditable(ctk.CTkTextbox):
    """Devuelve el teclado al texto al pulsar, conservando selección y scroll."""

    def __init__(self, padre, **opciones):
        """Conecta texto y fondo con su entrada nativa."""
        super().__init__(padre, **opciones)
        self.bind('<ButtonPress-1>', self._activar_texto)
        self.bind('<ButtonRelease-1>', self._activar_texto)
        self._canvas.bind('<Button-1>', self._activar_texto, add='+')

    def _activar_texto(self, evento):
        """Activa el teclado únicamente ante un clic sobre un cuadro editable."""
        if self.cget('state') != 'disabled':
            self._textbox.focus_force()


class EntradaEditable(ctk.CTkEntry):
    """Hace editable toda el área visible del campo, no solo la franja de texto."""

    def __init__(self, padre, **opciones):
        """Conserva validadores y máscaras y conecta el fondo con el cursor de texto."""
        super().__init__(padre, **opciones)
        self._canvas.bind('<Button-1>', self._enfocar_desde_fondo, add='+')
        self.bind('<ButtonPress-1>', self._enfocar_texto)
        self.bind('<ButtonRelease-1>', self._enfocar_texto)
        self.bind('<Control-a>', self._seleccionar_todo)
        self.bind('<Control-A>', self._seleccionar_todo)

    def _enfocar_texto(self, evento):
        """Activa el teclado por clic también sobre el texto, sin sustituir sus bindings."""
        if self.cget('state') != 'disabled' and self._entry.winfo_viewable():
            # En Windows el foco local de Tcl puede conservarse mientras el foco
            # del teclado quedó en otro contenedor. Se activa la entrada solo
            # como respuesta al clic del usuario, sin temporizadores que roben foco.
            self._entry.focus_force()

    def _enfocar_desde_fondo(self, evento):
        """Coloca el cursor al pulsar cualquier zona del rectángulo del campo."""
        if self.cget('state') != 'disabled':
            self._entry.focus_force()
            posicion = evento.x_root - self._entry.winfo_rootx()
            self._entry.icursor(self._entry.index('@' + str(posicion)))
        return 'break'

    def _seleccionar_todo(self, evento):
        """Permite corregir el contenido completo con Ctrl+A y escribir su reemplazo."""
        if self.cget('state') != 'disabled':
            self._entry.selection_range(0, 'end')
            self._entry.icursor('end')
        return 'break'


class SelectorCompacto(ctk.CTkComboBox):
    """Conserva el contrato CTk y limita las listas a ocho filas con teclado y rueda."""

    def __init__(self, padre, **opciones):
        """Añade apertura por teclado sin cambiar el contrato del selector."""
        super().__init__(padre, **opciones)
        self._ventana_menu = None
        self._lista_menu = None
        self._revision_foco = None
        self._cerrar_menu = None
        self.bind('<Button-1>', self._abrir_con_raton)
        self.bind('<Destroy>', self._destruir_selector)
        for secuencia in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind(secuencia, self._rueda_selector)
            self._canvas.bind(secuencia, self._rueda_selector, add='+')
        for tecla in ('<Down>', '<F4>', '<space>'):
            self.bind(tecla, self._abrir_con_teclado)

    def _abrir_con_raton(self, evento):
        """Abre también al pulsar el texto, además de la flecha del selector."""
        self._open_dropdown_menu()
        return 'break'

    def _clicked(self, event=None):
        """Conecta la flecha con el menú propio, sin usar el estado del menú original."""
        self._open_dropdown_menu()

    def _rueda_selector(self, evento):
        """Deja pasar la rueda al formulario sin abrir ni cambiar la selección."""
        if self._cerrar_menu is not None:
            self._cerrar_menu(devolver_foco=False)
        # No consumir el evento: el marco desplazable más cercano lo recibe.

    def _rueda_lista(self, evento):
        """Consume la rueda del menú incluso cuando no quedan opciones para desplazar."""
        if self._lista_menu is not None and self._lista_menu.winfo_exists():
            pasos = pasos_de_rueda(self, evento)
            if pasos:
                self._lista_menu.yview_scroll(pasos * 3, 'units')
        return 'break'

    def _destruir_selector(self, evento):
        """Cancela comprobaciones pendientes al cerrar el formulario del selector."""
        if self._cerrar_menu is not None:
            self._cerrar_menu(devolver_foco=False)
        if self._revision_foco is not None:
            self.after_cancel(self._revision_foco)
            self._revision_foco = None
        if self._ventana_menu is not None and self._ventana_menu.winfo_exists():
            self._ventana_menu.destroy()
            self._ventana_menu = None
            self._lista_menu = None

    def _abrir_con_teclado(self, evento):
        """Abre el menú con Flecha abajo, F4 o Espacio."""
        self._open_dropdown_menu()
        return 'break'

    def _open_dropdown_menu(self):
        """Abre una lista nativa desplazable y entrega la selección al comando vigente."""
        if self.cget('state') == 'disabled':
            return
        if self._ventana_menu is not None and self._ventana_menu.winfo_exists():
            self._ventana_menu.lift()
            return
        ventana = tk.Toplevel(self)
        ventana._rueda_menu = True
        self._ventana_menu = ventana
        ventana.withdraw()
        ventana.overrideredirect(True)
        ventana.transient(self.winfo_toplevel())
        valores = self.cget('values')
        lista = tk.Listbox(ventana, height=min(8, max(1, len(valores))), exportselection=False,
                           width=max(3, min(50, max((len(str(valor)) for valor in valores), default=3))),
                           font=(FONT, 12), activestyle='dotbox')
        self._lista_menu = lista
        barra = ttk.Scrollbar(ventana, command=lista.yview)
        for control in (lista, barra, ventana):
            for secuencia in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                control.bind(secuencia, self._rueda_lista, add='+')
        lista.configure(yscrollcommand=barra.set)
        lista.pack(side='left', fill='both', expand=True)
        if len(valores) > 8:
            barra.pack(side='right', fill='y')
        for valor in valores:
            lista.insert('end', valor)
        if self.get() in valores:
            indice = valores.index(self.get())
            lista.selection_set(indice)
            lista.activate(indice)
            lista.see(indice)
        etiqueta_eventos = f'SelectorAbierto{id(ventana)}'
        controles_observados = []
        def cerrar(evento=None, devolver_foco=True):
            """Devuelve el foco al control y cierra solo esta lista."""
            if self._ventana_menu is ventana:
                if self._revision_foco is not None:
                    self.after_cancel(self._revision_foco)
                    self._revision_foco = None
                self._ventana_menu = None
                self._lista_menu = None
                self._cerrar_menu = None
                for control in controles_observados:
                    if control.winfo_exists():
                        control.bindtags(tuple(tag for tag in control.bindtags() if tag != etiqueta_eventos))
                for secuencia in ('<ButtonPress>', '<MouseWheel>', '<Button-4>', '<Button-5>'):
                    ventana.unbind_class(etiqueta_eventos, secuencia)
                if ventana.winfo_exists():
                    ventana.destroy()
                if devolver_foco and self.winfo_exists():
                    self.focus_set()
        self._cerrar_menu = cerrar
        def al_destruir(evento):
            """Retira también estado y eventos si Tk destruye el menú externamente."""
            if evento.widget is ventana:
                cerrar(devolver_foco=False)
        ventana.bind('<Destroy>', al_destruir, add='+')
        def elegir(evento=None):
            """Confirma por clic, espacio o Intro y ejecuta el filtro asociado."""
            seleccion = lista.curselection()
            if seleccion:
                valor = valores[seleccion[0]]
                self.set(valor)
                comando = self.cget('command')
                cerrar()
                if comando:
                    comando(valor)
        lista.bind('<ButtonRelease-1>', elegir)
        lista.bind('<Return>', elegir)
        lista.bind('<space>', elegir)
        ventana.bind('<Escape>', cerrar)
        def cerrar_fuera(evento):
            """Cierra antes del clic o rueda exterior sin impedir la interacción de destino."""
            # El Canvas ejecuta primero el binding de su flecha: este mismo clic
            # puede llegar aquí después de abrir el menú y no debe cerrarlo.
            if evento.widget is self or str(evento.widget).startswith(str(self) + '.'):
                return
            # El menú también es descendiente del selector y ya quedó excluido.
            cerrar(devolver_foco=False)
        def comprobar_foco():
            """Cierra al cambiar de ventana sin interrumpir el foco dentro de la lista."""
            self._revision_foco = None
            if ventana.winfo_exists():
                foco = ventana.focus_get()
                if foco is None or not str(foco).startswith(str(ventana) + '.'):
                    cerrar(devolver_foco=False)
        def programar_revision(evento):
            """Evita dejar temporizadores de un menú cerrado en el formulario."""
            if self._ventana_menu is ventana and ventana.winfo_exists():
                if self._revision_foco is not None:
                    self.after_cancel(self._revision_foco)
                self._revision_foco = self.after(100, comprobar_foco)
        def observar(control):
            """Antecede a los bindings de scroll sin sustituir los controles del formulario."""
            controles_observados.append(control)
            control.bindtags((etiqueta_eventos,) + control.bindtags())
            for hijo in control.winfo_children():
                observar(hijo)
        observar(self._root())
        for secuencia in ('<ButtonPress>', '<MouseWheel>', '<Button-4>', '<Button-5>'):
            ventana.bind_class(etiqueta_eventos, secuencia, cerrar_fuera)
        ventana.bind('<FocusOut>', programar_revision)
        ventana.update_idletasks()
        ancho = self.winfo_width()
        alto = lista.winfo_reqheight()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        if y + alto > self.winfo_screenheight():
            y = self.winfo_rooty() - alto
        ventana.geometry(f'{ancho}x{alto}+{x}+{max(0, y)}')
        ventana.deiconify()
        ventana.lift()
        lista.focus_force()


class EntradaDocumento(ctk.CTkFrame):
    """Separa el tipo V/E del número y conserva get/set para los formularios."""

    def __init__(self, padre):
        """Crea el selector de nacionalidad y bloquea caracteres no numéricos."""
        super().__init__(padre, fg_color='transparent')
        self.tipo = SelectorCompacto(self, values=['V', 'E'], width=75, height=44, state='readonly')
        self.tipo.set('V')
        self.tipo.pack(side='left', padx=(0, 8))
        self.numero = EntradaEditable(self, height=44, placeholder_text='Número de cédula')
        self.numero.pack(side='left', fill='x', expand=True)
        self.numero.configure(validate='key', validatecommand=(self.register(self._validar), '%P'))

    @staticmethod
    def _validar(valor):
        """Permite borrar y escribir hasta ocho dígitos ASCII."""
        return len(valor) <= 8 and (not valor or valor.isascii() and valor.isdigit())

    def get(self):
        """Devuelve el documento completo o vacío cuando no hay número."""
        return f'{self.tipo.get()}-{self.numero.get()}' if self.numero.get() else ''

    def set(self, valor):
        """Carga una cédula existente sin duplicar su prefijo."""
        tipo, separador, numero = str(valor).partition('-')
        self.tipo.set(tipo if tipo in ('V', 'E') else 'V')
        self.numero.delete(0, 'end')
        self.numero.insert(0, numero if separador else tipo)

    def insert(self, indice, valor):
        """Mantiene compatibilidad con el autocompletado anterior."""
        self.set(valor)

    def delete(self, inicio, fin=None):
        """Vacía el número sin cambiar la nacionalidad elegida."""
        self.numero.delete(inicio, fin)

    def focus_set(self):
        """Coloca el cursor en el número de cédula."""
        self.numero.focus_set()


def abrir_calendario(padre, recibir, valor=None):
    """Selecciona una fecha entre 1970 y 2100 con navegación por teclado."""
    ventana = ctk.CTkToplevel(padre)
    ventana.title('Hemeroteca · Seleccionar fecha')
    ventana.geometry('370x380')
    ventana.resizable(False, False)
    ventana.transient(padre.winfo_toplevel())
    anterior = padre.grab_current()
    ventana.grab_set()
    fecha = valor or date.today()
    fecha = min(date(2100, 12, 31), max(date(1970, 1, 1), fecha))
    barra = ctk.CTkFrame(ventana)
    barra.pack(fill='x', padx=12, pady=12)
    anio = SelectorCompacto(barra, values=[str(n) for n in range(1970, 2101)], width=100, state='readonly')
    mes = SelectorCompacto(barra, values=[calendar.month_name[n] for n in range(1, 13)], width=180, state='readonly')
    # Nombres en español independientes de la configuración regional de Windows.
    from hemeroteca.config.settings import MONTHS
    mes.configure(values=MONTHS)
    anio.set(str(fecha.year))
    mes.set(MONTHS[fecha.month - 1])
    anio.pack(side='left', padx=4)
    mes.pack(side='left', padx=4)
    dias = ctk.CTkFrame(ventana, fg_color='transparent')
    dias.pack(fill='both', expand=True, padx=12)
    def cerrar():
        """Restablece el diálogo anterior, incluso al cancelar con Escape."""
        ventana.destroy()
        if anterior is not None and anterior.winfo_exists():
            anterior.grab_set()
    def seleccionar(numero):
        """Entrega una fecha validada al formulario y cierra el calendario."""
        seleccion = date(int(anio.get()), MONTHS.index(mes.get()) + 1, numero)
        recibir(seleccion)
        cerrar()
    def dibujar(valor=None):
        """Reconstruye los días válidos del mes, incluyendo años bisiestos."""
        for hijo in dias.winfo_children():
            hijo.destroy()
        for columna, nombre in enumerate(('L', 'M', 'M', 'J', 'V', 'S', 'D')):
            dias.grid_columnconfigure(columna, weight=1)
            ctk.CTkLabel(dias, text=nombre).grid(row=0, column=columna)
        for fila, semana in enumerate(calendar.monthcalendar(int(anio.get()), MONTHS.index(mes.get()) + 1), 1):
            for columna, numero in enumerate(semana):
                if numero:
                    ctk.CTkButton(dias, text=str(numero), width=38, height=32,
                                  command=lambda numero=numero: seleccionar(numero)).grid(row=fila, column=columna, padx=2, pady=2)
    anio.configure(command=dibujar)
    mes.configure(command=dibujar)
    ctk.CTkButton(ventana, text='Cancelar', command=cerrar).pack(pady=12)
    ventana.protocol('WM_DELETE_WINDOW', cerrar)
    ventana.bind('<Escape>', lambda evento: cerrar())
    dibujar()
    return ventana


class EntradaFecha(ctk.CTkFrame):
    """Fecha de solo lectura con calendario y botón para limpiar filtros."""

    def __init__(self, padre):
        """Construye una fecha opcional sin permitir texto manual."""
        super().__init__(padre, fg_color='transparent')
        self.variable = ctk.StringVar(value='')
        self.entrada = ctk.CTkEntry(self, textvariable=self.variable, height=44, state='readonly')
        self.entrada.pack(side='left', fill='x', expand=True)
        ctk.CTkButton(self, text='Calendario', width=90, height=44, command=self.abrir).pack(side='left', padx=4)
        ctk.CTkButton(self, text='×', width=28, height=44, command=lambda: self.variable.set('')).pack(side='left')

    def abrir(self):
        """Abre el calendario usando la fecha actual del filtro si existe."""
        valor = datetime.strptime(self.get(), '%d/%m/%Y').date() if self.get() else None
        abrir_calendario(self, lambda fecha: self.set(fecha.strftime('%d/%m/%Y')), valor)

    def get(self):
        """Devuelve la fecha visible o un filtro vacío."""
        return self.variable.get()

    def set(self, valor):
        """Restaura una fecha válida dentro del intervalo del calendario, 1970–2100."""
        if valor:
            from hemeroteca.utils.dates import parse_filter_date, validar_anio_publicacion
            fecha = parse_filter_date(valor)
            validar_anio_publicacion(fecha.year)
            valor = fecha.strftime('%d/%m/%Y')
        self.variable.set(valor)

    def insert(self, indice, valor):
        """Restaura filtros recordados manteniendo el contrato de entradas."""
        self.set(valor)

    def delete(self, inicio, fin=None):
        """Limpia el filtro de fecha."""
        self.variable.set('')
