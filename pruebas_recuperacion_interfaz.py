"""Prueba el registro y ambas recuperaciones mediante formularios con datos ficticios."""
from pruebas_ayudas import esperar_interfaz
import json
import os
from pathlib import Path
import tempfile


def principal():
    """Crea una cuenta temporal, conserva el código y recupera por preguntas y por código."""
    carpeta = Path(__file__).resolve().parent
    temporales = carpeta / '.pruebas_temporales'
    temporales.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporales, prefix='recuperacion-ui-') as directorio:
        os.environ['PERRI_DATOS'] = directorio
        import customtkinter as ctk
        from ui.controles import EntradaDocumento
        from services.container import create_services
        from config.settings import ROLES, SECURITY_QUESTIONS
        from ui.main_view import HemerotecaApp
        servicios = create_services(Path(directorio) / 'hemeroteca.db')
        preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Pecas')))
        servicios.auth.create_master('Responsable ficticio', 'V-810000', 'Respons!2026', preguntas)
        aplicacion = HemerotecaApp(servicios)
        aplicacion.withdraw()
        errores = []
        aplicacion.report_callback_exception = lambda tipo, error, traza: errores.append(str(error))

        def recorrer(control):
            """Enumera los controles reales de la instancia de prueba."""
            yield control
            for hijo in control.winfo_children():
                yield from recorrer(hijo)

        def completar(raiz, valores):
            """Introduce datos ficticios en entradas identificadas por su etiqueta."""
            for control in list(recorrer(raiz)):
                hijos = control.winfo_children()
                etiquetas = [hijo for hijo in hijos if isinstance(hijo, ctk.CTkLabel)]
                entradas = [hijo for hijo in hijos if isinstance(hijo, (ctk.CTkEntry, EntradaDocumento))]
                if etiquetas and entradas:
                    etiqueta = etiquetas[0].cget('text').removesuffix(' *')
                    if etiqueta in valores:
                        entradas[0].delete(0, 'end')
                        entradas[0].insert(0, valores[etiqueta])

        def pulsar(raiz, texto):
            """Invoca una acción inequívoca y comprueba errores del callback."""
            botones = [control for control in recorrer(raiz) if isinstance(control, ctk.CTkButton) and control.cget('text') == texto]
            assert len(botones) == 1, (texto, len(botones))
            botones[0].invoke()
            assert not errores, errores

        def dialogo_actual():
            """Obtiene el único diálogo de credenciales abierto en la prueba."""
            dialogos = [control for control in aplicacion.winfo_children() if isinstance(control, ctk.CTkToplevel)]
            assert len(dialogos) == 1, len(dialogos)
            return dialogos[0]

        def conservar_codigo():
            """Comprueba el código visible y confirma su conservación sin publicarlo."""
            dialogo = dialogo_actual()
            campos = [control for control in recorrer(dialogo) if isinstance(control, ctk.CTkTextbox)]
            assert len(campos) == 1
            codigo = campos[0].get('1.0', 'end').strip()
            assert codigo.startswith('HMR-') and len(codigo) > 30
            casilla = next(control for control in recorrer(dialogo) if isinstance(control, ctk.CTkCheckBox))
            casilla.toggle()
            pulsar(dialogo, 'Ya lo guardé · Continuar')
            return codigo

        try:
            aplicacion.show_login(True)
            aplicacion.reg_name[1].insert(0, 'Titular')
            aplicacion.reg_lastname[1].insert(0, 'ficticio')
            aplicacion.login_identity.set('V-810001')
            aplicacion.login_password.insert(0, 'Inicial!2026')
            aplicacion.reg_confirm.insert(0, 'Inicial!2026')
            aplicacion.reg_role.set(ROLES[2])
            aplicacion.register_user()
            completar(dialogo_actual(), {'Respuesta 1': 'Luna', 'Respuesta 2': 'María', 'Respuesta 3': 'Pecas'})
            pulsar(dialogo_actual(), 'Crear mi cuenta')
            codigo_inicial = conservar_codigo()
            assert aplicacion.user is None
            assert aplicacion.login_identity.get() == "V-810001"
            aplicacion.show_master_recovery()
            dialogo = dialogo_actual()
            completar(dialogo, {'Documento': 'V-810001'})
            pestañas = next(control for control in recorrer(dialogo) if isinstance(control, ctk.CTkTabview))
            pestañas.set('Con mis preguntas')
            pulsar(dialogo, 'Mostrar mis preguntas')
            completar(dialogo, {f'{numero}. {pregunta}': respuesta for numero, (pregunta, respuesta) in enumerate(preguntas, 1)})
            pulsar(dialogo, 'Recuperar acceso')
            assert aplicacion.user['must_change_password']
            completar(aplicacion, {'Nueva contraseña': 'Pregunt!2026', 'Confirmar nueva contraseña': 'Pregunt!2026'})
            pulsar(aplicacion, 'Guardar contraseña')
            codigo_por_preguntas = conservar_codigo()
            assert codigo_por_preguntas != codigo_inicial
            assert aplicacion.current_view == 'Consulta de periódicos'
            aplicacion.show_login()
            aplicacion.show_master_recovery()
            completar(dialogo_actual(), {'Documento': 'V-810001', 'Código de recuperación': codigo_por_preguntas.lower()})
            campo_codigo = next(control for control in recorrer(dialogo_actual()) if isinstance(control, ctk.CTkEntry) and control.cget('placeholder_text') == 'HMR-…')
            assert campo_codigo.cget('show') == ''
            assert campo_codigo.get() == codigo_por_preguntas
            campo_codigo.delete(0, 'end')
            campo_codigo.insert(0, 'hmr-abc')
            campo_codigo.insert(4, 'q')
            assert campo_codigo.get() == 'HMR-QABC'
            campo_codigo.delete(4, 5)
            assert campo_codigo.get() == 'HMR-ABC'
            campo_codigo.delete(0, 'end')
            campo_codigo.insert(0, codigo_por_preguntas.lower())
            documentos = [control for control in recorrer(dialogo_actual()) if isinstance(control, EntradaDocumento)]
            assert len(documentos) == 1 and documentos[0].tipo.cget('state') == 'readonly'
            documentos[0].tipo.set('E')
            assert documentos[0].get() == 'E-810001'
            documentos[0].tipo.set('V')
            pulsar(dialogo_actual(), 'Recuperar acceso')
            completar(aplicacion, {'Nueva contraseña': 'Codigo!2026', 'Confirmar nueva contraseña': 'Codigo!2026'})
            pulsar(aplicacion, 'Guardar contraseña')
            codigo_por_codigo = conservar_codigo()
            assert codigo_por_codigo != codigo_por_preguntas
            assert servicios.auth.authenticate('V-810001', 'Codigo!2026')['active']
            resultado = {'registro_muestra_codigo': True, 'confirmacion_conservacion': True,
                         'recuperacion_por_preguntas': True, 'recuperacion_por_codigo': True,
                         'codigo_rotado_en_ambos_metodos': True, 'errores': errores}
            (carpeta / 'RESULTADO_RECUPERACION_INTERFAZ.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(resultado, ensure_ascii=False))
        finally:
            esperar_interfaz(aplicacion)
            aplicacion._close()


if __name__ == '__main__':
    principal()
