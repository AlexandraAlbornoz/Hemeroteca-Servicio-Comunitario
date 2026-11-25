"""Rutas, catálogo de títulos, permisos y apariencia de la aplicación."""

from pathlib import Path
import sys
import os

BASE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
ASSETS = BASE / "assets"
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Hemeroteca-2.4.2-solo-consulta' / 'data'
if os.environ.get('HEMEROTECA_PRUEBAS_AISLADAS') == '1':
    DATA_DIR = Path(os.environ.get('HEMEROTECA_DATOS', os.environ.get('PERRI_DATOS', str(DATA_DIR))))
DB_PATH = DATA_DIR / "hemeroteca.db"
RECOVERY_MAX_ATTEMPTS = 5
RECOVERY_LOCK_SECONDS = 15 * 60
SECURITY_QUESTIONS = (
    "¿Cuál es el segundo nombre de tu mamá?",
    "¿Cuál es el primer nombre de tu padre?",
    "¿En qué ciudad naciste?",
    "¿Cuál es el primer apellido de tu abuela materna?",
    "¿Cómo se llamaba la escuela donde cursaste primer grado?",
    "¿Cómo se llamaba tu primera mascota?",
)
ISSUE_STATUSES = ("Disponible", "En sala", "En archivo", "En restauración", "Perdido", "Sala", "Donado", "Préstamo circulante")
RECORD_PERIODS = ("Últimos 5 registros", "Último día (24h)", "Última semana", "Últimos 15 días", "Último mes")
NETWORK_CONFIG_PATH = DATA_DIR / "network.json"
NETWORK_TLS_PATH = DATA_DIR / "tls"

BLUE, BLUE_HOVER, SIDEBAR = "#0180FF", "#0068D8", "#284B9B"
BG, WHITE, INK, MUTED = "#F4F7FC", "#FFFFFF", "#20304C", "#64748B"
LINE, SOFT, GREEN, RED, AMBER = "#DDE5F0", "#EAF0FC", "#16865A", "#BD625A", "#B77A12"
FONT = "Segoe UI" if sys.platform == "win32" else "Arial"
MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
REGIONAL = ["Diario El Tiempo", "Metropolitano", "El Norte", "Diario la Antorcha", "Diario Vea", "La Prensa", "Diario Hora cero", "Diario El Mío"]
NATIONAL = ["El Nacional", "Últimas noticias", "El Mundo", "El Universal", "El Correo del orinoco"]
TITLES = REGIONAL + NATIONAL
ROLES = ["Administrador maestro", "Administrador regular", "Usuario regular"]
VIEWS = ["Consulta de periódicos", "Catálogo de periódicos", "Solicitudes de acceso", "Auditoría", "Usuarios", "Registros eliminados"]
REPORT_ISSUES_PERMISSION = "Exportar ejemplares a PDF"
REPORT_DATABASE_PERMISSION = "Exportar base de datos a PDF"
REPORT_PERMISSIONS = {REPORT_ISSUES_PERMISSION, REPORT_DATABASE_PERMISSION}
VIEWS += ["Reportes PDF", "Respaldos de seguridad"]
ROLE_ACCESS = {
    "Administrador maestro": set(VIEWS) | REPORT_PERMISSIONS,
    "Administrador regular": {"Consulta de periódicos", "Solicitudes de acceso"},
    "Usuario regular": {"Consulta de periódicos"},
}
LEGACY_ADMIN_ACCESS = {"Catálogo de periódicos", "Auditoría", "Registros eliminados",
                       "Registrar ejemplares", "Editar ejemplares", "Eliminar ejemplares"}
PERMISSIONS = {
    "Consultar solicitudes de todos": "Ver el historial global de solicitudes. No permite aprobar ni rechazar solicitudes.",
    REPORT_ISSUES_PERMISSION: "Guardar en PDF todos los ejemplares activos o los que coincidan con los filtros seleccionados.",
    REPORT_DATABASE_PERMISSION: "Exportar el contenido operativo general, incluidas cuentas y auditoría. Excluye credenciales y secretos de seguridad.",
    "Catálogo de periódicos": "Consultar el inventario completo y las fechas sin publicación. Permite a un administrador regular registrar ejemplares desde la principal o una PC autorizada.",
    "Registrar ejemplares": "Agregar ejemplares y registrar fechas en las que un periódico no circuló.",
    "Editar ejemplares": "Actualizar los datos y la ubicación física de ejemplares existentes.",
    "Eliminar ejemplares": "Retirar ejemplares del catálogo y enviarlos a Registros eliminados.",
    "Auditoría": "Consultar el historial de acciones del sistema en modo de lectura.",
    "Usuarios": "Consultar la lista de cuentas. La administración de cuentas está reservada al administrador maestro.",
    "Registros eliminados": "Consultar los ejemplares retirados. Solo el administrador maestro puede restaurarlos.",
}
