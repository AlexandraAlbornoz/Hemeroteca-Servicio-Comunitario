"""Comprueba recursos del ejecutable autónomo sin abrir la base de la hemeroteca."""
import json
from pathlib import Path
import sys


def verificar():
    """Ejercita SQLite, icono, Tkinter y PDF con datos en memoria y escribe el resultado."""
    import tkinter as tk
    from config.settings import ASSETS
    from services.container import create_services
    from utils.iconos import aplicar_icono
    from utils.pdf_reports import build_report
    from services.recovery_service import RegistrationResult
    from ui.tareas import materializar
    posicion = sys.argv.index('--verificar-instalacion')
    destino = Path(sys.argv[posicion + 1])
    ventana = None
    servicios = None
    try:
        servicios = create_services(':memory:')
        ventana = tk.Tk()
        ventana.withdraw()
        aplicar_icono(ventana)
        ventana.update_idletasks()
        pdf = build_report({'scope': 'issues', 'generated_at': 'Prueba de instalación', 'generated_by': 'Verificación local',
                            'filters': {}, 'sections': [{'type': 'issues', 'title': 'Prueba', 'rows': []}]})
        pdf_rango = build_report({'scope': 'issues', 'generated_at': 'Prueba de instalación', 'generated_by': 'Verificación local',
            'filters': {'desde': '2020-01-01', 'hasta': '2020-12-31'},
            'sections': [{'type': 'issues', 'title': 'Prueba de rango', 'rows': []}]})
        from services.paginacion import instante_evento_utc
        resultado = {'correcto': True, 'autonomo': bool(getattr(sys, 'frozen', False)),
                     'sqlite': servicios.connection.execute('PRAGMA integrity_check').fetchone()[0],
                     'icono': (ASSETS / 'hemeroteca_periodico.ico').exists(), 'tkinter': True, 'pdf': pdf.startswith(b'%PDF-'),
                     'recuperacion_preguntas': callable(getattr(servicios.auth, 'autenticar_con_preguntas', None)),
                     'retorno_codigo': isinstance(materializar(RegistrationResult(1, 'CODIGO-DE-PRUEBA')), RegistrationResult),
                     'pdf_rango': pdf_rango.startswith(b'%PDF-'),
                     'fechas_utc': instante_evento_utc('28/10/2026 13:00:00') == '2026-10-28 17:00:00'}
        resultado['correcto'] = all((resultado['sqlite'] == 'ok', resultado['icono'], resultado['pdf'], resultado['recuperacion_preguntas'], resultado['retorno_codigo'], resultado['pdf_rango'], resultado['fechas_utc']))
        destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0 if resultado['correcto'] else 1
    except Exception as error:
        destino.write_text(json.dumps({'correcto': False, 'error': str(error)}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 1
    finally:
        if ventana is not None:
            ventana.destroy()
        if servicios is not None:
            servicios.close()
