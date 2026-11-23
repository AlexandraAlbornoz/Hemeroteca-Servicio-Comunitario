"""Dependencias comunes de los servicios que comparten conexión y autorización."""


class ServicioConAcceso:
    """Conserva la conexión y el control de acceso inyectados por el contenedor.

    No abre conexiones, autoriza operaciones ni confirma transacciones. Cada
    servicio mantiene esas responsabilidades en sus métodos de negocio.
    """

    def __init__(self, connection, access):
        """Recibe la conexión del hilo actual y el autorizador asociado a esa base.

        Los nombres de parámetros y atributos conservan el contrato de los
        servicios anteriores, incluidas las llamadas por argumentos nombrados.
        """
        self.conn = connection
        self.access = access
