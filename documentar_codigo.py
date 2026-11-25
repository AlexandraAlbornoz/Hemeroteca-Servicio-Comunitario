"""Genera una referencia navegable del código propio sin importar ni ejecutar módulos."""
import ast
from html import escape
import json
from pathlib import Path


def declaraciones(nodo, prefijo=''):
    """Enumera clases y funciones, incluidas las anidadas, con nombres completos."""
    for hijo in ast.iter_child_nodes(nodo):
        nombre = prefijo
        if isinstance(hijo, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            nombre = (prefijo + '.' if prefijo else '') + hijo.name
            yield hijo, nombre
        yield from declaraciones(hijo, nombre)


def descripcion_generica(texto):
    """Detecta las plantillas vacías que no explicaban la responsabilidad del código."""
    return texto.startswith(('Agrupa las operaciones y el estado de', 'Inicializa las dependencias y el estado que necesita')) or (
        texto.startswith('Gestiona ') and 'en el módulo de' in texto) or (
        texto.startswith('Prepara ') and 'actualiza sus controles desde el hilo de Tkinter' in texto)


def principal():
    """Comprueba cobertura documental y genera HTML buscable y un inventario JSON."""
    raiz = Path(__file__).resolve().parent
    modulos = []
    faltantes = []
    cantidad = 0
    for archivo in sorted(raiz.rglob('*.py')):
        relativa = archivo.relative_to(raiz)
        if any(parte.startswith('.') or parte == '_internal' for parte in relativa.parts):
            continue
        arbol = ast.parse(archivo.read_text(encoding='utf-8-sig'))
        elementos = []
        for nodo, nombre in declaraciones(arbol):
            documento = ast.get_docstring(nodo) or ''
            if not documento or descripcion_generica(documento):
                faltantes.append(f'{relativa.as_posix()}:{nodo.lineno}:{nombre}')
            firma = nombre + ('(' + ast.unparse(nodo.args) + ')' if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) else '')
            elementos.append({'nombre':nombre, 'firma':firma, 'linea':nodo.lineno,
                              'tipo':'Clase' if isinstance(nodo,ast.ClassDef) else 'Función', 'descripcion':documento})
        cantidad += len(elementos)
        modulos.append({'archivo':relativa.as_posix(), 'descripcion':ast.get_docstring(arbol) or '', 'elementos':elementos})
    informe = {'correcto':not faltantes, 'modulos':len(modulos), 'declaraciones':cantidad,
               'documentadas':cantidad-len(faltantes), 'pendientes':faltantes}
    (raiz/'DOCUMENTACION.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
    if faltantes:
        raise ValueError('Documentación incompleta: ' + ', '.join(faltantes))
    secciones = []
    for modulo in modulos:
        contenido = ''.join('<article><h3>'+escape(elemento['tipo']+' · '+elemento['nombre'])+'</h3><code>'+escape(elemento['firma'])+'</code><p class="ubicacion">Línea '+str(elemento['linea'])+'</p><p>'+escape(elemento['descripcion']).replace('\n','<br>')+'</p></article>' for elemento in modulo['elementos'])
        secciones.append('<details class="modulo"><summary>'+escape(modulo['archivo'])+' ('+str(len(modulo['elementos']))+')</summary><p>'+escape(modulo['descripcion'])+'</p>'+contenido+'</details>')
    pagina = '''<!doctype html><html lang="es"><meta charset="utf-8"><title>Hemeroteca · Referencia del código</title>
<style>body{font:16px/1.6 system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#20304c;background:#f4f7fc}h1,h2{color:#284b9b}input{width:95%;padding:14px;font:inherit}details{background:white;margin:14px 0;padding:16px;border-radius:8px}summary{cursor:pointer;font-weight:700}article{border-top:1px solid #dde5f0;padding:12px 0}code{white-space:pre-wrap;overflow-wrap:anywhere}.ubicacion{color:#64748b;font-size:13px}</style>
<h1>Hemeroteca · Referencia del código</h1>
<p>Documentación del código propio: clases, métodos, funciones y callbacks. Excluye dependencias de terceros y paquetes compilados. Cada entrada procede del docstring junto a su implementación.</p>
<h2>Cómo está organizado</h2><ul>
<li><b>ui:</b> vistas Tkinter, componentes y coordinador de servicios. Los widgets se manipulan en el hilo gráfico; las operaciones de datos se ejecutan en el trabajador.</li>
<li><b>services:</b> reglas de negocio y autorización. ServicioConAcceso comparte dependencias; paginacion centraliza conteo y lectura limitada; cada operación conserva sus controles de seguridad.</li>
<li><b>database:</b> esquema, conexiones, transacciones y exclusión de mantenimiento. Los servicios nunca comparten conexiones SQLite entre hilos.</li>
<li><b>network:</b> cliente, servidor HTTPS, identidad de equipo y emparejamiento. El servidor deriva la identidad de sesión del token, no de argumentos del cliente.</li>
<li><b>utils y config:</b> validación, fechas, criptografía, PDF, iconos y constantes comunes.</li>
<li><b>tests y pruebas:</b> regresiones unitarias, interfaz y red sobre datos sintéticos.</li></ul>
<h2>Reglas para mantener la reutilización</h2><p>Reutiliza fábricas de campos, limpieza de contenedores y estilo de tablas. Conserva alias y firmas anteriores por compatibilidad. No sustituyas verificaciones transaccionales por permisos almacenados en caché: deben detectar revocaciones y cambios concurrentes. Las consultas paginadas deben preservar filtros, orden y límites especiales como los últimos cinco registros.</p>
<p>Para regenerar esta referencia, ejecuta <code>python -B documentar_codigo.py</code> desde la carpeta del programa. El generador rechaza funciones sin explicación o con plantillas genéricas y no abre la base de datos.</p>
<label for="buscar">Buscar módulo, función o explicación</label><input id="buscar" type="search" placeholder="Ejemplo: paginar, recuperación, permisos">
''' + ''.join(secciones) + '''<script>document.querySelector('#buscar').addEventListener('input',function(){const texto=this.value.toLocaleLowerCase();document.querySelectorAll('.modulo').forEach(function(modulo){const coincide=modulo.textContent.toLocaleLowerCase().includes(texto);modulo.hidden=!coincide;modulo.open=Boolean(texto)&&coincide;});});</script></html>'''
    (raiz/'docs/REFERENCIA_CODIGO.html').write_text(pagina,encoding='utf-8')
    print(json.dumps(informe,ensure_ascii=False))


if __name__=='__main__':
    principal()
