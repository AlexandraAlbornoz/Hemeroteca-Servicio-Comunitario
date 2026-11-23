"""Usuarios, versiones y autorización sobre SQLite real con cuentas ficticias."""
import sqlite3
import unittest
from unittest.mock import patch
from hemeroteca.config.settings import ROLES,VIEWS,SECURITY_QUESTIONS,REPORT_ISSUES_PERMISSION,LEGACY_ADMIN_ACCESS
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied


class PruebasUsuariosPermisos(unittest.TestCase):
    """Comprueba cambios efectivos y rechazo sin alteraciones parciales."""

    @classmethod
    def setUpClass(cls):
        cls.seed=create_services(':memory:')
        cls.clave='Prueba#2026'
        cls.questions=tuple(zip(SECURITY_QUESTIONS[:3],('Luna','Sol','Mar')))
        cls.seed.auth.create_master('Maestra Ficticia','V-12345678',cls.clave,cls.questions)
        cls.seed.users.register_user('Administradora Ficticia','V-12345679',cls.clave,cls.questions,role=ROLES[1])
        cls.seed.users.register_user('Persona Ficticia','V-12345680',cls.clave,cls.questions,role=ROLES[2])
        cls.actors=[cls.seed.auth.authenticate(doc,cls.clave) for doc in ['V-12345678','V-12345679','V-12345680']]

    @classmethod
    def tearDownClass(cls):cls.seed.close()

    def setUp(self):
        self.s=create_services(':memory:')
        self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
        self.master,self.admin,self.user=[dict(a) for a in self.actors]

    def current(self,actor):return dict(self.s.connection.execute('SELECT * FROM users WHERE id=?',(actor['id'],)).fetchone())

    def grant(self,actor,permission):
        with self.s.connection:self.s.connection.execute('INSERT OR IGNORE INTO grants(user_id,permission) VALUES(?,?)',(actor['id'],permission))

    def test_registro_publico_rechaza_estructura_y_rol(self):
        for name,questions,role in [(None,self.questions,ROLES[1]),('x'*151,self.questions,ROLES[1]),
                                    ('Persona Ficticia',None,ROLES[1]),('Persona Ficticia',[1,2,3],ROLES[1]),
                                    ('Persona Ficticia',[(1,2)]*3,ROLES[1]),('Persona Ficticia',self.questions,ROLES[0])]:
            with self.subTest(name=name,role=role),self.assertRaises(ValueError):
                self.s.users.register_user(name,'V-12345681',self.clave,questions,role=role)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM users').fetchone()[0],3)

    def test_duplicado_publico_informa_cuenta_y_otro_error_no_se_oculta(self):
        with self.assertRaisesRegex(ValueError,'Ya existe una cuenta'):
            self.s.users.register_user('Persona Ficticia','V-12345679',self.clave,self.questions)
        with patch.object(self.s.users,'create_user',side_effect=sqlite3.IntegrityError('otra restricción ficticia')):
            with self.assertRaises(sqlite3.IntegrityError):
                self.s.users.register_user('Persona Ficticia','V-12345681',self.clave,self.questions)

    def test_alta_administrada_y_respuestas_historicas(self):
        for answers in [[],['Luna']]:
            with self.assertRaises(ValueError):
                self.s.users.create_user('Persona Ficticia','V-12345681',self.clave,security_answers=answers)
        result=self.s.users.create_user('Persona Ficticia','V-12345681',self.clave,security_answers=['Luna','Sol','Mar'])
        self.assertTrue(result.recovery_code.startswith('HMR-'))
        admin=self.s.users.create_user('Otra Ficticia','V-12345682',self.clave,ROLES[1],actor=self.master)
        actor=self.s.auth.authenticate('V-12345682',self.clave)
        self.assertTrue(actor['must_change_password'])
        self.assertTrue(self.s.recovery.needs_configuration(actor))
        self.assertEqual(admin.user_id,actor['id'])

    def test_alta_privilegiada_y_perfil_invalido_no_crean_cuentas(self):
        with self.assertRaises(AccessDenied):
            self.s.users.create_user('Persona Ficticia','V-12345681',self.clave,ROLES[0],security_questions=self.questions)
        with self.assertRaises(ValueError):
            self.s.users.create_user('Persona Ficticia','V-12345681',self.clave,'Perfil inexistente',actor=self.master)

    def test_destinatario_y_version_exigen_enteros_validos(self):
        for identifier,version in [('2',None),(True,None),(0,None),(self.admin['id'],True),(self.admin['id'],-1)]:
            with self.subTest(identifier=identifier,version=version),self.assertRaises(ValueError):
                self.s.users.set_user_active(self.master,identifier,False,expected_version=version)
        self.assertTrue(self.current(self.admin)['active'])

    def test_estado_no_convierte_texto_false_en_activacion(self):
        for value in ['false','true',0,1,None,[]]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.s.users.set_user_active(self.master,self.admin['id'],value)
        self.assertEqual(self.current(self.admin)['password_version'],self.admin['password_version'])

    def test_desactivacion_invalida_sesion_y_reactivacion_no_revalida_actor_antiguo(self):
        self.s.users.set_user_active(self.master,self.admin['id'],False,expected_version=self.admin['password_version'])
        self.assertEqual(self.s.access.permissions(self.admin),set())
        with self.assertRaises(AccessDenied):self.s.access.require_access(self.admin,action='Acción ficticia')
        with self.assertRaises(ValueError):self.s.users.set_user_active(self.master,self.admin['id'],True,expected_version=self.admin['password_version'])
        self.s.users.set_user_active(self.master,self.admin['id'],True)
        with self.assertRaises(AccessDenied):self.s.access.require_access(self.admin,action='Actor antiguo')
        refreshed=self.s.auth.authenticate('V-12345679',self.clave)
        self.s.access.require_access(refreshed,action='Actor actual')
        with self.assertRaises(AccessDenied):self.s.users.set_user_active(self.master,self.master['id'],False)

    def test_actualizar_verifica_clave_version_documento_y_perfil(self):
        for identity,role,clave,error in [('V-12345679',ROLES[1],'Incorrecta#2026',AccessDenied),
                                        ('V-12345678',ROLES[1],self.clave,sqlite3.IntegrityError),
                                        ('V-12345679','Perfil inválido',self.clave,ValueError)]:
            with self.subTest(identity=identity,role=role),self.assertRaises(error):
                self.s.users.update_user(self.master,self.admin['id'],'Nombre Ficticio',identity,role,clave)
        self.assertEqual(self.current(self.admin)['name'],self.admin['name'])
        with self.assertRaises(AccessDenied):
            self.s.users.update_user(self.master,self.master['id'],'Maestra Ficticia','V-12345678',ROLES[1],self.clave)

    def test_cambio_de_perfil_no_confiere_permisos_heredados(self):
        result=self.s.users.update_user(self.master,self.user['id'],'Persona Ficticia','V-12345680',ROLES[1],self.clave,
                                        expected_version=self.user['password_version'])
        self.assertEqual(result['managed_permissions'],1)
        self.assertFalse(set(LEGACY_ADMIN_ACCESS)&self.s.access.permissions(result))

    def test_pdf_rechaza_destinatario_inactivo_y_maestro(self):
        for permissions in [None,[1],['Inventado']]:
            with self.assertRaises(ValueError):self.s.users.set_report_permissions(self.master,self.admin['id'],permissions)
        with self.assertRaises(ValueError):self.s.users.set_report_permissions(self.master,self.master['id'],[])
        self.s.users.set_user_active(self.master,self.admin['id'],False)
        with self.assertRaises(ValueError):self.s.users.set_report_permissions(self.master,self.admin['id'],[REPORT_ISSUES_PERMISSION])

    def test_revocacion_pdf_se_aplica_inmediatamente_sin_cambiar_version(self):
        self.s.users.set_report_permissions(self.master,self.admin['id'],[REPORT_ISSUES_PERMISSION],expected_version=self.admin['password_version'])
        self.assertIn(REPORT_ISSUES_PERMISSION,self.s.access.permissions(self.admin))
        self.s.users.revoke_grant(self.master,self.admin['id'],REPORT_ISSUES_PERMISSION)
        self.assertNotIn(REPORT_ISSUES_PERMISSION,self.s.access.permissions(self.admin))
        with self.assertRaises(AccessDenied):self.s.access.require_access(self.admin,REPORT_ISSUES_PERMISSION,action='PDF tras revocación')
        with self.assertRaises(AccessDenied):self.s.users.revoke_grant(self.master,self.master['id'],VIEWS[0])

    def test_eliminar_cuenta_retira_relaciones_y_preserva_auditoria(self):
        self.grant(self.admin,REPORT_ISSUES_PERMISSION)
        self.s.requests.submit_request(self.admin,'Registrar ejemplares','Necesito registrar')
        with self.s.connection:
            self.s.connection.execute("INSERT INTO api_sessions VALUES(?,?,?,?,?,?,?)",('hash-ficticio',self.admin['id'],self.admin['password_version'],'password',None,9999999999,'pc-ficticia'))
        self.s.users.delete_user(self.master,self.admin['id'],self.clave,expected_version=self.admin['password_version'])
        self.assertIsNone(self.s.access.current_user(self.admin))
        for table in ['grants','requests','user_security','recovery_codes','api_sessions']:
            self.assertEqual(self.s.connection.execute('SELECT count(*) FROM '+table+' WHERE user_id=?',(self.admin['id'],)).fetchone()[0],0)
        self.assertTrue(self.s.connection.execute("SELECT 1 FROM audit WHERE action LIKE 'Cuenta eliminada:%'").fetchone())
        self.assertIsNone(self.s.connection.execute('PRAGMA foreign_key_check').fetchone())

    def test_eliminar_protege_maestro_y_contrasena(self):
        with self.assertRaises(AccessDenied):self.s.users.delete_user(self.master,self.admin['id'],'Incorrecta#2026')
        with self.assertRaises(AccessDenied):self.s.users.delete_user(self.master,self.master['id'],self.clave)
        with self.assertRaises(ValueError):self.s.users.delete_user(self.master,999,self.clave)

    def test_reset_temporal_rota_codigo_e_invalida_sesiones(self):
        with self.assertRaises(AccessDenied):self.s.users.reset_password(self.master,self.admin['id'],'Incorrecta#2026','Nueva#2026')
        with self.assertRaises(ValueError):self.s.users.reset_password(self.master,self.admin['id'],self.clave,self.clave)
        code=self.s.users.reset_password(self.master,self.admin['id'],self.clave,'NuevaFicticia#2026',expected_version=self.admin['password_version'])
        self.assertTrue(code.startswith('HMR-'))
        with self.assertRaises(AccessDenied):self.s.access.require_access(self.admin,action='Actor previo')
        refreshed=self.s.auth.authenticate('V-12345679','NuevaFicticia#2026')
        self.assertTrue(refreshed['must_change_password'])
        with self.assertRaises(AccessDenied):self.s.access.require_access(refreshed,VIEWS[0],action='Consulta temporal')
        self.s.access.require_access(refreshed,action='Cambiar clave',allow_password_change=True)

    def test_listados_publicos_y_permisos_de_terceros(self):
        self.grant(self.admin,REPORT_ISSUES_PERMISSION)
        rows=self.s.users.users(self.master)
        self.assertEqual(len(rows),3)
        self.assertNotIn('password',rows[0].keys())
        self.assertEqual(self.s.users.buscar_usuarios(self.master,estado='Activo')['total'],3)
        for options in [dict(texto=None),dict(estado='inexistente')]:
            with self.assertRaises(ValueError):self.s.users.buscar_usuarios(self.master,**options)
        self.assertTrue(self.s.access.has_grant(self.admin,self.admin['id'],REPORT_ISSUES_PERMISSION))
        self.assertTrue(self.s.access.has_grant(self.master,self.admin['id'],REPORT_ISSUES_PERMISSION))
        with self.assertRaises(AccessDenied):self.s.access.has_grant(self.user,self.admin['id'],REPORT_ISSUES_PERMISSION)
        self.assertEqual(len(self.s.users.grants(self.master,self.admin['id'])),1)

    def test_permisos_se_recargan_y_concesion_erronea_no_eleva_usuario_regular(self):
        self.grant(self.user,REPORT_ISSUES_PERMISSION)
        self.assertNotIn(REPORT_ISSUES_PERMISSION,self.s.access.permissions(self.user))
        self.assertEqual(self.s.access.permissions(None),set())
        self.assertEqual(self.s.access.permissions({'id':999}),set())
        with self.s.connection:self.s.connection.execute('UPDATE users SET managed_permissions=0 WHERE id=?',(self.admin['id'],))
        self.assertTrue(set(LEGACY_ADMIN_ACCESS)<=self.s.access.permissions(self.admin))

    def test_vistas_de_catalogo_y_pdf_por_permiso_operativo(self):
        self.grant(self.admin,'Editar ejemplares')
        self.grant(self.admin,REPORT_ISSUES_PERMISSION)
        self.s.access.require_access(self.admin,VIEWS[1],action='Abrir catálogo',view=True)
        self.s.access.require_access(self.admin,VIEWS[6],action='Abrir reportes',view=True)
        with self.assertRaises(AccessDenied):self.s.access.require_access(self.admin,VIEWS[1],action='Operación de catálogo',view=False)

    def test_estado_sesion_y_etiqueta_de_actor_antiguo(self):
        self.assertEqual(self.s.access.estado_sesion(None),dict(usuario=None,permisos=[],requiere_configuracion=False))
        self.assertEqual(self.s.access.actor_label(None),'Sin sesión')
        with self.s.connection:self.s.connection.execute('UPDATE users SET password_version=password_version+1 WHERE id=?',(self.admin['id'],))
        self.assertIn(self.admin['identity'],self.s.access.actor_label(self.admin))
        with self.s.connection:self.s.connection.execute('DELETE FROM user_security WHERE user_id=?',(self.user['id'],))
        self.assertTrue(self.s.access.estado_sesion(self.user)['requiere_configuracion'])

    def test_host_anterior_no_escribe_y_rollback_conserva_denegacion(self):
        self.s.access.node_id='local'
        with self.s.connection:self.s.connection.execute("INSERT INTO system_settings VALUES('active_host_id','otro')")
        with self.assertRaises(AccessDenied):self.s.access.require_host_write()
        with self.assertRaises(AccessDenied):
            with self.s.access.authorized_write(self.master,action='Cambio ficticio'):
                self.fail('No debe entrar')
        self.assertFalse(self.s.connection.in_transaction)
        self.assertTrue(self.s.connection.execute("SELECT 1 FROM audit WHERE result='Acceso denegado'").fetchone())

    def test_generacion_recuperacion_vencida_no_autoriza(self):
        actor=dict(self.admin,_auth_method='recovery',_recovery_generation=-1)
        with self.assertRaises(AccessDenied):self.s.access.require_access(actor,action='Recuperación inválida',record=False)

    def test_formateo_no_borra_sin_clave_confirmacion_y_respaldo_en_disco(self):
        for clave,confirmation,error in [('Incorrecta#2026','FORMATEAR HEMEROTECA',AccessDenied),
                                         (self.clave,'confirmación incorrecta',ValueError),
                                         (self.clave,'FORMATEAR HEMEROTECA',ValueError)]:
            with self.assertRaises(error):self.s.users.formatear_aplicacion(self.master,clave,confirmation)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM users').fetchone()[0],3)
