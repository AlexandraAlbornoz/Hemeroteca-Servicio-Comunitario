"""Ejecuta las verificaciones de entrega y registra evidencia reproducible."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def principal():
    """Comprueba sintaxis, documentación, pruebas de negocio, interfaz y red."""
    raiz = Path(__file__).resolve().parent
    faltantes = []
    archivos = []
    for archivo in raiz.rglob('*.py'):
        if any(parte.startswith('.') or parte == '_internal' for parte in archivo.relative_to(raiz).parts):
            continue
        texto = archivo.read_text(encoding='utf-8-sig')
        arbol = ast.parse(texto, filename=str(archivo))
        compile(texto, str(archivo), 'exec')
        archivos.append(str(archivo.relative_to(raiz)))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not ast.get_docstring(nodo):
                faltantes.append(f'{archivo.relative_to(raiz)}:{nodo.lineno}:{nodo.name}')
    informe = {'python': sys.version.split()[0], 'archivos_compilados': len(archivos), 'sin_documentacion': faltantes, 'verificaciones': {}}
    entorno = dict(os.environ, PYTHONIOENCODING='utf-8')
    pruebas = {'documentacion': ['documentar_codigo.py'],
              'unitarias': ['-m', 'unittest', 'discover', '-s', 'tests', '-v'],
              'interfaz': ['pruebas_interfaz.py'], 'edicion_registro': ['pruebas_edicion_registro.py'],
              'recuperacion_interfaz': ['pruebas_recuperacion_interfaz.py'], 'integracion': ['pruebas_integracion.py'],
              'navegacion': ['pruebas_navegacion.py'], 'guardar_ejemplar': ['pruebas_guardar_ejemplar.py'],
              'navegacion_pendiente': ['pruebas_navegacion_pendiente.py']}
    for nombre, argumentos in pruebas.items():
        print('Verificando:', nombre, flush=True)
        resultado = subprocess.run([sys.executable, '-B', *argumentos], cwd=raiz, env=entorno, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
        salida = resultado.stdout + resultado.stderr
        (raiz / f'VERIFICACION_{nombre.upper()}.txt').write_text(salida, encoding='utf-8')
        conteo = re.search(r'Ran (\d+) tests', salida)
        informe['verificaciones'][nombre] = {'correcto': resultado.returncode == 0, 'codigo_salida': resultado.returncode}
        if conteo:
            informe['verificaciones'][nombre]['pruebas'] = int(conteo.group(1))
        print(nombre, 'OK' if resultado.returncode == 0 else 'ERROR', flush=True)
    informe['correcto'] = not faltantes and all(prueba['correcto'] for prueba in informe['verificaciones'].values())
    (raiz / 'VERIFICACION.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(informe, ensure_ascii=False), flush=True)
    return 0 if informe['correcto'] else 1


if __name__ == '__main__':
    raise SystemExit(principal())
