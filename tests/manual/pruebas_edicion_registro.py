"""Comprueba la corrección de datos antes de Continuar en los tres registros."""
from tests.manual.pruebas_ayudas import esperar_interfaz
import json
import os
from pathlib import Path
import tempfile


def principal():
    """Prueba clic, reemplazo y borrado con controles reales y cuentas artificiales."""
    raiz = Path(__file__).resolve().parent
    temporales = raiz / '.pruebas_temporales'
    temporales.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporales, prefix='edicion-registro-') as directorio:
        os.environ['HEMEROTECA_DATOS'] = directorio
        from hemeroteca.config.settings import ROLES, SECURITY_QUESTIONS
        from hemeroteca.services.container import create_services
        from hemeroteca.ui.main_view import HemerotecaApp
        servicios = create_services(Path(directorio) / 'prueba.db')
        aplicacion = HemerotecaApp(servicios)
        errores = []
        aplicacion.report_callback_exception = lambda tipo, error, traza: errores.append(str(error))

        def corregir(campo, inicial, final, *, texto=False):
            """Vuelve por clic al campo lleno y corrige usando Ctrl+A y Retroceso."""
            campo.delete(0, 'end')
            campo.insert(0, inicial)
            aplicacion.reg_confirm.focus_force()
            aplicacion.update()
            fondo = campo._entry if texto else campo._canvas
            x, y = (fondo.winfo_width() // 2, fondo.winfo_height() // 2) if texto else (12, 3)
            opciones = dict(x=x, y=y, rootx=fondo.winfo_rootx() + x, rooty=fondo.winfo_rooty() + y)
            fondo.event_generate('<ButtonPress-1>', **opciones)
            fondo.event_generate('<ButtonRelease-1>', **opciones)
            aplicacion.update()
            assert aplicacion.focus_get() == campo._entry
            campo._entry.event_generate('<Control-a>')
            for letra in final:
                campo._entry.event_generate('<KeyPress>', keysym='numbersign' if letra == '#' else letra)
            aplicacion.update()
            assert campo.get() == final, (campo.get(), final)
            campo._entry.event_generate('<BackSpace>')
            aplicacion.update()
            assert campo.get() == final[:-1]
            campo._entry.event_generate('<KeyPress>', keysym=final[-1])
            aplicacion.update()
            assert campo.get() == final

        perfiles = []
        try:
            for indice, perfil in enumerate(ROLES):
                if indice == 1:
                    preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
                    servicios.auth.create_master('Responsable Ficticio', 'V-98765432', 'Prueba#2026', preguntas)
                aplicacion.show_login(True)
                if indice == 0:
                    assert aplicacion._setup_mode
                else:
                    aplicacion.reg_role.set(perfil)
                    assert not aplicacion._setup_mode
                corregir(aplicacion.reg_name[1], 'Erroneo', 'Corregido')
                corregir(aplicacion.reg_lastname[1], 'Erroneo', 'Apellido')
                corregir(aplicacion.login_identity.numero, '12345678', '87654321')
                corregir(aplicacion.login_password, 'Erronea#2026', 'Valida#2026')
                corregir(aplicacion.login_password, 'Erronea#2026', 'Valida#2026', texto=True)
                corregir(aplicacion.reg_confirm, 'Erronea#2026', 'Valida#2026')
                corregir(aplicacion.reg_confirm, 'Erronea#2026', 'Valida#2026', texto=True)
                aplicacion.reg_name[1]._entry.event_generate('<Tab>')
                aplicacion.update()
                assert not errores, errores
                perfiles.append(perfil)
            resultado = {'perfiles': perfiles, 'nombres_apellidos_editables': True,
                         'cedula_editable_con_validacion': True, 'contrasenas_editables': True,
                         'clic_en_area_completa': True, 'seleccion_y_reemplazo': True,
                         'retroceso': True, 'errores': errores}
            (raiz / 'RESULTADO_EDICION_REGISTRO.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(resultado, ensure_ascii=False))
        finally:
            esperar_interfaz(aplicacion)
            aplicacion._close()


if __name__ == '__main__':
    principal()
