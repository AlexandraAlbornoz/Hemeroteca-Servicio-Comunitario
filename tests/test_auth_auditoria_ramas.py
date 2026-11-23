"""Autenticación histórica, cambios concurrentes y filtros de auditoría reales."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hemeroteca.config.settings import ROLES,SECURITY_QUESTIONS
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services import auth_service as module


class PruebasAuthAuditoriaRamas(unittest.TestCase):
    """Inyecta cambios confirmados entre fases sin reemplazar las comprobaciones de contraseña."""

    @classmethod
    def setUpClass(cls):
        cls.seed=create_services(':memory:')
        cls.clave='Prueba#2026'
        cls.questions=tuple(zip(SECURITY_QUESTIONS[:3],('Luna','Sol','Mar')))
        cls.seed.auth.create_master('Maestra Ficticia','V-12345678',cls.clave,cls.questions)
        cls.registration=cls.seed.users.register_user('Persona Ficticia','V-12345679',cls.clave,cls.questions,role=ROLES[1])
        cls.actors=[cls.seed.auth.authenticate(doc,cls.clave) for doc in ['V-12345678','V-12345679']]

    @classmethod
    def tearDownClass(cls):cls.seed.close()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s=create_services(Path(self.temp.name)/'prueba.db')
        self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
        self.master,self.actor=[dict(a) for a in self.actors]

    def legacy(self):
        with self.s.connection:
            self.s.connection.execute("UPDATE users SET document=NULL,identity='legacy@fixture.invalid',active=1 WHERE id=?",(self.actor['id'],))

    def test_migracion_historica_verifica_clave_y_conserva_datos(self):
        self.legacy()
        self.assertEqual(self.s.auth.migration_accounts()[0]['id'],self.actor['id'])
        with self.assertRaises(AccessDenied):self.s.auth.migrate_document(self.actor['id'],'Incorrecta#2026','V-22222222')
        user=self.s.auth.migrate_document(self.actor['id'],self.clave,'V-22222222')
        self.assertEqual(user['id'],self.actor['id'])
        self.assertEqual(user['document'],'V-22222222')
        self.assertEqual(user['password_version'],self.actor['password_version']+1)
        self.assertEqual(self.s.auth.migration_accounts(),[])

    def test_migracion_revalida_version_estado_y_documento_antes_de_escribir(self):
        original=module.password_matches
        for sql,expected in [('UPDATE users SET password_version=password_version+1 WHERE id=?',None),
                             ('UPDATE users SET active=0 WHERE id=?',None),
                             ("UPDATE users SET document='V-33333333' WHERE id=?",'V-33333333')]:
            self.legacy()
            injected=False
            def check(*args):
                nonlocal injected
                valid=original(*args)
                if not injected:
                    injected=True
                    with self.s.connection:self.s.connection.execute(sql,(self.actor['id'],))
                return valid
            before=self.s.connection.execute("SELECT count(*) FROM audit WHERE action='Documento de cuenta anterior registrado'").fetchone()[0]
            with self.subTest(sql=sql),patch.object(module,'password_matches',side_effect=check),self.assertRaises(AccessDenied):
                self.s.auth.migrate_document(self.actor['id'],self.clave,'V-22222222')
            self.assertEqual(self.s.connection.execute('SELECT document FROM users WHERE id=?',(self.actor['id'],)).fetchone()[0],expected)
            self.assertEqual(self.s.connection.execute("SELECT count(*) FROM audit WHERE action='Documento de cuenta anterior registrado'").fetchone()[0],before)

    def test_preguntas_ajenas_no_disponibles_y_respuestas_malformadas(self):
        with self.assertRaises(AccessDenied):self.s.auth.obtener_preguntas_recuperacion('V-99999999')
        for answers in [None,[],['Una'],['Luna','Sol',None],['x'*201,'Sol','Mar']]:
            with self.subTest(answers=answers),self.assertRaises(ValueError):self.s.auth.autenticar_con_preguntas('V-12345679',answers)

    def test_preguntas_revalidan_cambio_confirmado_y_recrean_codigo_faltante(self):
        original=module.password_matches
        injected=False
        def check(*args):
            nonlocal injected
            valid=original(*args)
            if not injected:
                injected=True
                with self.s.connection:self.s.connection.execute('UPDATE users SET password_version=password_version+1 WHERE id=?',(self.actor['id'],))
            return valid
        with patch.object(module,'password_matches',side_effect=check),self.assertRaises(AccessDenied):
            self.s.auth.autenticar_con_preguntas('V-12345679',['Luna','Sol','Mar'])
        with self.s.connection:self.s.connection.execute('DELETE FROM recovery_codes WHERE user_id=?',(self.actor['id'],))
        actor=self.s.auth.autenticar_con_preguntas('V-12345679',['Luna','Sol','Mar'])
        self.assertTrue(actor['recovery_pending'])
        self.assertTrue(self.s.connection.execute('SELECT 1 FROM recovery_codes WHERE user_id=?',(self.actor['id'],)).fetchone())

    def test_codigo_rotado_entre_lecturas_no_abre_recuperacion(self):
        original=module.recovery_digest
        injected=False
        def digest(code):
            nonlocal injected
            result=original(code)
            if not injected:
                injected=True
                with self.s.connection:self.s.connection.execute("UPDATE recovery_codes SET code_hash=?,generation=generation+1 WHERE user_id=?",('f'*64,self.actor['id']))
            return result
        with patch.object(module,'recovery_digest',side_effect=digest),self.assertRaises(AccessDenied):
            self.s.auth.authenticate_with_code('V-12345679',self.registration.recovery_code)
        self.assertEqual(self.s.connection.execute('SELECT recovery_pending FROM users WHERE id=?',(self.actor['id'],)).fetchone()[0],0)

    def test_bloqueo_no_se_elude_y_verificacion_maestra_rechaza_clave(self):
        with self.assertRaises(AccessDenied):self.s.auth.verify_master(self.master,'Incorrecta#2026')
        key=self.s.auth._attempt_key('V-12345679','password')
        with self.s.connection:self.s.connection.execute('INSERT INTO auth_failures VALUES(?,?,?)',(key,5,9999999999))
        with self.assertRaises(AccessDenied):self.s.auth.authenticate('V-12345679',self.clave)

    def test_auditoria_filtros_historicos_y_listado_autorizado(self):
        self.s.audit.record('Persona Ficticia','Evento de prueba','Completado')
        self.s.audit.record('Otra Persona','Evento rechazado','Acceso denegado')
        with self.s.connection:self.s.connection.execute("INSERT INTO audit(at,user,action,result) VALUES('19/11/2026 08:30:00','Persona Ficticia','Evento histórico','Completado')")
        result=self.s.audit.buscar_eventos(self.master,fecha='2026-11-19',hora='08:30',usuario='Persona',accion='histórico',resultado='Completado')
        self.assertEqual(result['total'],1)
        self.assertIn('Evento histórico',self.s.audit.acciones_disponibles(self.master))
        self.assertIn('Acceso denegado',self.s.audit.resultados_disponibles(self.master))
        self.assertTrue(self.s.audit.list_events(self.master))
        for options in [dict(hora=None),dict(usuario=123),dict(fecha='incorrecta')]:
            with self.assertRaises(ValueError):self.s.audit.buscar_eventos(self.master,**options)
