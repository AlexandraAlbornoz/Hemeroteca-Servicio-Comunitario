"""Revalidaciones de permisos en cuentas, catálogo y sesión con widgets reales."""
import unittest
from unittest.mock import Mock,patch
import customtkinter as ctk
from hemeroteca.config.settings import ROLES,VIEWS,REPORT_ISSUES_PERMISSION
from hemeroteca.ui.main_view import HemerotecaApp
from tests.soporte_catalogo import VentanaCatalogo
from tests import test_ramas_sesion_navegacion as session


class PruebasPantallasUsuariosCatalogo(unittest.TestCase):
    """Invoca botones auténticos; mantiene servicios aislados."""
    def setUp(self):
        self.h=VentanaCatalogo();self.addCleanup(self.h.close_for_test)
        self.record=dict(self.h.user,id=2,role=ROLES[1],name='Otra Persona',created_at='2026-11-19')
        self.h.services.users.get_user.return_value=self.record
        self.h.services.users.grants.return_value=[{'permission':REPORT_ISSUES_PERMISSION}]
        self.h.services.users.buscar_usuarios.return_value=self.h.page([self.record])
        self.ask=patch('hemeroteca.ui.users_view.messagebox.askyesno',return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_limpiar_y_denegar_filtros_no_consulta_usuarios(self):
        self.h._users_page()
        self.h.write('Buscar usuario','Otra');self.h.combos['Estado'].set('Inactivo')
        self.h.button('Limpiar filtros').invoke()
        args=self.h.services.users.buscar_usuarios.call_args.kwargs
        self.assertEqual((args['texto'],args['estado']),('','Todos'))
        before=self.h.services.users.buscar_usuarios.call_count
        self.h._require_access.return_value=False;self.h.button('Filtrar usuarios').invoke()
        self.assertEqual(self.h.services.users.buscar_usuarios.call_count,before)

    def test_detalle_revocacion_y_estado_revalidan_antes_de_confirmar(self):
        self.h._user_detail(self.record)
        self.h._require_access.return_value=False
        self.h.button('Revocar').invoke();self.h.button('Desactivar cuenta').invoke()
        self.ask.assert_not_called()
        self.h.services.users.revoke_grant.assert_not_called();self.h.services.users.set_user_active.assert_not_called()

    def test_cancelar_estado_no_modifica_cuenta(self):
        self.h._user_detail(self.record);self.h.button('Desactivar cuenta').invoke()
        self.ask.assert_called_once();self.h.services.users.set_user_active.assert_not_called()
        self.assertTrue(self.h.dialogs[-1].winfo_exists())

    def test_formulario_revalida_permiso_al_guardar(self):
        self.h._admin_user_form()
        self.h._require_access.return_value=False;self.h.button('Crear cuenta').invoke()
        self.h.services.users.create_user.assert_not_called()
        self.assertTrue(self.h.dialogs[-1].winfo_exists())

    def test_consulta_revalida_permiso_antes_de_buscar(self):
        self.h._consult_page();before=self.h.services.periodicos.search_issues.call_count
        self.h._require_access.return_value=False;self.h.button('Buscar').invoke()
        self.assertEqual(self.h.services.periodicos.search_issues.call_count,before)

    def test_catalogo_revalida_panel_y_vista_antes_de_consultar(self):
        self.h._catalog_page();before=self.h.services.periodicos.search_issues.call_count
        self.h._require_access.return_value=False;self.h.button('Filtrar catálogo').invoke()
        self.assertEqual(self.h.services.periodicos.search_issues.call_count,before)
        self.h._require_access.side_effect=lambda *a,**kw:not kw.get('view',False)
        self.h.button('Filtrar catálogo').invoke()
        self.assertEqual(self.h.services.periodicos.search_issues.call_count,before)


class PruebasSesionPendiente(unittest.TestCase):
    """Comprueba el shell del producto, no su sustituto de prueba."""
    def setUp(self):
        self.h=session.VentanaEstado();self.addCleanup(self.h.clean)

    def test_estado_de_red_y_shell_maestro_con_equipo_conectado(self):
        network=Mock();network.describe.return_value={'mode':'server','server_url':'https://127.0.0.1:8765','fingerprint':'ficticia'}
        self.h.services.network=network
        self.h.footer_logos={}
        self.assertEqual(HemerotecaApp._network_state(self.h),('server','https://127.0.0.1:8765','ficticia'))
        HemerotecaApp.show_shell(self.h)
        def children(parent):
            for w in parent.winfo_children():
                yield w;yield from children(w)
        labels=[w.cget('text') for w in children(self.h) if isinstance(w,ctk.CTkButton)]
        self.assertIn('Computadoras conectadas',labels)
        self.h.navigate.assert_called_once()

    def test_shell_no_se_construye_si_falta_configuracion_o_acceso(self):
        self.h._enforce_account_requirements.return_value=True
        HemerotecaApp.show_shell(self.h)
        self.h.services.access.require_access.assert_not_called()
        self.h._enforce_account_requirements.return_value=False
        with patch.object(self.h,'_require_access',return_value=False):HemerotecaApp.show_shell(self.h)
        self.assertEqual(self.h.winfo_children(),[])

    def test_error_callback_desconocido_se_delega_a_tk(self):
        error=RuntimeError('fallo inesperado de prueba')
        with patch.object(ctk.CTk,'report_callback_exception') as report:
            self.h.report_callback_exception(type(error),error,None)
        report.assert_called_once_with(type(error),error,None)
