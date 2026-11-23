"""Punto de entrada de Hemeroteca para Python 3.13."""

from hemeroteca.config.settings import DB_PATH
from hemeroteca.services.container import ApplicationServices, create_services as _create_services


def crear_servicios(path=DB_PATH) -> ApplicationServices:
    """Servicios locales para scripts que no necesitan interfaz ni red."""
    ruta = path
    return _create_services(ruta)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
create_services = crear_servicios


def principal():
    'Construye el gestor de red, programa respaldos, abre Tkinter y libera recursos al salir.'
    from hemeroteca.network.manager import NetworkManager
    from hemeroteca.ui.main_view import HemerotecaApp
    from hemeroteca.services.backup_service import BackupScheduler
    gestor = NetworkManager()
    programador = BackupScheduler(gestor.database, gestor.config_path)
    servicios = None
    aplicacion = None
    try:
        servicios = gestor.services()
        programador.start()
        aplicacion = HemerotecaApp(servicios)
        aplicacion.mainloop()
    finally:
        programador.close()
        if aplicacion is not None:
            aplicacion.services.close()
        elif servicios is not None:
            servicios.close()
        gestor.close()
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
main = principal


if __name__ == '__main__':
    main()
