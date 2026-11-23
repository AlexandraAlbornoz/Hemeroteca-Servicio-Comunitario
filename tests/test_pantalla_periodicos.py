"""Consulta, catálogo, altas y bajas con tablas y calendarios reales."""
import sqlite3
import unittest
from unittest.mock import patch
import customtkinter as ctk
from tkinter import ttk
from hemeroteca.config.settings import TITLES, REGIONAL, ROLES, VIEWS, MONTHS, RECORD_PERIODS
from hemeroteca.ui.controles import TextoEditable
from hemeroteca.services.access_service import AccessDenied
from tests.soporte_catalogo import VentanaCatalogo


class PruebasPantallaPeriodicos(unittest.TestCase):
    """Conserva los controles y simula solamente mensajes y servicios externos."""

    def setUp(self):
        self.h = VentanaCatalogo()
        self.addCleanup(self.h.close_for_test)
        for name in ['showwarning', 'askyesno']:
            setattr(self, name, patch('hemeroteca.ui.periodicos_view.messagebox.'+name, return_value=True).start())
        self.addCleanup(patch.stopall)
        self.record = dict(id=11, title=TITLES[0], kind='Regional' if TITLES[0] in REGIONAL else 'Nacional',
                           edition='Matutina', year=2020, month=2, day=29, number='5', shelf='2', drawer='',
                           status='Disponible', revision=4, note='Nota ficticia')
        self.h.services.periodicos.get_issue.return_value = self.record

    def open_catalog(self):
        self.h._catalog_page()
        self.h.update_idletasks()

    def fill(self):
        self.h.dates['Fecha de publicación *'].set('29/02/2020')
        self.h.write('Edición *', 'Matutina')
        self.h.write('Número *', '5')
        self.h.write('Estante', '2')
        self.h.validate_record()

    def test_denegacion_impide_paginas_y_formularios(self):
        self.h._require_access.return_value = False
        self.h._consult_page()
        self.h._catalog_page()
        self.h._record_form()
        self.h._delete_issue(11)
        self.assertEqual(self.h.dialogs, [])
        self.h.services.periodicos.search_issues.assert_not_called()

    def test_permiso_de_alta_segun_rol_y_catalogo(self):
        self.assertEqual(self.h._issue_creation_permission(set()), 'Registrar ejemplares')
        self.h.user['role'] = ROLES[1]
        self.assertEqual(self.h._issue_creation_permission({VIEWS[1]}), VIEWS[1])
        self.h.user['role'] = ROLES[2]
        self.assertEqual(self.h._issue_creation_permission({VIEWS[1]}), 'Registrar ejemplares')

    def test_consulta_envia_filtros_y_pdf_usa_mismos_valores(self):
        self.h.services.periodicos.search_issues.return_value = self.h.page([self.record])
        self.h._consult_page()
        self.h.combos['Periódico'].set(TITLES[0])
        self.h.combos['Tipo de prensa'].set(self.record['kind'])
        self.h.dates['Publicación desde'].set('01/02/2020')
        self.h.dates['Publicación hasta'].set('29/02/2020')
        self.h.combos['Periodo de registro'].set(next(iter(RECORD_PERIODS)))
        self.h.text_checkbox('Filtrar por periodo').toggle()
        self.h.button('Buscar').invoke()
        args = self.h.services.periodicos.search_issues.call_args.kwargs
        self.assertEqual(args['desde'], '2020-02-01')
        self.assertEqual(args['title'], TITLES[0])
        self.assertEqual(args['period'], next(iter(RECORD_PERIODS)))
        with patch.object(self.h, '_export_pdf') as pdf:
            self.h.button('Guardar resultado en PDF').invoke()
            self.assertEqual(pdf.call_args.kwargs['filters']['hasta'], '2020-02-29')
        self.h.button('Mostrar todos').invoke()
        self.assertIsNone(self.h.services.periodicos.search_issues.call_args.kwargs['desde'])

    def test_consulta_fecha_unica_muestra_ausencias_y_limpia_nota(self):
        self.h._consult_page()
        self.h.services.periodicos.consult_absent_dates.return_value = [self.record]
        for label in ['Publicación desde', 'Publicación hasta']:
            self.h.dates[label].set('29/02/2020')
        self.h.button('Buscar').invoke()
        self.assertTrue(self.h.has_text('Sin publicación: '+TITLES[0]))
        self.h.services.periodicos.consult_absent_dates.assert_called_with(self.h.user, 2020, 2, 29)
        self.h.button('Mostrar todos').invoke()
        self.assertFalse(self.h.has_text('Sin publicación:'))

    def test_consulta_sin_permiso_pdf_y_resultado_vacio(self):
        self.h._can.return_value = False
        self.h._consult_page()
        with self.assertRaises(AssertionError):
            self.h.button('Guardar resultado en PDF')
        self.assertTrue(self.h.has_text('No hay registros'))

    def test_catalogo_sin_permisos_deshabilita_acciones(self):
        self.h._permisos_actuales.return_value = set()
        self.open_catalog()
        for title in ['Registrar ejemplar', 'Actualizar catálogo', 'Editar seleccionado', 'Eliminar seleccionado']:
            self.assertEqual(self.h.button(title).cget('state'), 'disabled')
        self.assertTrue(any('aún no tienes permisos' in label.cget('text') for label in self.h.widgets(ctk.CTkLabel)))
        self.h.services.periodicos.search_issues.assert_not_called()

    def test_catalogo_seleccion_habilita_edicion_y_baja(self):
        self.h.services.periodicos.search_issues.return_value = self.h.page([self.record])
        self.open_catalog()
        tree = self.h.widgets(ttk.Treeview)[0]
        self.h.select(tree, 11)
        self.assertEqual(self.h.button('Editar seleccionado').cget('state'), 'normal')
        with patch.object(self.h, '_record_form') as edit, patch.object(self.h, '_delete_issue') as delete:
            self.h.button('Editar seleccionado').invoke()
            self.h.button('Eliminar seleccionado').invoke()
            edit.assert_called_once_with(issue_id=11)
            delete.assert_called_once_with(11)

    def test_catalogo_filtros_y_limpiar_no_pierden_contrato_pdf(self):
        self.open_catalog()
        # El catálogo contiene también el selector de título de ausencias.
        next(c for label,c in self.h.all_combos if label=='Periódico').set(TITLES[0])
        self.h.combos['Año'].set('2020')
        self.h.combos['Mes'].set(MONTHS[1])
        self.h.combos['Día'].set('29')
        self.h.button('Filtrar catálogo').invoke()
        args = self.h.services.periodicos.search_issues.call_args.kwargs
        self.assertEqual((args['year'], args['month'], args['day']), (2020, 2, 29))
        self.assertTrue(args['catalog'])
        with patch.object(self.h, '_export_pdf') as pdf:
            self.h.button('Guardar resultado en PDF').invoke()
            self.assertEqual(pdf.call_args.kwargs['filters']['year'], 2020)
        self.h.button('Limpiar filtros').invoke()
        self.assertIsNone(self.h.services.periodicos.search_issues.call_args.kwargs['year'])

    def test_cambio_seccion_consulta_ausencias_y_sus_filtros(self):
        self.h._catalogo_seccion = 'Fechas sin publicación'
        self.h.services.periodicos.buscar_fechas_ausentes.return_value = self.h.page([self.record])
        self.open_catalog()
        self.h.dates['Desde'].set('01/02/2020')
        self.h.dates['Hasta'].set('29/02/2020')
        self.h.combos['Observaciones'].set('Con observación')
        self.h.combos['Periódico'].set(TITLES[0])
        self.h.button('Filtrar fechas sin publicación').invoke()
        args = self.h.services.periodicos.buscar_fechas_ausentes.call_args.kwargs
        self.assertEqual(args['observaciones'], 'Con observación')
        self.assertEqual(args['desde'], '2020-02-01')
        self.assertIsNone(args['year'])
        switch = self.h.widgets(ctk.CTkSegmentedButton)[0]
        switch.set('Ejemplares', from_button_callback=True)
        self.assertEqual(self.h._catalogo_seccion, 'Ejemplares')
        self.h.services.periodicos.search_issues.assert_called()

    def test_anular_ausencia_exige_seleccion_confirmacion_y_reintento(self):
        self.h._catalogo_seccion = 'Fechas sin publicación'
        self.h.services.periodicos.buscar_fechas_ausentes.return_value = self.h.page([self.record])
        self.open_catalog()
        tree = self.h.widgets(ttk.Treeview)[0]
        self.assertEqual(self.h.button('Anular anotación incorrecta').cget('state'), 'disabled')
        self.h.select(tree, 11)
        self.askyesno.return_value = False
        self.h.button('Anular anotación incorrecta').invoke()
        self.h.services.periodicos.corregir_fecha_ausente.assert_not_called()
        self.askyesno.return_value = True
        self.h.services.periodicos.corregir_fecha_ausente.side_effect = ValueError('anotación cambiada')
        self.h.button('Anular anotación incorrecta').invoke()
        self.showwarning.assert_called_once()
        self.h.services.periodicos.corregir_fecha_ausente.side_effect = None
        self.h.button('Anular anotación incorrecta').invoke()
        self.h.services.periodicos.corregir_fecha_ausente.assert_called_with(self.h.user, 11, anular=True)

    def test_formulario_alta_bloquea_incompleto_y_guarda_datos_validados(self):
        self.h._record_form()
        self.assertEqual(self.h.button('Guardar ejemplar').cget('state'), 'disabled')
        self.fill()
        self.h.button('Guardar ejemplar').invoke()
        args = self.h.services.periodicos.save_record.call_args
        self.assertEqual(args.args[1][3:6], (2020, 2, 29))
        self.assertEqual(args.kwargs, dict(absent=False, issue_id=None, expected_revision=None))
        self.assertFalse(self.h.dialogs[-1].winfo_exists())

    def test_guardado_no_cierra_ante_denegacion_validacion_o_duplicado(self):
        self.h._record_form()
        self.fill()
        dialog = self.h.dialogs[-1]
        for error in [AccessDenied('sin permiso'), ValueError('cambió la ficha'), sqlite3.IntegrityError('duplicado')]:
            self.h.services.periodicos.save_record.side_effect = error
            self.h.button('Guardar ejemplar').invoke()
            self.assertTrue(dialog.winfo_exists())
        self.assertTrue(self.h.has_text('Ya existe un registro'))
        # La validación periódica sin cambios no borra el error del servidor.
        self.h.validate_record()
        self.assertTrue(self.h.has_text('Ya existe un registro'))
        self.h._access_denied.assert_called_once()

    def test_edicion_precarga_ficha_y_envia_revision(self):
        self.h._record_form(issue_id=11)
        self.assertEqual(self.h.dates['Fecha de publicación *'].get(), '29/02/2020')
        self.assertEqual(self.h.entries['Número *'].get(), '5')
        self.h.button('Guardar cambios').invoke()
        self.assertEqual(self.h.services.periodicos.save_record.call_args.kwargs['expected_revision'], 4)
        self.h._notice.assert_called_once_with('Cambios guardados.')

    def test_ficha_retirada_no_abre_formulario(self):
        self.h.services.periodicos.get_issue.return_value = None
        self.h._record_form(issue_id=11)
        self.assertEqual(self.h.dialogs, [])

    def test_revocacion_entre_abrir_y_guardar_no_envia_datos(self):
        self.h._record_form()
        self.fill()
        self.h._require_access.return_value = False
        self.h.button('Guardar ejemplar').invoke()
        self.h.services.periodicos.save_record.assert_not_called()

    def test_formulario_fecha_ausente_exige_fecha_y_conserva_error(self):
        self.h._record_form(absent=True)
        self.h.button('Guardar fecha').invoke()
        self.assertTrue(self.h.has_text('Selecciona la fecha'))
        self.h.dates['Fecha sin publicación *'].set('29/02/2020')
        note = self.h.widgets(TextoEditable, self.h.dialogs[-1])[0]
        note.insert('1.0', ' Nota ficticia ')
        for error in [AccessDenied('sin permiso'), ValueError('fecha en conflicto'), sqlite3.IntegrityError('duplicado')]:
            self.h.services.periodicos.save_record.side_effect = error
            self.h.button('Guardar fecha').invoke()
            self.assertTrue(self.h.dialogs[-1].winfo_exists())
        self.h.services.periodicos.save_record.side_effect = None
        self.h.button('Guardar fecha').invoke()
        self.assertEqual(self.h.services.periodicos.save_record.call_args.args[1][-1], 'Nota ficticia')
        self.assertTrue(self.h.services.periodicos.save_record.call_args.kwargs['absent'])

    def test_eliminacion_cancela_reintenta_y_actualiza_catalogo(self):
        self.h._delete_issue(None)
        self.askyesno.return_value = False
        self.h._delete_issue(11)
        self.h.services.periodicos.delete_issue.assert_not_called()
        self.askyesno.return_value = True
        for error in [AccessDenied('revocado'), ValueError('ficha retirada')]:
            self.h.services.periodicos.delete_issue.side_effect = error
            self.h._delete_issue(11)
        self.h._access_denied.assert_called_once()
        self.showwarning.assert_called_once()
        self.h.services.periodicos.delete_issue.side_effect = None
        self.h._delete_issue(11)
        self.h.navigate.assert_called_once_with(VIEWS[1])

    def test_revocacion_al_leer_ficha_no_escapa_de_edicion_o_baja(self):
        self.h.services.periodicos.get_issue.side_effect = AccessDenied('acceso revocado')
        self.h._record_form(issue_id=11)
        self.h._delete_issue(11)
        self.assertEqual(self.h._access_denied.call_count, 2)
        self.assertEqual(self.h.dialogs, [])

    def test_error_de_datos_o_ficha_retirada_al_abrir_baja(self):
        self.h.services.periodicos.get_issue.side_effect = ValueError('ficha modificada')
        self.h._record_form(issue_id=11)
        self.h._delete_issue(11)
        self.assertEqual(self.showwarning.call_count, 2)
        self.h.services.periodicos.get_issue.side_effect = None
        self.h.services.periodicos.get_issue.return_value = None
        self.h._delete_issue(11)
        self.h.services.periodicos.delete_issue.assert_not_called()

