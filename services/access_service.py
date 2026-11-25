"""Roles, permisos y autorización de operaciones dentro de transacciones."""

from contextlib import contextmanager

from config.settings import ROLE_ACCESS, ROLES, VIEWS, REPORT_PERMISSIONS, LEGACY_ADMIN_ACCESS
from services.audit_service import record_event


class AccesoDenegado(ValueError):
    """La operación fue bloqueada antes de leer o modificar datos restringidos."""
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
AccessDenied = AccesoDenegado


class ServicioAcceso:
    """Centraliza identidad vigente, permisos y autorización de escrituras dentro de transacciones."""
    def __init__(self, connection, node_id=None):
        """Conserva la conexión y el identificador del nodo para comprobar permisos y propiedad de la base."""
        identificador_nodo = node_id
        conexion = connection
        self.conn = conexion
        self.node_id = identificador_nodo

    def usuario_actual(self, actor):
        'Recarga el estado vigente de la cuenta y conserva los indicadores de autenticación.'
        responsable = actor
        fila = self.conn.execute("SELECT * FROM users WHERE id=?", (responsable["id"],)).fetchone() if responsable is not None else None
        if fila is None:
            return None
        actual = dict(fila)
        for clave in ("_auth_method", "_recovery_generation"):
            if clave in responsable.keys():
                actual[clave] = responsable[clave]
        return actual
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    current_user = usuario_actual

    def etiqueta_responsable(self, actor):
        'Construye la identificación histórica del responsable para los eventos de auditoría.'
        responsable = actor
        actual = self.current_user(responsable)
        if responsable is not None and (actual is None or actual["password_version"] != responsable["password_version"]):
            return f"{responsable['name']} · {responsable['identity']}"
        return f"{actual['name']} · {actual['identity']}" if actual else "Sin sesión"
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    actor_label = etiqueta_responsable

    def exigir_acceso(self, actor, permission=None, *, action, master=False, view=False,
                       record=True, allow_password_change=False):
        """Consulta el estado real de la cuenta; no confía en el rol de la ventana."""
        permitir_contrasena_cambiar_local_local = allow_password_change
        permitir_contrasena_cambiar_local = permitir_contrasena_cambiar_local_local
        accion = action
        responsable = actor
        permitir_contrasena_cambiar = permitir_contrasena_cambiar_local
        maestro = master
        permiso = permission
        registro = record
        vista = view
        actual = self.current_user(responsable)
        motivo = None
        if actual is None:
            motivo = "Debes iniciar sesión para realizar esta acción."
        elif not actual["active"]:
            motivo = "Tu cuenta está desactivada. Contacta al administrador maestro."
        elif actual["password_version"] != responsable["password_version"]:
            motivo = "Tus datos de acceso o contraseña cambiaron. Vuelve a iniciar sesión."
        elif actual.get("_auth_method") == "recovery" and not self._recovery_valid(actual):
            motivo = "El código de recuperación ya no está vigente. Vuelve a iniciar sesión."
        elif actual["must_change_password"] and not permitir_contrasena_cambiar:
            motivo = "Debes cambiar tu contraseña temporal antes de continuar."
        elif maestro and actual["role"] != ROLES[0]:
            motivo = "Esta acción está reservada al administrador maestro."
        elif permiso:
            permitidos = self.permissions(actual)
            # Los permisos de operación también habilitan la vista del catálogo.
            if vista and permiso == VIEWS[1] and permitidos & {"Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"}:
                permitidos.add(VIEWS[1])
            if vista and permiso == VIEWS[6] and permitidos & REPORT_PERMISSIONS:
                permitidos.add(VIEWS[6])
            if permiso not in permitidos and actual["role"] == ROLES[2]:
                motivo = "El usuario regular solo puede consultar ejemplares."
            elif permiso not in permitidos:
                motivo = f"No tienes el permiso «{permiso}». Solicítalo desde Solicitudes de acceso."
        if motivo:
            if registro:
                record_event(self.conn, self.actor_label(responsable), f"{accion} · {motivo}", "Acceso denegado")
            raise AccessDenied(motivo)
        return actual
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    require_access = exigir_acceso

    @contextmanager
    def escritura_autorizada(self, actor, permission=None, *, action, master=False,
                         allow_password_change=False, authentication=False):
        """Comprueba el permiso dentro de la misma transacción que realiza el cambio."""
        permitir_contrasena_cambiar_local_local = allow_password_change
        permitir_contrasena_cambiar_local = permitir_contrasena_cambiar_local_local
        accion = action
        responsable = actor
        permitir_contrasena_cambiar = permitir_contrasena_cambiar_local
        maestro = master
        permiso = permission
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            if self.node_id:
                propietario = self.conn.execute("SELECT value FROM system_settings WHERE key='active_host_id'").fetchone()
                if propietario and propietario[0] != self.node_id:
                    raise AccessDenied("Esta computadora dejó de ser el servidor. Reconecta al servidor activo.")
            actual = self.require_access(responsable, permiso, action=accion, master=maestro,
                                          record=False, allow_password_change=permitir_contrasena_cambiar)
            yield actual
            self.conn.commit()
        except AccessDenied as excepcion:
            self.conn.rollback()
            # Registrar después del rollback conserva el intento, sin guardar cambios.
            record_event(self.conn, self.actor_label(responsable), f"{accion} · {excepcion}", "Acceso denegado")
            raise
        except BaseException:
            self.conn.rollback()
            raise
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    authorized_write = escritura_autorizada

    def _recuperacion_valido(self, actor):
        """Comprueba que la cuenta mantenga pendiente la recuperación y coincida con la generación de código vigente."""
        responsable = actor
        fila = self.conn.execute("SELECT generation FROM recovery_codes WHERE user_id=?", (responsable["id"],)).fetchone()
        return bool(fila and responsable.get("_recovery_generation") == fila[0] and responsable["recovery_pending"])
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _recovery_valid = _recuperacion_valido

    def exigir_escritura_principal(self):
        'Impide escribir cuando esta computadora dejó de ser el servidor activo.'
        propietario = self.conn.execute("SELECT value FROM system_settings WHERE key='active_host_id'").fetchone()
        if self.node_id and propietario and propietario[0] != self.node_id:
            raise AccessDenied("Esta computadora ya no es el servidor activo.")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    require_host_write = exigir_escritura_principal

    def permisos(self, user):
        'Combina permisos del perfil con las concesiones vigentes de la cuenta.'
        usuario = user
        if usuario is None:
            return set()
        usuario = self.conn.execute("SELECT * FROM users WHERE id=? AND active=1", (usuario["id"],)).fetchone()
        if usuario is None:
            return set()
        resultado = set(ROLE_ACCESS.get(usuario["role"], set()))
        if usuario["role"] == ROLES[2]:
            return resultado
        if usuario["role"] == ROLES[0]:
            resultado.update(("Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"))
        elif usuario["role"] == ROLES[1] and not usuario['managed_permissions']:
            # Las cuentas anteriores conservan sus accesos al actualizar.
            resultado.update(LEGACY_ADMIN_ACCESS)
        resultado.update(registro_breve[0] for registro_breve in self.conn.execute("SELECT permission FROM grants WHERE user_id=?", (usuario["id"],)))
        return resultado
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    permissions = permisos

    def estado_sesion(self, actor):
        """Agrupa usuario, permisos y requisitos de acceso en una sola consulta RPC."""
        responsable = actor
        usuario = self.current_user(responsable)
        if usuario is None:
            return {'usuario': None, 'permisos': [], 'requiere_configuracion': False}
        preguntas = self.conn.execute('SELECT 1 FROM user_security WHERE user_id=?', (usuario['id'],)).fetchone()
        codigo = self.conn.execute('SELECT 1 FROM recovery_codes WHERE user_id=?', (usuario['id'],)).fetchone()
        return {'usuario': usuario, 'permisos': sorted(self.permissions(usuario)),
                'requiere_configuracion': bool(usuario['must_change_password'] or not preguntas or not codigo)}

    def tiene_grant(self, actor, user_id: int, permission: str) -> bool:
        """Consulta un permiso aprobado; exige acceso adicional a Usuarios cuando el destinatario es otra cuenta."""
        usuario_id_local = user_id
        usuario_id = usuario_id_local
        responsable = actor
        permiso = permission
        identificador_usuario = usuario_id
        actual = self.require_access(responsable, action="Consultar permiso aprobado")
        if actual["id"] != identificador_usuario:
            self.require_access(responsable, VIEWS[4], action="Consultar permisos de otra cuenta", view=True)
        return self.conn.execute(
            "SELECT 1 FROM grants WHERE user_id=? AND permission=?",
            (identificador_usuario, permiso),
        ).fetchone() is not None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    has_grant = tiene_grant
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
AccessService = ServicioAcceso
