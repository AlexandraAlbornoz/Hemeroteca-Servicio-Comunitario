"""Registro y consulta del historial de auditoría."""

from hemeroteca.services.base import ServicioConAcceso

from datetime import datetime, timezone

from hemeroteca.config.settings import VIEWS


def agregar_evento(connection, user, action, result="Completado"):
    """Registra un evento en la transacción actual, sin guardar credenciales."""
    accion = action
    conexion = connection
    resultado = result
    usuario = user
    conexion.execute(
        "INSERT INTO audit(at,user,action,result) VALUES(?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec='seconds'), usuario, accion, resultado),
    )
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
append_event = agregar_evento


def registro_evento(connection, user, action, result="Completado"):
    """Registra y confirma un evento independiente."""
    accion = action
    conexion = connection
    resultado = result
    usuario = user
    append_event(conexion, usuario, accion, resultado)
    conexion.commit()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
record_event = registro_evento


class ServicioAuditoria(ServicioConAcceso):
    """Registra eventos y ofrece listados y filtros de auditoría sujetos al permiso de consulta."""
    def acciones_disponibles(self, actor):
        """Devuelve acciones registradas para el selector, sin exponer eventos ajenos."""
        self.access.require_access(actor, VIEWS[3], action='Consultar acciones de auditoría', view=True)
        return [fila[0] for fila in self.conn.execute('SELECT DISTINCT action FROM audit ORDER BY action')]

    def resultados_disponibles(self, actor):
        """Obtiene las opciones de resultado sin descargar el historial."""
        responsable = actor
        self.access.require_access(responsable, VIEWS[3], action='Consultar resultados de auditoría', view=True)
        return [fila[0] for fila in self.conn.execute('SELECT DISTINCT result FROM audit ORDER BY result')]

    def buscar_eventos(self, actor, *, fecha=None, hora='', usuario='', accion='', resultado='Todos', pagina=1):
        """Filtra eventos en la base y conserva formatos históricos de fechas."""
        responsable = actor
        from hemeroteca.services.paginacion import paginar
        from datetime import date
        self.access.require_access(responsable, VIEWS[3], action='Filtrar auditoría paginada', view=True)
        if fecha is not None:
            date.fromisoformat(fecha)
        if not all(isinstance(valor, str) for valor in (hora, usuario, accion, resultado)):
            raise ValueError('Los filtros de auditoría no son válidos.')
        consulta = 'SELECT * FROM audit WHERE instr(plegar_texto(user),?)>0 AND instr(plegar_texto(action),?)>0'
        from hemeroteca.services.paginacion import plegar_texto
        parametros = [plegar_texto(usuario.strip()), plegar_texto(accion.strip())]
        if fecha:
            consulta += ' AND substr(instante_evento(at),1,10)=?'
            parametros.append(fecha)
        if hora:
            consulta += ' AND substr(instante_evento(at),12,?)=?'
            parametros.extend((len(hora), hora))
        if resultado != 'Todos':
            consulta += ' AND result=?'
            parametros.append(resultado)
        return paginar(self.conn, consulta, parametros, pagina=pagina)


    def registro(self, user, action, result="Completado"):
        'Registra una acción en el historial de auditoría.'
        accion = action
        resultado = result
        usuario = user
        record_event(self.conn, usuario, accion, resultado)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    record = registro

    def listar_events(self, actor):
        'Devuelve el historial autorizado para llamadores del contrato anterior.'
        responsable = actor
        self.access.require_access(responsable, VIEWS[3], action="Consultar auditoría", view=True)
        return self.conn.execute("SELECT * FROM audit ORDER BY id DESC").fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    list_events = listar_events
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
AuditService = ServicioAuditoria
