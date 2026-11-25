"""Preparación de datos de formularios sin widgets ni escrituras en la base."""
from config.settings import ISSUE_STATUSES, REGIONAL, TITLES
from utils.dates import parse_filter_date, validar_anio_publicacion
from utils.validaciones import validar_edicion, validar_numero


def preparar_ejemplar(campos):
    """Valida valores visibles y devuelve la tupla que recibe save_record.

    La habilitación del botón y el guardado usan esta misma regla. Cada rechazo
    explica el campo que necesita corrección. Los servicios vuelven a validar
    los datos y permisos al escribir, también para llamadas remotas.
    """
    titulo = campos['Periódico']
    if titulo not in TITLES:
        raise ValueError('Periódico: selecciona una opción de la lista.')
    try:
        fecha = parse_filter_date(campos['Fecha de publicación'])
    except ValueError as excepcion:
        raise ValueError('Fecha de publicación: selecciona una fecha desde 1970 con el calendario.') from excepcion
    if fecha is None:
        raise ValueError('Fecha de publicación: selecciona una fecha con el calendario.')
    tipo = 'Regional' if titulo in REGIONAL else 'Nacional'
    validar_anio_publicacion(fecha.year)
    edicion = validar_edicion(campos['Edición'].strip())
    numero = validar_numero(campos['Número'].strip(), 'Número de edición')
    estante = validar_numero(campos['Estante'].strip(), 'Estante', opcional=True)
    gaveta = validar_numero(campos['Gaveta'].strip(), 'Gaveta', opcional=True)
    if not estante and not gaveta:
        raise ValueError('Ubicación: completa Estante, Gaveta o ambos con números.')
    estado = campos['Estado']
    if estado not in ISSUE_STATUSES:
        raise ValueError('Estado: selecciona una opción de la lista.')
    return (titulo, tipo, edicion, fecha.year, fecha.month, fecha.day, numero, estante, gaveta, estado)
