"""Regresiones de paginación, concurrencia, migración y compatibilidad de respaldos."""
import sqlite3
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

from hemeroteca.main import create_services
from hemeroteca.config.settings import TITLES, REGIONAL, SECURITY_QUESTIONS, ROLES
from hemeroteca.database.maintenance import database_guard
from hemeroteca.database.schema import SCHEMA_VERSION
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.backup_archive import validated_database


class PruebasMejoras(unittest.TestCase):
    """Prueba reglas del servicio sin abrir la base de datos de una instalación."""

    @classmethod
    def setUpClass(cls):
        """Prepara una base semilla y credenciales de prueba independientes."""
        cls.semilla = create_services(':memory:')
        cls.preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Una', 'Dos', 'Tres')))
        cls.semilla.auth.create_master('Responsable Prueba', 'V-7654321', 'Prueba!2026', cls.preguntas)
        cls.maestro = cls.semilla.auth.authenticate('V-7654321', 'Prueba!2026')
        resultado = cls.semilla.users.register_user('María Pérez', 'V-7654322', 'Prueba!2026', cls.preguntas)
        cls.usuario = dict(cls.semilla.connection.execute('SELECT * FROM users WHERE id=?', (resultado.user_id,)).fetchone())

    @classmethod
    def tearDownClass(cls):
        """Libera la base semilla una vez finalizada la clase."""
        cls.semilla.close()

    def setUp(self):
        """Crea una copia aislada para cada prueba de comportamiento."""
        self.servicios = create_services(':memory:')
        self.semilla.connection.backup(self.servicios.connection)

    def tearDown(self):
        """Cierra todas las conexiones propias de la prueba."""
        self.servicios.close()

    def valores(self, numero='1', estante='1'):
        """Devuelve un ejemplar válido con identificación única configurable."""
        return (TITLES[0], 'Regional' if TITLES[0] in REGIONAL else 'Nacional', 'Matutina', 2020, 1, 1, numero, estante, '2', 'Disponible')

    def test_edicion_obsoleta_conserva_primera_actualizacion(self):
        """El segundo formulario no sobrescribe la revisión guardada por el primero."""
        self.servicios.periodicos.save_record(self.maestro, self.valores())
        ficha = self.servicios.periodicos.get_issue(self.maestro, 1)
        self.servicios.periodicos.save_record(self.maestro, self.valores(estante='11'), issue_id=1, expected_revision=ficha['revision'])
        with self.assertRaisesRegex(ValueError, 'cambió'):
            self.servicios.periodicos.save_record(self.maestro, self.valores(estante='22'), issue_id=1, expected_revision=ficha['revision'])
        self.assertEqual(self.servicios.periodicos.get_issue(self.maestro, 1)['shelf'], '11')

    def test_catalogo_pagina_no_materializa_todo(self):
        """Dos páginas consecutivas tienen límites y registros disjuntos."""
        for numero in range(19):
            self.servicios.periodicos.save_record(self.maestro, self.valores(str(numero)))
        primera = self.servicios.periodicos.search_issues(self.maestro, catalog=True)
        segunda = self.servicios.periodicos.search_issues(self.maestro, catalog=True, page=2)
        self.assertEqual((primera['total'], len(primera['items']), primera['pages']), (19, 5, 4))
        self.assertTrue({fila['id'] for fila in primera['items']}.isdisjoint(fila['id'] for fila in segunda['items']))

    def test_ultimos_cinco_conserva_total_y_orden(self):
        """El conteo optimizado no elimina el límite funcional de cinco registros."""
        for numero in range(12):
            self.servicios.periodicos.save_record(self.maestro, self.valores(str(numero)))
        pagina = self.servicios.periodicos.search_issues(self.maestro, period='Últimos 5 registros', page_size=3, page=2)
        self.assertEqual(pagina['total'], 5)
        self.assertEqual([fila['id'] for fila in pagina['items']], [9, 8])

    def test_catalogo_respeta_permiso_de_vista(self):
        """La consulta habitual no da acceso al catálogo administrativo."""
        self.assertEqual(self.servicios.periodicos.search_issues(self.usuario)['total'], 0)
        with self.assertRaises(AccessDenied):
            self.servicios.periodicos.search_issues(self.usuario, catalog=True)

    def test_indice_fecha_y_migracion_activa(self):
        """El esquema nuevo admite revisión y una búsqueda por fecha indexada."""
        self.assertEqual(self.servicios.connection.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        plan = self.servicios.connection.execute('EXPLAIN QUERY PLAN SELECT * FROM issues WHERE deleted=0 AND year=2020 AND month=1 AND day=1').fetchall()
        self.assertTrue(any('issues_active_date' in fila[3] for fila in plan))

    def test_anulacion_ausencia_resuelve_conflicto_con_auditoria(self):
        """Una anotación errónea puede corregirse sin borrar su historia de auditoría."""
        titulo, tipo = self.valores()[:2]
        self.servicios.periodicos.save_record(self.maestro, (titulo, tipo, 2020, 1, 1, 'Error de registro'), absent=True)
        with self.assertRaises(ValueError):
            self.servicios.periodicos.save_record(self.maestro, self.valores())
        self.servicios.periodicos.corregir_fecha_ausente(self.maestro, 1, anular=True)
        self.servicios.periodicos.save_record(self.maestro, self.valores())
        eventos = self.servicios.audit.list_events(self.maestro)
        self.assertTrue(any('Error de registro' in fila['action'] for fila in eventos))

    def test_usuario_sin_permiso_no_corrige_ausencia(self):
        """La API de corrección vuelve a comprobar el permiso en el servidor."""
        with self.assertRaises(AccessDenied):
            self.servicios.periodicos.corregir_fecha_ausente(self.usuario, 1, anular=True)

    def test_paginacion_ausencias_y_eliminados(self):
        """Las anotaciones y los retirados respetan filtro, conteo y tamaño de página."""
        titulo, tipo = self.valores()[:2]
        for dia in range(1, 8):
            self.servicios.periodicos.save_record(self.maestro, (titulo, tipo, 2019, 1, dia, ''), absent=True)
        pagina = self.servicios.periodicos.buscar_fechas_ausentes(self.maestro, year=2019, page=2)
        self.assertEqual((pagina['total'], len(pagina['items'])), (7, 2))
        self.servicios.periodicos.save_record(self.maestro, self.valores())
        self.servicios.periodicos.delete_issue(self.maestro, 1)
        self.assertEqual(self.servicios.periodicos.buscar_eliminados(self.maestro, texto='01/01/2020')['total'], 1)

    def test_busqueda_unicode_usuarios(self):
        """El filtro SQL conserva casefold y tildes del comportamiento anterior."""
        resultado = self.servicios.users.buscar_usuarios(self.maestro, texto='MARÍA')
        self.assertEqual(resultado['total'], 1)
        self.assertEqual(resultado['items'][0]['name'], 'María Pérez')

    def test_solicitudes_paginadas_no_filtran_datos_ajenos(self):
        """El resumen y la lista se limitan al administrador regular titular."""
        self.servicios.connection.execute('UPDATE users SET role=?,managed_permissions=1 WHERE id=?', (ROLES[1], self.usuario['id']))
        self.servicios.connection.commit()
        self.servicios.requests.submit_request(self.usuario, 'Registrar ejemplares', 'Necesito registrar')
        self.assertEqual(self.servicios.requests.resumen_solicitudes(self.usuario)['contadores']['Pendiente'], 1)
        pagina = self.servicios.requests.buscar_solicitudes(self.usuario, texto='MARÍA')
        self.assertEqual(pagina['total'], 1)
        self.assertEqual(pagina['items'][0]['user_id'], self.usuario['id'])

    def test_auditoria_conserva_fecha_historica_y_filtros(self):
        """El servicio reconoce timestamps legibles antiguos y fechas ISO."""
        self.servicios.connection.execute("INSERT INTO audit(at,user,action,result) VALUES('15/01/2020 09:31:00','María','Registro técnico','Completado')")
        self.servicios.connection.execute("INSERT INTO audit(at,user,action,result) VALUES('2020-01-15T09:32:00','María','Registro técnico','Completado')")
        self.servicios.connection.commit()
        pagina = self.servicios.audit.buscar_eventos(self.maestro, fecha='2020-01-15', hora='09', usuario='MARÍA', accion='TÉCNICO')
        self.assertEqual(pagina['total'], 2)

    def test_estado_sesion_compacto(self):
        """La sincronización devuelve permisos y requisitos sin llamadas adicionales."""
        estado = self.servicios.access.estado_sesion(self.maestro)
        self.assertFalse(estado['requiere_configuracion'])
        self.assertIn('Registrar ejemplares', estado['permisos'])

    def test_restauracion_admite_esquema_cuatro(self):
        """Un respaldo de la versión anterior recibe revisión cero al reconstruirse."""
        anterior = sqlite3.connect(':memory:')
        self.servicios.connection.backup(anterior)
        anterior.execute('ALTER TABLE issues DROP COLUMN revision')
        anterior.execute('PRAGMA user_version=4')
        anterior.commit()
        restaurada = validated_database(anterior.serialize())
        try:
            self.assertEqual(restaurada.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertIn('revision', [fila[1] for fila in restaurada.execute('PRAGMA table_info(issues)')])
        finally:
            restaurada.close()
            anterior.close()

    def test_cierre_idempotente(self):
        """El cierre desde GUI y finally puede repetirse sin error."""
        self.servicios.close()
        self.servicios.close()

    def test_importacion_no_modifica_origen_ni_sobrescribe_destino(self):
        """La migración opcional copia datos y rechaza reemplazar una instalación nueva."""
        from scripts.importar_datos import importar
        with tempfile.TemporaryDirectory(prefix='perri-importacion-') as directorio:
            origen = Path(directorio) / 'anterior.db'
            destino = Path(directorio) / 'maximo.db'
            anterior = sqlite3.connect(origen)
            self.servicios.connection.backup(anterior)
            anterior.execute('ALTER TABLE issues DROP COLUMN revision')
            anterior.execute('PRAGMA user_version=4')
            anterior.commit()
            anterior.close()
            huella = hashlib.sha256(origen.read_bytes()).digest()
            importar(origen, destino)
            self.assertEqual(hashlib.sha256(origen.read_bytes()).digest(), huella)
            nueva = sqlite3.connect(destino)
            try:
                self.assertEqual(nueva.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(nueva.execute('SELECT count(*) FROM users').fetchone()[0], 2)
            finally:
                nueva.close()
            with self.assertRaisesRegex(ValueError, 'sobrescribió'):
                importar(origen, destino)


class PruebasBarrera(unittest.TestCase):
    """Verifica concurrencia real entre hilos y exclusión de mantenimiento."""

    def test_compartidas_coinciden_y_exclusiva_espera(self):
        """Dos operaciones entran juntas y la restauración no puede intercalarse."""
        with tempfile.TemporaryDirectory(prefix='perri-barrera-') as directorio:
            ruta = Path(directorio) / 'prueba.db'
            dentro = threading.Barrier(3)
            liberar = threading.Event()
            errores = []
            def lector():
                """Mantiene una operación activa hasta la señal de la prueba."""
                try:
                    with database_guard(ruta, exclusive=False, timeout=2):
                        dentro.wait(timeout=2)
                        liberar.wait(timeout=3)
                except Exception as error:
                    errores.append(error)
            hilos = [threading.Thread(target=lector) for _ in range(2)]
            for hilo in hilos:
                hilo.start()
            try:
                dentro.wait(timeout=2)
                with self.assertRaises(ValueError):
                    with database_guard(ruta, timeout=.1):
                        self.fail('El mantenimiento entró mientras había lectores.')
            finally:
                liberar.set()
                for hilo in hilos:
                    hilo.join(timeout=3)
            self.assertFalse(errores, errores)
            with database_guard(ruta, timeout=1):
                pass

    def test_anidacion_y_rechazo_de_conversion(self):
        """La reentrada exclusiva funciona y una actualización de bloqueo se rechaza."""
        with tempfile.TemporaryDirectory(prefix='perri-barrera-') as directorio:
            ruta = Path(directorio) / 'prueba.db'
            with database_guard(ruta):
                with database_guard(ruta, exclusive=False):
                    pass
            with database_guard(ruta, exclusive=False):
                with self.assertRaises(RuntimeError):
                    with database_guard(ruta):
                        pass


if __name__ == '__main__':
    unittest.main()
