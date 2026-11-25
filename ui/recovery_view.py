"""Preguntas seleccionables e inmutables y recuperación mediante código único."""

import sqlite3
import customtkinter as ctk
from tkinter import messagebox
from config.settings import BG, FONT, INK, RED, ROLES, SECURITY_QUESTIONS, VIEWS, WHITE
from services.access_service import AccessDenied
from utils.identity import DOCUMENT_HELP


class VistaRecuperacion:
    """Gestiona formularios de contraseña, preguntas, código y requisitos pendientes para completar el acceso a la cuenta."""
    def _credencial_contenedor(self, title, *, required=False):
        """Crea una pantalla obligatoria o diálogo modal de credenciales con cuerpo desplazable y acciones al pie."""
        titulo = title
        if required:
            self._clear()
            self.current_view = ''
            self.configure(fg_color=BG)
            self.grid_columnconfigure(0, weight=1, minsize=0, uniform='')
            self.grid_columnconfigure(1, weight=0, minsize=0, uniform='')
            recipiente = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
            recipiente.grid(row=0, column=0, columnspan=2, sticky='nsew')
        else:
            recipiente = self._dialog(titulo, '740x780')
        pie = ctk.CTkFrame(recipiente, fg_color=WHITE, corner_radius=0)
        pie.pack(side='bottom', fill='x')
        cuerpo = self._scrollable(recipiente, fg_color=WHITE, corner_radius=12)
        cuerpo.pack(fill='both', expand=True, padx=24, pady=20)
        encabezado = ctk.CTkLabel(cuerpo, text=titulo, text_color=INK, font=(FONT, 24, 'bold'),
                               wraplength=560, justify='left', anchor='w')
        encabezado.pack(fill='x', padx=18, pady=(18, 12))
        encabezado.bind('<Configure>', lambda _e: self._fit_text(encabezado, encabezado.winfo_width()))
        return recipiente, cuerpo, pie
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _credential_container = _credencial_contenedor

    def _credencial_error(self, error, label):
        """Muestra el error del formulario y agenda verificar la sesión si se trata de una denegación de acceso."""
        etiqueta = label
        etiqueta.configure(text=str(error))
        if isinstance(error, AccessDenied):
            self.after_idle(self._sync_session)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _credential_error = _credencial_error

    def _mostrar_recuperacion_codigo(self, code, document, on_close=None, *, registration=False):
        """Presenta el código recién emitido, permite copiarlo y exige el cierre previsto antes de continuar el flujo."""
        documento = document
        on_cerrar_local = on_close
        codigo = code
        on_cerrar = on_cerrar_local
        self._showing_recovery_code = True
        dialogo, cuerpo, pie = self._credential_container('Paso 3 de 3 · Guarda tu código' if registration else 'Guarda tu código de recuperación')
        self._paragraph(cuerpo, 'SE MUESTRA UNA SOLA VEZ', color=RED).pack(fill='x', padx=18, pady=(0, 12))
        self._paragraph(cuerpo, f'Cuenta: {documento}\nAnota o copia este código en un lugar privado y seguro. No se podrá consultar después de cerrar esta ventana. Reemplaza cualquier código anterior.', color=INK).pack(fill='x', padx=18, pady=(0, 18))
        valor = ctk.CTkTextbox(cuerpo, height=100, font=(FONT, 18, 'bold'), wrap='word')
        valor.pack(fill='x', padx=18, pady=(0, 16))
        valor.insert('1.0', codigo)
        valor.configure(state='disabled')
        self._paragraph(cuerpo, 'Permite recuperar el acceso junto con tu documento. No lo compartas. Si el maestro lo generó para otra persona, debe entregárselo de forma privada.').pack(fill='x', padx=18, pady=(0, 18))
        def copiar():
            """Copia el código recién mostrado al portapapeles e indica al usuario que debe guardarlo y limpiar el portapapeles."""
            self.clipboard_clear()
            self.clipboard_append(codigo)
            copied.configure(text='Código copiado. Guárdalo y limpia el portapapeles al terminar.')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        copy = copiar
        self._button(cuerpo, 'Copiar código', copy, 'secondary', width=160).pack(anchor='w', padx=18, pady=(0, 8))
        copied = self._paragraph(cuerpo, '')
        copied.pack(fill='x', padx=18, pady=(0, 18))
        acknowledged = ctk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(cuerpo, text='He guardado el código en un lugar seguro', variable=acknowledged,
                                  command=lambda: finish.configure(state='normal' if acknowledged.get() else 'disabled'))
        checkbox.pack(anchor='w', padx=18, pady=16)
        def cerrar():
            'Libera los recursos propios y finaliza esta instancia.'
            if not acknowledged.get():
                messagebox.showwarning('Guarda el código', 'Confirma que guardaste el código antes de continuar.', parent=dialogo)
                return
            self._showing_recovery_code = False
            dialogo.destroy()
            if on_cerrar:
                on_cerrar()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        close = cerrar
        finish = self._primary(pie, 'Ya lo guardé · Continuar', close, width=230, state='disabled')
        finish.pack(side='right', padx=20, pady=14)
        dialogo.protocol('WM_DELETE_WINDOW', close)
        dialogo.bind('<Escape>', lambda _e: close())
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _show_recovery_code = _mostrar_recuperacion_codigo

    def _exigir_cuenta_requisitos(self):
        """Detecta cambio obligatorio de contraseña, preguntas faltantes o código inicial y abre el paso pendiente en orden."""
        if self.user is None:
            return False
        if getattr(self, '_account_step', None) == 'code':
            return True
        if self.user['must_change_password']:
            if getattr(self, '_account_step', None) != 'password':
                self._password_form(required=True)
            return True
        if self.services.recovery.needs_configuration(self.user):
            if getattr(self, '_account_step', None) != 'questions':
                self._security_questions_form(required=True)
            return True
        if self.services.recovery.needs_code(self.user):
            codigo = self.services.recovery.enroll_code(self.user)
            self._account_step = 'code'
            def continue_sesion():
                """Finaliza el paso pendiente de código y abre la consulta de periódicos."""
                self._account_step = None
                self.show_shell(VIEWS[0])
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            continue_sesion_local = continue_sesion
            self._show_recovery_code(codigo, self.user['identity'], continue_sesion_local)
            return True
        return False
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _enforce_account_requirements = _exigir_cuenta_requisitos

    def _contrasena_formulario(self, *, required=False):
        'Construye los controles de contrasena formulario y conecta las acciones con los servicios autorizados.'
        if not self._require_access(action='Abrir cambio de contraseña propia', allow_password_change=True):
            return
        recuperacion = self.user.get('_auth_method') == 'recovery'
        if required:
            self._account_step = 'password'
        recipiente, cuerpo, pie = self._credential_container('Crear nueva contraseña' if recuperacion else 'Cambiar mi contraseña', required=required)
        self._paragraph(cuerpo, 'La recuperación exige una contraseña nueva antes de consultar la aplicación. Al guardarla recibirás un código nuevo.' if recuperacion else
                        'Elige una contraseña de 8 a 15 caracteres distinta de la actual o temporal.').pack(fill='x', padx=18, pady=(0, 16))
        contrasena_actual = None
        if not recuperacion:
            envoltura, contrasena_actual = self._entry(cuerpo, 'Contraseña actual o temporal *', '')
            envoltura.pack(fill='x', padx=18, pady=(0, 14))
        controles = []
        for etiqueta in ('Nueva contraseña *', 'Confirmar nueva contraseña *'):
            envoltura, entrada = self._entry(cuerpo, etiqueta, '')
            envoltura.pack(fill='x', padx=18, pady=(0, 14))
            controles.append(entrada)
        nueva_contrasena, confirmar = controles
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18, pady=(0, 14))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            if nueva_contrasena.get() != confirmar.get():
                error.configure(text='Las contraseñas nuevas no coinciden.')
                return
            try:
                actualizado = self.services.auth.change_password(self.user, contrasena_actual.get() if contrasena_actual else '', nueva_contrasena.get())
            except ValueError as excepcion:
                self._credential_error(excepcion, error)
                return
            codigo = actualizado.pop('_new_recovery_code', None)
            vista = self.current_view or VIEWS[0]
            self.user, self._authenticated_version = actualizado, actualizado['password_version']
            recipiente.destroy()
            def resume():
                """Finaliza el cambio obligatorio de contraseña, vuelve a la vista prevista y muestra la confirmación."""
                self._account_step = None
                self.show_shell(vista)
                self._notice('Contraseña actualizada.')
            if codigo:
                self._account_step = 'code'
                self._show_recovery_code(codigo, actualizado['identity'], resume)
            else:
                resume()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(pie, 'Guardar contraseña', save, width=185).pack(side='right', padx=(8, 20), pady=14)
        self._button(pie, 'Cerrar sesión' if required else 'Cancelar', self.show_login if required else recipiente.destroy, 'secondary', width=130).pack(side='left', padx=20, pady=14)
        (contrasena_actual or nueva_contrasena).focus_set()
        confirmar.bind('<Return>', lambda _e: save())
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _password_form = _contrasena_formulario

    def _seguridad_preguntas_formulario(self, account_data=None, *, required=False):
        'Construye los controles de seguridad preguntas formulario y conecta las acciones con los servicios autorizados.'
        cuenta_data_local = account_data
        cuenta_data = cuenta_data_local
        configuracion_inicial = cuenta_data is not None
        if not configuracion_inicial and not self._require_access(action='Abrir preguntas de seguridad propias'):
            return
        if required:
            self._account_step = 'questions'
        recipiente, cuerpo, pie = self._credential_container('Paso 2 de 3 · Tres preguntas de seguridad' if configuracion_inicial else 'Tres preguntas de seguridad', required=required)
        existente = self.services.recovery.configured_questions(self.user) if not configuracion_inicial else ()
        if existente:
            self._paragraph(cuerpo, 'Estas son tus preguntas registradas. Las preguntas y las respuestas son permanentes; las respuestas no se muestran ni se pueden editar.').pack(fill='x', padx=18, pady=(0, 16))
            for numero, pregunta in enumerate(existente, 1):
                self._paragraph(cuerpo, f'{numero}. {pregunta}', color=INK).pack(fill='x', padx=18, pady=12)
            self._paragraph(cuerpo, 'Puedes recuperar tu contraseña con estas tres respuestas o con tu código único. Si no guardaste el código, genera otro confirmando tu contraseña actual.').pack(fill='x', padx=18, pady=12)
            self._button(cuerpo, 'Generar nuevo código de recuperación', self._renovar_codigo_propio, 'secondary', width=310).pack(anchor='w', padx=18, pady=12)
            self._button(pie, 'Cerrar', recipiente.destroy, 'secondary').pack(side='right', padx=20, pady=14)
            return
        self._paragraph(cuerpo, 'Elige tres preguntas diferentes de hechos que no cambien. Recuerda o anota las respuestas en un lugar privado. Después del registro NO podrás cambiar las preguntas ni sus respuestas.', color=INK).pack(fill='x', padx=18, pady=(0, 16))
        self._paragraph(cuerpo, 'Cada respuesta admite de 2 a 50 caracteres. Conserva las tildes; se ignoran mayúsculas y espacios repetidos. Elige preguntas cuya respuesta conozcas.').pack(fill='x', padx=18, pady=(0, 16))
        contrasena_actual = None
        if not configuracion_inicial:
            envoltura, contrasena_actual = self._entry(cuerpo, 'Contraseña actual *', '', show='•')
            envoltura.pack(fill='x', padx=18, pady=(0, 18))
        controles = []
        for indice in range(3):
            envoltura, pregunta = self._combo(cuerpo, f'Pregunta {indice + 1} *', list(SECURITY_QUESTIONS), SECURITY_QUESTIONS[indice])
            envoltura.pack(fill='x', padx=18, pady=(0, 10))
            envoltura, respuesta_seguridad = self._entry(cuerpo, f'Respuesta {indice + 1} *', '')
            envoltura.pack(fill='x', padx=18, pady=(0, 20))
            controles.append((pregunta, respuesta_seguridad))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18, pady=(0, 14))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            preguntas = [(pregunta.get(), respuesta_seguridad.get()) for pregunta, respuesta_seguridad in controles]
            try:
                if configuracion_inicial:
                    nombre, identidad, contrasena, perfil = cuenta_data
                    resultado = (self.services.auth.create_master(nombre, identidad, contrasena, preguntas) if perfil == ROLES[0] else
                              self.services.users.register_user(nombre, identidad, contrasena, preguntas, role=perfil))
                else:
                    self.services.recovery.configure_questions(self.user, contrasena_actual.get(), preguntas)
            except sqlite3.IntegrityError:
                error.configure(text='Ya existe una cuenta con ese documento.')
                return
            except ValueError as excepcion:
                self._credential_error(excepcion, error)
                return
            recipiente.destroy()
            if configuracion_inicial:
                def signin():
                    """Recuerda el documento del registro completado y vuelve al inicio de sesión."""
                    self._documento_recordado = identidad
                    self.show_login()
                self._show_recovery_code(resultado.recovery_code, identidad, signin, registration=True)
            else:
                self._account_step = None
                if required:
                    self.show_shell(VIEWS[0])
                self._notice('Preguntas guardadas de forma permanente.')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(pie, ('Crear administrador principal' if cuenta_data[3] == ROLES[0] else 'Crear mi cuenta') if configuracion_inicial else 'Guardar preguntas', save, width=245 if configuracion_inicial and cuenta_data[3] == ROLES[0] else 190).pack(side='right', padx=(8, 20), pady=14)
        self._button(pie, 'Cerrar sesión' if required else 'Cancelar', self.show_login if required else recipiente.destroy, 'secondary', width=130).pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _security_questions_form = _seguridad_preguntas_formulario

    def _administrador_contrasena_formulario(self, record):
        'Construye los controles de administrador contrasena formulario y conecta las acciones con los servicios autorizados.'
        registro = record
        self._admin_recovery_form(registro, reset_password=True)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _admin_password_form = _administrador_contrasena_formulario

    def _administrador_codigo_formulario(self, record):
        'Construye los controles de administrador codigo formulario y conecta las acciones con los servicios autorizados.'
        registro = record
        self._admin_recovery_form(registro, reset_password=False)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _admin_code_form = _administrador_codigo_formulario

    def _administrador_recuperacion_formulario(self, record, *, reset_password):
        'Construye los controles de administrador recuperacion formulario y conecta las acciones con los servicios autorizados.'
        reiniciar_contrasena_local = reset_password
        registro = record
        reiniciar_contrasena = reiniciar_contrasena_local
        if self.services.read_only or not self._require_access(action='Gestionar recuperación', master=True):
            return
        recipiente, cuerpo, pie = self._credential_container('Restablecer contraseña' if reiniciar_contrasena else 'Regenerar código de recuperación')
        self._paragraph(cuerpo, f"Cuenta: {registro['name']} · {registro['identity']}", color=INK).pack(fill='x', padx=18, pady=(0, 16))
        self._paragraph(cuerpo, 'La contraseña temporal obliga a cambiarla al entrar. También se generará un código nuevo.' if reiniciar_contrasena else
                        'Se invalidará el código anterior. La contraseña de esta cuenta permanecerá igual.').pack(fill='x', padx=18, pady=(0, 16))
        envoltura, contrasena_maestro = self._entry(cuerpo, 'Tu contraseña actual de maestro *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=(0, 14))
        contrasena_temporal = confirmar = None
        if reiniciar_contrasena:
            envoltura, contrasena_temporal = self._entry(cuerpo, 'Contraseña temporal *', '', show='•')
            envoltura.pack(fill='x', padx=18, pady=(0, 14))
            envoltura, confirmar = self._entry(cuerpo, 'Confirmar contraseña temporal *', '', show='•')
            envoltura.pack(fill='x', padx=18, pady=(0, 14))
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18, pady=(0, 14))
        def guardar():
            'Valida los campos del formulario y guarda la operación autorizada.'
            if reiniciar_contrasena and contrasena_temporal.get() != confirmar.get():
                error.configure(text='Las contraseñas temporales no coinciden.')
                return
            try:
                if reiniciar_contrasena:
                    codigo = self.services.users.reset_password(self.user, registro['id'], contrasena_maestro.get(), contrasena_temporal.get(), expected_version=registro['password_version'])
                else:
                    codigo = self.services.recovery.regenerate_code(self.user, registro['id'], contrasena_maestro.get(), expected_version=registro['password_version'])
            except ValueError as excepcion:
                self._credential_error(excepcion, error)
                return
            recipiente.destroy()
            self_reiniciar = reiniciar_contrasena and registro['id'] == self.user['id']
            def resume():
                """Vuelve al ingreso si cambió la cuenta propia o al listado de usuarios tras regenerar credenciales de otra cuenta."""
                if self_reiniciar:
                    self.show_login()
                else:
                    self.navigate(VIEWS[4])
                    self._notice('Contraseña temporal y código actualizados.' if reiniciar_contrasena else 'Código regenerado; la contraseña se conserva.')
            self._show_recovery_code(codigo, registro['identity'], resume)
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        save = guardar
        self._primary(pie, 'Guardar y mostrar código', save, width=230).pack(side='right', padx=(8, 20), pady=14)
        self._button(pie, 'Cancelar', recipiente.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _admin_recovery_form = _administrador_recuperacion_formulario

    def _renovar_codigo_propio(self):
        """Permite al titular emitir y guardar un código nuevo confirmando su contraseña."""
        if not self._require_access(action='Renovar mi código de recuperación'):
            return
        dialogo, cuerpo, pie = self._credential_container('Generar nuevo código de recuperación')
        self._paragraph(cuerpo, 'El código anterior dejará de funcionar. Tu contraseña y tus preguntas se conservarán.').pack(fill='x', padx=18, pady=12)
        envoltura, contrasena = self._entry(cuerpo, 'Contraseña actual *', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=12)
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18, pady=12)
        def generar():
            """Solicita el código y obliga a confirmar que fue conservado."""
            try:
                codigo = self.services.recovery.renovar_codigo_propio(self.user, contrasena.get())
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            dialogo.destroy()
            self._show_recovery_code(codigo, self.user['identity'])
        self._primary(pie, 'Generar y mostrar código', generar, width=230).pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', dialogo.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)

    def mostrar_maestro_recuperacion(self):
        """Recupera cualquier perfil mediante código único o las tres respuestas guardadas."""
        from utils.identity import normalize_document
        if self.user is not None:
            return
        dialogo, cuerpo, pie = self._credential_container('Recuperar mi contraseña')
        self._paragraph(cuerpo, 'Elige uno de los dos métodos. Después tendrás que crear una contraseña nueva y guardar el código nuevo.').pack(fill='x', padx=18, pady=(0, 16))
        self._paragraph(cuerpo, DOCUMENT_HELP).pack(fill='x', padx=18, pady=(0, 12))
        envoltura, identidad = self._document_entry(cuerpo, 'Documento *')
        envoltura.pack(fill='x', padx=18, pady=(0, 12))
        metodos = ctk.CTkTabview(cuerpo)
        metodos.pack(fill='x', padx=18, pady=12)
        pestaña_codigo = metodos.add('Con mi código')
        pestaña_preguntas = metodos.add('Con mis preguntas')
        envoltura, codigo = self._entry(pestaña_codigo, 'Código de recuperación *', 'HMR-…')
        envoltura.pack(fill='x', padx=12, pady=14)
        variable_codigo = ctk.StringVar(master=codigo, value='')
        codigo.configure(textvariable=variable_codigo)
        codigo._variable_codigo = variable_codigo
        def convertir_codigo_mayusculas(*argumentos):
            """Normaliza al escribir o pegar, sin ocultar el código ni cambiar su validación."""
            contenido = variable_codigo.get()
            if contenido != contenido.upper():
                variable_codigo.set(contenido.upper())
        variable_codigo.trace_add('write', convertir_codigo_mayusculas)

        self._paragraph(pestaña_codigo, 'Usa el último código que guardaste. No necesitas responder las preguntas.').pack(fill='x', padx=12, pady=(0, 14))
        preguntas = {'documento': None, 'respuestas': []}
        contenedor_preguntas = ctk.CTkFrame(pestaña_preguntas, fg_color='transparent')
        contenedor_preguntas.pack(fill='x', padx=12, pady=10)
        error = self._paragraph(cuerpo, '', color=RED)
        error.pack(fill='x', padx=18, pady=12)
        def cargar_preguntas():
            """Muestra solo las preguntas del documento indicado y prepara respuestas ocultas."""
            try:
                documento = normalize_document(identidad.get())
                elegidas = self.services.auth.obtener_preguntas_recuperacion(documento)
            except ValueError as excepcion:
                preguntas.update(documento=None, respuestas=[])
                error.configure(text=str(excepcion))
                return
            for control in contenedor_preguntas.winfo_children():
                control.destroy()
            respuestas = []
            for numero, pregunta in enumerate(elegidas, 1):
                envoltura, respuesta = self._entry(contenedor_preguntas, f'{numero}. {pregunta}', '')
                envoltura.pack(fill='x', pady=(0, 14))
                respuestas.append(respuesta)
            preguntas.update(documento=documento, respuestas=respuestas)
            error.configure(text='')
        self._button(pestaña_preguntas, 'Mostrar mis preguntas', cargar_preguntas, 'secondary', width=220).pack(anchor='w', padx=12, pady=10, before=contenedor_preguntas)
        def recuperar():
            """Verifica únicamente el método elegido y abre el cambio obligatorio de contraseña."""
            try:
                if metodos.get() == 'Con mi código':
                    usuario = self.services.auth.authenticate_with_code(identidad.get(), codigo.get())
                else:
                    documento = normalize_document(identidad.get())
                    if preguntas['documento'] != documento or len(preguntas['respuestas']) != 3:
                        raise ValueError('Pulsa Mostrar mis preguntas para este documento y responde las tres preguntas.')
                    usuario = self.services.auth.autenticar_con_preguntas(documento, [respuesta.get() for respuesta in preguntas['respuestas']])
            except ValueError as excepcion:
                codigo.delete(0, 'end')
                for respuesta in preguntas['respuestas']:
                    respuesta.delete(0, 'end')
                error.configure(text=str(excepcion))
                return
            dialogo.destroy()
            self.user, self._authenticated_version = usuario, usuario['password_version']
            self.show_shell(VIEWS[0])
        self._primary(pie, 'Recuperar acceso', recuperar, width=185).pack(side='right', padx=20, pady=14)
        self._button(pie, 'Cancelar', dialogo.destroy, 'secondary', width=120).pack(side='left', padx=20, pady=14)
        identidad.focus_set()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    show_master_recovery = mostrar_maestro_recuperacion
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RecoveryView = VistaRecuperacion
