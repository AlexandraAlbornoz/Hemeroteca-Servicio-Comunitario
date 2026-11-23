"""Asistente de conexión por nombre y aprobación exclusiva del maestro."""

import sys
import subprocess  # nosec B404 # subprocess necesario para herramientas locales; sin shell=True
from tkinter import TclError, messagebox
import customtkinter as ctk
from hemeroteca.config.settings import WINDOWS_RESOURCES, WINDOWS_POWERSHELL, INK, RED, WHITE


class VistaRed:
    """Presenta preparación, autorización y desconexión de equipos y traslado de la computadora principal."""
    def _reiniciar_servicios(self):
        """Cierra el coordinador actual, reconstruye servicios según la red vigente y vuelve al inicio de sesión."""
        gestor = self.services.original.network
        self.services.close()
        from hemeroteca.ui.tareas import ServiciosDeInterfaz
        self.services = ServiciosDeInterfaz(self, gestor.services())
        self._network_signature = self._network_state()
        self.show_login()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _restart_services = _reiniciar_servicios

    def _windows_red_inicializacion(self):
        """Abre el asistente local de red en Windows o explica su disponibilidad en otras plataformas."""
        if sys.platform != 'win32':
            messagebox.showinfo('Configuración de Windows', 'En Windows este botón abre el asistente para permitir Hemeroteca en la red privada.', parent=self)
            return
        subprocess.Popen([str(WINDOWS_POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'RemoteSigned',  # nosec B603 # argumentos separados sin intérprete de comandos; ejecutable del entorno o ruta local controlada
                          '-File', str(WINDOWS_RESOURCES / 'Configurar_Red_Windows.ps1'),
                          '-PythonPath', sys.executable],
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _windows_network_setup = _windows_red_inicializacion

    def _conectar_servidor_formulario(self):
        'Construye los controles de conectar servidor formulario y conecta las acciones con los servicios autorizados.'
        try:
            receptor = self.services.network.prepare_consultation_pc(self.services)
        except (ValueError, OSError) as excepcion:
            messagebox.showwarning('Preparar computadora', str(excepcion), parent=self)
            return
        recipiente, cuerpo, pie = self._credential_container('Preparar PC de consulta')
        self._paragraph(cuerpo, '1. Deja esta ventana abierta.\n2. En la PC principal, el maestro abre Computadoras conectadas y pulsa Buscar computadoras.\n3. El maestro selecciona el nombre de esta PC y escribe el código que aparece aquí.', color=INK).pack(fill='x', padx=18, pady=(0, 18))
        self._label(cuerpo, 'Nombre de esta computadora').pack(anchor='w', padx=18)
        self._paragraph(cuerpo, receptor.name, color=INK).pack(fill='x', padx=18, pady=(4, 18))
        addresses = getattr(receptor, 'discovery_addresses', ())
        if addresses:
            self._paragraph(cuerpo, 'IPv4 para búsqueda directa: ' + ', '.join(addresses), color=INK).pack(fill='x', padx=18, pady=(0, 14))
        self._label(cuerpo, 'Código temporal de conexión').pack(anchor='w', padx=18)
        valor = ctk.CTkEntry(cuerpo, height=52, font=('Arial', 22, 'bold'), justify='center')
        valor.pack(fill='x', padx=18, pady=(6, 12))
        valor.insert(0, receptor.code)
        valor.configure(state='readonly')
        self._paragraph(cuerpo, 'Este código vence en cinco minutos. Compártelo únicamente con el administrador que está frente a la PC principal. Tu contraseña personal no se necesita para este paso.').pack(fill='x', padx=18, pady=(0, 14))
        estado = self._paragraph(cuerpo, 'Esperando la autorización del administrador principal…')
        estado.pack(fill='x', padx=18, pady=(0, 14))
        self._button(cuerpo, 'Permitir la red en Windows', self._windows_network_setup, 'secondary', width=250).pack(anchor='w', padx=18, pady=(0, 10))
        self._paragraph(cuerpo, 'Si Windows pide permiso, el responsable de esta PC debe permitir la aplicación en la red privada de la hemeroteca.').pack(fill='x', padx=18, pady=(0, 14))
        estado_local = {'job': None, 'closed': False}
        def limpieza(_event=None):
            'Cancela revisiones pendientes y libera los recursos de esta operación.'
            _evento_local = _event
            _evento = _evento_local
            if _evento is not None and _evento.widget is not recipiente:
                return
            if estado_local['closed']:
                return
            estado_local['closed'] = True
            if estado_local['job']:
                recipiente.after_cancel(estado_local['job'])
            self.services.network.stop_preparation()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        cleanup = limpieza
        def cerrar():
            'Libera los recursos propios y finaliza esta instancia.'
            cleanup()
            recipiente.destroy()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        close = cerrar
        def sondear():
            'Comprueba el progreso y programa la siguiente revisión sin bloquear Tk.'
            if estado_local['closed']:
                return
            if receptor.state == 'connected':
                cleanup()
                recipiente.destroy()
                self._restart_services()
                messagebox.showinfo('Computadora conectada', 'Esta PC ya está conectada. Inicia sesión con tu cuenta o pulsa «Crear mi cuenta» si todavía no tienes una.', parent=self)
                return
            if receptor.expired():
                estado.configure(text='El código venció o hubo demasiados intentos. Cierra esta ventana y vuelve a preparar la PC.', text_color=RED)
            elif receptor.last_error:
                estado.configure(text=receptor.last_error, text_color=RED)
            programar_sondeo()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        poll = sondear
        def programar_sondeo():
            """Libera la preparación si Tk rechaza crear o renovar el temporizador."""
            try:
                estado_local['job'] = recipiente.after(1000, poll)
            except (RuntimeError, TclError):
                cleanup()
                recipiente.destroy()
                messagebox.showwarning('Preparar computadora',
                    'No se pudo mantener la revisión de conexión. Vuelve a preparar esta computadora.', parent=self)
        recipiente.bind('<Destroy>', cleanup, add='+')
        recipiente.bind('<Escape>', lambda _e: close())
        recipiente.protocol('WM_DELETE_WINDOW', close)
        self._button(pie, 'Cancelar preparación', close, 'secondary', width=210).pack(side='right', padx=20, pady=14)
        programar_sondeo()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _connect_server_form = _conectar_servidor_formulario

    def _red_formulario(self):
        'Construye los controles de red formulario y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action='Gestionar computadoras', master=True):
            return
        gestor = self.services.network
        actual = gestor.describe()
        recipiente, cuerpo, pie = self._credential_container('Computadoras conectadas')
        if self.services.read_only:
            self._paragraph(cuerpo, 'Esta PC está conectada como equipo de consulta. Para conectar o retirar otras computadoras, usa la PC principal.', color=INK).pack(fill='x', padx=18, pady=(0, 18))
            self._button(cuerpo, 'Convertir esta PC en la principal', lambda: (recipiente.destroy(), self._promote_principal_form()), 'secondary', width=290).pack(anchor='w', padx=18, pady=14)
            self._button(pie, 'Cerrar', recipiente.destroy, 'secondary').pack(side='right', padx=20, pady=14)
            return
        activo = actual['mode'] == 'server'
        self._paragraph(cuerpo, 'Esta PC es la principal. Mantén la aplicación abierta para que las otras computadoras puedan consultar.' if activo else
                        'Primero activa esta PC como principal. Después podrás buscar y autorizar las computadoras de consulta.', color=INK).pack(fill='x', padx=18, pady=(0, 14))
        if not activo:
            envoltura, contrasena = self._entry(cuerpo, 'Tu contraseña de administrador maestro *', '', show='•')
            envoltura.pack(fill='x', padx=18, pady=(0, 14))
            error = self._paragraph(cuerpo, '', color=RED)
            error.pack(fill='x', padx=18)
            def activate():
                """Activa la PC principal, actualiza la firma de configuración y vuelve a mostrar las opciones de red."""
                try:
                    gestor.activate_principal(self.services, self.user, contrasena.get())
                except (ValueError, OSError) as excepcion:
                    error.configure(text=str(excepcion))
                    return
                self._network_signature = self._network_state()
                recipiente.destroy()
                self._network_form()
            self._primary(cuerpo, 'Activar esta PC como principal', activate, width=280).pack(anchor='w', padx=18, pady=14)
        self._button(cuerpo, 'Permitir la red en Windows', self._windows_network_setup, 'secondary', width=260).pack(anchor='w', padx=18, pady=10)
        self._paragraph(cuerpo, 'Para añadir una PC: abre allí Hemeroteca y pulsa Preparar PC de consulta. Luego vuelve aquí y busca las computadoras.').pack(fill='x', padx=18, pady=(8, 12))
        waiting = ctk.CTkFrame(cuerpo, fg_color=WHITE)
        waiting.pack(fill='x', padx=6)
        estado = self._paragraph(cuerpo, '')
        estado.pack(fill='x', padx=18, pady=10)
        address_row, address_field = self._entry(cuerpo, 'IPv4 de la PC de consulta (opcional)', '')
        address_row.pack(fill='x', padx=18, pady=(0, 10))
        def search():
            'Obtiene los resultados que corresponden a los filtros elegidos.'
            search_boton.configure(state='disabled', text='Buscando…')
            recipiente.update_idletasks()
            try:
                address = address_field.get().strip()
                options = {'address': address} if address else {}
                candidates = gestor.discover_computers(self.services, self.user, **options)
            except (ValueError, OSError) as excepcion:
                estado.configure(text=str(excepcion), text_color=RED)
                search_boton.configure(state='normal', text='Buscar computadoras')
                return
            self._vaciar_contenedor(waiting)
            for candidato in candidates:
                fila = ctk.CTkFrame(waiting, fg_color='#F4F7FC', corner_radius=8)
                fila.pack(fill='x', padx=10, pady=6)
                self._paragraph(fila, candidato['name'], color=INK).pack(fill='x', padx=12, pady=(10, 4))
                self._button(fila, 'Conectar esta computadora', lambda elegida=candidato: self._approve_computer_form(elegida), 'secondary', width=260).pack(anchor='w', padx=12, pady=(0, 10))
            estado.configure(text=f'{len(candidates)} computadora(s) esperando autorización.' if candidates else
                             'No encontramos computadoras en espera. Revisa que ambas estén en la misma red o introduce la IPv4 que muestra la PC de consulta.', text_color=INK)
            search_boton.configure(state='normal', text='Buscar computadoras')
        search_boton = self._primary(cuerpo, 'Buscar computadoras', search, width=240, state='normal' if activo else 'disabled')
        search_boton.pack(anchor='w', padx=18, pady=(0, 14))
        self._label(cuerpo, 'Computadoras autorizadas').pack(anchor='w', padx=18, pady=(12, 8))
        aprobado = gestor.approved_computers(self.services, self.user)
        if not aprobado:
            self._paragraph(cuerpo, 'Todavía no hay computadoras autorizadas.').pack(fill='x', padx=18, pady=(0, 12))
        for registro in aprobado:
            fila = ctk.CTkFrame(cuerpo, fg_color='#F4F7FC', corner_radius=8)
            fila.pack(fill='x', padx=18, pady=6)
            self._paragraph(fila, registro['name'] + (' · Autorizada' if registro['active'] else ' · Desconectada'), color=INK).pack(fill='x', padx=12, pady=10)
            if registro['active']:
                self._button(fila, 'Retirar acceso', lambda elegida=dict(registro): self._revoke_computer_form(elegida), 'danger', width=160).pack(anchor='w', padx=12, pady=(0, 10))
        self._button(pie, 'Actualizar lista', lambda: (recipiente.destroy(), self._network_form()), 'secondary', width=160).pack(side='left', padx=20, pady=14)
        self._button(pie, 'Cerrar', recipiente.destroy, 'secondary', width=110).pack(side='right', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _network_form = _red_formulario

    def _aprobar_computadora_formulario(self, candidate):
        'Construye los controles de aprobar computadora formulario y conecta las acciones con los servicios autorizados.'
        candidato = candidate
        if not self._require_access(action='Autorizar nueva computadora', master=True):
            return
        recipiente, cuerpo, pie = self._credential_container('Autorizar computadora')
        self._paragraph(cuerpo, 'Computadora: ' + candidato['name'] + '\nComprueba el nombre en la otra PC y copia aquí su código temporal.', color=INK).pack(fill='x', padx=18, pady=(0, 16))
        envoltura, codigo = self._entry(cuerpo, 'Código que muestra la otra computadora *', 'XXXX-XXXX-XXXX')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        envoltura, contrasena = self._entry(cuerpo, 'Tu contraseña de administrador maestro *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18)
        def aprobar():
            """Envía código y contraseña al servicio de emparejamiento, impide doble pulsación y presenta el resultado."""
            boton.configure(state='disabled', text='Conectando…')
            recipiente.update_idletasks()
            try:
                self.services.network.approve_computer(self.services, self.user, candidato, codigo.get(), contrasena.get())
            except (ValueError, OSError) as excepcion:
                error.configure(text=str(excepcion))
                boton.configure(state='normal', text='Autorizar y conectar')
                return
            recipiente.destroy()
            messagebox.showinfo('Autorización guardada', 'Esta computadora quedó autorizada. El usuario puede iniciar sesión allí con su propia cuenta. Actualiza la lista para verla.', parent=self)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        approve = aprobar
        boton = self._primary(pie, 'Autorizar y conectar', approve, width=220)
        boton.pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', recipiente.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _approve_computer_form = _aprobar_computadora_formulario

    def _revocar_computadora_formulario(self, record):
        'Construye los controles de revocar computadora formulario y conecta las acciones con los servicios autorizados.'
        registro = record
        if not self._require_access(action='Retirar acceso de computadora', master=True):
            return
        recipiente, cuerpo, pie = self._credential_container('Retirar acceso de computadora')
        self._paragraph(cuerpo, 'Se cerrará el acceso de ' + registro['name'] + '. Sus usuarios deberán usar otra PC autorizada o pedir una nueva conexión.', color=INK).pack(fill='x', padx=18, pady=(0, 16))
        envoltura, contrasena = self._entry(cuerpo, 'Tu contraseña de administrador maestro *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18)
        def revocar():
            """Solicita retirar el acceso del equipo seleccionado y conserva abierto el diálogo si hay un error."""
            try:
                self.services.network.revoke_computer(self.services, self.user, registro['device_id'], contrasena.get())
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            recipiente.destroy()
            messagebox.showinfo('Acceso retirado', 'La computadora ya no puede consultar la hemeroteca. Actualiza la lista para ver su estado.', parent=self)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        revoke = revocar
        self._button(pie, 'Retirar acceso', revoke, 'danger', width=180).pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', recipiente.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _revoke_computer_form = _revocar_computadora_formulario

    def _promover_principal_formulario(self):
        'Construye los controles de promover principal formulario y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action='Cambiar PC principal', master=True):
            return
        recipiente, cuerpo, pie = self._credential_container('Convertir esta PC en principal')
        self._paragraph(cuerpo, 'El maestro trasladará la base a esta computadora. Mantén ambas aplicaciones abiertas hasta terminar.', color=INK).pack(fill='x', padx=18, pady=(0, 16))
        envoltura, contrasena = self._entry(cuerpo, 'Tu contraseña de administrador maestro *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18)
        def promover():
            """Solicita trasladar la función de servidor a esta PC y reconstruye los servicios tras completarse."""
            try:
                self.services.network.activate_principal(self.services, self.user, contrasena.get())
            except (ValueError, OSError) as excepcion:
                error.configure(text=str(excepcion))
                return
            recipiente.destroy()
            self._restart_services()
            messagebox.showinfo('PC principal actualizada', 'El traslado terminó. Inicia sesión en esta computadora.', parent=self)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        promote = promover
        self._primary(pie, 'Trasladar a esta PC', promote, width=220).pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', recipiente.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _promote_principal_form = _promover_principal_formulario

    def _recuperar_traslado_formulario(self):
        'Construye los controles de recuperar traslado formulario y conecta las acciones con los servicios autorizados.'
        recipiente, cuerpo, pie = self._credential_container('Recuperar traslado pendiente')
        self._paragraph(cuerpo, 'Solo el maestro puede cancelar un traslado interrumpido. Mantén abierta la PC destino en espera.').pack(fill='x', padx=18, pady=(0, 16))
        envoltura, documento = self._entry(cuerpo, 'Documento del maestro *', 'V-12345678')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        envoltura, contrasena = self._entry(cuerpo, 'Contraseña del maestro *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18)
        def restaurar():
            'Restaura datos validados con exclusión de operaciones y una copia previa.'
            try:
                self.services.network.recover_pending_transfer(documento.get(), contrasena.get())
            except (ValueError, OSError) as excepcion:
                error.configure(text=str(excepcion))
                return
            recipiente.destroy()
            self._restart_services()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        restore = restaurar
        self._primary(pie, 'Recuperar PC anterior', restore, width=230).pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', recipiente.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _recover_transfer_form = _recuperar_traslado_formulario
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
NetworkView = VistaRed
