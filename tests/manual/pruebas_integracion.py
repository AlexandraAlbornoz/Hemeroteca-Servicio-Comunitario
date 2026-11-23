"""Verifica RPC TLS, reportes y restauración cifrada en una instalación temporal."""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile


def verificar():
    """Ejecuta un servidor de prueba en loopback y limpia todos sus datos al terminar."""
    carpeta_temporal = Path(__file__).resolve().parent / '.pruebas_temporales'
    carpeta_temporal.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=carpeta_temporal, prefix='integracion-') as directorio:
        os.environ['HEMEROTECA_DATA_DIR'] = directorio
        from hemeroteca.services.container import create_services
        from hemeroteca.config.settings import TITLES, REGIONAL, SECURITY_QUESTIONS
        from hemeroteca.network.configuration import ensure_certificate
        from hemeroteca.network.devices import DeviceIdentity
        from hemeroteca.network.server import LANServer
        from hemeroteca.network.client import RemoteClient, RemoteServices
        from hemeroteca.services.backup_archive import derive_key, snapshot, write_archive
        from hemeroteca.database.maintenance import database_guard
        from hemeroteca.services.access_service import AccessDenied
        from hemeroteca.services.paginacion import REGISTROS_POR_PAGINA

        ruta = Path(directorio) / 'hemeroteca.db'
        servicios = create_services(ruta, node_id='nodo-prueba')
        preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Una', 'Dos', 'Tres')))
        servicios.auth.create_master('Responsable temporal', 'V-555555', 'Prueba!2026', preguntas)
        maestro = servicios.auth.authenticate('V-555555', 'Prueba!2026')
        for numero in range(25):
            servicios.periodicos.save_record(maestro, (TITLES[0], 'Regional' if TITLES[0] in REGIONAL else 'Nacional', 'Matutina', 2020, 1, 1, str(numero), '1', '2', 'Disponible'))
        identidad = DeviceIdentity()
        servicios.connection.execute("INSERT INTO authorized_devices(device_id,public_key,node_id,name,approved_by,approved_at) VALUES(?,?,?,?,?,?)",
            (identidad.device_id, identidad.public_key, 'cliente-prueba', 'Equipo temporal', 'Prueba', '2026-01-01T00:00:00+00:00'))
        servicios.connection.commit()
        contexto, huella = ensure_certificate()
        configuracion = {'node_id': 'nodo-prueba', 'bind': '127.0.0.1', 'port': 0, 'fingerprint': huella}
        servidor = LANServer(ruta, configuracion, contexto)
        servidor.start()
        try:
            cliente = RemoteClient({'server_url': f'https://127.0.0.1:{servidor.httpd.server_port}', 'fingerprint': huella})
            remoto = RemoteServices(cliente, None)
            cuenta = remoto.auth.authenticate('V-555555', 'Prueba!2026')
            assert 'password' not in cuenta
            pagina = remoto.periodicos.search_issues(cuenta, catalog=True, page=2)
            assert pagina['total'] == 25 and len(pagina['items']) == REGISTROS_POR_PAGINA
            ficha = remoto.periodicos.get_issue(cuenta, 1)
            valores = (ficha['title'], ficha['kind'], ficha['edition'], ficha['year'], ficha['month'], ficha['day'], ficha['number'], '33', ficha['drawer'], ficha['status'])
            remoto.periodicos.save_record(cuenta, valores, issue_id=1, expected_revision=ficha['revision'])
            try:
                remoto.periodicos.save_record(cuenta, valores, issue_id=1, expected_revision=ficha['revision'])
            except ValueError:
                pass
            else:
                raise AssertionError('La API aceptó una edición obsoleta.')
            assert remoto.access.estado_sesion(cuenta)['usuario']['id'] == cuenta['id']
            assert remoto.users.buscar_usuarios(cuenta)['total'] == 1
            assert remoto.audit.buscar_eventos(cuenta)['total'] > 0
            assert remoto.requests.resumen_solicitudes(cuenta)['contadores'] == {}
            pdf = remoto.reports.generate(cuenta, scope='issues', filters={'year': 2020})
            assert pdf['records'] == 25 and base64.b64decode(pdf['content']).startswith(b'%PDF-')
            for filtros_rango in ({'desde': '2020-01-01', 'hasta': '2020-01-01'},
                                  {'desde': '2020-01-01'}, {'hasta': '2020-01-01'}):
                pdf_rango = remoto.reports.generate(cuenta, scope='issues', filters=filtros_rango)
                assert pdf_rango['records'] == 25 and base64.b64decode(pdf_rango['content']).startswith(b'%PDF-')

            registro_remoto = remoto.users.register_user('Titular de prueba', 'V-555556', 'Usuario!2026', preguntas)
            assert registro_remoto.recovery_code.startswith('HMR-')
            cliente_recuperacion = RemoteClient(dict(cliente.settings))
            sesion_recuperacion = RemoteServices(cliente_recuperacion, None)
            assert len(sesion_recuperacion.auth.obtener_preguntas_recuperacion('V-555556')) == 3
            recuperado = sesion_recuperacion.auth.autenticar_con_preguntas('V-555556', ('Una', 'Dos', 'Tres'))
            assert recuperado['must_change_password'] and cliente_recuperacion.token
            actualizado = sesion_recuperacion.auth.change_password(recuperado, '', 'NuevaRed#2026')
            assert actualizado['_new_recovery_code'].startswith('HMR-')
            assert sesion_recuperacion.auth.authenticate('V-555556', 'NuevaRed#2026')['id'] == registro_remoto.user_id

            clave = 'Respald!2026'
            archivo = Path(directorio) / 'prueba.hmbackup'
            sal = secrets.token_bytes(16)
            write_archive(archivo, snapshot(servicios.connection), derive_key(clave, sal), sal, reason='prueba')
            metadatos = servicios.backups.preview(maestro, archivo, clave)
            servicios.periodicos.delete_issue(maestro, 1)
            resultado = servicios.backups.restore(maestro, archivo, clave, 'Prueba!2026', metadatos['archive_sha256'])
            assert Path(resultado['before']).exists()
            assert servicios.connection.execute('SELECT deleted FROM issues WHERE id=1').fetchone()[0] == 0
            assert servicios.connection.execute('SELECT count(*) FROM authorized_devices').fetchone()[0] == 0
            try:
                remoto.periodicos.search_issues(cuenta)
            except AccessDenied:
                pass
            else:
                raise AssertionError('Un equipo retirado pudo consultar después de restaurar.')

            programa = "import sys\nfrom hemeroteca.database.maintenance import database_guard\ntry:\n with database_guard(sys.argv[1], timeout=.2, exclusive=sys.argv[2]=='exclusiva'):\n  pass\nexcept ValueError:\n sys.exit(3)\n"
            with database_guard(ruta, exclusive=False):
                compartida = subprocess.run([sys.executable, '-B', '-c', programa, str(ruta), 'compartida'], capture_output=True, timeout=10)
                exclusiva = subprocess.run([sys.executable, '-B', '-c', programa, str(ruta), 'exclusiva'], capture_output=True, timeout=10)
            assert compartida.returncode == 0, compartida.stderr.decode(errors='replace')
            assert exclusiva.returncode == 3, exclusiva.stderr.decode(errors='replace')
            informe = {'rpc_tls': 'correcto', 'paginacion_lan': 'correcta', 'conflicto_edicion_lan': 'rechazado',
                'pdf_lan': 'correcto', 'restauracion_cifrada': 'correcta', 'sesiones_y_equipos_tras_restaurar': 'retirados',
                'exclusion_entre_procesos': 'correcta', 'registro_y_recuperacion_preguntas_lan': 'correctos'}
            (Path(__file__).resolve().parent / 'RESULTADO_INTEGRACION.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(informe, ensure_ascii=False))
        finally:
            servidor.close()
            servicios.close()


if __name__ == '__main__':
    verificar()
