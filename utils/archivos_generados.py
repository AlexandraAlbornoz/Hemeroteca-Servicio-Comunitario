from hashlib import file_digest, sha256
from pathlib import Path

from utils.local_secrets import write_json


def registrar_archivo(ruta, datos):
    """Identifica la salida para que la desinstalación pueda borrar esa copia exacta."""
    archivo = Path(ruta).resolve(strict=True)
    datos = Path(datos).resolve()
    if archivo.is_relative_to(datos):
        return
    with archivo.open('rb') as flujo:
        huella = file_digest(flujo, 'sha256').hexdigest()
    identificador = sha256(str(archivo).casefold().encode('utf-8')).hexdigest()
    write_json(datos / 'archivos-generados' / (identificador + '.json'),
               {'ruta': str(archivo), 'sha256': huella})
