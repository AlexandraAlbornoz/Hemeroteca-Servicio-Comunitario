"""Ramas de sesión, navegación pendiente y cierre con raíz Tk real."""
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import customtkinter as ctk
from hemeroteca.config.settings import ROLES, VIEWS, REPORT_ISSUES_PERMISSION
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.ui.main_view import HemerotecaApp


class VentanaEstado(HemerotecaApp):
    """Inicializa solo Tk y las fronteras necesarias; conserva métodos del producto."""

    def __init__(self):
        ctk.CTk.__init__(self)
        self.withdraw()
        self.user = dict(id=1,password_version=7,active=True,role=ROLES[0],name='Persona Ficticia')
        self._authenticated_version = 7
        self.current_view = VIEWS[0]
        self._session_snapshot = (ROLES[0],frozenset(VIEWS))
        self.services = SimpleNamespace(access=Mock(),audit=Mock(),read_only=False,_trabajos=0,close=Mock(),agrupar_interfaz=nullcontext)
        self.services.access.permissions.return_value=set(VIEWS)
        self.services.access.require_access.return_value=self.user
        self.services.access.estado_sesion.return_value=dict(usuario=self.user,permisos=set(VIEWS),requiere_configuracion=False)
        self._network_state=Mock(return_value=None)
        self._network_signature=None
        self._notice=Mock()
        self.show_shell=Mock()
        self.show_login=Mock()
        self._enforce_account_requirements=Mock(return_value=False)
        self._restart_services=Mock()
        self.navigate=Mock()
        self._construir_vista=Mock()
        self._session_watch_job=self.after(60000,lambda:None)

    def clean(self):
        for task in self.tk.splitlist(self.tk.call('after','info')):
            self.tk.call('after','cancel',task)
        ctk.CTk.destroy(self)


class PruebasRamasSesionNavegacion(unittest.TestCase):
    """Simula respuestas, nunca los métodos de sesión que se verifican."""

    def setUp(self):
        self.h=VentanaEstado()
        self.addCleanup(self.h.clean)
        self.warning=patch('hemeroteca.ui.main_view.messagebox.showwarning').start()
        self.addCleanup(patch.stopall)

    def test_require_access_contexto_reutilizado_y_exito_actualizan_actor(self):
        self.h._contexto_construccion=set()
        self.assertTrue(self.h._require_access(VIEWS[0]))
        self.h.services.access.require_access.assert_not_called()
        self.h._contexto_construccion=None
        other=dict(self.h.user,name='Cuenta Actualizada')
        self.h.services.access.require_access.return_value=other
        self.assertTrue(self.h._require_access(VIEWS[0]))
        self.assertEqual(self.h.user['name'],'Cuenta Actualizada')

    def test_require_access_denegado_y_error_transitorio(self):
        with patch.object(self.h,'_access_denied') as denied:
            self.h.services.access.require_access.side_effect=AccessDenied('revocado')
            self.assertFalse(self.h._require_access(VIEWS[0]))
            denied.assert_called_once()
        for error in [ValueError('filtro inválido'),OSError('sin conexión')]:
            self.h.services.access.require_access.side_effect=error
            self.assertFalse(self.h._require_access(VIEWS[0]))
        self.assertEqual(self.warning.call_count,2)

    def test_callback_de_acceso_sincroniza_al_quedar_libre(self):
        with patch.object(self.h,'_sync_session') as sync:
            error=AccessDenied('sin permiso')
            self.h.report_callback_exception(type(error),error,None)
            sync.assert_not_called()
            self.h.update_idletasks()
            sync.assert_called_once()
        for error in [ValueError('dato'),OSError('red')]:
            self.h.report_callback_exception(type(error),error,None)
        self.assertEqual(self.warning.call_count,3)

    def test_vigilancia_pospone_durante_accion_y_reprograma(self):
        self.h._servicios_ocupados=True
        with patch.object(self.h,'_sync_session') as sync:
            self.h._watch_session()
            sync.assert_not_called()
        self.assertTrue(self.h._session_watch_job)

    def test_vigilancia_reinicia_servicios_al_cambiar_red(self):
        self.h._network_state.return_value=('client','destino','huella')
        with patch.object(self.h,'_sync_session') as sync:
            self.h._watch_session()
            sync.assert_called_once()
        self.h._restart_services.assert_called_once()

    def test_vigilancia_no_reinicia_durante_codigo_y_maneja_errores(self):
        self.h._showing_recovery_code=True
        self.h._network_state.return_value=('otra',)
        with patch.object(self.h,'_sync_session',side_effect=AccessDenied('vencida')):
            self.h._watch_session()
        self.h._restart_services.assert_not_called()
        self.h.show_login.assert_called_once()
        for error in [ValueError('desconectado'),OSError('red')]:
            with patch.object(self.h,'_sync_session',side_effect=error):self.h._watch_session()
        self.assertEqual(self.h._notice.call_count,2)

    def test_sync_sin_usuario_o_codigo_no_consulta(self):
        actor=self.h.user
        self.h.user=None
        self.h._sync_session()
        self.h.user=actor
        self.h._showing_recovery_code=True
        self.h._sync_session()
        self.h.services.access.estado_sesion.assert_not_called()

    def test_sync_sesion_vencida_y_error_transitorio_conserva_formulario(self):
        actor=self.h.user
        self.h.services.access.estado_sesion.side_effect=AccessDenied('sesión vencida')
        self.h._sync_session()
        self.h.show_login.assert_called_once()
        self.h.show_login.reset_mock()
        for error in [ValueError('desconectado'),OSError('red caída')]:
            self.h.services.access.estado_sesion.side_effect=error
            self.h._sync_session()
        self.assertIs(self.h.user,actor)
        self.h.show_shell.assert_not_called()
        self.h.show_login.assert_not_called()

    def test_sync_invalida_cuenta_retirada_inactiva_y_version_distinta(self):
        for actor in [None,dict(self.h.user,active=False),dict(self.h.user,password_version=8)]:
            self.h.services.access.estado_sesion.return_value=dict(usuario=actor,permisos=set(),requiere_configuracion=False)
            self.h._sync_session()
        self.assertEqual(self.h.show_login.call_count,3)
        self.assertEqual(self.h.services.audit.record.call_count,3)

    def test_sync_requisitos_y_permiso_modificado_respetan_dialogo_abierto(self):
        state=self.h.services.access.estado_sesion.return_value
        state['requiere_configuracion']=True
        self.h._enforce_account_requirements.return_value=True
        self.h._sync_session()
        self.h.show_shell.assert_not_called()
        state['requiere_configuracion']=False
        state['permisos']={VIEWS[0]}
        dialog=ctk.CTkToplevel(self.h)
        self.h._sync_session()
        self.h.show_shell.assert_not_called()
        self.h._notice.assert_called_once()
        dialog.destroy()
        self.h.current_view=VIEWS[5]
        self.h.services.access.permissions.return_value={VIEWS[0]}
        self.h._sync_session()
        self.h.show_shell.assert_called_once_with(VIEWS[0])

    def test_sync_permiso_modificado_conserva_destino_permitido(self):
        self.h.services.access.estado_sesion.return_value['permisos']={VIEWS[0]}
        self.h._sync_session()
        self.h.show_shell.assert_called_once_with(VIEWS[0])

    def test_allowed_views_por_rol_catalogo_pdf_y_cliente(self):
        for role,read_only,permissions in [(ROLES[0],False,set(VIEWS)),(ROLES[0],True,set(VIEWS)),
                                           (ROLES[1],False,set()),(ROLES[2],False,{'Editar ejemplares',REPORT_ISSUES_PERMISSION})]:
            self.h.user['role']=role
            self.h.services.read_only=read_only
            self.h.services.access.permissions.return_value=permissions
            result=self.h._allowed_views()
            self.assertEqual(VIEWS[7] in result,role==ROLES[0] and not read_only)
            if role==ROLES[1] or 'Editar ejemplares' in permissions:self.assertIn(VIEWS[1],result)
            if REPORT_ISSUES_PERMISSION in permissions:self.assertIn(VIEWS[6],result)
        self.h.user=None
        self.assertEqual(self.h._allowed_views(),set())

    def test_navegacion_pospuesta_conserva_ultimo_destino_de_la_misma_sesion(self):
        self.h._servicios_ocupados=True
        HemerotecaApp.navigate(self.h,VIEWS[1])
        job=self.h._navegacion_pendiente
        HemerotecaApp.navigate(self.h,VIEWS[2])
        self.assertEqual(self.h._navegacion_pendiente,job)
        self.h._reanudar_navegacion()
        self.h.navigate.assert_not_called()
        self.h._servicios_ocupados=False
        self.h._reanudar_navegacion()
        self.h.navigate.assert_called_once_with(VIEWS[2])

    def test_navegacion_pendiente_descarta_usuario_o_version_distinta(self):
        self.h._destino_pendiente=None
        self.h._reanudar_navegacion()
        for actor in [None,dict(self.h.user,id=2),dict(self.h.user,password_version=8)]:
            self.h._destino_pendiente=(VIEWS[1],1,7)
            self.h.user=actor
            self.h._reanudar_navegacion()
            self.assertIsNone(self.h._destino_pendiente)
        self.h.navigate.assert_not_called()

    def test_navegacion_error_restauracion_y_limpieza_de_eventos(self):
        self.h._construir_vista.side_effect=ValueError('no se pudo construir')
        with self.assertRaises(ValueError):HemerotecaApp.navigate(self.h,VIEWS[0])
        self.assertFalse(self.h._navegando)
        self.h._servicios_ocupados=True
        HemerotecaApp.navigate(self.h,VIEWS[2])
        self.h._guardar_estado_vista=Mock()
        self.h._login_bg_resize_job=self.h.after(60000,lambda:None)
        ctk.CTkLabel(self.h,text='Anterior').pack()
        self.h._clear()
        self.assertEqual(self.h.winfo_children(),[])
        self.assertIsNone(self.h._navegacion_pendiente)
        self.assertIsNone(self.h._login_bg_resize_job)

    def test_cierre_espera_trabajos_y_no_destruye_tcl_ocupado(self):
        with patch.object(self.h,'destroy') as destroy:
            self.h._servicios_ocupados=True
            self.h._close()
            destroy.assert_not_called()
            self.h._servicios_ocupados=False
            self.h.services._trabajos=1
            self.h._close()
            destroy.assert_not_called()
            self.h.services._trabajos=0
            self.h._close()
            destroy.assert_called_once()
            self.h.services.close.assert_called_once()
