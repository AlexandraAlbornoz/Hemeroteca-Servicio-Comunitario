"""TLS por conexión en trabajadores limitados, con tiempo de espera de negociación."""

import logging
import ssl
import sys
import threading
from http.server import ThreadingHTTPServer


class ServidorHttpSeguro(ThreadingHTTPServer):
    """Servidor HTTP con negociación TLS por trabajador y un máximo de 24 conexiones simultáneas."""
    daemon_threads = True

    def __init__(self, address, handler, context):
        """Conserva el contexto TLS y crea el semáforo antes de vincular la dirección y el manejador HTTP."""
        direccion = address
        contexto = context
        self.context = contexto
        self.connections = threading.BoundedSemaphore(24)
        super().__init__(direccion, handler)

    def procesar_peticion(self, request, client_address):
        """Reserva un cupo para la conexión o la cierra; libera el cupo si no puede iniciar el trabajador."""
        client_direccion = client_address
        client_direccion_local = client_direccion
        peticion = request
        direccion_cliente = client_direccion_local
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(peticion)
            return
        try:
            super().process_request(peticion, direccion_cliente)
        except BaseException:
            self.connections.release()
            raise
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    process_request = procesar_peticion

    def procesar_peticion_en_hilo(self, request, client_address):
        """Negocia TLS con plazo de diez segundos, atiende HTTP y libera siempre el cupo de conexión."""
        client_direccion = client_address
        client_direccion_local = client_direccion
        peticion = request
        direccion_cliente = client_direccion_local
        try:
            peticion.settimeout(10)
            with self.context.wrap_socket(peticion, server_side=True) as encrypted:
                super().process_request_thread(encrypted, direccion_cliente)
        except OSError:
            self.shutdown_request(peticion)
        finally:
            self.connections.release()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    process_request_thread = procesar_peticion_en_hilo

    def manejar_error(self, peticion, direccion_cliente):
        """Resume cierres esperados del cliente y conserva trazas de fallos inesperados."""
        error = sys.exc_info()[1]
        if isinstance(error, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, ssl.SSLEOFError)):
            logging.getLogger(__name__).debug('El cliente cerró la conexión TLS antes de completar la petición.')
            return
        super().handle_error(peticion, direccion_cliente)
    # ThreadingHTTPServer llama este contrato cuando un trabajador detecta un error.
    handle_error = manejar_error
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
TLSHTTPServer = ServidorHttpSeguro
