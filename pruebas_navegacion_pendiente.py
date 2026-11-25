"""Ejercita clics de navegación durante consultas y escrituras lentas con datos ficticios."""
from pruebas_ayudas import esperar_interfaz
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch


def principal():
    """Comprueba el último destino, un guardado único y la cancelación al salir de sesión."""
    with tempfile.TemporaryDirectory(prefix='hemeroteca-navegacion-') as temporal:
        os.environ['HEMEROTECA_DATOS']=temporal
        os.environ['PERRI_DATOS']=temporal
        from services.container import create_services
        from services.access_service import AccessService
        from services.periodico_service import PeriodicoService
        from config.settings import SECURITY_QUESTIONS,NATIONAL,VIEWS
        from ui.main_view import HemerotecaApp
        servicios=create_services(Path(temporal)/'prueba.db')
        servicios.auth.create_master('Prueba Navegación','V-12345678','Prueba#2026',tuple(zip(SECURITY_QUESTIONS[:3],('Uno','Dos','Tres'))))
        usuario=servicios.auth.authenticate('V-12345678','Prueba#2026')
        app=HemerotecaApp(servicios)
        app.withdraw()
        errores=[]
        app.report_callback_exception=lambda tipo,error,traza:errores.append(str(error))

        def terminar_navegacion():
            """Procesa eventos hasta finalizar la navegación encolada sin esperas indefinidas."""
            esperar_interfaz(app)

        try:
            app.user=dict(usuario)
            app._authenticated_version=usuario['password_version']
            app.show_shell()
            esperar_interfaz(app)
            exigir=AccessService.require_access
            demora=[True]

            def acceso_lento(instancia,*argumentos,**opciones):
                """Mantiene una consulta en curso mientras llegan nuevos clics del menú."""
                if demora[0]:
                    demora[0]=False
                    time.sleep(.12)
                return exigir(instancia,*argumentos,**opciones)

            with patch('ui.main_view.messagebox.showwarning') as avisos:
                with patch.object(AccessService,'require_access',acceso_lento):
                    app.after(1,lambda:app.navigate(VIEWS[2]))
                    app.after(2,lambda:app.navigate(VIEWS[3]))
                    app.navigate(VIEWS[1])
                    terminar_navegacion()
                assert app.current_view==VIEWS[3], app.current_view
                assert not avisos.called, avisos.call_args_list
                guardar=PeriodicoService.save_record

                def guardado_lento(instancia,*argumentos,**opciones):
                    """Retrasa una escritura real para comprobar que navegar no la interrumpe."""
                    time.sleep(.12)
                    return guardar(instancia,*argumentos,**opciones)

                with patch.object(PeriodicoService,'save_record',guardado_lento):
                    app.after(1,lambda:app.navigate(VIEWS[0]))
                    app.services.periodicos.save_record(app.user,(NATIONAL[0],'Nacional','Matutina',2026,1,1,'42','1','','Disponible'))
                    terminar_navegacion()
                assert app.current_view==VIEWS[0]
                assert servicios.connection.execute('SELECT count(*) FROM issues').fetchone()[0]==1
                assert not avisos.called, avisos.call_args_list
                app._servicios_ocupados=True
                app.navigate(VIEWS[2])
                app._servicios_ocupados=False
                app.show_login()
                assert app._destino_pendiente is None and app._navegacion_pendiente is None
                app.update()
                assert app.user is None
                assert not errores, errores
            informe={'correcto':True,'navegacion_rapida_sin_alertas':True,'ultimo_destino_respetado':True,'guardado_unico_conservado':True,'salida_cancela_destino':True,'errores':errores}
            (Path(__file__).parent/'RESULTADO_NAVEGACION_PENDIENTE.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(informe))
        finally:
            esperar_interfaz(app)
            app._close()


if __name__=='__main__':
    principal()
