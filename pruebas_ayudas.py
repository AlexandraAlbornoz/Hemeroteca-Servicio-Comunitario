"""Sincronización de pruebas de GUI con la entrega asíncrona de resultados."""
import time


def esperar_interfaz(app, segundos=15):
    """Espera trabajo real pendiente y procesa eventos sin una demora fija por pantalla."""
    fin = time.monotonic() + segundos
    app.update()
    while (app.services._trabajos or getattr(app, '_navegacion_pendiente', None)) and time.monotonic() < fin:
        app.update()
        time.sleep(.01)
    assert not app.services._trabajos, 'Las lecturas de la interfaz no terminaron a tiempo'
    assert not getattr(app, '_navegacion_pendiente', None), 'La navegación no terminó a tiempo'
    app.update()
