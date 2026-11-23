"""Carga idempotente de 100 ejemplares sintéticos en la base aislada.

Ejecutar desde esta carpeta: python -m scripts.seed_hemeroteca
No crea usuarios ni toca la base instalada de Hemeroteca.
"""

from datetime import date, datetime, timedelta, timezone

from hemeroteca.config.settings import DB_PATH, REGIONAL, TITLES
from hemeroteca.database.connection import conectar_base_datos


MARCA = 'Datos de prueba'
SECCIONES = ('Información', 'Cultura', 'Deportes', 'Economía', 'Opinión')
CONSERVACION = ('Excelente', 'Buena', 'Regular', 'Requiere restauración')
ESTADOS = ('Disponible', 'En archivo', 'En sala', 'En restauración')


def sembrar_ejemplares():
    """Inserta solo los ejemplares sintéticos ausentes y devuelve su total."""
    conexion = conectar_base_datos(DB_PATH)
    try:
        with conexion:
            for indice in range(100):
                publicacion = date(2015, 1, 5) + timedelta(days=37 * indice)
                registro = datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(minutes=indice)
                titulo = TITLES[indice % len(TITLES)]
                conexion.execute('''INSERT OR IGNORE INTO issues
                    (title, kind, edition, year, month, day, number, shelf, drawer,
                     status, created_by, created_at, section, page_count, physical_condition)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (titulo, 'Regional' if titulo in REGIONAL else 'Nacional',
                     ('Matutina', 'Vespertina', 'Especial')[indice % 3],
                     publicacion.year, publicacion.month, publicacion.day,
                     str(1001 + indice), str(1 + indice % 12),
                     str(1 + indice % 8), ESTADOS[indice % len(ESTADOS)],
                     MARCA, registro.isoformat(timespec='seconds'),
                     SECCIONES[indice % len(SECCIONES)], 8 + 4 * (indice % 7),
                     CONSERVACION[indice % len(CONSERVACION)]))
        return conexion.execute('SELECT count(*) FROM issues WHERE created_by=?', (MARCA,)).fetchone()[0]
    finally:
        conexion.close()


if __name__ == '__main__':
    cantidad = sembrar_ejemplares()
    print(f'{cantidad} ejemplares sintéticos en {DB_PATH}')
    print(f'{(cantidad + 4) // 5} páginas de cinco registros')
