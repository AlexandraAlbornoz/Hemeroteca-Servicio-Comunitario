"""Construcción de servicios locales sin depender de Tkinter."""

from dataclasses import dataclass
from hemeroteca.database.connection import connect_database
from hemeroteca.services.access_service import AccessService
from hemeroteca.services.audit_service import AuditService
from hemeroteca.services.auth_service import AuthService
from hemeroteca.services.periodico_service import PeriodicoService
from hemeroteca.services.recovery_service import RecoveryService
from hemeroteca.services.request_service import RequestService
from hemeroteca.services.user_service import UserService
from hemeroteca.services.backup_service import BackupService
from hemeroteca.services.report_service import ReportService


@dataclass
class ServiciosAplicacion:
    """Agrupa la conexión y los servicios locales para compartir su ciclo de vida y cierre."""
    connection: object
    access: object
    audit: object
    auth: object
    recovery: object
    periodicos: object
    requests: object
    users: object
    network: object = None
    read_only: bool = False
    backups: object = None
    reports: object = None

    def cerrar(self):
        """Cierra la conexión de manera idempotente para el cierre de GUI y servidor."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
ApplicationServices = ServiciosAplicacion


def crear_servicios(path, *, node_id=None, initialize=True):
    'Construye y conecta los servicios locales sobre una misma conexión SQLite.'
    identificador_nodo = node_id
    ruta = path
    conexion = connect_database(ruta, initialize=initialize)
    acceso = AccessService(conexion, node_id=identificador_nodo)
    servicios = ApplicationServices(conexion, acceso, AuditService(conexion, acceso), AuthService(conexion, acceso),
                                   RecoveryService(conexion, acceso), PeriodicoService(conexion, acceso),
                                   RequestService(conexion, acceso), UserService(conexion, acceso))
    servicios.backups = BackupService(conexion, acceso, ruta)
    servicios.reports = ReportService(conexion, acceso, ruta)
    return servicios
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
create_services = crear_servicios
