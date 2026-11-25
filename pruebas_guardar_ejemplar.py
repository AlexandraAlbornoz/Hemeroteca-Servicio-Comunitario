"""Prueba el bloqueo explicativo y el guardado real con una base temporal aislada."""
from pruebas_ayudas import esperar_interfaz
import json
import os
from pathlib import Path
import tempfile


def recorrer(control):
    """Recorre los widgets para encontrar campos, mensajes y botones por su etiqueta."""
    yield control
    for hijo in control.winfo_children():
        yield from recorrer(hijo)


def principal():
    """Ejercita alta y edición, mensajes persistentes y cierre de validadores sin datos reales."""
    with tempfile.TemporaryDirectory(prefix='hemeroteca-guardar-') as temporal:
        os.environ['HEMEROTECA_DATOS']=temporal
        os.environ['PERRI_DATOS']=temporal
        import customtkinter as ctk
        from config.settings import SECURITY_QUESTIONS,NATIONAL,REGIONAL,VIEWS,RED
        from services.container import create_services
        from ui.main_view import HemerotecaApp
        from ui.controles import EntradaFecha
        servicios=create_services(Path(temporal)/'prueba.db')
        servicios.auth.create_master('Responsable Prueba','V-12345678','Prueba#2026',tuple(zip(SECURITY_QUESTIONS[:3],('Luna','María','Caracas'))))
        usuario=servicios.auth.authenticate('V-12345678','Prueba#2026')
        app=HemerotecaApp(servicios)
        errores=[]
        app.report_callback_exception=lambda tipo,error,traza:errores.append(str(error))

        def esperar():
            """Procesa el temporizador real de validación y los eventos de dibujo."""
            listo=ctk.BooleanVar(master=app,value=False)
            app.after(300,lambda:listo.set(True))
            app.wait_variable(listo)
            app.update()

        def abrir(identificador=None):
            """Abre el formulario real y devuelve sus controles etiquetados y su botón."""
            app._record_form(issue_id=identificador)
            dialogo=next(h for h in app.winfo_children() if isinstance(h,ctk.CTkToplevel))
            dialogo.geometry('650x540')
            campos={}
            for control in recorrer(dialogo):
                hijos=control.winfo_children()
                etiquetas=[h for h in hijos if isinstance(h,ctk.CTkLabel)]
                entradas=[h for h in hijos if isinstance(h,(ctk.CTkEntry,ctk.CTkComboBox,EntradaFecha))]
                if etiquetas and entradas:
                    campos[etiquetas[0].cget('text').removesuffix(' *')]=entradas[0]
            boton=next(c for c in recorrer(dialogo) if isinstance(c,ctk.CTkButton) and c.cget('text') in ('Guardar ejemplar','Guardar cambios'))
            mensaje=next(c for c in boton.master.winfo_children() if isinstance(c,ctk.CTkLabel) and c.cget('text_color')==RED)
            return dialogo,campos,boton,mensaje

        def completar(campos,valores):
            """Cambia campos sin invocar callbacks privados y espera su validación automática."""
            for etiqueta,valor in valores.items():
                control=campos[etiqueta]
                if isinstance(control,(ctk.CTkComboBox,EntradaFecha)):
                    control.set(valor)
                else:
                    control.delete(0,'end')
                    control.insert(0,valor)
            esperar()

        try:
            app.user=dict(usuario)
            app._authenticated_version=usuario['password_version']
            app.show_shell(VIEWS[1])
            valores={'Periódico':REGIONAL[0],'Fecha de publicación':'01/01/2026','Edición':'Matutina',
                     'Número':'123','Estante':'1','Gaveta':'2','Estado':'Disponible'}
            dialogo,campos,boton,mensaje=abrir()
            completar(campos,valores)
            assert boton.cget('state')=='normal' and not mensaje.cget('text')
            completar(campos,{'Edición':'1'})
            assert boton.cget('state')=='disabled' and 'Edición:' in mensaje.cget('text')
            assert mensaje.winfo_viewable()
            assert mensaje.winfo_rooty()+mensaje.winfo_height() <= dialogo.winfo_rooty()+dialogo.winfo_height()
            completar(campos,{'Periódico':NATIONAL[0],'Edición':'1'})
            assert boton.cget('state')=='disabled' and 'Edición:' in mensaje.cget('text')
            completar(campos,{'Edición':'Matutina'})
            assert boton.cget('state')=='normal' and not mensaje.cget('text')
            boton.invoke()
            assert servicios.connection.execute('SELECT count(*) FROM issues').fetchone()[0]==1
            dialogo,campos,boton,mensaje=abrir()
            completar(campos,dict(valores,**{'Periódico':NATIONAL[0]}))
            boton.invoke()
            esperar()
            assert 'Ya existe' in mensaje.cget('text'), 'El temporizador no debe borrar el error del guardado.'
            assert servicios.connection.execute('SELECT count(*) FROM issues').fetchone()[0]==1
            pendiente=dialogo._validacion_pendiente
            dialogo.destroy()
            assert pendiente not in app.tk.splitlist(app.tk.call('after','info'))
            dialogo,campos,boton,mensaje=abrir(1)
            completar(campos,{'Estante':'','Gaveta':''})
            assert boton.cget('state')=='disabled' and 'Ubicación:' in mensaje.cget('text')
            completar(campos,{'Gaveta':'7'})
            assert boton.cget('state')=='normal'
            boton.invoke()
            assert tuple(servicios.connection.execute('SELECT shelf,drawer FROM issues WHERE id=1').fetchone())==('','7')
            esperar()
            assert not errores,errores
            informe={'correcto':True,'registro_y_edicion':'correctos','bloqueos_con_mensaje_visible':True,
                     'duplicado_sin_perdida_del_error':True,'temporizador_cancelado':True,'errores':errores}
            (Path(__file__).parent/'RESULTADO_GUARDAR_EJEMPLAR.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(informe,ensure_ascii=False))
        finally:
            for hijo in list(app.winfo_children()):
                if isinstance(hijo,ctk.CTkToplevel):
                    hijo.destroy()
            esperar_interfaz(app)
            app._close()


if __name__=='__main__':
    principal()
