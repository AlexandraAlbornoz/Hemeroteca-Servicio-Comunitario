"""Paginación SQL parametrizada compartida por los listados de administración."""
from functools import lru_cache


def validar_paginacion(pagina, tamano, mensaje='La página y el tamaño de página no son válidos.'):
    """Rechaza booleanos, páginas negativas y tamaños fuera del intervalo 1–100."""
    if type(pagina) is not int or pagina < 1 or type(tamano) is not int or not 1 <= tamano <= 100:
        raise ValueError(mensaje)


def paginar(conexion, consulta, parametros=(), *, pagina=1, tamano=8, orden='id DESC', consulta_conteo=None):
    """Cuenta coincidencias y lee solo una página, ajustándola al último resultado.

    Consulta y orden son SQL interno, nunca texto recibido del usuario. Los
    valores se enlazan mediante parámetros. Una consulta de conteo opcional
    evita ordenar al contar; debe conservar los mismos filtros y límites.
    Devuelve items, total, pages, page y page_size, también cuando no hay filas.
    """
    validar_paginacion(pagina, tamano)
    parametros = tuple(parametros)
    total = conexion.execute('SELECT count(*) FROM (' + (consulta_conteo if consulta_conteo is not None else consulta) + ')', parametros).fetchone()[0]
    paginas = max(1, (total + tamano - 1) // tamano)
    pagina = min(pagina, paginas)
    filas = conexion.execute('SELECT * FROM (' + consulta + ') ORDER BY ' + orden + ' LIMIT ? OFFSET ?',
                            tuple(parametros) + (tamano, (pagina - 1) * tamano)).fetchall()
    return {'items': filas, 'total': total, 'pages': paginas, 'page': pagina, 'page_size': tamano}


def plegar_texto(valor):
    """Mantiene las comparaciones Unicode del filtrado anterior en Python."""
    return str(valor or '').casefold()


@lru_cache(maxsize=8192)
def instante_evento(valor):
    """Normaliza a hora local y reutiliza fechas repetidas sin cargar el historial."""
    from utils.dates import instante_auditoria_local
    instante = instante_auditoria_local(valor)
    return instante.strftime('%Y-%m-%d %H:%M:%S') if instante else None


@lru_cache(maxsize=8192)
def instante_evento_utc(valor):
    """Compara ventanas de tiempo en UTC y conserva caché acotada por valor."""
    from utils.dates import instante_auditoria_utc
    instante = instante_auditoria_utc(valor)
    return instante.strftime('%Y-%m-%d %H:%M:%S') if instante else None
