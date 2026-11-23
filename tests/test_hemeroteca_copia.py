"""Contratos de aislamiento, permisos y filtros de esta copia de trabajo."""

import unittest
from pathlib import Path
import os

from hemeroteca.config.settings import BASE, DB_PATH, ROLES, VIEWS
from hemeroteca.main import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.network.server import codigo_acceso_denegado


class PruebasHemeroteca(unittest.TestCase):
    """Ejercita reglas de negocio sin datos reales ni cuentas instaladas."""

    def setUp(self):
        """Prepara tres roles ficticios en una base SQLite en memoria."""
        self.servicios = create_services(':memory:')
        with self.servicios.connection:
            for indice, rol in enumerate(ROLES, 1):
                self.servicios.connection.execute('''INSERT INTO users
                    (id,name,identity,password,role,active,created_at,document,managed_permissions)
                    VALUES (?,?,?,?,?,1,?,?,1)''',
                    (indice, f'Persona {indice}', f'V-{10000000 + indice}',
                     'hash-ficticio', rol, '2026-11-03T00:00:00+00:00', f'V-{10000000 + indice}'))
        self.maestro, self.admin, self.regular = (
            dict(self.servicios.connection.execute('SELECT * FROM users WHERE id=?', (indice,)).fetchone())
            for indice in range(1, 4))

    def tearDown(self):
        """Cierra la conexión sintética después de cada prueba."""
        self.servicios.close()

    def test_base_local_aislada(self):
        """La ruta predeterminada está dentro de esta copia y tiene nombre propio."""
        esperada = Path(os.environ.get('HEMEROTECA_DATA_DIR', str(BASE.parents[1] / 'datos'))).expanduser().resolve()
        self.assertEqual(DB_PATH.parent.resolve(), esperada)
        self.assertEqual(DB_PATH.name, 'hemeroteca.db')

    def test_api_distingue_sesion_de_permiso(self):
        """Una sesión regular autenticada recibe 403 al negar una operación."""
        self.assertEqual(codigo_acceso_denegado(None), 401)
        self.assertEqual(codigo_acceso_denegado(self.regular), 403)

    def test_regular_no_eleva_ni_consulta_solicitudes(self):
        """Un grant heredado no abre solicitudes, catálogo ni escritura al rol regular."""
        with self.servicios.connection:
            self.servicios.connection.execute('INSERT INTO grants(user_id,permission) VALUES (?,?)',
                                             (self.regular['id'], VIEWS[2]))
        self.assertEqual(self.servicios.access.permissions(self.regular), {VIEWS[0]})
        self.assertEqual(self.servicios.periodicos.search_issues(self.regular)['total'], 0)
        for llamada in (
            lambda: self.servicios.access.require_access(self.regular, VIEWS[2], action='Ruta directa', view=True),
            lambda: self.servicios.requests.available_permissions(self.regular),
            lambda: self.servicios.requests.submit_request(self.regular, 'Auditoría', 'Motivo'),
        ):
            with self.assertRaises(AccessDenied):
                llamada()

    def test_permiso_desaparece_y_reaparece_al_revocarlo(self):
        """Pendiente y aprobado se ocultan; revocado vuelve a ser solicitables."""
        permiso = 'Auditoría'
        self.assertIn(permiso, self.servicios.requests.available_permissions(self.admin))
        solicitud = self.servicios.requests.submit_request(self.admin, permiso, 'Necesito consultar')
        self.assertNotIn(permiso, self.servicios.requests.available_permissions(self.admin))
        self.servicios.requests.decide_request(self.maestro, solicitud, True)
        self.assertNotIn(permiso, self.servicios.requests.available_permissions(self.admin))
        self.servicios.users.revoke_grant(self.maestro, self.admin['id'], permiso)
        self.assertIn(permiso, self.servicios.requests.available_permissions(self.admin))
        self.assertIsInstance(self.servicios.requests.submit_request(self.admin, permiso, 'Permiso revocado'), int)

    def test_pendientes_ajenos_no_reducen_opciones(self):
        """La consulta global no aplica solicitudes de terceros al selector propio."""
        with self.servicios.connection:
            self.servicios.connection.execute('INSERT INTO grants(user_id,permission) VALUES (?,?)',
                                             (self.admin['id'], 'Consultar solicitudes de todos'))
            self.servicios.connection.execute('''INSERT INTO requests(user_id,permission,reason,created_at)
                VALUES (?,?,?,?)''', (self.regular['id'], 'Usuarios', 'Prueba', '2026-11-03'))
        self.assertIn('Usuarios', self.servicios.requests.available_permissions(self.admin))

    def test_eliminados_busca_fragmentos_sin_acentos(self):
        """Título, número, fecha y responsable admiten fragmentos Unicode."""
        with self.servicios.connection:
            self.servicios.connection.execute('''INSERT INTO issues
                (title,kind,edition,year,month,day,number,shelf,drawer,status,deleted,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)''',
                ('Correo del Caroní', 'Nacional', 'Matutina', 2020, 2, 1,
                 '1456', '2', '', 'Disponible', 'María Pérez', '2020-02-01T12:00:00+00:00'))
        for termino in ('caroni', 'CARONÍ', '145', 'maria', '01/02/2020', '2020-02'):
            with self.subTest(termino=termino):
                resultado = self.servicios.periodicos.buscar_eliminados(self.maestro, texto=termino)
                self.assertEqual((resultado['total'], resultado['pages']), (1, 1))

    def test_cien_registros_tienen_veinte_paginas(self):
        """El servicio ordena cien filas por ID descendente en lotes de cinco."""
        with self.servicios.connection:
            for numero in range(100):
                self.servicios.connection.execute('''INSERT INTO issues
                    (title,kind,edition,year,month,day,number,shelf,drawer,status,created_by,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('El Nacional', 'Nacional', 'Matutina', 2020, 1, 1,
                     str(1000 + numero), '1', '', 'Disponible', 'Prueba', '2026-11-03'))
        primera = self.servicios.periodicos.search_issues(self.maestro)
        ultima = self.servicios.periodicos.search_issues(self.maestro, page=20)
        self.assertEqual((primera['total'], primera['pages'], primera['page_size']), (100, 20, 5))
        self.assertEqual([fila['id'] for fila in primera['items']], [100, 99, 98, 97, 96])
        self.assertEqual([fila['id'] for fila in ultima['items']], [5, 4, 3, 2, 1])

if __name__ == '__main__':
    unittest.main()
