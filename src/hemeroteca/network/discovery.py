"""Descubrimiento local de aplicaciones que esperan autorización, por UDP."""

import ipaddress
import json
import logging
import secrets
import socket
import sys
import threading
import time
from contextlib import ExitStack
from select import select

DISCOVERY_PORT = 8766
# Grupo IPv4 de alcance local administrativo. Las consultas salen con TTL 1.
DISCOVERY_GROUP = '239.255.77.76'
LOOPBACK = '127.0.0.1'
PRIVATE_LANS = tuple(map(ipaddress.IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
MAX_UNICAST_PEERS = 254
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


def _discovery_interfaces():
    """Enumera las IPv4 privadas del equipo, con respaldo para hosts sin DNS local."""
    addresses = []
    try:
        records = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
        addresses.extend(record[4][0] for record in records)
    except OSError:
        pass
    try:
        addresses.append(local_address(DISCOVERY_GROUP))
    except ValueError:
        pass
    private = dict.fromkeys(address for address in addresses
                            if private_ip(address) and not address.startswith('127.'))
    return (*private, LOOPBACK)


def _configure_query(udp, interface, multicast):
    """Recibe respuestas únicamente en la dirección que originó la búsqueda."""
    udp.bind((interface, 0))
    if multicast:
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    udp.settimeout(.3)


def _ready(sockets, timeout):
    """Evita que una interfaz sin tráfico retrase la lectura de las demás."""
    if len(sockets) == 1:
        return sockets
    return select(sockets, [], [], timeout)[0]


def _windows_ipv4_subnets():
    """Lee las máscaras IPv4 de Windows sin cambiar rutas ni reglas de red."""
    if sys.platform != 'win32':
        return {}

    import ctypes
    from ctypes import wintypes

    class AddressRow(ctypes.Structure):
        _fields_ = [
            ('address', wintypes.DWORD),
            ('index', wintypes.DWORD),
            ('mask', wintypes.DWORD),
            ('broadcast', wintypes.DWORD),
            ('reassembly_size', wintypes.DWORD),
            ('reserved', wintypes.WORD),
            ('flags', wintypes.WORD),
        ]

    class AddressTableHeader(ctypes.Structure):
        _fields_ = [('count', wintypes.DWORD), ('rows', AddressRow * 0)]

    get_table = ctypes.WinDLL('Iphlpapi.dll').GetIpAddrTable
    get_table.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG), wintypes.BOOL)
    get_table.restype = wintypes.DWORD
    size = wintypes.ULONG()
    if get_table(None, ctypes.byref(size), False) != 122:  # ERROR_INSUFFICIENT_BUFFER
        return {}
    buffer = ctypes.create_string_buffer(size.value)
    if get_table(buffer, ctypes.byref(size), False) != 0:
        return {}

    header = AddressTableHeader.from_buffer(buffer)
    rows = (AddressRow * header.count).from_buffer(buffer, AddressTableHeader.rows.offset)
    networks = {}
    for row in rows:
        if row.flags & 0x00C8:  # Dirección desconectada, eliminada o transitoria.
            continue
        address = socket.inet_ntoa(row.address.to_bytes(4, sys.byteorder))
        mask = socket.inet_ntoa(row.mask.to_bytes(4, sys.byteorder))
        try:
            network = ipaddress.IPv4Network((address, mask), strict=False)
        except ValueError:
            continue
        if 24 <= network.prefixlen <= 30 and any(network.subnet_of(private) for private in PRIVATE_LANS):
            networks[address] = network
    return networks


def _probe(udp, payload, destination):
    """Envía una consulta opcional sin cancelar la búsqueda en otras interfaces."""
    try:
        udp.sendto(payload, (destination, DISCOVERY_PORT))
    except OSError:
        logging.getLogger(__name__).debug('No se pudo consultar una dirección de la LAN.', exc_info=True)


def _collect_invitations(sockets, nonce, found, timeout, address):
    """Filtra las respuestas usando el nonce y los límites de la invitación."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(found) < 32:
        for udp in _ready(sockets, .3):
            if len(found) == 32:
                return
            try:
                payload, origin = udp.recvfrom(4096)
                item = json.loads(payload)
                if item.get('protocol') != PROTOCOL or item.get('nonce') != nonce or not private_ip(origin[0]):
                    continue
                if address is not None and origin[0] != address:
                    continue
                if not isinstance(item.get('invitation_id'), str) or not isinstance(item.get('name'), str):
                    continue
                port = int(item['port'])
                if not 1024 <= port <= 65535 or int(item['expires_at']) < time.time():
                    continue
                item['name'] = ''.join(char for char in item['name'][:80] if char.isprintable()) or 'PC de consulta'
                item['url'] = f'https://{origin[0]}:{port}'
                found[item['invitation_id']] = item
            except (socket.timeout, ValueError, KeyError, TypeError, AttributeError, OverflowError):
                continue
            except OSError as error:
                if not _is_udp_reset(error):
                    raise


def _discover_without_multicast(sockets, payload, nonce, found):
    """Consulta solamente puertos de Hemeroteca en las subredes privadas conectadas."""
    try:
        networks = _windows_ipv4_subnets()
    except (AttributeError, OSError, ValueError):
        logging.getLogger(__name__).debug('No se pudieron consultar las subredes locales.', exc_info=True)
        return
    interfaces = {address: udp for address, udp in sockets.items() if address in networks}
    if not interfaces:
        return

    for address, udp in interfaces.items():
        _probe(udp, payload, address)
    _collect_invitations(interfaces.values(), nonce, found, .35, None)
    if found:
        return

    # Una consulta por destino y hasta 254 en total. Se usa la máscara real.
    visited = set(interfaces)
    for address, udp in interfaces.items():
        for peer in networks[address].hosts():
            if len(visited) - len(interfaces) == MAX_UNICAST_PEERS:
                break
            destination = str(peer)
            if destination not in visited:
                visited.add(destination)
                _probe(udp, payload, destination)
    _collect_invitations(interfaces.values(), nonce, found, 1.2, None)


def descubrir_esperando(timeout=3, *, address=None):
    """Busca invitaciones por multicast o consulta una IPv4 indicada por el operador."""
    if address is not None:
        if not private_ip(address) or ipaddress.IPv4Address(address).is_reserved:
            raise ValueError('Introduce una dirección IPv4 privada de la PC de consulta.')
        interface = LOOPBACK if address.startswith('127.') else local_address(address)
        interfaces = (interface,)
    else:
        interfaces = _discovery_interfaces()
    nonce, found = secrets.token_hex(16), {}
    consulta = json.dumps({'protocol': PROTOCOL, 'kind': 'discover', 'nonce': nonce}).encode()
    with ExitStack() as resources:
        sockets = {}
        setup_error = None
        for interface in interfaces:
            with ExitStack() as candidate:
                udp = candidate.enter_context(_discovery_socket())
                destination = address or (LOOPBACK if interface == LOOPBACK else DISCOVERY_GROUP)
                try:
                    _configure_query(udp, interface, destination == DISCOVERY_GROUP)
                except OSError as error:
                    setup_error = error
                    continue
                try:
                    udp.sendto(consulta, (destination, DISCOVERY_PORT))
                except OSError as error:
                    if not _is_udp_reset(error):
                        setup_error = error
                        continue
                resources.enter_context(candidate.pop_all())
                sockets[interface] = udp
        if not sockets:
            raise OSError('No se pudo iniciar el descubrimiento en ninguna interfaz local.') from setup_error
        _collect_invitations(sockets.values(), nonce, found, timeout, address)
        if address is None and not found:
            _discover_without_multicast(sockets, consulta, nonce, found)
    return list(found.values())
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
discover_waiting = descubrir_esperando


class DiscoveryResponder:
    """Responde búsquedas UDP con la invitación vigente y limita la frecuencia por dirección de origen."""
    def __init__(self, description):
        """Abre el socket de descubrimiento y prepara el hilo y la señal de cierre sin iniciar todavía la recepción."""
        self.description = description
        self.stop = threading.Event()
        self.resources = ExitStack()
        self.sockets = []
        try:
            interfaces = _discovery_interfaces()
            lan = tuple(interface for interface in interfaces if interface != LOOPBACK)
            if sys.platform == 'win32':
                listeners = [(interface, (interface,)) for interface in lan]
            else:
                # En Unix los sockets unidos al grupo y a cada IP reciben destinos distintos.
                listeners = [(interface, ()) for interface in lan]
                if lan:
                    listeners.append((DISCOVERY_GROUP, lan))
            if LOOPBACK in interfaces:
                listeners.append((LOOPBACK, (LOOPBACK,)))
            error = None
            listening_on_lan = False
            self.addresses = []
            for address, memberships in listeners:
                try:
                    self._open_listener(address, memberships)
                    listening_on_lan |= address != LOOPBACK
                    if address in lan:
                        self.addresses.append(address)
                except OSError as exception:
                    error = exception
                    if address != LOOPBACK:
                        logging.getLogger(__name__).debug('No se pudo escuchar en %s.', address, exc_info=True)
            if not self.sockets or (lan and not listening_on_lan):
                raise error
            self.thread = threading.Thread(target=self.run, daemon=True, name='hemeroteca-descubrimiento')
        except (OSError, RuntimeError):
            self.resources.close()
            raise

    def _open_listener(self, address, interfaces):
        """Une el grupo solo en las interfaces aprobadas por el descubrimiento."""
        with ExitStack() as candidate:
            udp = _discovery_socket()
            candidate.callback(udp.close)
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            udp.bind((address, DISCOVERY_PORT))
            for interface in interfaces:
                if interface != LOOPBACK:
                    membership = socket.inet_aton(DISCOVERY_GROUP) + socket.inet_aton(interface)
                    udp.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            udp.settimeout(.5)
            self.resources.enter_context(candidate.pop_all())
        self.sockets.append(udp)

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
                ready = _ready(self.sockets, .5)
            except (OSError, ValueError):
                if not self.stop.is_set():
                    logging.getLogger(__name__).exception('Se interrumpió la espera de búsquedas de computadoras.')
                return
            for udp in ready:
                try:
                    contenido, origen = udp.recvfrom(2048)
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
                        udp.sendto(json.dumps(dict(description, protocol=PROTOCOL, nonce=nonce)).encode(), origen)
                except (socket.timeout, ValueError, AttributeError):
                    continue
                except OSError as excepcion:
                    if not self.stop.is_set() and _is_udp_reset(excepcion):
                        continue
                    if not self.stop.is_set():
                        logging.getLogger(__name__).exception('Se interrumpió la recepción de búsquedas de computadoras.')
                    return
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    run = ejecutar

    def cerrar(self):
        'Libera los recursos propios y finaliza esta instancia.'
        self.stop.set()
        self.resources.close()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar
