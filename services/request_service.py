"""Solicitudes de permisos y decisiones del administrador maestro."""

from services.base import ServicioConAcceso

from datetime import datetime

from config.settings import PERMISSIONS, ROLES, VIEWS
from services.audit_service import append_event

# Proyección única para listados completos y paginados; conserva las claves RPC.
CONSULTA_SOLICITUDES = "SELECT r.*,u.name,coalesce(u.document,'Documento pendiente') AS identity,u.active,u.password_version AS account_version FROM requests r JOIN users u ON u.id=r.user_id"


class ServicioSolicitudes(ServicioConAcceso):
    """Gestiona solicitudes de permisos, alcance de consulta y decisiones auditadas del administrador maestro."""
    def resumen_solicitudes(self, actor):
        """Devuelve contadores y permisos distintos de las solicitudes visibles."""
        responsable = actor
        usuario = self.access.require_access(responsable, VIEWS[2], action='Resumir solicitudes', view=True)
        condicion = '' if self._puede_consultar_todas(usuario) else ' WHERE user_id=?'
        parametros = () if not condicion else (usuario['id'],)
        contadores = dict(self.conn.execute('SELECT status,count(*) FROM requests' + condicion + ' GROUP BY status', parametros))
        acciones = [fila[0] for fila in self.conn.execute('SELECT DISTINCT permission FROM requests' + condicion + ' ORDER BY permission', parametros)]
        return {'contadores': contadores, 'acciones': acciones}

    def buscar_solicitudes(self, actor, *, texto='', fecha=None, permiso=None, estado='Todos', pagina=1):
        """Aplica filtros en el servidor y nunca muestra solicitudes de otra cuenta."""
        responsable = actor
        from services.paginacion import paginar
        from datetime import date
        usuario = self.access.require_access(responsable, VIEWS[2], action='Consultar solicitudes paginadas', view=True)
        if fecha is not None:
            date.fromisoformat(fecha)
        if not isinstance(texto, str) or estado not in ('Todos', 'Pendiente', 'Aprobada', 'Declinada'):
            raise ValueError('Los filtros de solicitudes no son válidos.')
        consulta = CONSULTA_SOLICITUDES + " WHERE instr(plegar_texto(u.name || ' ' || coalesce(u.document,'Documento pendiente')),?)>0"
        parametros = [texto.strip().casefold()]
        for campo, valor in (('r.user_id', usuario['id'] if not self._puede_consultar_todas(usuario) else None),
                             ('substr(r.created_at,1,10)', fecha), ('r.permission', permiso),
                             ('r.status', estado if estado != 'Todos' else None)):
            if valor is not None:
                consulta += ' AND ' + campo + '=?'
                parametros.append(valor)
        return paginar(self.conn, consulta, parametros, pagina=pagina, tamano=6)


    def _puede_consultar_todas(self, usuario):
        """Consulta permisos vigentes y distingue el alcance global del personal.

        Recibe el usuario ya validado por require_access. No guarda permisos en
        caché: una revocación debe reflejarse en la siguiente consulta.
        """
        return usuario['role'] == ROLES[0] or 'Consultar solicitudes de todos' in self.access.permissions(usuario)

    def _alcance_listado(self, actor):
        """Autoriza el listado y devuelve su condición SQL con parámetros separados."""
        usuario = self.access.require_access(actor, VIEWS[2], action="Consultar solicitudes", view=True)
        return ('', ()) if self._puede_consultar_todas(usuario) else (' WHERE r.user_id=?', (usuario['id'],))

    def solicitudes(self, actor):
        'Consulta las solicitudes visibles según la identidad y el perfil del actor.'
        responsable = actor
        condicion, parametros = self._alcance_listado(responsable)
        return self.conn.execute(CONSULTA_SOLICITUDES + condicion + " ORDER BY r.id DESC", parametros).fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    requests = solicitudes

    def disponibles_permisos(self, actor):
        """Calcula en el servidor los permisos que esta cuenta aún puede solicitar."""
        responsable = actor
        condicion, parametros = self._alcance_listado(responsable)
        condicion += (' AND ' if condicion else ' WHERE ') + "r.status='Pendiente'"
        # SQL devuelve solo permisos distintos; no transporta motivos ni historiales.
        pendiente = {fila[0] for fila in self.conn.execute(
            'SELECT DISTINCT r.permission FROM requests r JOIN users u ON u.id=r.user_id' + condicion, parametros)}
        activo = self.access.permissions(responsable)
        return [permiso for permiso in PERMISSIONS
                if permiso not in activo and permiso not in pendiente]
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    available_permissions = disponibles_permisos

    def enviar_solicitud(self, actor, permission, reason):
        'Valida un permiso pendiente y registra la solicitud sin duplicarla.'
        responsable = actor
        permiso = permission
        motivo = reason
        self.access.require_access(responsable, VIEWS[2], action="Enviar solicitud de permiso")
        if not isinstance(permiso, str) or permiso not in PERMISSIONS:
            raise ValueError("Selecciona un permiso de la lista.")
        if not isinstance(motivo, str):
            raise ValueError("Escribe un motivo de entre 1 y 1.000 caracteres.")
        motivo = motivo.strip()
        if not motivo or len(motivo) > 1000:
            raise ValueError("Escribe un motivo de entre 1 y 1.000 caracteres.")
        with self.access.authorized_write(responsable, VIEWS[2], action="Enviar solicitud de permiso") as responsable:
            if permiso in self.access.permissions(responsable):
                raise ValueError("Ya tienes este permiso activo.")
            if self.conn.execute("SELECT 1 FROM requests WHERE user_id=? AND permission=? AND status='Pendiente'", (responsable["id"], permiso)).fetchone():
                raise ValueError("Ya tienes una solicitud pendiente para este permiso.")
            cursor_insercion = self.conn.execute("INSERT INTO requests(user_id,permission,reason,created_at) VALUES(?,?,?,?)", (responsable["id"], permiso, motivo, datetime.now().isoformat(timespec="seconds")))
            append_event(self.conn, responsable['name'], f"Solicitud #{cursor_insercion.lastrowid}: {permiso}", 'Enviada')
            return cursor_insercion.lastrowid
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    submit_request = enviar_solicitud

    def decidir_solicitud(self, actor, request_id, approved, response="", expected_account_version=None):
        'Aprueba o rechaza una solicitud vigente dentro de una transacción autorizada.'
        expected_cuenta_version_local_local = expected_account_version
        solicitud_id_local = request_id
        expected_cuenta_version_local = expected_cuenta_version_local_local
        solicitud_id = solicitud_id_local
        responsable = actor
        aprobado = approved
        expected_cuenta_version = expected_cuenta_version_local
        identificador_solicitud = solicitud_id
        respuesta = response
        self.access.require_access(responsable, action=f"{'Aprobar' if aprobado else 'Rechazar'} solicitud #{identificador_solicitud}", master=True)
        respuesta = respuesta.strip()
        if len(respuesta) > 1000:
            raise ValueError("La respuesta debe tener como máximo 1.000 caracteres.")
        if not aprobado and not respuesta:
            raise ValueError("Indica el motivo del rechazo para que el usuario pueda entender la decisión.")
        with self.access.authorized_write(responsable, action=f"{'Aprobar' if aprobado else 'Rechazar'} solicitud #{identificador_solicitud}", master=True) as responsable:
            req = self.conn.execute("SELECT r.*, u.active, u.password_version AS account_version FROM requests r JOIN users u ON u.id=r.user_id WHERE r.id=?", (identificador_solicitud,)).fetchone()
            if not req or req["status"] != "Pendiente":
                raise ValueError("Esta solicitud ya fue atendida. Actualiza la lista.")
            if expected_cuenta_version is not None and req["account_version"] != expected_cuenta_version:
                raise ValueError("La cuenta de esta solicitud cambió. Actualiza la lista antes de decidir.")
            if aprobado and (not req["active"] or req["permission"] not in PERMISSIONS):
                raise ValueError("No se puede aprobar: la cuenta está inactiva o el permiso no está disponible.")
            estado = "Aprobada" if aprobado else "Declinada"
            self.conn.execute("UPDATE requests SET status=?,response=?,decided_by=?,decided_at=? WHERE id=?", (estado, respuesta, responsable["name"], datetime.now().isoformat(timespec="seconds"), identificador_solicitud))
            if aprobado:
                self.conn.execute("INSERT OR IGNORE INTO grants(user_id,permission) VALUES(?,?)", (req["user_id"], req["permission"]))
            append_event(self.conn, responsable['name'], f"Solicitud #{identificador_solicitud}: {req['permission']}", estado)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    decide_request = decidir_solicitud
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
RequestService = ServicioSolicitudes
