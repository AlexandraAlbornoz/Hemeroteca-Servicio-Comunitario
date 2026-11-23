"""Filtros, formularios y decisiones de solicitudes con widgets reales."""
import unittest
from unittest.mock import Mock, patch
from tkinter import ttk
from hemeroteca.ui.controles import TextoEditable
from hemeroteca.config.settings import ROLES, VIEWS, PERMISSIONS
from hemeroteca.services.access_service import AccessDenied
from tests.soporte_catalogo import VentanaCatalogo


class PruebasPantallaSolicitudes(unittest.TestCase):
    """No sustituye los callbacks del formulario ni de las tablas."""

    def setUp(self):
        self.h = VentanaCatalogo()
        self.addCleanup(self.h.close_for_test)
        self.h.current_view = VIEWS[2]
        self.permission = next(iter(PERMISSIONS))
        self.record = dict(id=7, user_id=2, name='Persona Ficticia', identity='V-12345679', permission=self.permission,
                           created_at='2026-11-19T10:00:00', status='Pendiente', reason='Consulta ficticia',
                           active=True, response='', decided_at=None, decided_by=None, account_version=3)
        self.h.services.requests.requests.return_value = [self.record]

    def regular(self):
        self.h.user['role'] = ROLES[1]
        self.h._permisos_actuales.return_value = {VIEWS[0], VIEWS[2]}

    def open(self):
        self.h._requests_page()
        self.h.update_idletasks()

    def test_permiso_rechazado_no_abre_pagina_formulario_ni_detalle(self):
        self.h._require_access.return_value = False
        self.h._requests_page()
        self.h._request_form()
        self.h._request_detail(self.record)
        self.h._request_detail(None)
        self.assertEqual(self.h.dialogs, [])
        self.h.services.requests.requests.assert_not_called()

    def test_pagina_maestro_contadores_seleccion_y_detalle(self):
        self.h.services.requests.resumen_solicitudes.return_value = {'contadores': {'Pendiente': 1}, 'acciones': [self.permission]}
        self.h.services.requests.buscar_solicitudes.return_value = self.h.page([self.record])
        self.open()
        tree = self.h.widgets(ttk.Treeview)[0]
        self.assertEqual(tree.get_children(), ('7',))
        self.assertEqual(self.h.button('Revisar solicitud').cget('state'), 'disabled')
        self.h.select(tree, 7)
        with patch.object(self.h, '_request_detail') as detail:
            self.h.button('Revisar solicitud').invoke()
            detail.assert_called_once_with(self.record)

    def test_filtros_estado_fecha_texto_y_limpieza(self):
        self.open()
        self.h.write('Usuario', ' Persona ')
        self.h.dates['Fecha de solicitud'].set('19/11/2026')
        self.h.combos['Estado'].set('Rechazada')
        self.h.button('Filtrar solicitudes').invoke()
        args = self.h.services.requests.buscar_solicitudes.call_args.kwargs
        self.assertEqual(args['estado'], 'Declinada')
        self.assertEqual(args['fecha'], '2026-11-19')
        self.assertEqual(args['texto'], ' Persona ')
        self.h.button('Limpiar filtros').invoke()
        self.assertEqual(self.h.services.requests.buscar_solicitudes.call_args.kwargs['estado'], 'Todos')
        self.assertIsNone(self.h.services.requests.buscar_solicitudes.call_args.kwargs['fecha'])

    def test_filtro_accion_recordado_se_restaura_al_cargar_resumen(self):
        self.h._request_filters = {self.h.user['id']: {'action': self.permission, 'status': 'Todos'}}
        self.h.services.requests.resumen_solicitudes.return_value = {'contadores': {}, 'acciones': [self.permission]}
        self.open()
        self.assertEqual(self.h.combos['Acción solicitada'].get(), self.permission)
        self.assertEqual(self.h.services.requests.buscar_solicitudes.call_args.kwargs['permiso'], self.permission)

    def test_fecha_invalida_no_lanza_consulta(self):
        self.open()
        self.h.services.requests.buscar_solicitudes.reset_mock()
        with patch.object(self.h.dates['Fecha de solicitud'], 'get', return_value='fecha inválida'):
            self.h.button('Filtrar solicitudes').invoke()
        self.h.services.requests.buscar_solicitudes.assert_not_called()
        self.assertTrue(any(p.winfo_exists() and p.cget('text') for p in self.h.paragraphs))

    def test_pagina_regular_muestra_permiso_revocado_como_solicitable(self):
        self.regular()
        self.h.services.requests.available_permissions.return_value = [self.permission]
        self.open()
        self.assertTrue(self.h.has_text('Cada aprobación'))
        self.h.button('Solicitar permiso').invoke()
        self.assertTrue(self.h.dialogs[-1].winfo_exists())

    def test_regular_sin_permisos_disponibles_no_abre_dialogo(self):
        self.regular()
        self.open()
        self.assertTrue(self.h.has_text('No hay permisos nuevos'))
        self.h.button('Solicitar permiso').invoke()
        self.h._notice.assert_called_once()
        self.assertEqual(self.h.dialogs, [])

    def test_envio_error_permiso_datos_y_exito(self):
        self.regular()
        self.h.services.requests.available_permissions.return_value = [self.permission]
        self.h._request_form()
        dialog = self.h.dialogs[-1]
        text = self.h.widgets(TextoEditable, dialog)[0]
        text.insert('1.0', 'Motivo ficticio')
        for error in [AccessDenied('sesión cambiada'), ValueError('motivo inválido')]:
            self.h.services.requests.submit_request.side_effect = error
            self.h.button('Enviar solicitud').invoke()
            self.assertTrue(dialog.winfo_exists())
        self.assertTrue(self.h.has_text('motivo inválido'))
        self.h._access_denied.assert_called_once()
        self.h.services.requests.submit_request.side_effect = None
        self.h.services.requests.submit_request.return_value = 12
        self.h.button('Enviar solicitud').invoke()
        self.assertFalse(dialog.winfo_exists())
        self.h.navigate.assert_called_once_with(VIEWS[2])
        self.h._notice.assert_called_once_with('Solicitud #12 enviada al administrador maestro.')

    def test_detalle_no_disponible_se_audita(self):
        self.h.services.requests.requests.return_value = []
        self.h._request_detail(self.record)
        self.h.services.audit.record.assert_called_once()
        self.assertEqual(self.h.dialogs, [])

    def test_decision_conserva_formulario_error_y_version_esperada(self):
        self.h._request_detail(self.record)
        dialog = self.h.dialogs[-1]
        response = self.h.widgets(TextoEditable, dialog)[1]
        response.insert('1.0', 'Respuesta ficticia')
        for error in [AccessDenied('no autorizado'), ValueError('cuenta modificada')]:
            self.h.services.requests.decide_request.side_effect = error
            self.h.button('Aprobar permiso').invoke()
            self.assertTrue(dialog.winfo_exists())
        self.assertTrue(self.h.has_text('cuenta modificada'))
        self.h.services.requests.decide_request.side_effect = None
        self.h.button('Aprobar permiso').invoke()
        self.assertEqual(self.h.services.requests.decide_request.call_args.kwargs['expected_account_version'], 3)
        self.assertEqual(self.h.services.requests.decide_request.call_args.args[2:4], (True, 'Respuesta ficticia'))
        self.assertFalse(dialog.winfo_exists())

    def test_rechazo_se_permite_en_cuenta_inactiva_sin_aprobar(self):
        self.record['active'] = False
        self.h._request_detail(self.record)
        self.assertEqual(self.h.button('Aprobar permiso').cget('state'), 'disabled')
        self.h.button('Rechazar').invoke()
        self.assertFalse(self.h.services.requests.decide_request.call_args.args[2])

    def test_permiso_antiguo_no_puede_aprobarse(self):
        self.record['permission'] = 'Permiso de versión antigua'
        self.h._request_detail(self.record)
        self.assertTrue(self.h.has_text('versión anterior'))
        self.assertEqual(self.h.button('Aprobar permiso').cget('state'), 'disabled')
        self.h.button('Volver').invoke()

    def test_detalle_cliente_solo_lectura_y_pendiente_sin_respuesta(self):
        self.h.services.read_only = True
        self.h._request_detail(self.record)
        self.assertTrue(self.h.has_text('Aún no hay una respuesta'))
        with self.assertRaises(AssertionError):
            self.h.button('Aprobar permiso')
        self.h.button('Cerrar detalle').invoke()

    def test_detalle_aprobado_indica_permiso_activo_o_revocado(self):
        self.record.update(status='Aprobada', decided_at='2026-11-19T11:00:00', decided_by='Maestra Ficticia')
        for granted in [True, False]:
            self.h.services.access.has_grant.return_value = granted
            self.h._request_detail(self.record)
            self.assertTrue(self.h.has_text('Permiso activo' if granted else 'fue revocado'))
            self.h.button('Cerrar detalle').invoke()

    def test_detalle_rechazado_muestra_respuesta_vigente(self):
        self.record.update(status='Declinada', response='Falta justificar el acceso')
        self.h._request_detail(self.record)
        self.assertTrue(self.h.has_text('Falta justificar'))
        self.h.button('Cerrar detalle').invoke()

    def test_revocacion_al_abrir_formulario_o_detalle_no_escapa(self):
        self.h.services.requests.available_permissions.side_effect = AccessDenied('sesión revocada')
        self.h._request_form()
        self.h.services.requests.requests.side_effect = AccessDenied('sesión revocada')
        self.h._request_detail(self.record)
        self.assertEqual(self.h._access_denied.call_count, 2)
        self.assertEqual(self.h.dialogs, [])

    def test_filtro_accion_obsoleto_se_restablece(self):
        self.h._request_filters = {self.h.user['id']: {'action': 'Permiso retirado'}}
        self.open()
        self.assertEqual(self.h.combos['Acción solicitada'].get(), 'Todas las acciones')
        self.assertIsNone(self.h.services.requests.buscar_solicitudes.call_args.kwargs['permiso'])

    def test_error_de_datos_al_abrir_solicitud_se_informa(self):
        self.h.services.requests.available_permissions.side_effect = ValueError('datos no disponibles')
        self.h._request_form()
        self.h.services.requests.requests.side_effect = ValueError('lista no disponible')
        self.h._request_detail(self.record)
        self.assertEqual(self.h._notice.call_count, 2)
        self.assertEqual(self.h.dialogs, [])

