"""Paginación real con fallos entregados por trabajadores y filtros recordados."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import customtkinter as ctk
from hemeroteca.services.access_service import AccessDenied
from hemeroteca.services.container import create_services
from hemeroteca.ui.carga import CargaDeVistas
from hemeroteca.ui.components import UIComponents
from hemeroteca.ui.tareas import ServiciosDeInterfaz
from tests.soporte_catalogo import VentanaCatalogo


class PruebasTablaAsincrona(unittest.TestCase):
    """No simula el ejecutor, callbacks de tabla ni controles de paginación."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.h=VentanaCatalogo()
        self.original=create_services(Path(self.temp.name)/'prueba.db')
        self.s=ServiciosDeInterfaz(self.h,self.original)
        self.h.services=self.s
        self.h._cargar_seccion=CargaDeVistas._cargar_seccion.__get__(self.h)
        self.addCleanup(self.clean)
        self.parent=ctk.CTkFrame(self.h.content)
        self.parent.grid(row=0,column=0)

    def pump(self):
        end=time.monotonic()+5
        while self.s._trabajos and time.monotonic()<end:
            self.h.update()
            time.sleep(.001)
        self.assertEqual(self.s._trabajos,0)
        self.h.update_idletasks()

    def clean(self):
        try:self.pump()
        finally:
            self.s.close()
            self.h.close_for_test()
            self.temp.cleanup()

    def open(self,fetch=None):
        self.h._paged_table(self.parent,fetch or (lambda page:self.s.consulta('periodicos','search_issues',self.h.user,page=page)),
                            lambda row:(row['title'],),[('title','Título',180)],key='consulta')
        return self.parent._tabla_paginada

    def test_error_de_consulta_se_muestra_y_reintento_reutiliza_tabla(self):
        with patch.object(self.s,'_con_servicios',side_effect=OSError('servidor no disponible')):
            state=self.open()
            tree=state['tabla']
            self.pump()
        self.assertEqual(tree.get_children(),())
        self.assertEqual(state['etiqueta'].cget('text'),'No se pudieron cargar los resultados')
        self.assertEqual(state['area']._indicadores_carga['datos'].cget('text'),'servidor no disponible')
        result=self.h.page([dict(id=1,title='Ficha ficticia')])
        with patch.object(self.s,'_con_servicios',return_value=[result]):
            self.open()
            self.pump()
        self.assertIs(self.parent._tabla_paginada['tabla'],tree)
        self.assertEqual(tree.get_children(),('1',))
        self.assertEqual(state['area']._indicadores_carga['datos'].cget('text'),'')

    def test_denegacion_en_tabla_sincroniza_sesion_en_tk(self):
        with patch.object(self.s,'_con_servicios',side_effect=AccessDenied('permiso revocado')):
            self.open()
            self.pump()
        self.h._sync_session.assert_called_once()

    def test_error_al_capturar_filtros_no_envia_trabajo(self):
        with patch.object(self.s,'leer_async',wraps=self.s.leer_async) as submit:
            state=self.open(Mock(side_effect=ValueError('fecha de filtro inválida')))
            submit.assert_not_called()
        self.assertEqual(state['mensaje'].cget('text'),'fecha de filtro inválida')
        self.assertEqual(state['etiqueta'].cget('text'),'No se pudieron cargar los resultados')

    def test_nueva_pagina_restaura_seleccion_y_no_toca_filtros_ajenos(self):
        result=self.h.page([dict(id=1,title='Ficha ficticia')],number=2,pages=3,total=11)
        with patch.object(self.s,'_con_servicios',return_value=[result]):
            state=self.open()
            self.pump()
            state['tabla'].selection_set('1')
            state['tabla'].event_generate('<<TreeviewSelect>>')
            self.h.update()
            self.open()
            self.pump()
        self.assertEqual(state['tabla'].selection(),('1',))
        self.assertEqual(state['anterior'].cget('state'),'normal')
        self.assertEqual(state['siguiente'].cget('state'),'normal')
        # Usa la implementación real de memoria, no el doble de otras pantallas.
        register=UIComponents._registrar_estado_vista.__get__(self.h)
        filters={'campo':ctk.StringVar(value='anterior')}
        register('consulta',filters)
        other=(99,'Otra vista','consulta')
        self.h._paginas_recordadas[other]=3
        filters['campo'].set('nuevo')
        self.h._guardar_estado_vista()
        self.assertEqual(self.h._paginas_recordadas,{other:3})

