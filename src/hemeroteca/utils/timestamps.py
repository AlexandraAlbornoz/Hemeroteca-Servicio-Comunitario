"""Fechas de registro en UTC para filtrar igual desde cualquier computadora."""

from datetime import datetime, timezone


def ahora_utc():
    """Devuelve el instante actual en formato ISO 8601 UTC con precisión de segundos."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
utc_now = ahora_utc
