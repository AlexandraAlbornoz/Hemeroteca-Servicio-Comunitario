"""Respaldos transportables y restauración guiada, solo en la computadora principal."""

from datetime import datetime
import sqlite3
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from hemeroteca.config.settings import BG, FONT, INK, RED, VIEWS, WHITE


class VistaRespaldos:
    """Presenta configuración, creación, exportación y restauración de respaldos para el maestro en la PC principal."""
    def _respaldos_pagina(self):
        'Construye los controles de respaldos pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action='Abrir respaldos', master=True) or self.services.read_only:
            return
        self._heading('Protección de datos', 'Respaldos de seguridad', 'Solo el administrador maestro puede configurar, llevarse o restaurar las copias de la PC principal.')
        tarjeta = self._card(1)
        self._label(tarjeta, 'Copias diarias automáticas').pack(anchor='w', padx=20, pady=(18, 10))
        descripcion = self._paragraph(tarjeta, 'Consultando configuración…')
        descripcion.pack(fill='x', padx=20, pady=(0, 10))
        self._paragraph(tarjeta, 'La PC debe estar encendida y con tu cuenta de Windows iniciada. La copia pendiente se intenta al volver a iniciar Windows o abrir Hemeroteca.').pack(fill='x', padx=20, pady=(0, 10))
        errores = self._paragraph(tarjeta, '', color=RED)
        errores.pack(fill='x', padx=20)
        acciones = ctk.CTkFrame(tarjeta, fg_color='transparent')
        acciones.pack(fill='x', padx=20, pady=(4, 18))
        self._primary(acciones, 'Configurar copias diarias', self._backup_configuration_form, width=225).pack(anchor='w', pady=(0, 8))
        botones = {}
        for clave, titulo, metodo in (
            ('crear', 'Crear respaldo ahora', self.services.backups.create_now),
            ('programar', 'Reintentar programación de Windows', self.services.backups.retry_schedule),
            ('desactivar', 'Desactivar copias diarias', self.services.backups.disable)):
            boton = self._button(acciones, titulo,
                lambda t=titulo, m=metodo: self._backup_master_action(t, m),
                'danger' if clave == 'desactivar' else 'secondary', width=295, state='disabled')
            boton.pack(anchor='w', pady=(0, 8))
            botones[clave] = boton

        def mostrar_estado(datos):
            """Actualiza descripción y acciones tras consultar la configuración real."""
            estado = datos[0]
            if estado.get('enabled'):
                plan = 'Windows ejecutará la tarea aunque Hemeroteca esté cerrada.' if estado.get('scheduler') == 'windows' else 'La copia diaria se crea mientras Hemeroteca esté abierta.'
                descripcion.configure(text=f"Activadas a las {estado['time']} (hora de esta PC).\nCarpeta: {estado['directory']}\n{plan}\nÚltima copia: {estado.get('last_success') or 'Pendiente'} (UTC).")
            else:
                descripcion.configure(text='Configura una carpeta y una clave para activar la primera copia y los respaldos diarios.')
            errores.configure(text='\n'.join(str(estado[c]) for c in ('last_error', 'scheduler_error') if estado.get(c)))
            habilitados = {'crear': bool(estado.get('directory')), 'programar': estado.get('enabled') and estado.get('scheduler') != 'windows', 'desactivar': estado.get('enabled')}
            for clave, boton in botones.items():
                boton.configure(state='normal' if habilitados[clave] else 'disabled')

        archivos = self._card(2)
        self._label(archivos, 'Copiar un respaldo para llevarlo a otra máquina').pack(anchor='w', padx=20, pady=(18, 8))
        self._paragraph(archivos, 'Selecciona una copia y pulsa Guardar en USB u otra carpeta. Conserva su clave por separado.').pack(fill='x', padx=20, pady=(0, 12))
        respaldos = []
        seleccion = {'path': None}

        def elegir(tabla):
            """Habilita exportación exclusivamente para un archivo de la lista cargada."""
            filas = tabla.selection() if tabla else ()
            seleccion['path'] = respaldos[int(filas[0])]['path'] if filas else None
            guardar.configure(state='normal' if filas else 'disabled')

        def exportar():
            """Solicita destino y conserva la comprobación de acceso del servicio."""
            if not seleccion['path']:
                return
            destino = filedialog.asksaveasfilename(parent=self, title='Guardar respaldo para llevar',
                defaultextension='.hmbackup', filetypes=[('Respaldo de Hemeroteca', '*.hmbackup')], initialfile=Path(seleccion['path']).name)
            if not destino:
                return
            try:
                self.services.backups.export(self.user, seleccion['path'], destino)
            except (OSError, ValueError, sqlite3.Error) as excepcion:
                messagebox.showerror('No se pudo copiar', str(excepcion), parent=self)
                return
            messagebox.showinfo('Respaldo copiado', f'Archivo guardado en:\n{destino}\n\nNecesitarás la clave del respaldo para restaurarlo.', parent=self)

        guardar = self._button(archivos, 'Guardar en USB u otra carpeta', exportar, 'secondary', width=280, state='disabled')
        guardar.pack(anchor='w', padx=20, pady=(0, 12))
        lista = ctk.CTkFrame(archivos, fg_color=WHITE)
        lista.pack(fill='x')

        def mostrar_archivos(datos):
            """Carga el listado y crea la paginación sin bloquear las demás secciones."""
            respaldos[:] = datos[0]
            if respaldos:
                filas = [(r['name'], datetime.fromtimestamp(r['modified']).strftime('%d/%m/%Y %H:%M'), f"{r['size'] / 1024 / 1024:.2f} MiB") for r in respaldos]
                self._paginate(lista, filas, [('file', 'ARCHIVO', 400), ('date', 'FECHA LOCAL', 170), ('size', 'TAMAÑO', 95)], 'backups', page_size=5, selected_callback=elegir, row_ids=list(range(len(filas))))
            else:
                self._empty(lista, 'Todavía no hay respaldos disponibles', 'Configura las copias diarias para crear el primero.')
        self._cargar_seccion(tarjeta, [self.services.consulta('backups', 'status', self.user)], mostrar_estado)
        self._cargar_seccion(lista, [self.services.consulta('backups', 'list_backups', self.user)], mostrar_archivos)
        restore = self._card(3, (0, 24))
        self._label(restore, 'Restaurar un archivo .hmbackup').pack(anchor='w', padx=20, pady=(18, 8))
        self._paragraph(restore, 'Reemplaza el contenido actual por el del respaldo, incluidas sus cuentas y contraseñas. Se crea primero una copia cifrada del estado actual. Después deberás iniciar sesión con una cuenta del respaldo y volver a autorizar las computadoras de consulta.').pack(fill='x', padx=20, pady=(0, 12))
        self._button(restore, 'Seleccionar respaldo para restaurar', self._restore_backup_form, 'danger', width=295).pack(anchor='w', padx=20, pady=(0, 18))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _backups_page = _respaldos_pagina

    def _respaldo_maestro_accion(self, title, operation):
        """Pide la contraseña maestra para ejecutar una acción de respaldo y actualiza la vista al terminar."""
        operacion = operation
        titulo = title
        if not self._require_access(action=titulo, master=True) or self.services.read_only:
            return
        dialogo = self._dialog(titulo, '540x360')
        cuerpo = self._scrollable(dialogo, fg_color=WHITE)
        cuerpo.pack(fill='both', expand=True, padx=20, pady=20)
        self._label(cuerpo, titulo).pack(anchor='w', padx=12, pady=(12, 10))
        self._paragraph(cuerpo, 'Confirma con tu contraseña actual de administrador maestro.').pack(fill='x', padx=12, pady=(0, 12))
        envoltura, contrasena = self._entry(cuerpo, 'Tu contraseña de maestro', show='•')
        envoltura.pack(fill='x', padx=12, pady=(0, 14))
        def aplicar():
            'Valida y ejecuta la operación confirmada por el usuario.'
            try:
                resultado = operacion(self.user, contrasena.get())
            except (OSError, ValueError, sqlite3.Error) as excepcion:
                messagebox.showerror('No se completó la acción', str(excepcion), parent=dialogo)
                return
            dialogo.destroy()
            self.navigate(VIEWS[7])
            if isinstance(resultado, str):
                messagebox.showinfo('Respaldo creado', f'Archivo creado:\n{resultado}', parent=self)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        apply = aplicar
        self._primary(cuerpo, 'Confirmar', apply, width=150).pack(anchor='e', padx=12, pady=(0, 12))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _backup_master_action = _respaldo_maestro_accion

    def _respaldo_configuracion_formulario(self):
        'Construye los controles de respaldo configuracion formulario y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action='Configurar respaldos', master=True) or self.services.read_only:
            return
        estado_local = self.services.backups.status(self.user)
        dialogo = self._dialog('Configurar respaldos diarios', '680x800')
        cuerpo = self._scrollable(dialogo, fg_color=WHITE)
        cuerpo.pack(fill='both', expand=True, padx=20, pady=20)
        self._label(cuerpo, 'Respaldos automáticos cada día').pack(anchor='w', padx=12, pady=(12, 10))
        self._paragraph(cuerpo, 'La clave del respaldo es diferente de la contraseña de inicio de sesión. Guárdala fuera de esta PC: sin ella no podrás restaurar los archivos. Cambiarla solo afecta a las copias nuevas.').pack(fill='x', padx=12, pady=(0, 14))
        envoltura_dia, directorio = self._entry(cuerpo, 'Carpeta donde se guardarán las copias')
        envoltura_dia.pack(fill='x', padx=12, pady=(0, 8))
        directorio.insert(0, estado_local.get('directory') or estado_local['default_directory'])
        directorio.configure(state='readonly')
        def seleccionar_carpeta():
            """Abre el selector de carpeta y copia la ruta elegida al campo de solo lectura."""
            seleccionado = filedialog.askdirectory(parent=dialogo, title='Seleccionar carpeta de respaldos', mustexist=True)
            if seleccionado:
                directorio.configure(state='normal')
                directorio.delete(0, 'end')
                directorio.insert(0, seleccionado)
                directorio.configure(state='readonly')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        seleccionar_carpeta_local = seleccionar_carpeta
        self._button(cuerpo, 'Elegir carpeta', seleccionar_carpeta_local, 'secondary', width=160).pack(anchor='w', padx=12, pady=(0, 14))
        fila = ctk.CTkFrame(cuerpo, fg_color='transparent')
        fila.pack(fill='x', padx=12, pady=(0, 14))
        fila.grid_columnconfigure((0, 1), weight=1)
        anterior = estado_local.get('time') or '18:00'
        hw, hora = self._combo(fila, 'Hora diaria (24 h)', [f'{h:02}' for h in range(24)], anterior[:2])
        envoltura_mes, minuto = self._combo(fila, 'Minutos', [f'{mes_breve:02}' for mes_breve in range(60)], anterior[3:])
        hw.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        envoltura_mes.grid(row=0, column=1, sticky='ew')
        envoltura_periodo, contrasena = self._entry(cuerpo, 'Clave para abrir los respaldos *', 'Mínimo 12 caracteres', show='•')
        envoltura_periodo.pack(fill='x', padx=12, pady=(0, 12))
        cw, confirmacion = self._entry(cuerpo, 'Repetir la clave del respaldo *', show='•')
        cw.pack(fill='x', padx=12, pady=(0, 12))
        aw, contrasena_maestro = self._entry(cuerpo, 'Tu contraseña actual de maestro *', show='•')
        aw.pack(fill='x', padx=12, pady=(0, 12))
        acknowledged = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(cuerpo, text='Guardé la clave fuera de esta PC.', variable=acknowledged, font=(FONT, 12)).pack(anchor='w', padx=12, pady=(0, 14))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=12, pady=(0, 8))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            if contrasena.get() != confirmacion.get():
                error.configure(text='Las claves de respaldo no coinciden.')
                return
            if not acknowledged.get():
                error.configure(text='Guarda la clave y marca la confirmación antes de continuar.')
                return
            try:
                resultado = self.services.backups.configure(self.user, contrasena_maestro.get(), contrasena.get(), directorio.get(), f'{hora.get()}:{minuto.get()}')
            except (OSError, ValueError, sqlite3.Error) as excepcion:
                error.configure(text=str(excepcion))
                return
            dialogo.destroy()
            self.navigate(VIEWS[7])
            messagebox.showinfo('Respaldos configurados', 'Se creó la primera copia cifrada.\n' + (resultado.get('scheduler_error') or 'La programación diaria está configurada.'), parent=self)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(cuerpo, 'Activar y crear primera copia', save, width=275).pack(anchor='e', padx=12, pady=(0, 16))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _backup_configuration_form = _respaldo_configuracion_formulario

    def _restaurar_respaldo_formulario(self):
        'Construye los controles de restaurar respaldo formulario y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action='Revisar respaldo para restaurar', master=True) or self.services.read_only:
            return
        origen = filedialog.askopenfilename(parent=self, title='Abrir respaldo de Hemeroteca', filetypes=[('Respaldo de Hemeroteca', '*.hmbackup')])
        if not origen:
            return
        dialogo = self._dialog('Revisar y restaurar respaldo', '690x780')
        cuerpo = self._scrollable(dialogo, fg_color=WHITE)
        cuerpo.pack(fill='both', expand=True, padx=20, pady=20)
        self._label(cuerpo, '1. Abre el respaldo con su clave').pack(anchor='w', padx=12, pady=(12, 10))
        self._paragraph(cuerpo, Path(origen).name).pack(fill='x', padx=12, pady=(0, 12))
        envoltura_periodo, clave_respaldo = self._entry(cuerpo, 'Clave con la que se creó este respaldo', show='•')
        envoltura_periodo.pack(fill='x', padx=12, pady=(0, 12))
        revision_area = ctk.CTkFrame(cuerpo, fg_color=BG)
        reviewed = {'metadata': None, 'password': None}  # nosec B105 # None inicializa metadatos de revisión, no contiene una contraseña
        def revisar():
            """Valida y descifra el respaldo seleccionado, muestra su contenido resumido y prepara la confirmación de restauración."""
            try:
                metadata = self.services.backups.preview(self.user, origen, clave_respaldo.get())
            except (OSError, ValueError, sqlite3.Error) as excepcion:
                messagebox.showerror('No se pudo validar el archivo', str(excepcion), parent=dialogo)
                return
            reviewed.update(metadata=metadata, password=clave_respaldo.get())
            self._vaciar_contenedor(revision_area)
            revision_area.pack(fill='x', padx=12, pady=(14, 8))
            counts = metadata['counts']
            self._paragraph(revision_area, f"Respaldo del {metadata['created_at']} (UTC)\n{counts['issues']} ejemplares (incluye eliminados), {counts['users']} cuentas, {counts['absent_dates']} fechas sin publicación y {counts['audit']} eventos.\nAdministrador del respaldo: {metadata['master_document']}", color=INK).pack(fill='x', padx=12, pady=12)
            self._paragraph(revision_area, '2. Confirma la restauración. Se reemplazarán los datos actuales. Iniciarás sesión con las credenciales del respaldo; las PC de consulta deberán autorizarse de nuevo.', color=RED).pack(fill='x', padx=12, pady=(0, 12))
            envoltura_mes, contrasena_maestro = self._entry(revision_area, 'Tu contraseña de maestro actual', show='•')
            envoltura_mes.pack(fill='x', padx=12, pady=(0, 12))
            cw, confirmacion = self._entry(revision_area, 'Escribe RESTAURAR para continuar')
            cw.pack(fill='x', padx=12, pady=(0, 12))
            def restaurar():
                'Restaura datos validados con exclusión de operaciones y una copia previa.'
                if confirmacion.get().strip() != 'RESTAURAR':
                    messagebox.showwarning('Confirmación pendiente', 'Escribe RESTAURAR para confirmar el reemplazo.', parent=dialogo)
                    return
                if clave_respaldo.get() != reviewed['password']:
                    messagebox.showwarning('Clave modificada', 'Vuelve a revisar el respaldo con la clave actual.', parent=dialogo)
                    return
                try:
                    resultado = self.services.backups.restore(self.user, origen, reviewed['password'], contrasena_maestro.get(), reviewed['metadata']['archive_sha256'])
                except (OSError, ValueError, sqlite3.Error) as excepcion:
                    messagebox.showerror('No se completó la restauración', str(excepcion), parent=dialogo)
                    return
                dialogo.destroy()
                self.show_login()
                messagebox.showinfo('Base de datos restaurada', 'Inicia sesión con una cuenta del respaldo.\nLas computadoras de consulta requieren autorización nuevamente.\n\nLa copia del estado anterior está en:\n' + resultado['before'] + '\n\nEsa copia usa la misma clave que acabas de introducir.' + ('\n\n' + resultado['warning'] if resultado.get('warning') else ''), parent=self)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            restore = restaurar
            self._button(revision_area, 'Restaurar y cerrar las sesiones', restore, 'danger', width=290).pack(anchor='e', padx=12, pady=(0, 14))
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        review = revisar
        self._primary(cuerpo, 'Revisar respaldo sin cambiar los datos', review, width=315).pack(anchor='w', padx=12, pady=(0, 12))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _restore_backup_form = _restaurar_respaldo_formulario
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
BackupsView = VistaRespaldos
