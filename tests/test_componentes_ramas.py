"""Ramas de paginación, filtros históricos y accesibilidad con Tk real."""
from datetime import date
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch
import customtkinter as ctk
from hemeroteca.config.settings import MONTHS
from hemeroteca.ui import components
from tests.soporte_catalogo import VentanaCatalogo


class PruebasComponentesRamas(unittest.TestCase):
    """Conserva widgets y callbacks reales; aísla autorizaciones y consultas."""

    def setUp(self):
        self.h=VentanaCatalogo()
        self.addCleanup(self.h.close_for_test)
        self.h._require_access=Mock(return_value=True)

    def button(self, area, text):
        return next(w for w in self.h.widgets(ctk.CTkButton,area) if w.cget('text')==text)

    def tree(self, area):
        return self.h.widgets(ttk.Treeview,area)[0]

    def test_paginacion_en_memoria_seleccion_ids_y_denegacion(self):
        selected=Mock()
        area=self.h._paginate(self.h.content,[(str(i),) for i in range(12)],[('dato','Dato',100)],'consulta',selected_callback=selected,row_ids=list(range(12)))
        tree=self.tree(area)
        self.assertEqual(tree.get_children(),tuple(str(i) for i in range(5)))
        self.h.select(tree,2)
        self.assertIs(selected.call_args.args[0],tree)
        self.h._require_access.return_value=False
        self.button(area,'Siguiente').invoke()
        self.assertIs(self.tree(area),tree)
        self.h._require_access.return_value=True
        self.button(area,'Última').invoke()
        self.assertEqual(self.tree(area).get_children(),('10','11'))
        self.button(area,'Anterior').invoke()
        self.assertEqual(self.tree(area).get_children(),tuple(str(i) for i in range(5,10)))
        self.button(area,'Primera').invoke()
        self.assertEqual(self.tree(area).get_children(),tuple(str(i) for i in range(5)))

    def test_tamano_pagina_invalido_no_crea_widgets(self):
        before=self.h.content.winfo_children()
        for value in [0,-1,True,1.5,'5',None]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.h._paginate(self.h.content,[],[('dato','Dato',100)],'consulta',page_size=value)
        self.assertEqual(self.h.content.winfo_children(),before)

    def test_estado_restaurado_entry_sin_set_y_aislamiento_de_paginas(self):
        self.h._registrar_estado_vista=components.UIComponents._registrar_estado_vista.__get__(self.h)
        entry=tk.Entry(self.h.content)
        key=(self.h.user['id'],'filtro')
        self.h._filtros_recordados={key:{'texto':'guardado'}}
        current=(self.h.user['id'],self.h.current_view,'consulta')
        other=(999,self.h.current_view,'consulta')
        self.h._paginas_recordadas={current:3,other:4}
        self.h._registrar_estado_vista('filtro',{'texto':entry})
        self.assertEqual(entry.get(),'guardado')
        entry.delete(0,'end');entry.insert(0,'nuevo')
        self.h._guardar_estado_vista()
        self.assertNotIn(current,self.h._paginas_recordadas)
        self.assertEqual(self.h._paginas_recordadas[other],4)

    def test_filtros_en_memoria_combinados_y_sin_restricciones(self):
        rows=[dict(title='Uno',kind='Regional'),dict(title='Dos',kind='Nacional')]
        self.assertEqual(self.h._filter_rows(rows,'Uno','Regional'),rows[:1])
        self.assertEqual(self.h._filter_rows(rows,'Uno','Nacional'),[])
        self.assertEqual(self.h._filter_rows(rows,'Todos los periódicos','Todos'),rows)
        self.assertEqual(self.h._filter_rows(rows,'',''),rows)

    def campos(self, entry=False):
        controls=[]
        for values,default in [(['2024','Todos'],'2024'),(MONTHS,MONTHS[1]),(['31'],'31')]:
            box=ctk.CTkFrame(self.h.content);box.pack()
            c=ctk.CTkEntry(box) if entry and not controls else ctk.CTkComboBox(box,values=values)
            c.pack()
            if hasattr(c,'set'):c.set(default)
            else:c.insert(0,default)
            controls.append(c)
        return controls

    def test_fecha_historica_bisiesta_todos_y_entrada_invalida(self):
        year,month,day=self.campos()
        adjust=self.h._connect_date_fields(year,month,day,allow_all=True)
        self.assertEqual(day.get(),'Todos')
        self.assertIn('29',day.cget('values'))
        day.set('29');year.set('2023');year.cget('command')('2023')
        self.assertEqual(day.get(),'Todos')
        month.set('Todos');year.set('Todos');adjust()
        self.assertIn('31',day.cget('values'))
        year.set('invalido');before=day.cget('values');adjust()
        self.assertEqual(day.cget('values'),before)

    def test_calendario_historico_fallback_y_eleccion_sin_perder_dia(self):
        year,month,day=self.campos(entry=True)
        self.h._connect_date_fields(year,month,day)
        self.assertEqual(day.get(),'29')
        with patch.object(components,'abrir_calendario') as open_calendar:
            self.button(year.master,'Calendario').invoke()
            self.assertEqual(open_calendar.call_args.args[2],date(2024,2,29))
            callback=open_calendar.call_args.args[1]
            callback(date(2023,4,15))
            self.assertEqual((year.get(),month.get(),day.get()),('2023',MONTHS[3],'15'))
            year.delete(0,'end');year.insert(0,'invalido')
            self.button(year.master,'Calendario').invoke()
            self.assertEqual(open_calendar.call_args.args[2],date.today())

    def test_barra_fija_se_retira_con_tabla_y_foco_boton(self):
        # La barra es hermana del contenido, como en la ventana principal.
        holder=ctk.CTkFrame(self.h);holder.pack()
        self.h.navegacion_resultados=ctk.CTkFrame(holder)
        self.h.navegacion_resultados.grid(row=0,column=0)
        area=ctk.CTkFrame(self.h.content);area.pack()
        nav,_,_=self.h._barra_resultados(area,'backups')
        self.assertTrue(nav.winfo_exists())
        area.destroy();self.h.update()
        self.assertFalse(nav.winfo_exists())
        self.assertEqual(self.h.navegacion_resultados.winfo_manager(),'')
        button=self.h._button(self.h.content,'Prueba',lambda:None)
        button.pack();self.h.update()
        button._canvas.event_generate('<FocusIn>');self.h.update()
        self.assertEqual(button.cget('border_width'),2)
        button._canvas.event_generate('<FocusOut>');self.h.update()
        self.assertEqual(button.cget('border_width'),1)
        empty=self.h._empty(self.h.content,'Sin filas')
        self.assertTrue(empty.winfo_exists())
        self.h._notice('sin etiqueta')
        missing=ctk.CTkFrame(self.h.content);missing.destroy()
        self.h._mostrar_resultados(missing)

    def test_titulos_sin_tipo_y_aviso_sin_etiqueta_o_destruida(self):
        grid=ctk.CTkFrame(self.h.content);grid.pack()
        fields=self.h._title_filter_fields(grid,include_type=False)
        self.assertEqual(set(fields),{'Periódico'})
        components.UIComponents._notice(self.h,'sin etiqueta')
        self.h.status_label=ctk.CTkLabel(self.h.content,text='anterior')
        components.UIComponents._notice(self.h,'nuevo')
        self.assertEqual(self.h.status_label.cget('text'),'nuevo')
        self.h.status_label.destroy()
        components.UIComponents._notice(self.h,'retirado')

    def test_calendario_historico_grid_y_sin_limite_de_mes(self):
        grid=ctk.CTkFrame(self.h.content);grid.pack()
        controls=[]
        for i,(values,value) in enumerate([(['Todos'],'Todos'),(['Todos'],'Todos'),(['99'],'99')]):
            box=ctk.CTkFrame(grid);box.grid(row=0,column=i)
            c=ctk.CTkComboBox(box,values=values);c.pack();c.set(value);controls.append(c)
        self.h._connect_date_fields(*controls)
        self.assertEqual(controls[2].get(),'31')
        self.assertIn('n',controls[0].master.grid_info()['sticky'])

    def test_tabla_paginada_sin_callback_restaura_seleccion_y_pagina(self):
        parent=ctk.CTkFrame(self.h.content);parent.pack()
        row={'id':7}
        identifier=(self.h.user['id'],self.h.current_view,'consulta')
        self.h._selecciones_recordadas={identifier:'7'}
        fetch=Mock(return_value=lambda:self.h.page([row],2,2,6))
        area=self.h._paged_table(parent,fetch,lambda r:(str(r['id']),),[('dato','Dato',100)])
        tree=self.tree(area)
        self.assertEqual(tree.selection(),('7',))
        self.h.select(tree,7)
        self.assertEqual(self.h._paginas_recordadas[identifier],2)
