"""Prueba la aprobación desde el coordinador de la interfaz hasta el aviso del cliente."""
import os
from pathlib import Path
import socket
import tempfile
import time
from unittest.mock import patch


def probar():
    with tempfile.TemporaryDirectory() as carpeta:
        os.environ.update(HEMEROTECA_PRUEBAS_AISLADAS='1', HEMEROTECA_DATOS=carpeta)
        from config.settings import SECURITY_QUESTIONS
        from network.configuration import load_settings
        from network.manager import NetworkManager
        from network.transport import ErrorConexion, request
        from ui.main_view import HemerotecaApp
        from ui.tareas import ServiciosDeInterfaz

        raiz = Path(carpeta)
        servidor = NetworkManager(raiz / 'central.db', raiz / 'central.json')
        cliente = NetworkManager(raiz / 'consulta.db', raiz / 'consulta.json')
        central = servidor.services()
        preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Uno', 'Dos', 'Tres')))
        central.auth.create_master('Administrador temporal', 'V-555555', 'Prueba!2026', preguntas)
        maestro = central.auth.authenticate('V-555555', 'Prueba!2026')
        with socket.socket() as libre:
            libre.bind(('127.0.0.1', 0))
            puerto = libre.getsockname()[1]
        servidor.configure_server(central, maestro, 'Prueba!2026', '127.0.0.1', puerto)
        ventana = HemerotecaApp(cliente.services())
        ventana.withdraw()
        emisor = ServiciosDeInterfaz(ventana, central)
        try:
            with (patch('network.manager.local_address', return_value='127.0.0.1'),
                  patch('network.pairing.PAIRING_PORT', 0),
                  patch('network.discovery.DISCOVERY_PORT', 0),
                  patch('ui.network_view.messagebox.showinfo') as aviso):
                ventana._connect_server_form()
                receptor = cliente.receiver
                candidato = dict(receptor.description(), url=f'https://127.0.0.1:{receptor.httpd.server_port}')
                inaccesible = 'https://127.0.0.2:8767'
                codigo_erroneo = ('A' if receptor.code[0] != 'A' else 'B') + receptor.code[1:]
                try:
                    emisor.network.approve_computer(emisor, maestro, candidato, codigo_erroneo, 'Prueba!2026')
                except ValueError:
                    assert receptor.state == 'waiting'
                else:
                    raise AssertionError('Se aceptó un código incorrecto.')
                candidato['urls'] = [inaccesible, candidato['url']]
                def probar_ruta(url, *args, **kwargs):
                    if url == inaccesible:
                        raise ErrorConexion('Ruta inaccesible simulada')
                    return request(url, *args, **kwargs)

                with patch('network.manager.request', side_effect=probar_ruta) as transporte:
                    with patch('network.pairing.request', side_effect=ErrorConexion('Retorno bloqueado simulado')):
                        try:
                            emisor.network.approve_computer(emisor, maestro, candidato, receptor.code, 'Prueba!2026')
                        except ValueError as error:
                            assert 'PC principal' in str(error) and 'Permitir la red en Windows' in str(error)
                        else:
                            raise AssertionError('No se diagnosticó el bloqueo de vuelta a la principal.')
                    equipo = emisor.network.approve_computer(emisor, maestro, candidato, receptor.code, 'Prueba!2026')
                    assert transporte.call_args_list[0].args[0] == inaccesible
                    assert transporte.call_args_list[1].args[0] == candidato['url']
                assert equipo == receptor.identity.device_id and receptor.state == 'connected'
                limite = time.monotonic() + 8
                while not aviso.called and time.monotonic() < limite:
                    ventana.update()
                    time.sleep(.02)
                assert aviso.call_count == 1 and aviso.call_args.args[0] == 'Computadora conectada'
                assert ventana.services.read_only and load_settings(cliente.config_path)['mode'] == 'client'
                cuenta = ventana.services.auth.authenticate('V-555555', 'Prueba!2026')
                assert cuenta['id'] == maestro['id']
        finally:
            emisor.close()
            ventana.services.close()
            cliente.close()
            servidor.close()
            ventana.destroy()


if __name__ == '__main__':
    probar()
    print('Aprobación HTTPS, aviso del cliente e inicio de sesión verificados.')
