"""Datos autorizados para PDF. No exporta hashes, códigos ni secretos de la red."""

import base64
from contextlib import nullcontext
from datetime import datetime

from hemeroteca.config.settings import REPORT_ISSUES_PERMISSION, REPORT_DATABASE_PERMISSION
from hemeroteca.database.maintenance import database_guard
from hemeroteca.services.audit_service import record_event
from hemeroteca.services.periodico_service import issue_search_query
from hemeroteca.utils.timestamps import utc_now


class ServicioReportes:
    """Prepara y genera informes PDF con secciones y datos sujetos a los permisos vigentes del solicitante."""
    def __init__(self, connection, access, database):
        """Conserva la conexión, el autorizador y la ruta de base necesarios para obtener instantáneas de informes."""
        acceso = access
        conexion = connection
        base_datos = database
        self.conn, self.access, self.database = conexion, acceso, base_datos

    def _proteger_base(self):
        """Conserva el bloqueo de archivo solo para bases persistidas en disco."""
        return nullcontext() if str(self.database) == ':memory:' else database_guard(self.database, exclusive=False)

    def generar(self, actor, *, scope='issues', filters=None):
        """La API comprueba este permiso en el servidor, incluso si la PC solo consulta."""
        responsable = actor
        filtros = filters
        ambito = scope
        if ambito not in ('issues', 'database'):
            raise ValueError("Selecciona un tipo de reporte válido.")
        permiso = REPORT_ISSUES_PERMISSION if ambito == 'issues' else REPORT_DATABASE_PERMISSION
        responsable = self.access.require_access(responsable, permiso, action='Generar reporte PDF')
        if filtros is not None and not isinstance(filtros, dict):
            raise ValueError("Los filtros del reporte no son válidos.")
        filtros = filtros or {}
        if set(filtros) - {'title', 'kind', 'year', 'month', 'day', 'period', 'desde', 'hasta'}:
            raise ValueError("El reporte contiene filtros desconocidos.")
        if ambito == 'database' and any(valor is not None for valor in filtros.values()):
            raise ValueError("El reporte general contiene todos los datos operativos; no admite filtros.")
        with self._proteger_base():
            self.conn.execute('BEGIN')
            try:
                actual = self.access.require_access(responsable, permiso, action='Leer datos para reporte', record=False)
                datos = {'scope': ambito, 'generated_at': utc_now(),
                        'generated_by': f"{actual['name']} · {actual['document'] or actual['identity']}",
                        'filters': filtros, 'sections': []}
                if ambito == 'issues':
                    consulta, parametros_consulta = issue_search_query(**filtros)
                    datos['sections'].append({'type': 'issues', 'title': 'Ejemplares registrados',
                                             'rows': [dict(fila) for fila in self.conn.execute(consulta, parametros_consulta)]})
                else:
                    # Lista cerrada de columnas, sin SELECT * sobre tablas de seguridad.
                    sections = (
                        ('issues', 'Ejemplares activos', 'SELECT * FROM issues WHERE deleted=0 ORDER BY id DESC'),
                        ('issues', 'Ejemplares eliminados', 'SELECT * FROM issues WHERE deleted=1 ORDER BY id DESC'),
                        ('absent', 'Fechas sin publicación', 'SELECT id,title,kind,year,month,day,note,created_by,created_at FROM absent_dates ORDER BY id DESC'),
                        ('users', 'Cuentas de usuario', 'SELECT id,name,coalesce(document,identity) AS document,role,active,created_at FROM users ORDER BY id DESC'),
                        ('grants', 'Permisos adicionales', 'SELECT u.name,coalesce(u.document,u.identity) AS document,g.permission FROM grants g JOIN users u ON u.id=g.user_id ORDER BY u.id DESC,g.permission'),
                        ('requests', 'Solicitudes de acceso', 'SELECT r.id,u.name,coalesce(u.document,u.identity) AS document,r.permission,r.reason,r.status,r.created_at,r.decided_by,r.decided_at,r.response FROM requests r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC'),
                        ('audit', 'Historial de auditoría', 'SELECT id,at,user,action,result FROM audit ORDER BY id DESC'),
                        ('devices', 'Computadoras autorizadas', 'SELECT name,active,approved_by,approved_at FROM authorized_devices ORDER BY approved_at DESC'),
                    )
                    for tipo, titulo, consulta in sections:
                        datos['sections'].append({'type': tipo, 'title': titulo,
                                                 'rows': [dict(fila) for fila in self.conn.execute(consulta)]})
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise
        from hemeroteca.utils.pdf_reports import build_report
        contenido = build_report(datos)
        if len(contenido) > 64 * 1024 * 1024:
            raise ValueError("El PDF supera 64 MiB. Exporta los ejemplares por periodos o solicita al maestro un respaldo completo.")
        # Una revocación o desactivación durante la generación impide entregar el documento.
        cantidad = sum(len(section['rows']) for section in datos['sections'])
        filename = f"hemeroteca-{'ejemplares' if ambito == 'issues' else 'general'}-{datetime.now():%Y%m%d-%H%M%S}.pdf"
        with self._proteger_base():
            self.access.require_access(responsable, permiso, action='Entregar reporte PDF')
            record_event(self.conn, self.access.actor_label(responsable), f"Reporte PDF generado: {'ejemplares' if ambito == 'issues' else 'contenido general'} · {cantidad} registros")
        return {'filename': filename, 'content': base64.b64encode(contenido).decode('ascii'),
                'records': cantidad, 'generated_at': datos['generated_at']}
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    generate = generar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
ReportService = ServicioReportes
