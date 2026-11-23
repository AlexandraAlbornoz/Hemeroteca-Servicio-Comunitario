"""Diálogos de red con controles reales y temporizadores de sondeo deterministas."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.soporte_pantallas import VentanaGeneral
from hemeroteca.ui import network_view as module


class PruebasPantallaRed(unittest.TestCase):
    """No abre puertos, cambia firewall ni ejecuta PowerShell real."""

    def setUp(self):
        """Construye una ventana aislada y un gestor de frontera controlado."""
        self.h = VentanaGeneral()
        self.addCleanup(self.h.close_for_test)
        self.net = self.h.services.network
        for name in ('showwarning', 'showinfo'):
            setattr(self, name, patch('hemeroteca.ui.network_view.messagebox.' + name).start())
        self.addCleanup(patch.stopall)

    def sondear(self):
        """Ejecuta el callback real de Tk sin dormir un segundo ni dejar su evento duplicado."""
        for task in self.h.tk.splitlist(self.h.tk.call('after', 'info')):
            script, kind = self.h.tk.splitlist(self.h.tk.call('after', 'info', task))
            if str(script).endswith('sondear'):
                self.h.tk.call('after', 'cancel', task)
                self.h.tk.call(script)
                return
        self.fail('No hay sondeo pendiente')

    def test_formularios_restringidos_no_se_abren(self):
        """Todas las acciones administrativas consultan el guardián de acceso."""
        self.h._require_access.return_value = False
        self.h._network_form()
        self.h._approve_computer_form({'name': 'PC ficticia'})
        self.h._revoke_computer_form({'name': 'PC ficticia'})
        self.h._promote_principal_form()
        self.assertEqual(self.h.dialogs, [])

    def test_asistente_windows_ruta_absoluta_y_otra_plataforma(self):
        """Solo se construye el proceso; ninguna regla de firewall se modifica."""
        with patch.object(module, 'sys', SimpleNamespace(platform='linux')):
            self.h._windows_network_setup()
        self.showinfo.assert_called_once()
        with patch.object(module.subprocess, 'Popen') as process:
            self.h._windows_network_setup()
        self.assertEqual(process.call_args.args[0][0], str(module.WINDOWS_POWERSHELL))

    def test_preparacion_error_no_crea_dialogo(self):
        """Una colección no preparable informa el error sin abrir otra ventana."""
        self.net.prepare_consultation_pc.side_effect = ValueError('fallo ficticio')
        self.h._connect_server_form()
        self.showwarning.assert_called_once()
        self.assertEqual(self.h.dialogs, [])

    def test_sondeo_expiracion_error_conexion_y_cierre(self):
        """La espera actualiza mensajes y cierra el receptor una sola vez al conectar."""
        receiver = SimpleNamespace(name='PC ficticia', code='ABCD-EFGH-JKMN', state='waiting',
                                   last_error='', expired=Mock(return_value=False))
        self.net.prepare_consultation_pc.return_value = receiver
        self.h._connect_server_form()
        self.sondear()
        receiver.expired.return_value = True
        self.sondear()
        self.assertTrue(self.h.has_text('venció'))
        receiver.expired.return_value = False
        receiver.last_error = 'red ficticia no disponible'
        self.sondear()
        self.assertTrue(self.h.has_text('no disponible'))
        receiver.state = 'connected'
        self.sondear()
        self.net.stop_preparation.assert_called_once()
        self.h._restart_services.assert_called_once()

    def test_cancelacion_preparacion_detiene_receptor(self):
        """Cancelar y destruir el diálogo no repite la liberación del receptor."""
        self.net.prepare_consultation_pc.return_value = SimpleNamespace(name='PC ficticia', code='ABCD', state='waiting')
        self.h._connect_server_form()
        self.h.button('Cancelar preparación').invoke()
        self.net.stop_preparation.assert_called_once()

    def test_activar_principal_fallo_y_reintento(self):
        """La activación fallida conserva el campo y el éxito reconstruye opciones."""
        self.h._network_form()
        self.h.write('Tu contraseña de administrador maestro *', 'Prueba#2026')
        self.net.activate_principal.side_effect = OSError('fallo ficticio de red')
        self.h.button('Activar esta PC como principal').invoke()
        self.assertTrue(self.h.has_text('fallo ficticio'))
        self.net.activate_principal.side_effect = None
        with patch.object(self.h, '_network_form') as refresh:
            self.h.button('Activar esta PC como principal').invoke()
            refresh.assert_called_once()

    def test_busqueda_error_vacia_candidato_y_enlaces_de_accion(self):
        """Los estados se recuperan tras error y cada botón conserva la fila elegida."""
        self.net.describe.return_value['mode'] = 'server'
        record = dict(name='PC autorizada', active=True, device_id='ficticia')
        self.net.approved_computers.return_value = [record, dict(name='Retirada', active=False)]
        self.h._network_form()
        self.net.discover_computers.side_effect = ValueError('búsqueda ficticia fallida')
        self.h.button('Buscar computadoras').invoke()
        self.assertEqual(self.h.button('Buscar computadoras').cget('state'), 'normal')
        self.net.discover_computers.side_effect = None
        self.h.button('Buscar computadoras').invoke()
        self.assertTrue(self.h.has_text('No encontramos'))
        candidate = {'name': 'PC candidata'}
        self.net.discover_computers.return_value = [candidate]
        self.h.button('Buscar computadoras').invoke()
        with patch.object(self.h, '_approve_computer_form') as approve:
            self.h.button('Conectar esta computadora').invoke()
            approve.assert_called_once_with(candidate)
        with patch.object(self.h, '_revoke_computer_form') as revoke:
            self.h.button('Retirar acceso').invoke()
            revoke.assert_called_once_with(record)
        with patch.object(self.h, '_network_form') as refresh:
            self.h.button('Actualizar lista').invoke()
            refresh.assert_called_once()

    def test_cliente_puede_abrir_promocion_sin_gestionar_equipos(self):
        """La pantalla remota explica su límite y deriva a la promoción explícita."""
        self.h.services.read_only = True
        self.h._network_form()
        with patch.object(self.h, '_promote_principal_form') as promote:
            self.h.button('Convertir esta PC en la principal').invoke()
            promote.assert_called_once()
        self.net.approved_computers.assert_not_called()

    def test_aprobacion_reintenta_y_restaura_boton(self):
        """La contraseña y código se entregan al servicio; un fallo habilita reintentar."""
        candidate = {'name': 'PC ficticia'}
        self.h._approve_computer_form(candidate)
        self.h.write('Código que muestra la otra computadora *', 'ABCD-EFGH-JKMN')
        self.net.approve_computer.side_effect = ValueError('rechazo ficticio')
        self.h.button('Autorizar y conectar').invoke()
        self.assertEqual(self.h.button('Autorizar y conectar').cget('state'), 'normal')
        self.net.approve_computer.side_effect = None
        self.h.button('Autorizar y conectar').invoke()
        self.assertEqual(self.net.approve_computer.call_args.args[2], candidate)

    def test_revocacion_promocion_y_recuperacion_error_exito(self):
        """Los tres formularios mantienen el error y solo cierran tras éxito del servicio."""
        cases = [(lambda: self.h._revoke_computer_form({'name': 'Ficticia', 'device_id': 'ficticia'}), 'Retirar acceso', self.net.revoke_computer),
                 (self.h._promote_principal_form, 'Trasladar a esta PC', self.net.activate_principal),
                 (self.h._recover_transfer_form, 'Recuperar PC anterior', self.net.recover_pending_transfer)]
        for open_form, text, operation in cases:
            open_form()
            operation.side_effect = ValueError('fallo ficticio controlado')
            self.h.button(text).invoke()
            self.assertTrue(self.h.has_text('controlado'))
            operation.side_effect = None
            self.h.button(text).invoke()
            self.assertFalse(self.h.dialogs[-1].winfo_exists())

    def test_reconstruccion_de_servicios_cierra_anterior_y_vuelve_al_ingreso(self):
        """Ejercita la coordinación de reemplazo sin crear otro servidor o colección."""
        old = self.h.services
        old.close = Mock()
        replacement = SimpleNamespace()
        with patch('hemeroteca.ui.tareas.ServiciosDeInterfaz', return_value=replacement) as wrapper:
            module.NetworkView._restart_services(self.h)
        old.close.assert_called_once()
        wrapper.assert_called_once_with(self.h, old.original.network.services.return_value)
        self.assertIs(self.h.services, replacement)
        self.h.show_login.assert_called_once()
