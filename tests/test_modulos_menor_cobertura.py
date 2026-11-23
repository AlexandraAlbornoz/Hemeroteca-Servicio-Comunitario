"""Migración, recuperación, PDF y utilidades antes poco ejercitadas."""
import base64
from contextlib import closing
import importlib
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from hemeroteca.config.settings import SECURITY_QUESTIONS, ROLES, TITLES, REGIONAL
from hemeroteca.database.connection import connect_database
from hemeroteca.database.schema import initialize_schema, SCHEMA_VERSION
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services import recovery_service as recovery
from hemeroteca.utils.identity import normalize_document, valid_document
from hemeroteca.utils.pdf_reports import build_report


class PruebasUtilidadesDeEntrada(unittest.TestCase):
    """Ejercita entradas sin lanzar cuentas ni el programador de respaldos."""

    def test_documentos_historicos_ascii_y_validacion_booleana(self):
        for value, expected in [(' v-123 ','V-123'),('p-es-abc123','P-ES-ABC123'),('D-VE-123456','D-VE-123456')]:
            self.assertEqual(normalize_document(value),expected)
            self.assertTrue(valid_document(value))
        for value in [None,123,'V-１２３','correo@ejemplo.invalid','P-E-12345','V-123456789']:
            self.assertFalse(valid_document(value))
            with self.assertRaises(ValueError):normalize_document(value)

    def test_entradas_main_y_backup_conservan_contrato(self):
        with patch('hemeroteca.main.main') as main:
            runpy.run_module('hemeroteca',run_name='__main__')
            main.assert_called_once_with()
        with patch('hemeroteca.backup_worker.main',return_value=4) as worker:
            with self.assertRaises(SystemExit) as result:
                runpy.run_module('hemeroteca.backup_worker_entry',run_name='__main__')
            self.assertEqual(result.exception.code,4)
            worker.assert_called_once_with()
        importlib.import_module('hemeroteca.__main__')
        importlib.import_module('hemeroteca.backup_worker_entry')

    def test_icono_nativo_y_alternativa_png(self):
        from hemeroteca.utils.iconos import aplicar_icono
        window=Mock()
        with patch.object(sys,'platform','win32'):
            aplicar_icono(window)
        self.assertEqual(window.iconbitmap.call_count,2)
        image=object()
        with patch.object(sys,'platform','linux'),patch('tkinter.PhotoImage',return_value=image):
            aplicar_icono(window)
        window.iconphoto.assert_called_once_with(True,image)
        self.assertIs(window._imagen_icono_periodico,image)

    def test_verificador_instalacion_real_no_crea_archivos_de_datos(self):
        import json
        from hemeroteca.utils.verificacion_instalacion import verificar
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'resultado.json'
            with patch.object(sys,'argv',['hemeroteca','--verificar-instalacion',str(path)]):
                self.assertEqual(verificar(),0)
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertTrue(data['correcto'])
            self.assertEqual(data['sqlite'],'ok')
            self.assertEqual([p.name for p in Path(folder).iterdir()],['resultado.json'])

    def test_verificador_informa_error_con_y_sin_ventana(self):
        import json
        from hemeroteca.utils.verificacion_instalacion import verificar
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'resultado.json'
            with patch.object(sys,'argv',['app','--verificar-instalacion',str(path)]):
                with patch('hemeroteca.services.container.create_services',side_effect=ValueError('base ficticia no disponible')):
                    self.assertEqual(verificar(),1)
                self.assertFalse(json.loads(path.read_text(encoding='utf-8'))['correcto'])
                with patch('hemeroteca.utils.pdf_reports.build_report',side_effect=ValueError('pdf ficticio fallido')):
                    self.assertEqual(verificar(),1)
                self.assertIn('pdf ficticio',json.loads(path.read_text(encoding='utf-8'))['error'])


class PruebasMigracionDeRamas(unittest.TestCase):
    """SQLite real, esquema histórico mínimo y copia previa verificable."""

    def legacy(self,path=':memory:'):
        c=sqlite3.connect(path)
        c.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,identity TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE api_sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER,password_version INTEGER,
          method TEXT,recovery_generation INTEGER,expires_at INTEGER);
        CREATE TABLE requests(id INTEGER PRIMARY KEY,user_id INTEGER,permission TEXT,reason TEXT,
          status TEXT DEFAULT 'Pendiente',created_at TEXT,decided_by TEXT,decided_at TEXT);
        CREATE TABLE master_recovery(user_id INTEGER,question_1 TEXT,answer_1 TEXT,question_2 TEXT,answer_2 TEXT,
          question_3 TEXT,answer_3 TEXT,failed_attempts INTEGER,locked_until INTEGER);
        INSERT INTO users VALUES(1,'Una Ficticia',' v-12345678 ','hash-fixture','Usuario regular',1,'2020-01-01');
        INSERT INTO users VALUES(2,'Otra Ficticia','V-12345678','hash-fixture','Usuario regular',1,'2020-01-01');
        INSERT INTO users VALUES(3,'Sin documento','correo@ejemplo.invalid','hash-fixture','Usuario regular',1,'2020-01-01');
        INSERT INTO api_sessions VALUES('hash-fixture',1,0,'password',NULL,9999999999);
        INSERT INTO master_recovery VALUES(1,'Q1','hash-fixture','Q2','hash-fixture','Q3','hash-fixture',0,0);
        ''')
        return c

    def test_migracion_completa_conserva_cuentas_y_retira_sesiones_antiguas(self):
        with closing(self.legacy()) as c:
            initialize_schema(c)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],3)
            self.assertEqual(c.execute('SELECT document FROM users WHERE id=2').fetchone()[0],'V-12345678')
            self.assertIsNone(c.execute('SELECT document FROM users WHERE id=1').fetchone()[0])
            self.assertIsNone(c.execute('SELECT document FROM users WHERE id=3').fetchone()[0])
            self.assertEqual(c.execute('SELECT count(*) FROM api_sessions').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT question_1 FROM user_security WHERE user_id=1').fetchone()[0],'Q1')
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='master_recovery'").fetchone())

    def test_respaldo_previo_contiene_esquema_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'prueba.db'
            self.legacy(path).close()
            with closing(connect_database(path)) as c:
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            backups=list((Path(folder)/'backups').glob('*.db'))
            self.assertEqual(len(backups),1)
            with closing(sqlite3.connect(backups[0])) as original:
                self.assertEqual(original.execute('PRAGMA user_version').fetchone()[0],0)
                self.assertEqual(original.execute('SELECT count(*) FROM api_sessions').fetchone()[0],1)

    def test_fechas_heredadas_validas_invalidas_y_documento_duplicado(self):
        with closing(connect_database(':memory:')) as c:
            with c:
                for index,value in enumerate(['2020-01-01T10:00:00+00:00','texto histórico',None],1):
                    c.execute('INSERT INTO absent_dates(title,kind,year,month,day,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',
                              (str(index),'Nacional',2020,1,index,'','Fixture',value or ''))
                c.execute('PRAGMA user_version=0')
            initialize_schema(c)
            rows=c.execute('SELECT created_at FROM absent_dates ORDER BY id').fetchall()
            self.assertEqual(rows[0][0],'2020-01-01T10:00:00+00:00')
            self.assertEqual(rows[1][0],'texto histórico')

    def test_migracion_fallida_revierte_alteraciones(self):
        with closing(self.legacy()) as c:
            c.execute("CREATE TRIGGER impedir_migracion BEFORE UPDATE ON users BEGIN SELECT RAISE(ABORT,'fallo ficticio'); END")
            # Una tabla heredada inválida hace fallar la copia dentro de la transacción.
            c.execute('ALTER TABLE master_recovery RENAME COLUMN question_1 TO columna_incompatible')
            c.commit()
            with self.assertRaises(sqlite3.Error):initialize_schema(c)
            columns={r[1] for r in c.execute('PRAGMA table_info(users)')}
            self.assertNotIn('document',columns)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],0)

    def test_conexion_cierra_si_falla_inicializacion(self):
        from hemeroteca.database import connection
        real=sqlite3.connect(':memory:')
        with patch.object(connection.sqlite3,'connect',return_value=real),patch.object(connection,'initialize_schema',side_effect=ValueError('fallo ficticio')):
            with self.assertRaises(ValueError):connection.connect_database(':memory:')
        with self.assertRaises(sqlite3.ProgrammingError):real.execute('SELECT 1')

    def test_base_de_version_futura_no_se_reescribe(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'futura.db'
            with closing(sqlite3.connect(path)) as c:
                c.execute('CREATE TABLE conservada(valor TEXT)')
                c.execute("INSERT INTO conservada VALUES('dato ficticio')")
                c.execute(f'PRAGMA user_version={SCHEMA_VERSION+1}')
                c.commit()
            before=path.read_bytes()
            with self.assertRaises(ValueError),closing(connect_database(path)):pass
            self.assertEqual(path.read_bytes(),before)


class PruebasRecuperacionPendiente(unittest.TestCase):
    """Recuperación real sobre copias de una semilla sin datos personales."""

    @classmethod
    def setUpClass(cls):
        cls.seed=create_services(':memory:')
        cls.questions=tuple(zip(SECURITY_QUESTIONS[:3],('Luna','Sol','Mar')))
        cls.clave='Prueba#2026'
        cls.seed.auth.create_master('Maestra Ficticia','V-12345678',cls.clave,cls.questions)
        cls.seed.users.register_user('Persona Ficticia','V-12345679',cls.clave,cls.questions)
        cls.actors=[cls.seed.auth.authenticate(doc,cls.clave) for doc in ['V-12345678','V-12345679']]

    @classmethod
    def tearDownClass(cls):cls.seed.close()

    def setUp(self):
        self.s=create_services(':memory:')
        self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
        self.master,self.actor=[dict(a) for a in self.actors]

    def test_preguntas_inmutables_clave_incorrecta_y_configuracion_inicial(self):
        with self.assertRaises(ValueError):self.s.recovery.configure_questions(self.actor,self.clave,self.questions)
        with self.s.connection:self.s.connection.execute('DELETE FROM user_security WHERE user_id=?',(self.actor['id'],))
        self.assertTrue(self.s.recovery.needs_configuration(self.actor))
        self.assertEqual(self.s.recovery.configured_questions(self.actor),())
        with self.assertRaises(AccessDenied):self.s.recovery.configure_questions(self.actor,'Incorrecta#2026',self.questions)
        self.s.recovery.configure_questions(self.actor,self.clave,self.questions)
        self.assertEqual(self.s.recovery.configured_questions(self.actor),tuple(q for q,a in self.questions))
        self.assertFalse(self.s.recovery.needs_configuration(None))
        self.assertFalse(self.s.recovery.needs_code(None))

    def test_codigo_inicial_no_se_repite_y_renovacion_exige_clave(self):
        with self.assertRaises(ValueError):self.s.recovery.enroll_code(self.actor)
        with self.assertRaises(AccessDenied):self.s.recovery.renovar_codigo_propio(self.actor,'Incorrecta#2026')
        with self.s.connection:self.s.connection.execute('DELETE FROM recovery_codes WHERE user_id=?',(self.actor['id'],))
        code=self.s.recovery.enroll_code(self.actor)
        self.assertTrue(code.startswith('HMR-'))
        self.assertNotEqual(code,self.s.recovery.renovar_codigo_propio(self.actor,self.clave))

    def test_regeneracion_maestro_valida_destinatario_clave_y_version(self):
        for user,clave,version,error in [(self.actor['id'],'Incorrecta#2026',None,AccessDenied),
                                       (99,self.clave,None,ValueError),(self.actor['id'],self.clave,-1,ValueError)]:
            with self.assertRaises(error):self.s.recovery.regenerate_code(self.master,user,clave,expected_version=version)
        code=self.s.recovery.regenerate_code(self.master,self.actor['id'],self.clave,expected_version=self.actor['password_version'])
        self.assertTrue(code.startswith('HMR-'))

    def test_api_historica_recupera_por_preguntas_y_cambia_clave(self):
        self.assertEqual(self.s.recovery.questions_for_recovery('V-12345679'),[q for q,a in self.questions])
        user=self.s.recovery.recover_password('V-12345679',[a for q,a in self.questions])
        self.assertTrue(user['must_change_password'])
        self.assertEqual(user['_auth_method'],'recovery')

    def test_recuperacion_clave_invalida_no_altera_cuenta_y_exito_emite_codigo(self):
        with self.assertRaises(ValueError):self.s.recovery.recover_password('V-12345679',['Luna','Sol','Mar'],'débil')
        self.assertFalse(self.s.auth.authenticate('V-12345679',self.clave)['must_change_password'])
        result=self.s.recovery.recover_password('V-12345679',['Luna','Sol','Mar'],'NuevaFicticia#2026')
        self.assertTrue(result['_new_recovery_code'].startswith('HMR-'))
        self.s.auth.authenticate('V-12345679','NuevaFicticia#2026')

    def test_colisiones_de_codigo_reintentan_y_agotamiento_no_deja_cambios(self):
        with self.s.connection,patch.object(recovery.secrets,'choice',return_value='A'):
            recovery.issue_recovery_code(self.s.connection,self.actor['id'])
        before=self.s.connection.execute('SELECT generation FROM recovery_codes WHERE user_id=?',(self.actor['id'],)).fetchone()[0]
        with self.assertRaises(RuntimeError),self.s.connection,patch.object(recovery.secrets,'choice',return_value='A'):
            recovery.issue_recovery_code(self.s.connection,self.actor['id'])
        self.assertEqual(self.s.connection.execute('SELECT generation FROM recovery_codes WHERE user_id=?',(self.actor['id'],)).fetchone()[0],before)
        with self.s.connection,patch.object(recovery.secrets,'choice',side_effect=['A']*30+['B']*30):
            code=recovery.issue_recovery_code(self.s.connection,self.actor['id'])
        self.assertIn('BBBBB',code)

    def test_reportes_invalidos_revierte_transaccion_sin_exportar(self):
        for options in [dict(scope='desconocido'),dict(filters=[]),dict(filters={'campo_invalido':1}),
                        dict(scope='database',filters={'year':2020}),dict(filters={'year':'2020'})]:
            with self.subTest(options=options),self.assertRaises(ValueError):
                self.s.reports.generate(self.master,**options)
            self.assertFalse(self.s.connection.in_transaction)

    def test_pdf_excesivo_no_se_entrega_ni_registra_exito(self):
        class ContenidoExcesivo:
            def __len__(self):return 64*1024*1024+1
        before=self.s.connection.execute('SELECT count(*) FROM audit WHERE action LIKE ?',('Reporte PDF generado:%',)).fetchone()[0]
        with patch('hemeroteca.utils.pdf_reports.build_report',return_value=ContenidoExcesivo()):
            with self.assertRaisesRegex(ValueError,'64 MiB'):self.s.reports.generate(self.master)
        after=self.s.connection.execute('SELECT count(*) FROM audit WHERE action LIKE ?',('Reporte PDF generado:%',)).fetchone()[0]
        self.assertEqual(after,before)


class PruebasPDFSecciones(unittest.TestCase):
    """Composición real de todas las secciones sin datos privados."""

    def data(self):
        record=dict(id=1,title='Diario <Ficticio>',kind='Nacional',day=1,month=1,year=2020,
                    edition='',number='',shelf='',drawer='',status='Disponible',created_at='2020-01-01',created_by='Fixture',
                    note='Nota\ncon & texto',name='Persona Ficticia',document='V-12345678',role=ROLES[2],active=False,
                    permission='Consulta',reason='Prueba',decided_by=None,decided_at=None,response=None,at='2020-01-01',
                    user='Fixture',action='Acción',result='Completado',approved_by='Maestra Ficticia',approved_at='2020-01-01')
        return dict(scope='database',generated_at='2026-11-19',generated_by='Fixture',filters={},
                    sections=[dict(type=t,title=t,rows=[record]) for t in ['issues','absent','users','grants','requests','audit','devices']])

    def test_pdf_general_incluye_todas_secciones_y_escapa_texto(self):
        from reportlab.platypus import Paragraph,SimpleDocTemplate
        data=self.data()
        original=SimpleDocTemplate.build
        paragraphs=[]
        def inspect(doc,story,**kwargs):
            paragraphs.extend(p.text for p in story if isinstance(p,Paragraph))
            return original(doc,story,**kwargs)
        with patch.object(SimpleDocTemplate,'build',inspect):
            pdf=build_report(data)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf),10000)
        self.assertIn('Reporte general de Hemeroteca',paragraphs)

    def test_reportlab_ausente_da_instruccion_vigente(self):
        with patch.dict(sys.modules,{'reportlab':None}):
            with self.assertRaisesRegex(ValueError,'README'):
                build_report(self.data())

    def test_seccion_desconocida_se_rechaza(self):
        data=self.data()
        data['sections']=[dict(type='desconocida',title='No válida',rows=[{}])]
        with self.assertRaisesRegex(ValueError,'desconocida'):build_report(data)

    def test_reporte_general_servicio_excluye_credenciales(self):
        # La semilla se crea sin cuentas para mantener el PDF completamente sintético.
        with closing(create_services(':memory:')) as s:
            s.auth.create_master('Maestra Ficticia','V-12345678','Prueba#2026',tuple(zip(SECURITY_QUESTIONS[:3],('Luna','Sol','Mar'))))
            actor=s.auth.authenticate('V-12345678','Prueba#2026')
            from hemeroteca.utils import pdf_reports
            real=pdf_reports.build_report
            with patch.object(pdf_reports,'build_report',wraps=real) as build:
                output=s.reports.generate(actor,scope='database')
            self.assertTrue(base64.b64decode(output['content']).startswith(b'%PDF-'))
            sections=build.call_args.args[0]['sections']
            users=next(section['rows'] for section in sections if section['type']=='users')
            self.assertNotIn('password',users[0])
            self.assertNotIn('password_version',users[0])

