"""Regresiones de permisos, decisiones y catálogo sobre SQLite aislado."""
import sqlite3
import unittest
from hemeroteca.config.settings import ROLES, VIEWS, SECURITY_QUESTIONS, TITLES, REGIONAL
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied


class PruebasSolicitudesCatalogoSQLite(unittest.TestCase):
    """Comprueba estado y auditoría sin simular las reglas del negocio."""

    @classmethod
    def setUpClass(cls):
        cls.seed = create_services(':memory:')
        questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'Sol', 'Mar')))
        clave = 'Prueba#2026'
        cls.seed.auth.create_master('Maestra Ficticia', 'V-12345678', clave, questions)
        cls.seed.users.register_user('Administradora Ficticia', 'V-12345679', clave, questions, role=ROLES[1])
        cls.seed.users.register_user('Otra Ficticia', 'V-12345680', clave, questions, role=ROLES[1])
        cls.actors = [cls.seed.auth.authenticate(doc, clave) for doc in ['V-12345678', 'V-12345679', 'V-12345680']]

    @classmethod
    def tearDownClass(cls):
        cls.seed.close()

    def setUp(self):
        self.s = create_services(':memory:')
        self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
        self.master, self.admin, self.other = [dict(actor) for actor in self.actors]
        self.permission = 'Registrar ejemplares'
        self.values = (TITLES[0], 'Regional' if TITLES[0] in REGIONAL else 'Nacional', 'Matutina', 2020, 2, 29, '5', '2', '', 'Disponible')

    def submit(self, actor=None):
        return self.s.requests.submit_request(actor or self.admin, self.permission, 'Necesito registrar ejemplares de prueba')

    def test_decision_rechaza_tipos_invalidos_y_no_modifica_estado(self):
        request = self.submit()
        cases = [(request, 'false', ''), (request, 1, ''), (request, True, None),
                 (request, False, []), (True, True, ''), ('1', True, ''), (request, True, '', True)]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.s.requests.decide_request(self.master, *args)
        row = self.s.connection.execute('SELECT status,response FROM requests WHERE id=?', (request,)).fetchone()
        self.assertEqual(tuple(row), ('Pendiente', ''))
        self.assertNotIn(self.permission, self.s.access.permissions(self.admin))

    def test_decision_obsoleta_y_repetida_no_otorgan_permiso(self):
        request = self.submit()
        with self.assertRaisesRegex(ValueError, 'cuenta.*cambió'):
            self.s.requests.decide_request(self.master, request, True, expected_account_version=self.admin['password_version']+1)
        self.s.requests.decide_request(self.master, request, False, 'Falta justificar')
        with self.assertRaises(ValueError):
            self.s.requests.decide_request(self.master, request, True)
        self.assertNotIn(self.permission, self.s.access.permissions(self.admin))

    def test_alcance_paginado_y_resumen_no_filtran_solicitudes_ajenas(self):
        own = self.submit()
        self.submit(self.other)
        results = self.s.requests.buscar_solicitudes(self.admin, estado='Pendiente')
        self.assertEqual([r['id'] for r in results['items']], [own])
        self.assertEqual(self.s.requests.resumen_solicitudes(self.admin)['contadores'], {'Pendiente': 1})
        self.assertEqual(self.s.requests.buscar_solicitudes(self.master, estado='Pendiente')['total'], 2)
        self.assertEqual(self.s.requests.buscar_solicitudes(self.admin, texto='Otra Ficticia')['total'], 0)

    def test_decidir_necesita_maestro_y_rechazar_respuesta(self):
        request = self.submit()
        with self.assertRaises(AccessDenied):
            self.s.requests.decide_request(self.admin, request, True)
        for response in ['', ' '*5, 'x'*1001]:
            with self.assertRaises(ValueError):
                self.s.requests.decide_request(self.master, request, False, response)
        self.assertEqual(self.s.requests.buscar_solicitudes(self.admin)['items'][0]['status'], 'Pendiente')

    def test_aprobacion_revocacion_y_nueva_solicitud(self):
        request = self.submit()
        self.s.requests.decide_request(self.master, request, True, expected_account_version=self.admin['password_version'])
        self.assertIn(self.permission, self.s.access.permissions(self.admin))
        self.assertNotIn(self.permission, self.s.requests.available_permissions(self.admin))
        with self.s.connection:
            self.s.connection.execute('DELETE FROM grants WHERE user_id=? AND permission=?', (self.admin['id'], self.permission))
        self.assertIn(self.permission, self.s.requests.available_permissions(self.admin))
        self.assertNotEqual(self.submit(), request)

    def test_cuenta_inactiva_se_rechaza_pero_no_se_aprueba(self):
        request = self.submit()
        with self.s.connection:
            self.s.connection.execute('UPDATE users SET active=0 WHERE id=?', (self.admin['id'],))
        with self.assertRaises(ValueError):
            self.s.requests.decide_request(self.master, request, True)
        self.s.requests.decide_request(self.master, request, False, 'Cuenta inactiva')
        self.assertEqual(self.s.requests.buscar_solicitudes(self.master)['items'][0]['status'], 'Declinada')

    def test_edicion_obsoleta_preserva_campos_y_revision(self):
        self.s.periodicos.save_record(self.master, self.values)
        record = self.s.periodicos.get_issue(self.master, 1)
        self.s.periodicos.save_record(self.master, self.values[:7]+('8', '', 'Disponible'), issue_id=1, expected_revision=record['revision'])
        with self.assertRaises(ValueError):
            self.s.periodicos.save_record(self.master, self.values, issue_id=1, expected_revision=record['revision'])
        current = self.s.periodicos.get_issue(self.master, 1)
        self.assertEqual(current['shelf'], '8')
        self.assertEqual(current['revision'], record['revision']+1)

    def test_alta_con_permiso_catalogo_no_autoriza_edicion_ni_ausencia(self):
        with self.s.connection:
            self.s.connection.execute('INSERT INTO grants(user_id,permission) VALUES(?,?)', (self.admin['id'], VIEWS[1]))
        self.s.periodicos.register_issue(self.admin, list(self.values))
        self.assertEqual(self.s.periodicos.search_issues(self.admin, catalog=True)['total'], 1)
        with self.assertRaises(AccessDenied):
            self.s.periodicos.save_record(self.admin, self.values, issue_id=1)
        with self.assertRaises(AccessDenied):
            self.s.periodicos.save_record(self.admin, (TITLES[0], self.values[1], 2020, 3, 1, ''), absent=True)

    def test_duplicado_no_deja_auditoria_ni_estado_parcial(self):
        self.s.periodicos.save_record(self.master, self.values)
        events = self.s.connection.execute('SELECT count(*) FROM audit').fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.s.periodicos.save_record(self.master, self.values)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM issues').fetchone()[0], 1)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM audit').fetchone()[0], events)
        self.assertEqual(self.s.connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_ausencia_conflicto_correccion_y_anulacion_auditadas(self):
        absent = (TITLES[0], self.values[1], 2020, 2, 29, 'Sin publicación')
        self.s.periodicos.save_record(self.master, absent, absent=True)
        with self.assertRaises(ValueError):
            self.s.periodicos.save_record(self.master, self.values)
        self.s.periodicos.corregir_fecha_ausente(self.master, 1, observacion='Nota corregida')
        self.assertEqual(self.s.periodicos.buscar_fechas_ausentes(self.master, observaciones='Con observación')['items'][0]['note'], 'Nota corregida')
        self.s.periodicos.corregir_fecha_ausente(self.master, 1, anular=True)
        self.s.periodicos.save_record(self.master, self.values)
        self.assertEqual(self.s.periodicos.search_issues(self.master)['total'], 1)
        self.assertTrue(any('Anulación de fecha' in r[0] for r in self.s.connection.execute('SELECT action FROM audit')))

    def test_filtros_catalogo_rechazan_tipos_fecha_y_ambito_invalidos(self):
        for filters in [dict(period='inventado'), dict(year=True), dict(title=3), dict(kind=[]),
                        dict(year=1969), dict(month=13), dict(day=32), dict(year=2021,month=2,day=29),
                        dict(catalog='true'), dict(desde='2020-03-01',hasta='2020-02-01')]:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.s.periodicos.search_issues(self.master, **filters)
        for filters in [dict(texto=None), dict(periodo='inventado')]:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.s.periodicos.buscar_eliminados(self.master, **filters)

    def test_ausencias_validan_paginacion_filtro_y_correccion(self):
        for filters in [dict(page=0), dict(observaciones='inventado')]:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.s.periodicos.buscar_fechas_ausentes(self.master, **filters)
        for identifier, options in [(True, dict(anular=True)), (1, dict(anular='true')),
                                     (1, dict(observacion=None)), (1, dict(observacion='x'*1001)),
                                     (99, dict(anular=True))]:
            with self.subTest(identifier=identifier, options=options), self.assertRaises(ValueError):
                self.s.periodicos.corregir_fecha_ausente(self.master, identifier, **options)
        self.s.periodicos.save_record(self.master, (TITLES[0], self.values[1], 2020, 2, 29, ''), absent=True)
        self.assertEqual(self.s.periodicos.buscar_fechas_ausentes(self.master, observaciones='Sin observación')['total'], 1)

    def test_registro_remoto_valida_perfil_y_formato_antes_de_alta(self):
        with self.assertRaises(AccessDenied):
            self.s.periodicos.register_issue(self.master, self.values)
        with self.s.connection:
            self.s.connection.execute('INSERT INTO grants(user_id,permission) VALUES(?,?)', (self.admin['id'], VIEWS[1]))
        for values in [[], self.values[:3]+('2020',)+self.values[4:]]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.s.periodicos.register_issue(self.admin, values)
        for options in [dict(absent=True), dict(issue_id=1)]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.s.periodicos.save_record(self.admin, self.values, _catalog_registration=True, **options)
        with self.assertRaises(AccessDenied):
            self.s.periodicos.save_record(self.master, self.values, _catalog_registration=True)

    def test_guardar_rechaza_estructura_ubicacion_y_revision_invalidas(self):
        for values, options in [(self.values, dict(absent='true')), (self.values, dict(issue_id=True)),
                                (self.values, dict(expected_revision=True)), (self.values, dict(expected_revision=-1)),
                                (self.values, dict(absent=True, issue_id=1)), ([], {}),
                                (self.values[:3]+(True,)+self.values[4:], {}),
                                (self.values[:2]+('',)+self.values[3:], {}),
                                (self.values[:7]+('', '', 'Disponible'), {}),
                                (self.values[:-1]+('inventado',), {}),
                                ((TITLES[0], self.values[1], 2020, 2, 29, None), dict(absent=True))]:
            with self.subTest(values=values, options=options), self.assertRaises(ValueError):
                self.s.periodicos.save_record(self.master, values, **options)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM issues').fetchone()[0], 0)

    def test_listados_legacy_consulta_y_retiro_son_consistentes(self):
        self.s.periodicos.save_record(self.master, self.values)
        self.s.periodicos.save_record(self.master, (TITLES[0], self.values[1], 2020, 3, 1, ''), absent=True)
        self.assertEqual(len(self.s.periodicos.list_issues(self.master)), 1)
        self.assertEqual(len(self.s.periodicos.list_absent_dates(self.master)), 1)
        self.assertEqual(len(self.s.periodicos.consult_issues(self.master, 2020, 2, 29)), 1)
        self.assertEqual(len(self.s.periodicos.consult_absent_dates(self.master, 2020, 3, 1)), 1)
        self.s.periodicos.delete_issue(self.master, 1)
        self.assertEqual(len(self.s.periodicos.list_deleted_issues(self.master)), 1)
        self.assertEqual(self.s.periodicos.get_deleted_issue(self.master, 1)['id'], 1)
        self.assertEqual(self.s.periodicos.buscar_eliminados(self.master, texto=TITLES[0], periodo='24h')['total'], 1)
        self.assertEqual(self.s.periodicos.list_issues(self.master), [])
        self.s.periodicos.restore_issue(self.master, 1)
        self.assertEqual(len(self.s.periodicos.list_deleted_issues(self.master)), 0)

    def test_permiso_de_lectura_y_ficha_deben_ser_validos(self):
        with self.assertRaises(ValueError):
            self.s.periodicos.get_issue(self.master, 1, permission='inventado')
        for identifier in [True, 0]:
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.s.periodicos.delete_issue(self.master, identifier)
        with self.assertRaises(ValueError):
            self.s.periodicos.restore_issue(self.master, 99)

    def test_solicitudes_rechazan_filtros_y_motivos_invalidos(self):
        for filters in [dict(estado='inventado'), dict(texto=None), dict(fecha='fecha inválida')]:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.s.requests.buscar_solicitudes(self.admin, **filters)
        for permission, reason in [(None, 'Motivo'), (self.permission, None), (self.permission, ''), (self.permission, 'x'*1001)]:
            with self.subTest(permission=permission, reason=reason), self.assertRaises(ValueError):
                self.s.requests.submit_request(self.admin, permission, reason)
        self.assertEqual(self.s.requests.available_permissions(self.master), [])

    def test_version_negativa_y_id_cero_no_deciden_solicitudes(self):
        request = self.submit()
        for identifier, expected in [(0, None), (-1, None), (request, -1)]:
            with self.subTest(identifier=identifier, expected=expected), self.assertRaises(ValueError):
                self.s.requests.decide_request(self.master, identifier, True, expected_account_version=expected)
        self.assertEqual(self.s.requests.buscar_solicitudes(self.admin)['items'][0]['status'], 'Pendiente')

