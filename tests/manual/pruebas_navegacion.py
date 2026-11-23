"""Verifica navegación fija y geometría de las ocho pantallas con datos sintéticos."""
from tests.manual.pruebas_ayudas import esperar_interfaz
import json
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import customtkinter as ctk


def recorrer(control):
    """Recorre widgets para comprobar visibilidad sin depender de coordenadas fijas."""
    yield control
    for hijo in control.winfo_children():
        yield from recorrer(hijo)


def principal():
    """Revisa todas las vistas y permite una inspección visual aislada opcional."""
    carpeta = Path(__file__).resolve().parent / '.pruebas_temporales'
    carpeta.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=carpeta, prefix='navegacion-') as temporal:
        os.environ['HEMEROTECA_DATOS'] = temporal
        os.environ['HEMEROTECA_DATA_DIR'] = temporal
        from hemeroteca.services.container import create_services
        from hemeroteca.config.settings import SECURITY_QUESTIONS, TITLES, REGIONAL, VIEWS
        from hemeroteca.ui.main_view import HemerotecaApp
        servicios = create_services(Path(temporal) / 'hemeroteca.db')
        servicios.auth.create_master('Prueba Navegación', 'V-123456', 'Prueba!2026', tuple(zip(SECURITY_QUESTIONS[:3], ('Uno', 'Dos', 'Tres'))))
        usuario = servicios.auth.authenticate('V-123456', 'Prueba!2026')
        for indice in range(45):
            servicios.periodicos.save_record(usuario, (TITLES[0], 'Regional' if TITLES[0] in REGIONAL else 'Nacional', 'Matutina', 2020, 1, 1, str(indice + 1), '1', '', 'Disponible'))
        for dia in range(2, 17):
            servicios.periodicos.save_record(usuario, (TITLES[0], 'Regional' if TITLES[0] in REGIONAL else 'Nacional', 2020, 1, dia, 'Sin circulación, prueba de navegación'), absent=True)
        app = HemerotecaApp(servicios)
        errores = []
        app.report_callback_exception = lambda tipo, error, traza: errores.append(str(error))
        resultados = []
        try:
            app.user = dict(usuario)
            app._authenticated_version = usuario['password_version']
            app.show_shell()
            for dimensiones in ('900x600', '1280x800'):
                app._paginas_recordadas = {}
                app.geometry(dimensiones)
                for vista in VIEWS:
                    app.navigate(vista)
                    esperar_interfaz(app)
                    for boton_menu in app.sidebar_buttons.values():
                        lienzo_menu = boton_menu.master._parent_canvas
                        assert boton_menu.winfo_rooty() >= lienzo_menu.winfo_rooty(), 'Menú oculto por arriba'
                        assert boton_menu.winfo_rooty() + boton_menu.winfo_height() <= lienzo_menu.winfo_rooty() + lienzo_menu.winfo_height(), 'Menú oculto por abajo'
                    barra = app.navegacion_resultados
                    botones = [control for control in recorrer(barra) if isinstance(control, ctk.CTkButton) and control.winfo_viewable()]
                    assert len([h for h in barra.winfo_children() if h.winfo_ismapped()]) == (0 if vista in VIEWS[6:] else 1), vista
                    if vista == VIEWS[1]:
                        pestañas = next(control for control in recorrer(app.content) if isinstance(control, ctk.CTkSegmentedButton))
                        for nombre, titulo_barra in (('Fechas sin publicación', 'Fechas sin publicación'), ('Ejemplares', 'Ejemplares')):
                            pestañas.set(nombre)
                            pestañas.cget('command')(nombre)
                            esperar_interfaz(app)
                            assert len([h for h in barra.winfo_children() if h.winfo_ismapped()]) == 1
                            assert [h for h in barra.winfo_children() if h.winfo_ismapped()][0]._titulo_resultados == titulo_barra
                            siguientes = [control for control in recorrer(barra) if isinstance(control, ctk.CTkButton) and control.winfo_viewable() and control.cget('text') == 'Siguiente']
                            siguientes[0].invoke()
                            esperar_interfaz(app)
                            assert any('Página 2' in control.cget('text') for control in recorrer(barra) if isinstance(control, ctk.CTkLabel))
                        pestañas.set('Fechas sin publicación')
                        pestañas.cget('command')('Fechas sin publicación')
                        esperar_interfaz(app)
                        assert any('Página 2' in control.cget('text') for control in recorrer(barra) if isinstance(control, ctk.CTkLabel)), 'La pestaña debe recordar su página'
                        pestañas.set('Ejemplares')
                        pestañas.cget('command')('Ejemplares')
                        esperar_interfaz(app)
                        botones = [control for control in recorrer(barra) if isinstance(control, ctk.CTkButton) and control.winfo_viewable()]
                    for posicion in (0, 1, .5):
                        app.content._parent_canvas.yview_moveto(posicion)
                        esperar_interfaz(app)
                        for boton in botones:
                            assert boton.winfo_viewable(), (vista, boton.cget('text'))
                            assert app.winfo_rootx() <= boton.winfo_rootx()
                            assert boton.winfo_rootx() + boton.winfo_width() <= app.winfo_rootx() + app.winfo_width(), (vista, dimensiones, boton.cget('text'), 'horizontal')
                            assert app.winfo_rooty() <= boton.winfo_rooty()
                            assert boton.winfo_rooty() + boton.winfo_height() <= app.winfo_rooty() + app.winfo_height(), (vista, dimensiones, 'vertical')
                    if vista == VIEWS[0]:
                        siguiente = next(boton for boton in botones if boton.cget('text') == 'Siguiente')
                        assert siguiente.cget('state') == 'normal'
                        siguiente.invoke()
                        esperar_interfaz(app)
                        assert any('Página 2' in control.cget('text') for control in recorrer(barra) if isinstance(control, ctk.CTkLabel))
                        next(boton for boton in botones if boton.cget('text') == 'Anterior').invoke()
                        next(boton for boton in botones if boton.cget('text') == 'Ir a filtros').invoke()
                        esperar_interfaz(app)
                        assert app.content._parent_canvas.yview()[0] == 0
                    resultados.append({'vista': vista, 'ventana': dimensiones, 'botones_fijos': len(botones), 'correcto': True})
            assert not errores, errores
            # Verifica también la paginación en memoria utilizada por Respaldos.
            app.navigate(VIEWS[7])
            esperar_interfaz(app)
            tarjeta = app._card(4)
            app._paginate(tarjeta, [(str(indice),) for indice in range(12)], [('dato', 'ARCHIVO', 300)], 'backups', page_size=5)
            esperar_interfaz(app)
            siguientes = [control for control in recorrer(app.navegacion_resultados) if isinstance(control, ctk.CTkButton) and control.winfo_viewable() and control.cget('text') == 'Siguiente']
            assert len(siguientes) == 1
            siguientes[0].invoke()
            esperar_interfaz(app)
            assert any('Página 2' in control.cget('text') for control in recorrer(app.navegacion_resultados) if isinstance(control, ctk.CTkLabel))
            tarjeta.destroy()
            esperar_interfaz(app)
            assert not app.navegacion_resultados.winfo_children(), 'No deben quedar barras de tablas destruidas.'
            (Path(__file__).parent / 'RESULTADO_NAVEGACION.json').write_text(json.dumps({'correcto': True, 'casos': resultados, 'errores': errores}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'correcto': True, 'pantallas_y_tamanos': len(resultados), 'errores': errores}), flush=True)
            if '--visual' in sys.argv:
                app.geometry('1000x640+10+10')
                app.navigate(VIEWS[1])
                app.title('Hemeroteca · Revisión visual QA aislada')
                app.mainloop()
        finally:
            try:
                existe = app.winfo_exists()
            except tk.TclError:
                existe = False
            if existe:
                for tarea in app.tk.call('after', 'info'):
                    app.after_cancel(tarea)
                app.destroy()
            if servicios.connection is not None:
                servicios.connection.close()


if __name__ == '__main__':
    principal()
