"""Pruebas de interfaz real con datos ficticios y demoras controladas, sin tocar la colección instalada."""
import json
import os
import sys
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch


def principal(remoto=False):
    """Comprueba navegación, repintado, resultados obsoletos y reutilización de tablas."""
    with tempfile.TemporaryDirectory(prefix='hemeroteca-230-') as temporal:
        os.environ['HEMEROTECA_PRUEBAS_AISLADAS'] = '1'
        os.environ['HEMEROTECA_DATOS'] = temporal
        from services.container import create_services
        from services.periodico_service import PeriodicoService
        from config.settings import SECURITY_QUESTIONS, NATIONAL, VIEWS, ROLES
        from ui.main_view import HemerotecaApp
        servicios = create_services(Path(temporal) / 'prueba.db')
        servicios.auth.create_master('Prueba Interfaz', 'V-12345678', 'Prueba#2026',
            tuple(zip(SECURITY_QUESTIONS[:3], ('Primera', 'Segunda', 'Tercera'))))
        usuario = servicios.auth.authenticate('V-12345678', 'Prueba#2026')
        for numero in range(1, 12):
            servicios.periodicos.save_record(usuario, (NATIONAL[0], 'Nacional', 'Matutina', 2026, 1, numero, str(numero), '1', '', 'Disponible'))
        servidor = None
        interfaz_servicios = servicios
        if remoto:
            from network.configuration import ensure_certificate
            from network.devices import DeviceIdentity
            from network.server import LANServer
            from network.client import RemoteClient, RemoteServices
            identidad = DeviceIdentity()
            servicios.connection.execute('INSERT INTO authorized_devices(device_id,public_key,node_id,name,approved_by,approved_at) VALUES(?,?,?,?,?,?)',
                (identidad.device_id, identidad.public_key, 'cliente-ficticio', 'Cliente ficticio', 'Prueba', '2026-11-02T00:00:00+00:00'))
            servicios.connection.commit()
            contexto, huella = ensure_certificate()
            servidor = LANServer(Path(temporal) / 'prueba.db', {'node_id': 'servidor-ficticio', 'bind': '127.0.0.1', 'port': 0, 'fingerprint': huella}, contexto)
            servidor.start()
            cliente = RemoteClient({'server_url': f'https://127.0.0.1:{servidor.httpd.server_port}', 'fingerprint': huella})
            interfaz_servicios = RemoteServices(cliente, None)
            usuario = interfaz_servicios.auth.authenticate('V-12345678', 'Prueba#2026')
        app = HemerotecaApp(interfaz_servicios)
        app.title('Hemeroteca 2.3.0 · Pruebas con datos ficticios')
        errores = []
        app.report_callback_exception = lambda tipo, error, traza: errores.append(repr(error))

        def esperar(condicion, limite=12):
            """Procesa eventos de Tk con un plazo para detectar bloqueos de callbacks."""
            fin = time.monotonic() + limite
            while not condicion() and time.monotonic() < fin:
                app.update()
                time.sleep(.01)
            assert condicion(), ('Tiempo agotado', errores)
            assert not errores, errores

        def reposo():
            """Espera la entrega en Tk de todos los trabajos pendientes."""
            esperar(lambda: app.services._trabajos == 0 and not getattr(app, '_navegacion_pendiente', None))

        def descendientes(widget):
            """Enumera controles de la aplicación de prueba sin usar datos personales."""
            for hijo in widget.winfo_children():
                yield hijo
                yield from descendientes(hijo)

        def tablas():
            """Encuentra árboles reutilizables en la vista activa."""
            return [w for w in descendientes(app.content) if hasattr(w, '_tabla_paginada')]

        try:
            app.user = dict(usuario)
            app._authenticated_version = usuario['password_version']
            app.show_shell()
            reposo()
            vistas = []
            for vista in app._allowed_views():
                app.navigate(vista)
                reposo()
                assert app.current_view == vista
                vistas.append(vista)

            original = PeriodicoService.search_issues
            iniciada = threading.Event()
            liberar = threading.Event()
            def consulta_lenta(servicio, *args, **kwargs):
                """Simula una red lenta sin bloquear Tcl ni cambiar el resultado del servicio."""
                iniciada.set()
                assert liberar.wait(8)
                return original(servicio, *args, **kwargs)

            with patch.object(PeriodicoService, 'search_issues', consulta_lenta):
                inicio = time.perf_counter()
                app.navigate(VIEWS[0])
                retorno_ms = round((time.perf_counter() - inicio) * 1000, 2)
                esperar(iniciada.is_set)
                assert tablas(), 'La tabla debe existir antes de que termine su consulta'
                assert not getattr(app, '_servicios_ocupados', False)
                latido = []
                app.after(10, lambda: latido.append(True))
                esperar(lambda: bool(latido))
                app.navigate(VIEWS[6])
                esperar(lambda: app.current_view == VIEWS[6] and getattr(app, '_contexto_construccion', None) is None and len(app.content.winfo_children()) > 1)
                liberar.set()
                reposo()
                assert app.current_view == VIEWS[6]
                assert not tablas(), 'Una respuesta antigua reconstruyó la tabla en Reportes'

            app.navigate(VIEWS[0])
            reposo()
            padre = tablas()[0]
            estado = padre._tabla_paginada
            arbol = estado['tabla']
            assert len(arbol.get_children()) == 8
            estado['siguiente'].invoke()
            reposo()
            assert padre._tabla_paginada['tabla'] is arbol
            assert len(arbol.get_children()) == 3
            # Dos consultas se terminan en orden inverso: solo se presenta la última.
            area = estado['area']
            resultados = []
            def invertir(operacion, grupo='', metodo=''):
                """Entrega un resultado tardío que la generación debe descartar."""
                time.sleep(.25 if threading.current_thread().name.endswith('_0') else .02)
                return [threading.current_thread().name]
            with patch.object(app.services, '_con_servicios', invertir):
                app._cargar_seccion(area, [], lambda datos: resultados.append('anterior'), clave='carrera')
                app._cargar_seccion(area, [], lambda datos: resultados.append('ultima'), clave='carrera')
                reposo()
                assert resultados == ['ultima'], resultados

            # Un cierre de sesión invalida la entrega de cualquier lectura anterior.
            with patch.object(app.services, '_con_servicios', invertir):
                app._cargar_seccion(area, [], lambda datos: resultados.append('sesion_anterior'), clave='salida')
                app._invalidar_cargas()
                reposo()
                assert 'sesion_anterior' not in resultados
            perfiles = []
            if not remoto:
                for indice, perfil in enumerate(ROLES[1:], 1):
                    documento = f'V-2234567{indice}'
                    servicios.users.register_user('Persona Prueba', documento, 'Prueba#2026',
                        tuple(zip(SECURITY_QUESTIONS[:3], ('Primera', 'Segunda', 'Tercera'))), role=perfil)
                    cuenta = servicios.auth.authenticate(documento, 'Prueba#2026')
                    app.user = dict(cuenta)
                    app._authenticated_version = cuenta['password_version']
                    app.show_shell()
                    reposo()
                    for vista in app._allowed_views():
                        app.navigate(vista)
                        reposo()
                    perfiles.append(perfil)
                    # Una ruta no autorizada no construye una tabla de datos privados.
                    with patch.object(app, '_sync_session', lambda: None):
                        app.navigate(VIEWS[3])
                        reposo()
                        assert not tablas()
                    app.show_login()
                    reposo()
                    assert app.user is None
            assert not errores, errores
            informe = {'correcto': True, 'modo': 'cliente_https_simulado' if remoto else 'local', 'vistas': vistas, 'retorno_navegacion_ms': retorno_ms,
                'controles_antes_de_resultados': True, 'interfaz_responde_durante_consulta': True,
                'respuesta_de_vista_anterior_descartada': True, 'ultima_busqueda_prevalece': True,
                'tabla_reutilizada': True, 'paginacion_8_y_3': True, 'sesion_invalida_descartada': True,
                'perfiles_adicionales': perfiles, 'errores_tk': errores}
            (Path(__file__).parent / ('RESULTADO_CARGA_REMOTA.json' if remoto else 'RESULTADO_CARGA_ASINCRONA.json')).write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(informe, ensure_ascii=False))
        finally:
            liberar.set() if 'liberar' in locals() else None
            fin = time.monotonic() + 12
            while app.services._trabajos and time.monotonic() < fin:
                app.update()
                time.sleep(.01)
            app._close()
            if servidor:
                servidor.close()
                servicios.close()


if __name__ == '__main__':
    principal('--remoto' in sys.argv)
