"""Contratos de paginación, alcance de solicitudes y estilos reutilizados."""
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from hemeroteca.config.settings import NATIONAL, PERMISSIONS, SECURITY_QUESTIONS, ROLES
from hemeroteca.services.container import create_services
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.ui.components import UIComponents


class PruebasServiciosCompartidos(unittest.TestCase):
    """Comprueba resultados públicos de los servicios sobre datos sintéticos."""

    @classmethod
    def setUpClass(cls):
        """Crea una semilla con dos usuarios, solicitudes y siete ejemplares."""
        cls.semilla = create_services(':memory:')
        preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        cls.semilla.auth.create_master('Maestro Prueba', 'V-12345678', 'Prueba#2026', preguntas)
        maestro = cls.semilla.auth.authenticate('V-12345678', 'Prueba#2026')
        cls.id_maestro = maestro['id']
        cls.id_usuario = cls.semilla.users.create_user('Usuario Prueba', 'V-12345679', 'Prueba#2026', security_answers=['Luna','María','Caracas']).user_id
        cls.id_otro = cls.semilla.users.create_user('Otra Persona', 'V-12345680', 'Prueba#2026', security_answers=['Luna','María','Caracas']).user_id
        for dia in range(1,8):
            cls.semilla.periodicos.save_record(maestro, (NATIONAL[0], 'Nacional', 'Matutina', 2020, 1, dia, str(dia), '1', '', 'Disponible'))
        for dia, nota in ((1,'Anotación'), (2,''), (3,'Otra nota')):
            cls.semilla.periodicos.save_record(maestro, (NATIONAL[1],'Nacional',2020,1,dia,nota), absent=True)

    @classmethod
    def tearDownClass(cls):
        """Libera la conexión semilla al terminar las pruebas de servicios."""
        cls.semilla.close()

    def setUp(self):
        """Copia la semilla para que ninguna prueba herede cambios de otra."""
        self.servicios = create_services(':memory:')
        self.semilla.connection.backup(self.servicios.connection)
        self.maestro = dict(self.servicios.connection.execute('SELECT * FROM users WHERE id=?',(self.id_maestro,)).fetchone())
        self.usuario = dict(self.servicios.connection.execute('SELECT * FROM users WHERE id=?',(self.id_usuario,)).fetchone())
        self.otro = dict(self.servicios.connection.execute('SELECT * FROM users WHERE id=?',(self.id_otro,)).fetchone())

    def tearDown(self):
        """Cierra la copia independiente de la prueba."""
        self.servicios.close()

    def test_ultimos_cinco_y_ultima_pagina(self):
        """El límite de últimos cinco se aplica al total y no solo a la página visible."""
        resultado = self.servicios.periodicos.search_issues(self.maestro,period='Últimos 5 registros',page=99,page_size=2)
        self.assertEqual((resultado['total'],resultado['pages'],resultado['page'],resultado['page_size']),(5,3,3,2))
        self.assertEqual([fila['day'] for fila in resultado['items']],[3])
        self.assertEqual(set(resultado),{'items','total','pages','page','page_size'})

    def test_ausencias_filtradas_y_resultado_vacio(self):
        """La paginación compartida conserva observaciones, rango y metadatos vacíos."""
        resultado = self.servicios.periodicos.buscar_fechas_ausentes(self.maestro,observaciones='Con observación',page=99,page_size=1)
        self.assertEqual((resultado['total'],resultado['page']), (2,2))
        self.assertEqual(resultado['items'][0]['day'],1)
        vacio = self.servicios.periodicos.buscar_fechas_ausentes(self.maestro,desde='2021-01-01',page=99)
        self.assertEqual((vacio['items'],vacio['total'],vacio['pages'],vacio['page']),([],0,1,1))

    def test_paginacion_rechaza_booleanos_y_conserva_mensajes(self):
        """Se conservan los mensajes de cada API y la validación previa de los límites."""
        for metodo,mensaje in ((self.servicios.periodicos.search_issues,'La página y el tamaño de página no son válidos.'),
                               (self.servicios.periodicos.buscar_fechas_ausentes,'La página o su tamaño no son válidos.')):
            for argumentos in ({'page':True},{'page':0},{'page_size':101},{'page_size':False}):
                with self.assertRaises(ValueError) as error:
                    metodo(self.maestro,**argumentos)
                self.assertEqual(str(error.exception),mensaje)

    def test_permisos_disponibles_conservan_alcance_y_actualizacion(self):
        """Pendientes ajenos no afectan al usuario común; concesiones y revocaciones se leen de nuevo."""
        self.servicios.connection.execute('UPDATE users SET role=?,managed_permissions=1 WHERE id IN (?,?)',
                                         (ROLES[1], self.id_usuario, self.id_otro))
        self.servicios.connection.commit()
        solicitudes = self.servicios.requests
        solicitudes.submit_request(self.usuario,'Auditoría','Necesito consultar el historial')
        solicitudes.submit_request(self.otro,'Usuarios','Necesito consultar las cuentas')
        self.assertNotIn('Auditoría',solicitudes.available_permissions(self.usuario))
        self.assertIn('Usuarios',solicitudes.available_permissions(self.usuario))
        with self.servicios.connection:
            self.servicios.connection.execute('INSERT INTO grants(user_id,permission) VALUES(?,?)',(self.id_usuario,'Consultar solicitudes de todos'))
        # El permiso global de lectura no mezcla pendientes de otra cuenta.
        self.assertIn('Usuarios',solicitudes.available_permissions(self.usuario))
        with self.servicios.connection:
            self.servicios.connection.execute('DELETE FROM grants WHERE user_id=?',(self.id_usuario,))
            self.servicios.connection.execute("UPDATE requests SET status='Declinada' WHERE user_id=?",(self.id_usuario,))
        self.assertIn('Auditoría',solicitudes.available_permissions(self.usuario))
        self.assertIn('Usuarios',solicitudes.available_permissions(self.usuario))
        self.assertEqual([fila['user_id'] for fila in solicitudes.requests(self.usuario)],[self.id_usuario])

    def test_listado_y_permisos_rechazan_cuenta_desactivada(self):
        """La reutilización de consultas no omite la revalidación de la cuenta."""
        with self.servicios.connection:
            self.servicios.connection.execute('UPDATE users SET active=0 WHERE id=?',(self.id_usuario,))
        for metodo in (self.servicios.requests.requests,self.servicios.requests.available_permissions):
            with self.assertRaises(AccessDenied):
                metodo(self.usuario)


class PruebasEstilosCompartidos(unittest.TestCase):
    """Comprueba el comportamiento de Tk al reutilizar estilos y destruir controles."""

    def test_estilo_no_repite_cambio_global_y_se_recupera(self):
        """La segunda tabla no cambia el tema; un tema distinto sí restaura el estilo común."""
        raiz = tk.Tk()
        raiz.withdraw()
        componentes = UIComponents()
        original = ttk.Style.theme_use
        try:
            with patch.object(ttk.Style,'theme_use',autospec=True,side_effect=original) as cambiar:
                componentes._preparar_estilo_tablas(raiz)
                componentes._preparar_estilo_tablas(raiz)
                escrituras = [llamada for llamada in cambiar.call_args_list if len(llamada.args)>1]
                self.assertEqual(len(escrituras),1)
            estilo = ttk.Style(raiz)
            otro = next(tema for tema in estilo.theme_names() if tema!='clam')
            estilo.theme_use(otro)
            componentes._preparar_estilo_tablas(raiz)
            self.assertEqual(estilo.theme_use(),'clam')
            self.assertEqual(int(estilo.lookup('Hemeroteca.Treeview','rowheight')),42)
        finally:
            raiz.update_idletasks()
            raiz.destroy()

    def test_limpieza_conserva_contenedor_y_notifica_destruccion(self):
        """La limpieza compartida conserva el padre y ejecuta los callbacks Destroy de sus hijos."""
        raiz = tk.Tk()
        raiz.withdraw()
        try:
            marco = tk.Frame(raiz)
            hijo = tk.Label(marco,text='Prueba')
            avisos = []
            hijo.bind('<Destroy>',lambda evento: avisos.append(evento.widget))
            UIComponents()._vaciar_contenedor(marco)
            self.assertTrue(marco.winfo_exists())
            self.assertEqual(marco.winfo_children(),[])
            self.assertEqual(avisos,[hijo])
        finally:
            raiz.update_idletasks()
            raiz.destroy()
