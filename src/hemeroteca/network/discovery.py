"""Descubrimiento local de aplicaciones que esperan autorización, por UDP."""

import ipaddress
import json
import logging
import secrets
import socket
import sys
import threading
import time

DISCOVERY_PORT = 8766
PROTOCOL = 'hemeroteca-pair-v1'


def _es_udp_reiniciar(error):
    """Reconoce el reinicio UDP de Windows 10054 para tolerar destinos sin receptor."""
    return (isinstance(error, ConnectionResetError)
            or getattr(error, 'winerror', None) == 10054
            or error.errno == 10054)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
_is_udp_reset = _es_udp_reiniciar


def _descubrimiento_conector():
    """Evita que un puerto UDP sin receptor interrumpa la búsqueda en Windows."""
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if sys.platform != 'win32':
        return udp
    try:
        import ctypes
        from ctypes import wintypes

        # socket.ioctl de Python 3.13 no admite SIO_UDP_CONNRESET.
        # SOCKET tiene el tamaño de un puntero, también en Windows de 64 bits.
        winsock = ctypes.WinDLL('Ws2_32.dll')
        ioctl = winsock.WSAIoctl
        ioctl.argtypes = [ctypes.c_size_t, wintypes.DWORD,
                          ctypes.c_void_p, wintypes.DWORD,
                          ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD),
                          ctypes.c_void_p, ctypes.c_void_p]
        ioctl.restype = ctypes.c_int
        disabled = wintypes.BOOL(False)
        returned = wintypes.DWORD()
        sio_udp_connreset = 0x9800000C
        resultado = ioctl(udp.fileno(), sio_udp_connreset,
                       ctypes.byref(disabled), ctypes.sizeof(disabled),
                       None, 0, ctypes.byref(returned), None, None)
        if resultado == -1:
            winsock.WSAGetLastError.argtypes = []
            winsock.WSAGetLastError.restype = ctypes.c_int
            logging.getLogger(__name__).debug(
                'SIO_UDP_CONNRESET no disponible; se manejarán los avisos UDP (Winsock %s).',
                winsock.WSAGetLastError())
    except (AttributeError, OSError):
        # Algunos proveedores no admiten el control; el bucle maneja el 10054.
        logging.getLogger(__name__).debug(
            'Se utilizará el manejo de avisos UDP sin SIO_UDP_CONNRESET.', exc_info=True)
    return udp
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
_discovery_socket = _descubrimiento_conector


def privado_ip(value):
    """Indica si el texto es una IPv4 privada o de bucle local, excluyendo direcciones indefinidas y multicast."""
    valor = value
    try:
        direccion = ipaddress.IPv4Address(valor)
        return (direccion.is_private or direccion.is_loopback) and not direccion.is_unspecified and not direccion.is_multicast
    except ipaddress.AddressValueError:
        return False
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
private_ip = privado_ip


def local_direccion(peer='224.0.0.251'):
    """Obtiene la IPv4 de la ruta hacia el equipo indicado y rechaza una conexión limitada al bucle local."""
    equipo_remoto = peer
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        try:
            route.connect((equipo_remoto, DISCOVERY_PORT))
            direccion = route.getsockname()[0]
        except OSError as excepcion:
            raise ValueError('Conecta esta PC a la misma red WiFi o cableada que las demás computadoras.') from excepcion
    if not private_ip(direccion) or direccion.startswith('127.'):
        raise ValueError('No se encontró una conexión de red local disponible.')
    return direccion
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
local_address = local_direccion


def descubrir_esperando(timeout=3):
    """Busca invitaciones por UDP durante el plazo indicado y devuelve hasta 32 equipos válidos sin duplicados."""
    tiempo_espera = timeout
    nonce, found = secrets.token_hex(16), {}
    consulta = json.dumps({'protocol': PROTOCOL, 'kind': 'discover', 'nonce': nonce}).encode()
    with _discovery_socket() as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.bind(('', 0))
        udp.settimeout(.3)
        for direccion in ('255.255.255.255', '127.0.0.1'):
            try:
                udp.sendto(consulta, (direccion, DISCOVERY_PORT))
            except OSError as excepcion:
                if not _is_udp_reset(excepcion):
                    raise
        plazo = time.monotonic() + tiempo_espera
        while time.monotonic() < plazo and len(found) < 32:
            try:
                contenido, origen = udp.recvfrom(4096)
                elemento = json.loads(contenido)
                if elemento.get('protocol') != PROTOCOL or elemento.get('nonce') != nonce or not private_ip(origen[0]):
                    continue
                if not isinstance(elemento.get('invitation_id'), str) or not isinstance(elemento.get('name'), str):
                    continue
                puerto = int(elemento['port'])
                if not 1024 <= puerto <= 65535 or int(elemento['expires_at']) < time.time():
                    continue
                elemento['name'] = ''.join(elemento_breve for elemento_breve in elemento['name'][:80] if elemento_breve.isprintable()) or 'PC de consulta'
                elemento['url'] = f'https://{origen[0]}:{puerto}'
                found[elemento['invitation_id']] = elemento
            except (socket.timeout, ValueError, KeyError, TypeError, AttributeError, OverflowError):
                continue
            except OSError as excepcion:
                # Un destino sin receptor no invalida las respuestas de otros.
                if not _is_udp_reset(excepcion):
                    raise
    return list(found.values())
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
discover_waiting = descubrir_esperando


class DiscoveryResponder:
    """Responde búsquedas UDP con la invitación vigente y limita la frecuencia por dirección de origen."""
    def __init__(self, description):
        """Abre el socket de descubrimiento y prepara el hilo y la señal de cierre sin iniciar todavía la recepción."""
        self.description = description
        self.stop = threading.Event()
        self.socket = _discovery_socket()
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind(('', DISCOVERY_PORT))
            self.socket.settimeout(.5)
            self.thread = threading.Thread(target=self.run, daemon=True, name='hemeroteca-descubrimiento')
        except (OSError, RuntimeError):
            self.socket.close()
            raise

    def iniciar(self):
        'Inicia el trabajador o servidor y conserva su referencia para el cierre.'
        self.thread.start()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    start = iniciar

    def ejecutar(self):
        """Recibe búsquedas válidas, responde con su nonce y tolera expiraciones de espera hasta que se solicita cerrar."""
        last = {}
        while not self.stop.is_set():
            try:
                contenido, origen = self.socket.recvfrom(2048)
                consulta = json.loads(contenido)
                if consulta.get('protocol') != PROTOCOL or consulta.get('kind') != 'discover' or not private_ip(origen[0]):
                    continue
                nonce = consulta.get('nonce', '')
                if not isinstance(nonce, str) or len(nonce) != 32:
                    continue
                if time.monotonic() - last.get(origen[0], 0) < .5:
                    continue
                last[origen[0]] = time.monotonic()
                if len(last) > 256:
                    last.clear()
                description = self.description()
                if description:
                    self.socket.sendto(json.dumps(dict(description, protocol=PROTOCOL, nonce=nonce)).encode(), origen)
            except (socket.timeout, ValueError, AttributeError):
                continue
            except OSError as excepcion:
                if not self.stop.is_set() and _is_udp_reset(excepcion):
                    continue
                if not self.stop.is_set():
                    logging.getLogger(__name__).exception('Se interrumpió la recepción de búsquedas de computadoras.')
                break
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    run = ejecutar

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        self.stop.set()
        self.socket.close()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
