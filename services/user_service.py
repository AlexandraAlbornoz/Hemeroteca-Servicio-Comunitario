"""Consulta y administración de cuentas de usuario."""

from services.base import ServicioConAcceso

import sqlite3

from config.settings import ROLES, SECURITY_QUESTIONS, VIEWS, REPORT_PERMISSIONS
from database.connection import transaction
from services.access_service import AccessDenied
from services.audit_service import append_event
from services.recovery_service import RegistrationResult, issue_recovery_code, store_security_questions
from utils.identity import normalize_document
from utils.validaciones import validar_nombre, validar_documento_nuevo
from utils.security import validate_password
from utils.timestamps import utc_now
from utils.security import new_password_version, password_hash, password_matches, prepare_security_questions


class ServicioUsuarios(ServicioConAcceso):
    """Administra altas, perfiles, permisos y estado de cuentas, protegiendo la cuenta maestra y los cambios concurrentes."""
    def formatear_aplicacion(self, actor, contrasena, confirmacion):
        """Respalda y reinicia datos operativos, conservando maestro, red y auditoría."""
        from datetime import datetime
        from pathlib import Path
        from database.maintenance import database_guard
        actual = self.access.require_access(actor, action='Formatear aplicación', master=True)
        if not password_matches(contrasena, actual['password']):
            raise AccessDenied('La contraseña actual del maestro no es correcta.')
        if confirmacion != 'FORMATEAR HEMEROTECA':
            raise ValueError('La confirmación del formateo no coincide.')
        archivo = self.conn.execute('PRAGMA database_list').fetchone()[2]
        if not archivo:
            raise ValueError('El formateo requiere una base de datos con respaldo en disco.')
        ruta = Path(archivo)
        with database_guard(ruta):
            # BEGIN IMMEDIATE bloquea otros escritores durante respaldo y borrado.
            with self.access.authorized_write(actor, action='Formatear aplicación', master=True) as actual:
                if not password_matches(contrasena, actual['password']):
                    raise AccessDenied('La contraseña cambió. Vuelve a verificarla.')
                carpeta = ruta.parent / 'backups'
                carpeta.mkdir(exist_ok=True)
                copia = carpeta / f'antes-formateo-{datetime.now():%Y%m%d-%H%M%S-%f}.db'
                # Una segunda conexión lee el estado previo confirmado mientras se
                # conserva el bloqueo de escritura de esta transacción.
                origen = sqlite3.connect(f'{ruta.as_uri()}?mode=ro', uri=True)
                destino = sqlite3.connect(copia)
                try:
                    origen.backup(destino)
                    if destino.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('No se pudo verificar la copia; no se borró información.')
                finally:
                    destino.close()
                    origen.close()
                for tabla in ('api_sessions', 'grants', 'requests', 'issues', 'absent_dates', 'auth_failures'):
                    self.conn.execute('DELETE FROM ' + tabla)
                self.conn.execute('DELETE FROM users WHERE id<>?', (actual['id'],))
                self.conn.execute('UPDATE users SET password_version=password_version+1 WHERE id=?', (actual['id'],))
                append_event(self.conn, self.access.actor_label(actual), 'Formateo de Hemeroteca con copia previa verificada')
        return str(copia)

    def buscar_usuarios(self, actor, *, texto='', estado='Todos', pagina=1):
        """Busca cuentas en SQL preservando las columnas públicas y los permisos."""
        responsable = actor
        from services.paginacion import paginar
        self.access.require_access(responsable, VIEWS[4], action='Consultar usuarios paginados', view=True)
        if not isinstance(texto, str) or estado not in ('Todos', 'Activo', 'Inactivo'):
            raise ValueError('Los filtros de usuarios no son válidos.')
        consulta = "SELECT id,name,coalesce(document,'Documento pendiente') AS identity,document,role,active,created_at FROM users WHERE instr(plegar_texto(name || ' ' || coalesce(document,'Documento pendiente')),?)>0"
        parametros = [texto.strip().casefold()]
        if estado != 'Todos':
            consulta += ' AND active=?'
            parametros.append(int(estado == 'Activo'))
        return paginar(self.conn, consulta, parametros, pagina=pagina, orden='name COLLATE NOCASE,id')


    def usuarios(self, actor):
        """Lista datos públicos de cuentas ordenados por nombre tras autorizar la vista de Usuarios."""
        responsable = actor
        self.access.require_access(responsable, VIEWS[4], action="Consultar usuarios", view=True)
        return self.conn.execute("SELECT id,name,coalesce(document,'Documento pendiente') AS identity,document,role,active,created_at FROM users ORDER BY name COLLATE NOCASE").fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    users = usuarios

    def revocar_grant(self, actor, user_id, permission, expected_version=None):
        """Retira un permiso de una cuenta no maestra, comprueba su versión y registra la revocación."""
        usuario_id_local = user_id
        usuario_id = usuario_id_local
        responsable = actor
        permiso = permission
        identificador_usuario = usuario_id
        with self.access.authorized_write(responsable, action=f"Revocar permiso: {permiso}", master=True) as responsable:
            destinatario = self._managed_user(identificador_usuario, expected_version)
            if destinatario["role"] == ROLES[0]:
                raise AccessDenied("No se pueden revocar permisos del administrador maestro desde aquí.")
            self.conn.execute("DELETE FROM grants WHERE user_id=? AND permission=?", (identificador_usuario, permiso))
            append_event(self.conn, self.access.actor_label(responsable), f"Permiso revocado: {permiso} · {destinatario['identity']}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    revoke_grant = revocar_grant

    def establecer_reporte_permisos(self, actor, user_id, permissions, expected_version=None):
        """Actualiza únicamente los permisos PDF seleccionados de una cuenta activa y registra la decisión maestra."""
        usuario_id_local = user_id
        usuario_id = usuario_id_local
        responsable = actor
        permisos = permissions
        identificador_usuario = usuario_id
        if not isinstance(permisos, (list, tuple)) or any(not isinstance(p, str) or p not in REPORT_PERMISSIONS for p in permisos):
            raise ValueError("Selecciona únicamente los permisos PDF disponibles.")
        with self.access.authorized_write(responsable, action='Actualizar permisos PDF', master=True) as actual:
            destinatario = self._managed_user(identificador_usuario, expected_version)
            if not destinatario['active'] or destinatario['role'] == ROLES[0]:
                raise ValueError("Selecciona una cuenta activa diferente del administrador maestro.")
            for permiso in REPORT_PERMISSIONS:
                if permiso in permisos:
                    self.conn.execute('INSERT OR IGNORE INTO grants(user_id,permission) VALUES(?,?)', (identificador_usuario, permiso))
                else:
                    self.conn.execute('DELETE FROM grants WHERE user_id=? AND permission=?', (identificador_usuario, permiso))
            append_event(self.conn, self.access.actor_label(actual), f"Permisos PDF actualizados: {destinatario['identity']} · {', '.join(sorted(set(permisos))) or 'Ninguno'}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    set_report_permissions = establecer_reporte_permisos

    def establecer_usuario_activo(self, actor, user_id, active, expected_version=None):
        """Activa o desactiva una cuenta no maestra e incrementa su versión para invalidar sesiones anteriores."""
        usuario_id_local = user_id
        activo = active
        usuario_id = usuario_id_local
        responsable = actor
        identificador_usuario = usuario_id
        with self.access.authorized_write(responsable, action=f"{'Activar' if activo else 'Desactivar'} cuenta #{identificador_usuario}", master=True) as responsable:
            destinatario = self._managed_user(identificador_usuario, expected_version)
            if destinatario["role"] == ROLES[0]:
                raise AccessDenied("No se puede cambiar el estado de un administrador maestro desde aquí.")
            self.conn.execute("UPDATE users SET active=?,password_version=password_version+1 WHERE id=?", (int(bool(activo)), identificador_usuario))
            append_event(self.conn, self.access.actor_label(responsable), f"Cuenta {'activada' if activo else 'desactivada'}: {destinatario['identity']}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    set_user_active = establecer_usuario_activo

    def registrar_usuario(self, name, identity, password, security_questions, role=ROLES[2]):
        """Registro personal de usuario o administrador regular, sin permisos extra."""
        seguridad_preguntas_local = security_questions
        seguridad_preguntas = seguridad_preguntas_local
        identidad = identity
        nombre = name
        contrasena = password
        perfil = role
        preguntas_seguridad = seguridad_preguntas
        if perfil not in ROLES[1:]:
            raise ValueError("Selecciona Usuario regular o Administrador regular.")
        if not isinstance(nombre, str) or not nombre.strip() or len(nombre.strip()) > 150:
            raise ValueError("Completa el nombre con un máximo de 150 caracteres.")
        if not isinstance(preguntas_seguridad, (list, tuple)) or len(preguntas_seguridad) != 3:
            raise ValueError("Selecciona y responde tres preguntas de seguridad diferentes.")
        for elemento in preguntas_seguridad:
            if (not isinstance(elemento, (list, tuple)) or len(elemento) != 2
                    or not all(isinstance(valor, str) for valor in elemento)):
                raise ValueError("Selecciona cada pregunta de la lista y escribe su respuesta.")
        try:
            return self.create_user(nombre, identidad, contrasena, perfil,
                                    security_questions=preguntas_seguridad)
        except sqlite3.IntegrityError as excepcion:
            documento = normalize_document(identidad)
            if self.conn.execute("SELECT 1 FROM users WHERE document=? OR lower(identity)=lower(?)",
                                 (documento, documento)).fetchone():
                raise ValueError("Ya existe una cuenta con ese documento. Inicia sesión o recupera tu contraseña.") from excepcion
            raise
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    register_user = registrar_usuario

    def create_usuario(self, name: str, identity: str, password: str, role: str = "Usuario regular", actor=None, security_answers=None, security_questions=None):
        'Valida la cuenta nueva y conserva permisos iniciales y recuperación.'
        seguridad_answers_local = security_answers
        seguridad_preguntas_local = security_questions
        seguridad_answers = seguridad_answers_local
        seguridad_preguntas = seguridad_preguntas_local
        responsable = actor
        identidad = identity
        nombre = name
        contrasena = password
        perfil = role
        respuestas_seguridad = seguridad_answers
        preguntas_seguridad = seguridad_preguntas
        identidad = validar_documento_nuevo(identidad)
        nombre = validar_nombre(nombre)
        validate_password(contrasena)
        if responsable is None and perfil not in ROLES[1:]:
            self.access.require_access(None, action="Crear una cuenta con privilegios", master=True)
        valores_recuperacion = None
        if preguntas_seguridad is not None:
            valores_recuperacion = prepare_security_questions(preguntas_seguridad)
        elif respuestas_seguridad is not None:
            if len(respuestas_seguridad) != 3:
                raise ValueError("Responde las tres preguntas de seguridad.")
            valores_recuperacion = prepare_security_questions(list(zip(SECURITY_QUESTIONS[:3], respuestas_seguridad)))
        elif responsable is None:
            raise ValueError("Responde las tres preguntas de seguridad para registrar tu cuenta.")
        contexto = transaction(self.conn) if responsable is None else self.access.authorized_write(responsable, action="Crear cuenta", master=True)
        with contexto:
            self.access.require_host_write()
            if not self.conn.execute("SELECT 1 FROM users WHERE role=? LIMIT 1", (ROLES[0],)).fetchone():
                raise ValueError("Configura primero el administrador maestro.")
            if perfil not in ROLES[1:]:
                raise ValueError("Selecciona Administrador regular o Usuario regular.")
            if not nombre.strip() or len(nombre.strip()) > 150:
                raise ValueError("Completa el nombre con un máximo de 150 caracteres.")
            if self.conn.execute("SELECT 1 FROM users WHERE lower(identity)=lower(?)", (identidad.strip(),)).fetchone():
                raise sqlite3.IntegrityError("Cuenta existente")
            cursor = self.conn.execute(
                "INSERT INTO users(name,identity,document,password,role,created_at,must_change_password,password_version,managed_permissions) VALUES(?,?,?,?,?,?,?,?,1)",
                (nombre.strip(), identidad, identidad, password_hash(contrasena), perfil, utc_now(), int(responsable is not None), new_password_version()),
            )
            if valores_recuperacion is not None:
                store_security_questions(self.conn, cursor.lastrowid, valores_recuperacion)
            etiqueta = self.access.actor_label(responsable) if responsable else identidad.strip()
            append_event(self.conn, etiqueta, f"Cuenta creada: {identidad.strip()}")
            codigo = issue_recovery_code(self.conn, cursor.lastrowid)
            return RegistrationResult(cursor.lastrowid, codigo)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    create_user = create_usuario

    def _administrado_usuario(self, user_id, expected_version=None):
        """Obtiene la cuenta objetivo y rechaza operar si fue eliminada o cambió respecto de la versión esperada."""
        usuario_id_local = user_id
        usuario_id = usuario_id_local
        identificador_usuario = usuario_id
        destinatario = self.conn.execute("SELECT * FROM users WHERE id=?", (identificador_usuario,)).fetchone()
        if destinatario is None:
            raise ValueError("Esta cuenta ya no está disponible.")
        if expected_version is not None and destinatario["password_version"] != expected_version:
            raise ValueError("Los datos de esta cuenta cambiaron. Actualiza la lista y vuelve a abrirla.")
        return destinatario
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _managed_user = _administrado_usuario

    def actualizar_usuario(self, actor, user_id, name, identity, role, master_password, expected_version=None):
        'Actualiza datos de cuenta con confirmación maestra y control de versión.'
        maestro_contrasena_local = master_password
        usuario_id_local = user_id
        maestro_contrasena = maestro_contrasena_local
        usuario_id = usuario_id_local
        responsable = actor
        identidad = identity
        contrasena_maestro = maestro_contrasena
        nombre = name
        perfil = role
        identificador_usuario = usuario_id
        with self.access.authorized_write(responsable, action=f"Actualizar cuenta #{identificador_usuario}", master=True) as actual:
            if not password_matches(contrasena_maestro, actual["password"]):
                raise AccessDenied("La contraseña actual del administrador maestro no es correcta.")
            destinatario = self._managed_user(identificador_usuario, expected_version)
            if destinatario["role"] == ROLES[0]:
                if destinatario["id"] != actual["id"] or perfil != ROLES[0]:
                    raise AccessDenied("El perfil del administrador maestro debe conservarse.")
            elif perfil not in ROLES[1:]:
                raise ValueError("Selecciona Administrador regular o Usuario regular.")
            nombre = validar_nombre(nombre)
            # Conservar un documento antiguo no obliga a cambiarlo al editar el nombre.
            identidad = identidad if identidad == destinatario['document'] else validar_documento_nuevo(identidad)
            if not nombre or len(nombre) > 150:
                raise ValueError("Completa el nombre (máximo 150 caracteres) y el documento.")
            if self.conn.execute("SELECT 1 FROM users WHERE lower(identity)=lower(?) AND id<>?", (identidad, identificador_usuario)).fetchone():
                raise sqlite3.IntegrityError("Cuenta existente")
            managed = destinatario['managed_permissions'] if destinatario['role'] == perfil else 1
            self.conn.execute(
                "UPDATE users SET name=?,identity=?,document=?,role=?,managed_permissions=?,password_version=password_version+1 WHERE id=?",
                (nombre, identidad, identidad, perfil, managed, identificador_usuario),
            )
            append_event(self.conn, self.access.actor_label(actual), f"Cuenta actualizada: {destinatario['identity']} → {identidad} · {perfil}")
        return self.conn.execute("SELECT * FROM users WHERE id=?", (identificador_usuario,)).fetchone()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    update_user = actualizar_usuario

    def eliminar_usuario(self, actor, user_id, master_password, expected_version=None):
        """Verifica la contraseña maestra y elimina una cuenta no maestra con sus relaciones y constancia de auditoría."""
        maestro_contrasena_local = master_password
        usuario_id_local = user_id
        maestro_contrasena = maestro_contrasena_local
        usuario_id = usuario_id_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        identificador_usuario = usuario_id
        with self.access.authorized_write(responsable, action=f"Eliminar cuenta #{identificador_usuario}", master=True) as actual:
            if not password_matches(contrasena_maestro, actual["password"]):
                raise AccessDenied("La contraseña actual del administrador maestro no es correcta.")
            destinatario = self._managed_user(identificador_usuario, expected_version)
            if destinatario["role"] == ROLES[0]:
                raise AccessDenied("El administrador maestro no puede eliminarse.")
            self.conn.execute("DELETE FROM grants WHERE user_id=?", (identificador_usuario,))
            self.conn.execute("DELETE FROM requests WHERE user_id=?", (identificador_usuario,))
            self.conn.execute("DELETE FROM user_security WHERE user_id=?", (identificador_usuario,))
            self.conn.execute("DELETE FROM users WHERE id=?", (identificador_usuario,))
            append_event(self.conn, self.access.actor_label(actual), f"Cuenta eliminada: {destinatario['name']} · {destinatario['identity']}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    delete_user = eliminar_usuario

    def reiniciar_contrasena(self, actor, user_id, master_password, temporary_password, expected_version=None):
        'Emite una contraseña temporal y exige al titular sustituirla antes de continuar.'
        maestro_contrasena_local = master_password
        temporary_contrasena = temporary_password
        usuario_id_local = user_id
        maestro_contrasena = maestro_contrasena_local
        temporary_contrasena_local = temporary_contrasena
        usuario_id = usuario_id_local
        responsable = actor
        contrasena_maestro = maestro_contrasena
        contrasena_temporal = temporary_contrasena_local
        identificador_usuario = usuario_id
        with self.access.authorized_write(responsable, action=f"Restablecer contraseña de cuenta #{identificador_usuario}", master=True) as actual:
            if not password_matches(contrasena_maestro, actual["password"]):
                raise AccessDenied("La contraseña actual del administrador maestro no es correcta.")
            destinatario = self._managed_user(identificador_usuario, expected_version)
            validate_password(contrasena_temporal)
            if password_matches(contrasena_temporal, destinatario["password"]):
                raise ValueError("Elige una contraseña diferente de la actual.")
            self.conn.execute(
                "UPDATE users SET password=?,must_change_password=1,recovery_pending=0,password_version=password_version+1 WHERE id=?",
                (password_hash(contrasena_temporal), identificador_usuario),
            )
            codigo = issue_recovery_code(self.conn, identificador_usuario)
            self.conn.execute("DELETE FROM api_sessions WHERE user_id=?", (identificador_usuario,))
            append_event(self.conn, self.access.actor_label(actual), f"Contraseña temporal asignada y código renovado: {destinatario['document'] or 'Documento pendiente'}")
            return codigo
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    reset_password = reiniciar_contrasena

    def obtener_usuario(self, actor, user_id):
        'Comprueba el acceso y recupera los datos de la cuenta seleccionada.'
        usuario_id_local = user_id
        usuario_id = usuario_id_local
        responsable = actor
        identificador_usuario = usuario_id
        self.access.require_access(responsable, VIEWS[4], action="Consultar cuenta", view=True)
        return self.conn.execute(
            "SELECT id,name,coalesce(document,'Documento pendiente') AS identity,document,role,active,created_at,must_change_password,password_version,managed_permissions FROM users WHERE id=?", (identificador_usuario,)
        ).fetchone()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    get_user = obtener_usuario

    def permisos_concedidos(self, actor, user_id):
        'Consulta los permisos adicionales concedidos a la cuenta seleccionada.'
        usuario_id_local = user_id
        usuario_id = usuario_id_local
        responsable = actor
        identificador_usuario = usuario_id
        self.access.require_access(responsable, VIEWS[4], action="Consultar permisos de una cuenta", view=True)
        return self.conn.execute(
            "SELECT permission FROM grants WHERE user_id=? ORDER BY permission", (identificador_usuario,)
        ).fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    grants = permisos_concedidos
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
UserService = ServicioUsuarios
