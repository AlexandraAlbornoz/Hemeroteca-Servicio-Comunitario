"""Declaraciones inmutables de formularios y navegación, sin crear widgets."""
from dataclasses import dataclass
from hemeroteca.config.settings import TITLES, MONTHS, ISSUE_STATUSES, VIEWS


@dataclass(frozen=True)
class CampoFormulario:
    """Describe la etiqueta, el tipo de control y sus valores permitidos."""
    etiqueta: str
    tipo: str
    opciones: object


CAMPOS_IDENTIFICACION = (
    CampoFormulario('Periódico', 'combo', TITLES),
    CampoFormulario('Año', 'combo', tuple(str(anio) for anio in range(1970, 2101))),
    CampoFormulario('Mes', 'combo', MONTHS),
    CampoFormulario('Día', 'combo', tuple(str(dia) for dia in range(1, 32))),
)
CAMPOS_EJEMPLAR = (
    CampoFormulario('Edición', 'entry', 'Ej. Matutina'),
    CampoFormulario('Número', 'entry', 'Número de edición'),
    CampoFormulario('Estante', 'entry', 'Solo números · opcional si indicas gaveta'),
    CampoFormulario('Gaveta', 'entry', 'Solo números · opcional si indicas estante'),
    CampoFormulario('Estado', 'combo', ISSUE_STATUSES),
)
CAMPOS_AUSENCIA = (CampoFormulario('Observación', 'entry', 'Ej. El diario no circuló ese día'),)
PAGINAS = dict(zip(VIEWS, ('_consult_page', '_catalog_page', '_requests_page', '_audit_page', '_users_page', '_deleted_page', '_reports_page', '_backups_page')))
