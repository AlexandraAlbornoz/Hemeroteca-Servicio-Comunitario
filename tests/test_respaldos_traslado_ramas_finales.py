"""Fronteras de respaldo/traslado y permisos del catálogo con SQLite real."""
import base64
import sqlite3
import unittest
from unittest.mock import Mock,patch
from hemeroteca.config.settings import ROLES,VIEWS,TITLES,REGIONAL
from hemeroteca.services import backup_archive as archive
from hemeroteca.network import manager as net
from hemeroteca.services.access_service import AccessDenied
from tests import test_gestion_red as fixtures


class ConexionInspeccion:
    """Intercepta solo integridad y registra el cierre de la conexión real."""
    def __init__(self,conn):self.conn=conn;self.closed=False
    def execute(self,sql,*args):
        if sql=='PRAGMA integrity_check':return Mock(fetchone=lambda:('dañada',),fetchall=lambda:[('dañada',)])
        return self.conn.execute(sql,*args)
    def close(self):self.closed=True;self.conn.close()
    def __getattr__(self,name):return getattr(self.conn,name)


class PruebasRespaldosTrasladoFinales(unittest.TestCase):
    """Reutiliza la semilla y los cierres, sin heredar pruebas anteriores."""
    setUpClass=classmethod(fixtures.PruebasGestionRed.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.PruebasGestionRed.tearDownClass.__func__)
    setUp=fixtures.PruebasGestionRed.setUp
    snapshot=fixtures.PruebasGestionRed.snapshot
    remoto=fixtures.PruebasGestionRed.remoto

    def test_importacion_malformada_no_modifica_base_ni_crea_temporal(self):
        valid=self.snapshot('destino');before=self.manager.database.read_bytes()
        for value in [None,[],{},dict(valid,database=None),dict(valid,sha256=12),dict(valid,sha256='á'*64)]:
            with self.subTest(value=type(value).__name__),self.assertRaises(ValueError):self.manager._import_snapshot(value,'destino')
            self.assertEqual(self.manager.database.read_bytes(),before)
            self.assertFalse(self.manager.database.with_suffix('.incoming.db').exists())

    def test_importacion_integridad_invalida_retira_temporal(self):
        valid=self.snapshot('destino');before=self.manager.database.read_bytes()
        real=sqlite3.connect;opened=[]
        def connect(*a,**kw):
            c=ConexionInspeccion(real(*a,**kw));opened.append(c);return c
        with patch.object(net.sqlite3,'connect',side_effect=connect),self.assertRaisesRegex(ValueError,'integridad'):
            self.manager._import_snapshot(valid,'destino')
        self.assertTrue(all(c.closed for c in opened));self.assertEqual(self.manager.database.read_bytes(),before)
        self.assertFalse(self.manager.database.with_suffix('.incoming.db').exists())

    def test_configurar_servidor_remoto_delega_promocion(self):
        remote=self.remoto();remote.auth=Mock()
        with patch.object(net,'ensure_certificate',return_value=(object(),'a'*64)),patch.object(self.manager,'_promote',return_value='promovido') as promote:
            result=self.manager.configure_server(remote,self.master,fixtures.CLAVE,'127.0.0.1',8766)
        self.assertEqual(result,'promovido');remote.auth.verify_master.assert_called_once()
        self.assertEqual(promote.call_args.args[3]['port'],8766)

    def test_validar_base_fallo_segunda_apertura_cierra_primera(self):
        real=sqlite3.connect;first=ConexionInspeccion(real(':memory:'))
        self.addCleanup(first.close)
        with patch.object(archive.sqlite3,'connect',side_effect=[first,OSError('sin recursos')]),self.assertRaises(OSError):
            archive.validated_database(b'no se llega a leer')
        self.assertTrue(first.closed)

    def test_validar_base_integridad_invalida_cierra_ambas(self):
        content=base64.b64decode(self.snapshot('destino')['database']);real=sqlite3.connect;opened=[]
        def connect(*a,**kw):
            conn=real(*a,**kw)
            if not opened:conn=ConexionInspeccion(conn)
            opened.append(conn);return conn
        with patch.object(archive.sqlite3,'connect',side_effect=connect),self.assertRaisesRegex(ValueError,'dañada'):
            archive.validated_database(content)
        self.assertTrue(opened[0].closed)
        with self.assertRaises(sqlite3.ProgrammingError):opened[1].execute('SELECT 1')

    def test_instantanea_comprueba_limite_despues_de_serializar(self):
        source=Mock(wraps=self.s.connection)
        # Simula un proveedor que no entrega progreso; se conserva el límite final.
        source.backup.side_effect=lambda target,**kw:self.s.connection.backup(target)
        with patch.object(archive,'MAX_DATABASE',1),self.assertRaisesRegex(ValueError,'256 MiB'):archive.snapshot(source)
        source.backup.assert_called_once()

    def test_catalogo_autoriza_alta_admin_sin_bandera_legacy(self):
        with self.s.connection:
            self.s.connection.execute('UPDATE users SET role=?,managed_permissions=1 WHERE id=?',(ROLES[1],self.user['id']))
            self.s.connection.execute('INSERT INTO grants(user_id,permission) VALUES(?,?)',(self.user['id'],VIEWS[1]))
        actor=dict(self.s.connection.execute('SELECT * FROM users WHERE id=?',(self.user['id'],)).fetchone())
        values=(TITLES[0],'Regional' if TITLES[0] in REGIONAL else 'Nacional','Matutina',2026,1,1,'1','1','','Disponible')
        self.s.periodicos.save_record(actor,values)
        self.assertEqual(self.s.connection.execute('SELECT count(*) FROM issues').fetchone()[0],1)

    def test_fecha_sin_publicacion_existe_y_requiere_maestro(self):
        self.assertFalse(self.s.periodicos.has_absent_date(self.master,TITLES[0],2026,1,1))
        values=(TITLES[0],'Regional' if TITLES[0] in REGIONAL else 'Nacional',2026,1,1,'Motivo ficticio')
        self.s.periodicos.save_record(self.master,values,absent=True)
        self.assertTrue(self.s.periodicos.has_absent_date(self.master,TITLES[0],2026,1,1))
        with self.assertRaises(AccessDenied):self.s.periodicos.has_absent_date(self.user,TITLES[0],2026,1,1)
