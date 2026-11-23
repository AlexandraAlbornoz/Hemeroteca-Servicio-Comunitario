"""Verifica pantallas reales de Tkinter con datos temporales y sin servidor LAN."""
from tests.manual.pruebas_ayudas import esperar_interfaz
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

carpeta = Path(__file__).resolve().parent / '.pruebas_temporales'
carpeta.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=carpeta, prefix='interfaz-') as directorio:
    os.environ['HEMEROTECA_DATA_DIR'] = directorio
    from hemeroteca.services.container import create_services
    from hemeroteca.config.settings import VIEWS, TITLES, REGIONAL, SECURITY_QUESTIONS
    from hemeroteca.ui.main_view import HemerotecaApp
    from hemeroteca.services.auth_service import AuthService
    from hemeroteca.services.access_service import AccessService
    from hemeroteca.network.transport import ErrorConexion
    import customtkinter as ctk
    servicios = create_services(Path(directorio) / 'hemeroteca.db')
    preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Uno', 'Dos', 'Tres')))
    servicios.auth.create_master('Prueba de interfaz', 'V-123456', 'Prueba!2026', preguntas)
    usuario = servicios.auth.authenticate('V-123456', 'Prueba!2026')
    servicios.periodicos.save_record(usuario, (TITLES[0], 'Regional' if TITLES[0] in REGIONAL else 'Nacional', 'Matutina', 2020, 1, 1, '1', '1', '2', 'Disponible'))
    aplicacion = HemerotecaApp(servicios)
    aplicacion.withdraw()
    errores = []
    aplicacion.report_callback_exception = lambda tipo, error, traza: errores.append(str(error))
    try:
        aplicacion.user = dict(usuario)
        aplicacion._authenticated_version = usuario['password_version']
        aplicacion.show_shell()
        visitadas = []
        for vista in VIEWS:
            aplicacion.navigate(vista)
            esperar_interfaz(aplicacion)
            visitadas.append(vista)
        from hemeroteca.ui.controles import EntradaFecha, SelectorCompacto
        from tkinter import Listbox
        fecha_prueba = EntradaFecha(aplicacion)
        fecha_prueba.set('29/02/2020')
        assert fecha_prueba.entrada.cget('state') == 'readonly'
        fecha_prueba.set('31/12/2100')
        assert fecha_prueba.get() == '31/12/2100'
        try:
            fecha_prueba.set('01/01/2101')
        except ValueError:
            pass
        else:
            raise AssertionError('El calendario aceptó una fecha posterior a 2100.')
        assert fecha_prueba.get() == '31/12/2100'
        try:
            fecha_prueba.set('01/01/1969')
        except ValueError:
            pass
        else:
            raise AssertionError('El calendario aceptó una fecha anterior a 1970.')
        selector_prueba = SelectorCompacto(aplicacion, values=[str(n) for n in range(20)], state='readonly')
        selector_prueba.set('12')
        selector_prueba._open_dropdown_menu()
        menu_prueba = next(hijo for hijo in selector_prueba.winfo_children() if hijo.winfo_class() == 'Toplevel')
        lista_prueba = next(hijo for hijo in menu_prueba.winfo_children() if isinstance(hijo, Listbox))
        assert int(lista_prueba.cget('height')) == 8
        assert lista_prueba.curselection() == (12,)
        menu_prueba.destroy()
        selector_prueba.destroy()
        fecha_prueba.destroy()
        aplicacion.navigate(VIEWS[1])
        aplicacion._record_form(issue_id=1)
        aplicacion.update_idletasks()
        def recorrer(control):
            """Recorre controles reales para comprobar el formulario sin atajos de servicio."""
            yield control
            for hijo in control.winfo_children():
                yield from recorrer(hijo)
        def completar(dialogo, valores):
            """Completa entradas por etiqueta y acciona el botón real de guardar."""
            for control in list(recorrer(dialogo)):
                hijos = control.winfo_children()
                etiquetas = [hijo for hijo in hijos if isinstance(hijo, ctk.CTkLabel)]
                entradas = [hijo for hijo in hijos if isinstance(hijo, (ctk.CTkEntry, ctk.CTkComboBox, EntradaFecha))]
                if etiquetas and entradas:
                    etiqueta = etiquetas[0].cget('text').removesuffix(' *')
                    if etiqueta in valores:
                        if isinstance(entradas[0], (ctk.CTkComboBox, EntradaFecha)):
                            entradas[0].set(valores[etiqueta])
                        else:
                            entradas[0].delete(0, 'end')
                            entradas[0].insert(0, valores[etiqueta])
            dialogo.update()
            validacion = ctk.BooleanVar(value=False)
            dialogo.after(250, lambda: validacion.set(True))
            dialogo.wait_variable(validacion)
            botones = [control for control in recorrer(dialogo) if isinstance(control, ctk.CTkButton) and control.cget('text') in ('Guardar cambios', 'Guardar ejemplar')]
            assert len(botones) == 1
            botones[0].invoke()
        dialogo = next(control for control in aplicacion.winfo_children() if isinstance(control, ctk.CTkToplevel))
        completar(dialogo, {'Estante': '11'})
        assert servicios.connection.execute('SELECT shelf FROM issues WHERE id=1').fetchone()[0] == '11'
        aplicacion._record_form()
        dialogo = next(control for control in aplicacion.winfo_children() if isinstance(control, ctk.CTkToplevel))
        calendarios = [control for control in recorrer(dialogo) if isinstance(control, EntradaFecha)]
        assert len(calendarios) == 1, 'El ejemplar debe tener un único calendario.'
        etiquetas = [control.cget('text') for control in recorrer(dialogo) if isinstance(control, ctk.CTkLabel)]
        assert not any(texto in ('Año *', 'Mes *', 'Día *') for texto in etiquetas)
        completar(dialogo, {'Fecha de publicación': '02/01/2020', 'Edición': 'Matutina', 'Número': '2'})
        assert servicios.connection.execute('SELECT count(*) FROM issues').fetchone()[0] == 1, 'No se admite un ejemplar sin ubicación.'
        boton_guardar = next(control for control in recorrer(dialogo) if isinstance(control, ctk.CTkButton) and control.cget('text') == 'Guardar ejemplar')
        assert boton_guardar.cget('state') == 'disabled'
        completar(dialogo, {'Estante': '22'})
        assert servicios.connection.execute('SELECT count(*) FROM issues').fetchone()[0] == 2
        aplicacion._record_form(issue_id=2)
        dialogo = next(control for control in aplicacion.winfo_children() if isinstance(control, ctk.CTkToplevel))
        assert next(control for control in recorrer(dialogo) if isinstance(control, EntradaFecha)).get() == '02/01/2020'
        completar(dialogo, {'Estante': '', 'Gaveta': ''})
        assert servicios.connection.execute('SELECT shelf FROM issues WHERE id=2').fetchone()[0] == '22'
        completar(dialogo, {'Gaveta': '3'})
        assert tuple(servicios.connection.execute('SELECT shelf, drawer FROM issues WHERE id=2').fetchone()) == ('', '3')
        from hemeroteca.ui.controles import EntradaFecha
        aplicacion._record_form(absent=True)
        ausencia_dialogo = next(control for control in aplicacion.winfo_children() if isinstance(control, ctk.CTkToplevel))
        calendarios = [control for control in recorrer(ausencia_dialogo) if isinstance(control, EntradaFecha)]
        assert len(calendarios) == 1
        selectores = [control for control in recorrer(ausencia_dialogo) if isinstance(control, ctk.CTkComboBox)]
        assert len(selectores) == 1, 'No deben repetirse año, mes y día fuera del calendario.'
        calendarios[0].set('03/02/2020')
        observacion = next(control for control in recorrer(ausencia_dialogo) if isinstance(control, ctk.CTkTextbox))
        observacion.insert('1.0', 'Sin circulación.\nObservación de varias líneas.')
        next(control for control in recorrer(ausencia_dialogo) if isinstance(control, ctk.CTkButton) and control.cget('text') == 'Guardar fecha').invoke()
        assert servicios.connection.execute('SELECT note FROM absent_dates WHERE year=2020 AND month=2 AND day=3').fetchone()[0] == 'Sin circulación.\nObservación de varias líneas.'
        usuario_previo = aplicacion.user['id']
        with patch.object(AccessService, 'estado_sesion', side_effect=ErrorConexion('Red temporalmente no disponible')):
            aplicacion._sync_session()
        assert aplicacion.user['id'] == usuario_previo
        for ventana in list(aplicacion.winfo_children()):
            if ventana.winfo_class() in ('Toplevel',):
                ventana.destroy()
        aplicacion._sync_session()
        aplicacion.show_login()
        aplicacion.user = dict(usuario)
        aplicacion._authenticated_version = usuario['password_version']
        aplicacion.show_shell()
        latidos = []
        def latir():
            """Registra que Tk procesa temporizadores durante una operación lenta."""
            latidos.append(time.monotonic())
            aplicacion.after(20, latir)
        aplicacion.after(20, latir)
        original = AuthService.needs_setup
        def lento(instancia):
            """Simula una operación de datos lenta sin manipular widgets."""
            time.sleep(.4)
            return original(instancia)
        with patch.object(AuthService, 'needs_setup', lento):
            assert aplicacion.services.auth.needs_setup() is False
        assert len(latidos) >= 5, latidos
        assert not errores, errores
        resultado = {'pantallas': visitadas, 'alta_y_edicion_desde_formulario': 'correctas', 'sesion_con_fallo_transitorio': 'conservada', 'latidos_durante_operacion_lenta': len(latidos), 'errores': errores}
        (Path(__file__).resolve().parent / 'RESULTADO_INTERFAZ.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(resultado, ensure_ascii=False))
    finally:
        esperar_interfaz(aplicacion)
        aplicacion._close()
