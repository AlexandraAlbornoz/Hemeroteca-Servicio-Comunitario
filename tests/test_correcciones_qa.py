"""Regresiones de PDF, UTC, caché y diagnóstico de conexiones detectadas por QA."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config.settings import NATIONAL, SECURITY_QUESTIONS
from services.container import create_services
from services.audit_service import append_event
from services.paginacion import instante_evento, instante_evento_utc
from utils.dates import instante_auditoria_local, instante_auditoria_utc, ZONA_AUDITORIA_LOCAL
from network.http_server import TLSHTTPServer


class PruebasCorreccionesQA(unittest.TestCase):
    """Comprueba los defectos con bases separadas y con formatos antiguos y nuevos."""

    @classmethod
    def setUpClass(cls):
        """Prepara una semilla compartida sin repetir hashes costosos por cada caso."""
        cls.semilla = create_services(':memory:')
        preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Elena', 'Gabriel', 'Caracas')))
        cls.semilla.auth.create_master('Maestra QA', 'V-83000001', 'Ensayo#2026Ab', preguntas)
        cls.actor = cls.semilla.auth.authenticate('V-83000001', 'Ensayo#2026Ab')
        for dia in (1, 15, 28):
            cls.semilla.periodicos.save_record(cls.actor, (NATIONAL[0], 'Nacional', 'QA', 2020, 2, dia, str(dia), '1', '', 'Disponible'))

    @classmethod
    def tearDownClass(cls):
        """Libera la semilla al terminar todas las regresiones."""
        cls.semilla.close()

    def setUp(self):
        """Copia los registros de prueba en una base temporal que admite reportes y bloqueos."""
        self.temporal = tempfile.TemporaryDirectory()
        self.s = create_services(Path(self.temporal.name) / 'qa.db')
        self.semilla.connection.backup(self.s.connection)

    def tearDown(self):
        """Cierra SQLite antes de retirar la carpeta temporal de cada prueba."""
        self.s.close()
        self.temporal.cleanup()

    def test_pdf_rango_completo(self):
        """El rango se exporta con exactamente los registros visibles de la consulta."""
        filtros = {'desde': '2020-02-01', 'hasta': '2020-02-15'}
        resultado = self.s.reports.generate(self.actor, filters=filtros)
        self.assertEqual(resultado['records'], 2)
        self.assertEqual(resultado['records'], self.s.periodicos.search_issues(self.actor, **filtros)['total'])

    def test_pdf_solo_desde(self):
        """El límite inferior por sí solo tiene etiqueta y se aplica al PDF."""
        self.assertEqual(self.s.reports.generate(self.actor, filters={'desde': '2020-02-15'})['records'], 2)

    def test_pdf_solo_hasta(self):
        """El límite superior por sí solo deja de provocar KeyError."""
        self.assertEqual(self.s.reports.generate(self.actor, filters={'hasta': '2020-02-15'})['records'], 2)

    def test_pdf_filtros_vacios_anteriores_y_periodo(self):
        """Se conservan reportes sin límites, con mes/año y con periodo complementario."""
        for filtros in ({}, {'desde': None, 'hasta': None}, {'year': 2020, 'month': 2},
                        {'desde': '2020-02-01', 'hasta': '2020-02-28', 'period': 'Último día (24h)'}):
            with self.subTest(filtros=filtros):
                self.assertEqual(self.s.reports.generate(self.actor, filters=filtros)['records'], 3)

    def test_pdf_rango_vacio(self):
        """Un rango sin resultados produce un documento válido con cero ejemplares."""
        self.assertEqual(self.s.reports.generate(self.actor, filters={'desde': '2021-01-01'})['records'], 0)

    def test_pdf_rango_invertido_rechazado(self):
        """Un rango inválido se rechaza antes de componer el documento."""
        with self.assertRaises(ValueError):
            self.s.reports.generate(self.actor, filters={'desde': '2021-01-01', 'hasta': '2020-01-01'})

    def test_pdf_general_no_admite_filtros(self):
        """La compatibilidad con rangos no cambia el alcance del PDF general."""
        with self.assertRaises(ValueError):
            self.s.reports.generate(self.actor, scope='database', filters={'desde': '2020-01-01'})

    def test_eventos_nuevos_tienen_zona_utc(self):
        """La auditoría nueva se guarda con offset explícito para no depender del equipo."""
        with self.s.connection:
            append_event(self.s.connection, 'QA', 'Prueba de zona horaria')
        valor = self.s.connection.execute('SELECT at FROM audit ORDER BY id DESC LIMIT 1').fetchone()[0]
        self.assertEqual(datetime.fromisoformat(valor).utcoffset(), timedelta(0))

    def test_eventos_antiguos_conservan_hora_local(self):
        """La interpretación del historial no reescribe el texto ni desplaza la hora mostrada."""
        for valor in ('28/10/2026 13:00:00', '2026-10-28T13:00:00'):
            self.assertEqual(instante_evento(valor), '2026-10-28 13:00:00')
            self.assertEqual(instante_evento_utc(valor), '2026-10-28 17:00:00')

    def test_eventos_con_offsets_distintos_representan_el_mismo_instante(self):
        """ISO UTC y otros offsets se comparan y se muestran de forma consistente."""
        for valor in ('2026-10-28T17:00:00Z', '2026-10-28T13:00:00-04:00', '2026-10-28T19:00:00+02:00'):
            self.assertEqual(instante_evento(valor), '2026-10-28 13:00:00')
            self.assertEqual(instante_evento_utc(valor), '2026-10-28 17:00:00')

    def test_historial_sin_formato_no_rompe_consulta(self):
        """Fechas vacías o históricas inválidas no fallan ni entran en filtros de tiempo."""
        for valor in (None, '', 'sin fecha', '31/02/2020 10:00:00'):
            self.assertIsNone(instante_evento(valor))
            self.assertIsNone(instante_evento_utc(valor))

    def test_eliminados_limites_de_24h_semana_y_mes(self):
        """Comprueba límites inclusivos, un segundo antes y después, en cuatro formatos."""
        ahora = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
        self.s.connection.execute('UPDATE issues SET deleted=1 WHERE id=1')
        self.s.connection.commit()
        for periodo, horas in (('24h', 24), ('1 semana', 168), ('1 mes', 720)):
            for diferencia in (-1, 0, 1):
                instante = ahora - timedelta(hours=horas, seconds=diferencia)
                local = instante.astimezone(ZONA_AUDITORIA_LOCAL)
                for valor in (local.strftime('%d/%m/%Y %H:%M:%S'), local.replace(tzinfo=None).isoformat(),
                              instante.isoformat(), instante.astimezone(timezone(timedelta(hours=2))).isoformat()):
                    with self.subTest(periodo=periodo, diferencia=diferencia, fecha=valor):
                        with self.s.connection:
                            self.s.connection.execute('INSERT INTO audit(at,user,action,result) VALUES(?,?,?,?)',
                                (valor, 'QA', 'Ejemplar eliminado: #1', 'Completado'))
                        with patch('services.periodico_service.utc_now', return_value=ahora.isoformat()):
                            self.assertEqual(self.s.periodicos.buscar_eliminados(self.actor, periodo=periodo)['total'], int(diferencia <= 0))

    def test_baja_hace_23_horas_incluida_y_25_excluida(self):
        """Reproduce exactamente el defecto QA-005 con horas locales sin zona."""
        ahora = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
        self.s.connection.execute('UPDATE issues SET deleted=1 WHERE id=1')
        for horas, esperado in ((23, 1), (25, 0)):
            valor = (ahora - timedelta(hours=horas)).astimezone(ZONA_AUDITORIA_LOCAL).strftime('%d/%m/%Y %H:%M:%S')
            with self.s.connection:
                self.s.connection.execute('INSERT INTO audit(at,user,action,result) VALUES(?,?,?,?)', (valor, 'QA', 'Ejemplar eliminado: #1', 'Completado'))
            with patch('services.periodico_service.utc_now', return_value=ahora.isoformat()):
                self.assertEqual(self.s.periodicos.buscar_eliminados(self.actor, periodo='24h')['total'], esperado)

    def test_auditoria_filtra_fecha_local_al_cruzar_medianoche(self):
        """Un evento UTC del día siguiente se encuentra por su fecha visible en Caracas."""
        valor = '2026-10-29T03:30:00+00:00'
        with self.s.connection:
            self.s.connection.execute('INSERT INTO audit(at,user,action,result) VALUES(?,?,?,?)', (valor, 'QA', 'Medianoche QA', 'Completado'))
        self.assertEqual(self.s.audit.buscar_eventos(self.actor, fecha='2026-10-28', hora='23:30', accion='Medianoche QA')['total'], 1)
        self.assertEqual(self.s.connection.execute("SELECT at FROM audit WHERE action='Medianoche QA'").fetchone()[0], valor)
        self.assertEqual(instante_auditoria_local(valor).hour, 23)

    def test_caches_acotadas_usan_el_valor_sin_invalidacion_global(self):
        """Las fechas repetidas reutilizan el resultado y una fecha diferente se recalcula."""
        for funcion in (instante_evento, instante_evento_utc):
            funcion.cache_clear()
            primero = funcion('2026-10-29T03:30:00Z')
            self.assertEqual(funcion('2026-10-29T03:30:00Z'), primero)
            self.assertNotEqual(funcion('2026-10-29T04:30:00Z'), primero)
            self.assertEqual(funcion.cache_info().maxsize, 8192)
            self.assertEqual(funcion.cache_info().hits, 1)

    def test_cierre_tls_esperado_sin_traza_alarmante(self):
        """Una desconexión esperada se registra en debug y libera el diagnóstico detallado."""
        servidor = TLSHTTPServer.__new__(TLSHTTPServer)
        with patch('http.server.ThreadingHTTPServer.handle_error') as original:
            with self.assertLogs('network.http_server', level='DEBUG'):
                try:
                    raise ConnectionResetError('Desconexión ficticia de QA')
                except ConnectionResetError:
                    servidor.handle_error(None, ('127.0.0.1', 0))
            original.assert_not_called()

    def test_error_tls_inesperado_conserva_traza(self):
        """Un error de programación continúa llegando al manejador original."""
        servidor = TLSHTTPServer.__new__(TLSHTTPServer)
        with patch('http.server.ThreadingHTTPServer.handle_error') as original:
            try:
                raise RuntimeError('Error ficticio inesperado de QA')
            except RuntimeError:
                servidor.handle_error(None, ('127.0.0.1', 0))
            original.assert_called_once()


class PruebasAlineacionCalendario(unittest.TestCase):
    """Verifica que el botón adicional no desplace los selectores de mes y día."""

    def test_selectores_conservan_alineacion_superior(self):
        """Los tres campos quedan alineados y conservan el calendario y los filtros parciales."""
        import customtkinter as ctk
        from ui.components import UIComponents
        from config.settings import MONTHS
        class VentanaPrueba(UIComponents, ctk.CTk):
            """Contiene únicamente los filtros para medir su distribución real en Tkinter."""
        ventana = VentanaPrueba()
        try:
            ventana.geometry('720x220')
            panel = ctk.CTkFrame(ventana)
            panel.pack(fill='both', expand=True)
            campos = []
            for indice, (etiqueta, opciones) in enumerate((('Año', ['Todos', '2020']), ('Mes', ['Todos'] + MONTHS), ('Día', ['Todos', '1']))):
                envoltura, control = ventana._combo(panel, etiqueta, opciones, 'Todos')
                envoltura.grid(row=0, column=indice, sticky='ew')
                campos.append(control)
            ventana._connect_date_fields(*campos, allow_all=True)
            ventana.update()
            self.assertEqual(len({control.master.winfo_y() for control in campos}), 1)
            self.assertTrue(all(control.master.grid_info()['sticky'] == 'new' for control in campos))
        finally:
            ventana.destroy()


if __name__ == '__main__':
    unittest.main()
