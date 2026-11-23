"""Contenedor de catálogo y solicitudes con controles y tablas del producto."""
from unittest.mock import Mock
from tests.soporte_pantallas import VentanaGeneral
from hemeroteca.ui.periodicos_view import PeriodicosView
from hemeroteca.ui.requests_view import RequestsView
from hemeroteca.config.settings import VIEWS, PERMISSIONS


class VentanaCatalogo(PeriodicosView, RequestsView, VentanaGeneral):
    """Solo aísla las fronteras de servicios y la entrega asíncrona de consultas."""

    def __init__(self):
        super().__init__()
        self.content.destroy()
        self.content = self._scrollable(self)
        self.content.pack(fill='both', expand=True)
        self.content.grid_columnconfigure(0, weight=1)
        self.current_view = VIEWS[1]
        self.dates, self.all_combos = {}, []
        self._permisos_actuales = Mock(return_value=set(PERMISSIONS) | set(VIEWS))
        self.services.periodicos = Mock()
        self.services.requests = Mock()
        self.services.audit = Mock()
        self.services.requests.resumen_solicitudes.return_value = {'contadores': {}, 'acciones': []}
        self.services.requests.available_permissions.return_value = []
        self.services.requests.requests.return_value = []
        self.services.periodicos.consult_absent_dates.return_value = []
        for obj, name in [(self.services.periodicos, 'search_issues'), (self.services.periodicos, 'buscar_fechas_ausentes'), (self.services.requests, 'buscar_solicitudes')]:
            getattr(obj, name).return_value = self.page([])
        self.services.consulta = lambda group, method, actor, *args, **kwargs: lambda: getattr(getattr(self.services, group), method)(actor, *args, **kwargs)

    @staticmethod
    def page(rows, number=1, pages=1, total=None):
        """Contrato mínimo de la paginación real."""
        return dict(items=rows, page=number, pages=pages, total=len(rows) if total is None else total)

    def _date_entry(self, parent, label):
        """Conserva calendarios reales para usar set, get y sus eventos."""
        wrapper, control = super()._date_entry(parent, label)
        self.dates[label] = control
        return wrapper, control

    def _combo(self, parent, label, *args, **kwargs):
        """Distingue filtros de ejemplares y de ausencias con el mismo rótulo."""
        wrapper, combo = super()._combo(parent, label, *args, **kwargs)
        self.all_combos.append((label, combo))
        return wrapper, combo

    def _cargar_seccion(self, parent, queries, present, **kwargs):
        """Entrega resultados o errores sin sustituir la tabla ni sus callbacks."""
        try:
            results = [query() for query in queries]
        except ValueError as error:
            self._paragraph(parent, str(error)).pack(fill='x')
            if kwargs.get('error'):
                kwargs['error'](error)
        else:
            present(results)

    def select(self, tree, identifier):
        """Emite el evento público de selección de una tabla real."""
        tree.selection_set(str(identifier))
        tree.event_generate('<<TreeviewSelect>>')
        self.update()

    def validate_record(self):
        """Ejecuta el temporizador real del diálogo sin depender del reloj."""
        dialog = self.dialogs[-1]
        script = dialog.tk.call('after', 'info', dialog._validacion_pendiente)[0]
        dialog.tk.eval(script)
