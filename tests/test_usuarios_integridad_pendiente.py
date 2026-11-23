"""Formateo con SQLite real, fallos de respaldo y cuentas menos ejercitadas."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock,patch
from hemeroteca.config.settings import SECURITY_QUESTIONS,ROLES
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services import user_service as module
from hemeroteca.utils.dates import display_date
from hemeroteca.utils.security import prepare_security_questions


class ConexionControlada:
    """Conserva la conexión real y permite inyectar solo el resultado de integridad."""
    def __init__(self,conn,integrity=None,foreign=None):
        self.conn=conn;self.integrity=integrity;self.foreign=foreign;self.closed=False
    def execute(self,sql,*args):
        if sql=='PRAGMA integrity_check' and self.integrity is not None:return Mock(fetchone=lambda:(self.integrity,))
        if sql=='PRAGMA foreign_key_check' and self.foreign is not None:return Mock(fetchone=lambda:self.foreign)
        return self.conn.execute(sql,*args)
    def backup(self,dest):self.conn.backup(dest.conn if isinstance(dest,ConexionControlada) else dest)
    def close(self):self.closed=True;self.conn.close()
    def __getattr__(self,name):return getattr(self.conn,name)


class PruebasUsuariosIntegridadPendiente(unittest.TestCase):
    """Cada prueba usa una copia de la semilla en una base temporal propia."""
    @classmethod
    def setUpClass(cls):
        cls.seed=create_services(':memory:');cls.clave='Prueba#2026'
        cls.questions=tuple(zip(SECURITY_QUESTIONS[:3],('Luna','Sol','Mar')))
        cls.seed.auth.create_master('Maestra Ficticia','V-12345678',cls.clave,cls.questions)
        cls.master=dict(cls.seed.auth.authenticate('V-12345678',cls.clave))
    @classmethod
    def tearDownClass(cls):cls.seed.close()
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'coleccion.db'
        self.s=create_services(self.path);self.addCleanup(self.s.close)
        self.seed.connection.backup(self.s.connection)
    def preserved(self):
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM users').fetchone()[0],1)
        self.assertEqual(self.s.connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_fallo_al_abrir_destino_cierra_origen_y_no_borra(self):
        real=sqlite3.connect;opened=[]
        def connect(path,*args,**kw):
            if kw.get('uri'):
                c=ConexionControlada(real(path,*args,**kw));opened.append(c);return c
            raise OSError('destino sin espacio')
        with patch.object(module.sqlite3,'connect',side_effect=connect),self.assertRaises(OSError):
            self.s.users.formatear_aplicacion(self.master,self.clave,'FORMATEAR HEMEROTECA')
        self.assertEqual(len(opened),1);self.assertTrue(opened[0].closed);self.preserved()

    def test_respaldo_sin_integridad_no_borra_y_cierra_conexiones(self):
        real=sqlite3.connect;opened=[]
        def connect(path,*args,**kw):
            c=ConexionControlada(real(path,*args,**kw),integrity=None if kw.get('uri') else 'error simulado')
            opened.append(c);return c
        with patch.object(module.sqlite3,'connect',side_effect=connect),self.assertRaisesRegex(ValueError,'verificar la copia'):
            self.s.users.formatear_aplicacion(self.master,self.clave,'FORMATEAR HEMEROTECA')
        self.assertTrue(all(c.closed for c in opened));self.preserved()

    def test_fallo_claves_foraneas_revierte_borrado(self):
        proxy=ConexionControlada(self.s.connection,foreign=('tabla',1,'padre',0))
        with patch.object(self.s.users,'conn',proxy),self.assertRaisesRegex(ValueError,'integridad'):
            self.s.users.formatear_aplicacion(self.master,self.clave,'FORMATEAR HEMEROTECA')
        self.preserved()
        copies=list(self.path.parent.glob('backups/*.db'));self.assertEqual(len(copies),1)
        with closing(sqlite3.connect(copies[0])) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM users').fetchone()[0],1)

    def test_revalidacion_contrasena_dentro_transaccion_no_borra(self):
        with patch.object(module,'password_matches',side_effect=[True,False]),self.assertRaisesRegex(AccessDenied,'cambió'):
            self.s.users.formatear_aplicacion(self.master,self.clave,'FORMATEAR HEMEROTECA')
        self.preserved();self.assertFalse((self.path.parent/'backups').exists())

    def test_consultar_usuario_existente_ausente_y_sin_acceso(self):
        row=self.s.users.get_user(self.master,self.master['id']);self.assertEqual(row['document'],'V-12345678')
        self.assertNotIn('password',row.keys())
        self.assertIsNone(self.s.users.get_user(self.master,999))
        with self.assertRaises(AccessDenied):self.s.users.get_user(None,self.master['id'])

    def test_editar_maestra_preserva_perfil_y_version(self):
        self.s.users.update_user(self.master,self.master['id'],'Maestra Actualizada','V-12345678',ROLES[0],self.clave,expected_version=self.master['password_version'])
        row=self.s.connection.execute('SELECT * FROM users').fetchone()
        self.assertEqual(row['name'],'Maestra Actualizada');self.assertEqual(row['role'],ROLES[0])

    def test_fecha_invalida_y_pregunta_repetida_son_controladas(self):
        for value,expected in [('fecha dañada','fecha dañada'),(None,'—'),('', '—')]:self.assertEqual(display_date(value),expected)
        with self.assertRaisesRegex(ValueError,'diferentes'):prepare_security_questions([self.questions[0]]*3)
