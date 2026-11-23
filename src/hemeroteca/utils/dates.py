"""Presentación y validación de fechas del sistema."""

from datetime import datetime, timedelta, timezone

# Los eventos anteriores no guardaban zona: se interpretan como hora de Caracas
# UTC-04:00. Se conserva su texto original; la política no depende del Windows del lector.
ZONA_AUDITORIA_LOCAL = timezone(timedelta(hours=-4), 'America/Caracas')


def validar_anio_publicacion(anio):
    """Aplica el intervalo inclusivo de la colección, igual para todos los periódicos."""
    if type(anio) is not int or not 1970 <= anio <= 2100:
        raise ValueError('Selecciona una fecha entre 1970 y 2100, ambos incluidos.')


def mostrar_fecha(value):
    """Presentación legible sin modificar el formato almacenado."""
    valor = value
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m/%Y · %H:%M")
    except (ValueError, TypeError):
        return valor or "—"
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
display_date = mostrar_fecha


def interpretar_fecha_filtro(value):
    """Una fecha vacía no limita la búsqueda; las fechas escritas deben ser válidas."""
    valor = value
    valor = valor.strip()
    if not valor:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            fecha = datetime.strptime(valor, pattern).date()
            if fecha.year < 1970:
                raise ValueError('Selecciona una fecha desde 1970.')
            return fecha
        except ValueError:
            continue
    raise ValueError("Escribe una fecha válida en formato dd/mm/aaaa.")
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
parse_filter_date = interpretar_fecha_filtro


def interpretar_instante_auditoria(value):
    """Lee el formato actual del historial y las fechas ISO de registros anteriores."""
    valor = value
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(valor, pattern)
        except (ValueError, TypeError):
            continue
    try:
        return datetime.fromisoformat(valor)
    except (ValueError, TypeError):
        return None
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
audit_timestamp = interpretar_instante_auditoria


def instante_auditoria_utc(valor):
    """Convierte eventos ISO o antiguos a UTC sin reescribir el historial existente."""
    instante = audit_timestamp(valor)
    if instante is None:
        return None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZONA_AUDITORIA_LOCAL)
    return instante.astimezone(timezone.utc)


def instante_auditoria_local(valor):
    """Presenta y filtra los eventos por la misma hora local visible de Caracas."""
    instante = instante_auditoria_utc(valor)
    return instante.astimezone(ZONA_AUDITORIA_LOCAL) if instante else None
