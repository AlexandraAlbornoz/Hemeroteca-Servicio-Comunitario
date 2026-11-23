"""Acceso compartido entre operaciones y exclusivo durante mantenimiento."""
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_registro = threading.Lock()
_barreras = {}
_adquiridos = threading.local()


class BarreraLecturaEscritura:
    """Coordina hilos y da prioridad al mantenimiento pendiente."""

    def __init__(self):
        """Inicializa los contadores protegidos por una condición."""
        self.condicion = threading.Condition()
        self.lectores = 0
        self.escritor = False
        self.esperando = 0

    def adquirir(self, exclusiva, limite):
        """Espera el modo solicitado hasta alcanzar el plazo monotónico."""
        with self.condicion:
            if exclusiva:
                self.esperando += 1
            try:
                while self.escritor or (self.lectores if exclusiva else self.esperando):
                    restante = limite - time.monotonic()
                    if restante <= 0:
                        raise ValueError('La base está ocupada con mantenimiento. Inténtalo de nuevo.')
                    self.condicion.wait(restante)
                if exclusiva:
                    self.escritor = True
                else:
                    self.lectores += 1
            finally:
                if exclusiva:
                    self.esperando -= 1
                    self.condicion.notify_all()

    def liberar(self, exclusiva):
        """Devuelve el permiso y despierta a los participantes pendientes."""
        with self.condicion:
            if exclusiva:
                self.escritor = False
            else:
                self.lectores -= 1
            self.condicion.notify_all()


def bloquear_archivo(archivo, exclusiva):
    """Intenta bloquear un byte sin esperar y devuelve su contexto nativo."""
    if os.name != 'nt':
        import fcntl
        fcntl.flock(archivo.fileno(), (fcntl.LOCK_EX if exclusiva else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        return None
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Solapamiento(ctypes.Structure):
        """Representa OVERLAPPED con alineación de punteros Win32/Win64."""
        _fields_ = [('interno', ctypes.c_size_t), ('interno_alto', ctypes.c_size_t),
                    ('desplazamiento', wintypes.DWORD), ('desplazamiento_alto', wintypes.DWORD),
                    ('evento', wintypes.HANDLE)]

    sistema = ctypes.WinDLL('kernel32', use_last_error=True)
    sistema.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Solapamiento)]
    sistema.LockFileEx.restype = wintypes.BOOL
    solapamiento = Solapamiento()
    descriptor = msvcrt.get_osfhandle(archivo.fileno())
    if not sistema.LockFileEx(descriptor, 1 | (2 if exclusiva else 0), 0, 1, 0, ctypes.byref(solapamiento)):
        raise ctypes.WinError(ctypes.get_last_error())
    return sistema, descriptor, solapamiento


def liberar_archivo(archivo, bloqueo):
    """Libera el mismo rango sin modificar el archivo de la base."""
    if os.name != 'nt':
        import fcntl
        fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
        return
    import ctypes
    from ctypes import wintypes
    sistema, descriptor, solapamiento = bloqueo
    sistema.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.DWORD, ctypes.POINTER(type(solapamiento))]
    sistema.UnlockFileEx.restype = wintypes.BOOL
    if not sistema.UnlockFileEx(descriptor, 0, 1, 0, ctypes.byref(solapamiento)):
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def proteger_base_datos(database, timeout=45, *, exclusive=True):
    """Protege operaciones; conserva exclusividad para llamadores anteriores."""
    base_datos = database
    tiempo_espera = timeout
    clave = os.path.normcase(str(Path(base_datos).resolve()))
    adquiridos = getattr(_adquiridos, 'rutas', None)
    if adquiridos is None:
        adquiridos = _adquiridos.rutas = {}
    if clave in adquiridos:
        if exclusive and not adquiridos[clave]:
            raise RuntimeError('El mantenimiento debe solicitar exclusividad al iniciar la operación.')
        yield
        return
    with _registro:
        barrera = _barreras.setdefault(clave, BarreraLecturaEscritura())
    limite = time.monotonic() + tiempo_espera
    barrera.adquirir(exclusive, limite)
    archivo = None
    bloqueado = False
    try:
        ruta = Path(clave + '.maintenance.lock')
        ruta.parent.mkdir(parents=True, exist_ok=True)
        archivo = ruta.open('a+b')
        while True:
            try:
                bloqueo = bloquear_archivo(archivo, exclusive)
                bloqueado = True
                break
            except OSError:
                if time.monotonic() >= limite:
                    raise ValueError('Otro proceso mantiene la base ocupada. Inténtalo de nuevo.')
                time.sleep(.025)
        adquiridos[clave] = exclusive
        try:
            yield
        finally:
            adquiridos.pop(clave, None)
    finally:
        try:
            if archivo is not None:
                try:
                    if bloqueado:
                        liberar_archivo(archivo, bloqueo)
                finally:
                    archivo.close()
        finally:
            barrera.liberar(exclusive)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
database_guard = proteger_base_datos
