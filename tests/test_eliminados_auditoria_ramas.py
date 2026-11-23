"""Restauración y auditoría con tablas, fechas y formularios auténticos."""
from tkinter import ttk
import unittest
from unittest.mock import patch
from hemeroteca.ui.deleted_records_view import DeletedRecordsView
from hemeroteca.ui.audit_view import AuditView
from hemeroteca.ui.selector_hora import SelectorHora
from hemeroteca.config.settings import VIEWS,ROLES,TITLES
from hemeroteca.services.access_service import AccessDenied
from tests.soporte_catalogo import VentanaCatalogo


class VentanaRevision(DeletedRecordsView,AuditView,VentanaCatalogo):
    """Reutiliza fábricas reales; solo separa servicios y navegación."""


class PruebasEliminadosAuditoria(unittest.TestCase):
    """Comprueba ramas de filtros, restauración y denegación del servicio."""

    def setUp(self):
        self.h=VentanaRevision()
        self.addCleanup(self.close_window)
        self.h.services.periodicos.buscar_eliminados.return_value=self.h.page([])
        self.h.services.audit.buscar_eventos.return_value=self.h.page([])
        self.h.services.audit.acciones_disponibles.return_value=['Restaurar']
        self.h.services.audit.resultados_disponibles.return_value=['Completado']
        self.record=dict(id=1,title=TITLES[0],day=1,month=1,year=2020,edition='',shelf='',eliminado_el='2026-11-19T10:00:00+00:00')
        self.h.services.periodicos.get_deleted_issue.return_value=self.record
        self.h.services.periodicos.has_absent_date.return_value=False
        self.warning=patch('hemeroteca.ui.deleted_records_view.messagebox.showwarning').start()
        self.ask=patch('hemeroteca.ui.deleted_records_view.messagebox.askyesno',return_value=True).start()
        self.addCleanup(patch.stopall)

    def close_window(self):
        self.h.update_idletasks()
        self.h.close_for_test()

    def test_denegacion_no_construye_vistas_ni_restaura(self):
        self.h._require_access.return_value=False
        self.h._deleted_page()
        self.h._audit_page()
        self.h._restore_issue(1)
        self.h._restore_issue(None)
        self.h.services.periodicos.restore_issue.assert_not_called()
        self.h.services.audit.buscar_eventos.assert_not_called()

    def test_eliminados_filtros_seleccion_y_limpieza(self):
        self.h.services.periodicos.buscar_eliminados.return_value=self.h.page([self.record])
        self.h._deleted_page()
        tree=self.h.widgets(ttk.Treeview)[0]
        self.h.select(tree,1)
        self.assertEqual(self.h.button('Restaurar ejemplar').cget('state'),'normal')
        self.h.write('Buscar ejemplar eliminado','Ficticio')
        self.h.dates['Eliminación desde'].set('01/11/2026')
        self.h.dates['Eliminación hasta'].set('19/11/2026')
        self.h.combos['Eliminados recientemente'].set('1 semana')
        self.h.button('Filtrar').invoke()
        args=self.h.services.periodicos.buscar_eliminados.call_args.kwargs
        self.assertEqual(args['desde'],'2026-11-01')
        self.assertEqual(args['periodo'],'1 semana')
        self.h.button('Limpiar').invoke()
        self.assertIsNone(self.h.services.periodicos.buscar_eliminados.call_args.kwargs['desde'])

    def test_cliente_y_no_maestro_no_muestran_accion_de_restaurar(self):
        self.h.services.read_only=True
        self.h._deleted_page()
        self.assertEqual(self.h.button('Restaurar ejemplar').winfo_manager(),'')

    def test_restaurar_conflicto_cancelacion_y_ficha_retirada(self):
        self.h.services.periodicos.get_deleted_issue.return_value=None
        self.h._restore_issue(1)
        self.h.services.periodicos.get_deleted_issue.return_value=self.record
        self.h.services.periodicos.has_absent_date.return_value=True
        self.h._restore_issue(1)
        self.warning.assert_called_once()
        self.h.services.periodicos.has_absent_date.return_value=False
        self.ask.return_value=False
        self.h._restore_issue(1)
        self.h.services.periodicos.restore_issue.assert_not_called()

    def test_restaurar_error_permiso_datos_y_exito(self):
        for error in [AccessDenied('revocado'),ValueError('conflicto nuevo')]:
            self.h.services.periodicos.restore_issue.side_effect=error
            self.h._restore_issue(1)
        self.h._access_denied.assert_called_once()
        self.warning.assert_called_once()
        self.h.services.periodicos.restore_issue.side_effect=None
        self.h._restore_issue(1)
        self.h.navigate.assert_called_once_with(VIEWS[5])

    def test_revocacion_al_leer_restauracion_se_informa(self):
        self.h.services.periodicos.get_deleted_issue.side_effect=AccessDenied('sesión cambiada')
        self.h._restore_issue(1)
        self.h.services.periodicos.get_deleted_issue.side_effect=None
        self.h.services.periodicos.has_absent_date.side_effect=ValueError('ficha cambiada')
        self.h._restore_issue(1)
        self.h._access_denied.assert_called_once()
        self.warning.assert_called_once()
        self.h.services.periodicos.restore_issue.assert_not_called()

    def test_auditoria_formatea_legacy_y_filtros_enviados_al_servicio(self):
        self.h.services.audit.buscar_eventos.return_value=self.h.page([dict(id=1,at='fecha histórica ilegible',user='Fixture',action='Restaurar',result='Completado')])
        self.h._audit_page()
        self.h.dates['Fecha'].set('19/11/2026')
        self.h.widgets(SelectorHora)[0].set('08:30')
        self.h.write('Usuario','Persona')
        self.h.combos['Acción'].set('Restaurar')
        self.h.combos['Resultado'].set('Completado')
        self.h.button('Filtrar historial').invoke()
        args=self.h.services.audit.buscar_eventos.call_args.kwargs
        self.assertEqual(args['hora'],'08:30')
        self.assertEqual(args['fecha'],'2026-11-19')
        self.assertEqual(args['accion'],'Restaurar')
        self.assertIn('fecha histórica ilegible',self.h.widgets(ttk.Treeview)[0].item('1')['values'])
        self.h.button('Limpiar filtros').invoke()
        self.assertEqual(self.h.services.audit.buscar_eventos.call_args.kwargs['hora'],'')

    def test_auditoria_no_consulta_con_fecha_u_hora_invalidas(self):
        self.h._audit_page()
        self.h.services.audit.buscar_eventos.reset_mock()
        with patch.object(self.h.dates['Fecha'],'get',return_value='fecha inválida'):
            self.h.button('Filtrar historial').invoke()
        time=self.h.widgets(SelectorHora)[0]
        for value in ['25:00','08:60','8:2:99','8:x','8:2:3:4','１２:30']:
            with patch.object(time,'get',return_value=value):self.h.button('Filtrar historial').invoke()
        self.h.services.audit.buscar_eventos.assert_not_called()
        self.assertTrue(self.h.has_text('hora válida'))

