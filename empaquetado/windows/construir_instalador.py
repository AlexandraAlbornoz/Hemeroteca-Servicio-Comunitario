"""Empaqueta los asistentes usando herramientas ya disponibles en Windows."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def huella(ruta):
    """Calcula la huella de cada archivo distribuido sin incorporar datos privados."""
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def copiar_recursos(origen, destino):
    """Añade los scripts del asistente y su identidad visual al autoextraíble."""
    destino.mkdir(parents=True, exist_ok=True)
    for nombre in ('operaciones_instalacion.ps1', 'limpiar_desinstalador.ps1', 'firewall.ps1'):
        texto = (origen / nombre).read_text(encoding='utf-8-sig')
        (destino / nombre).write_bytes(texto.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8-sig'))
    (destino / 'recursos').mkdir(exist_ok=True)
    for nombre in ('hemeroteca_periodico.ico', 'asistente_lateral.bmp'):
        shutil.copy2(origen.parents[1] / 'assets' / nombre, destino / 'recursos' / nombre)


def crear_asistente(carpeta, salida, modo, trabajo, raiz):
    """Compila un lanzador de Windows con su paquete incorporado y sin descargas."""
    archivo = trabajo / (modo + '.zip')
    with zipfile.ZipFile(archivo, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as paquete:
        for ruta in sorted(carpeta.rglob('*')):
            if ruta.is_file():
                paquete.write(ruta, ruta.relative_to(carpeta).as_posix())
    configuracion = trabajo / (modo + '-modo.txt')
    configuracion.write_text(modo, encoding='utf-8')
    compilador = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(compilador), '/nologo', '/target:winexe', '/platform:anycpu',
        '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
        '/reference:System.Web.Extensions.dll', '/reference:System.IO.Compression.dll',
        '/win32icon:' + str(raiz / 'assets/hemeroteca_periodico.ico'),
        '/resource:' + str(archivo) + ',paquete.zip',
        '/resource:' + str(configuracion) + ',modo.txt',
        '/out:' + str(salida), str(raiz / 'empaquetado/windows/lanzador_asistente.cs')], check=True)


def principal():
    """Construye un instalador sin bases, claves, sesiones ni dependencias externas."""
    origen = Path(__file__).resolve().parent
    raiz = origen.parents[1]
    espacio = raiz.parent
    trabajo = raiz / '.build/asistentes'
    trabajo.mkdir(parents=True, exist_ok=True)
    programa = raiz / '.build/dist/Hemeroteca'
    if not (programa / 'Hemeroteca.exe').is_file():
        raise RuntimeError('Primero construye el programa autónomo con PyInstaller.')
    for carpeta in ('assets', 'docs'):
        shutil.copytree(raiz / carpeta, programa / carpeta, dirs_exist_ok=True)
    for nombre in ('backup_worker.py', 'Programar_Respaldos_Windows.ps1', 'Configurar_Red_Windows.ps1', 'Configurar_Red_Windows.cmd', 'LEEME_HEMEROTECA.txt', 'LICENSE', 'VERSION.json'):
        shutil.copy2(raiz / nombre, programa / nombre)
    shutil.copy2(origen / "firewall.ps1", programa / "firewall.ps1")
    # PowerShell 5.1 necesita BOM para interpretar correctamente las tildes.
    for script in programa.glob('*.ps1'):
        script.write_bytes(script.read_text(encoding='utf-8-sig').encode('utf-8-sig'))
    # Distribuye las licencias de las dependencias incluidas, además de la del programa.
    ruedas = espacio / 'herramientas_empaquetado/ruedas'
    for rueda in ruedas.glob('*.whl'):
        with zipfile.ZipFile(rueda) as comprimido:
            for nombre in comprimido.namelist():
                if not nombre.endswith('/') and ('/licenses/' in nombre or Path(nombre).name.upper().startswith(('LICENSE', 'COPYING'))):
                    destino = programa / 'licencias' / rueda.stem / nombre
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(comprimido.read(nombre))
    desinstalacion = trabajo / 'desinstalacion'
    copiar_recursos(origen, desinstalacion)
    crear_asistente(desinstalacion, programa / 'Desinstalar_Hemeroteca.exe', 'Desinstalar', trabajo, raiz)
    prohibidos = [archivo for archivo in programa.rglob('*') if archivo.is_file() and (
        archivo.suffix.lower() in ('.db', '.sqlite', '.sqlite3', '.hmbackup', '.key')
        or archivo.name.lower() in ('ubicacion_datos.json', 'network.json', 'backup-settings.json')
        or 'datos_prueba_vscode' in archivo.parts or '.vscode' in archivo.parts)]
    if prohibidos:
        raise RuntimeError('Se detectaron datos privados en el paquete: ' + str(prohibidos))
    contenido = [{'ruta': archivo.relative_to(programa).as_posix(), 'sha256': huella(archivo)}
                 for archivo in sorted(programa.rglob('*')) if archivo.is_file() and archivo.name != 'contenido.json']
    (programa / 'contenido.json').write_text(json.dumps({'version': '2.4.2', 'archivos': contenido}, ensure_ascii=False, indent=2), encoding='utf-8')
    instalacion = trabajo / 'instalacion'
    copiar_recursos(origen, instalacion)
    shutil.copytree(programa, instalacion / 'programa', dirs_exist_ok=True)
    salida = raiz / 'Instalar_Hemeroteca_2.4.2_Solo_Consulta.exe'
    crear_asistente(instalacion, salida, 'Instalar', trabajo, raiz)
    informe = {'version': '2.4.2', 'archivo': salida.name, 'sha256': huella(salida),
               'tamano_mib': round(salida.stat().st_size / 1024**2, 2), 'archivos_programa': len(contenido),
               'datos_personales_incluidos': False, 'python_incluido': True,
               'compresor': 'ZIP incorporado'}
    (raiz / 'INSTALADOR.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    salida.with_suffix('.exe.sha256').write_text(informe['sha256'] + '  ' + salida.name + '\n', encoding='ascii')
    print(json.dumps(informe, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    principal()
