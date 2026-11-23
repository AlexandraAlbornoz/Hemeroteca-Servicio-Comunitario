"""Rangos inclusivos, combinación de filtros y motivo editable sin datos reales."""
import unittest
from hemeroteca.config.settings import NATIONAL, SECURITY_QUESTIONS
from hemeroteca.services.container import create_services
from hemeroteca.services.periodico_service import issue_search_query


class PruebasRangosFlujos(unittest.TestCase):
    """Valida que los rangos respeten calendario y se combinen con filtros anteriores."""

    def setUp(self):
        """Crea una colección artificial con fechas en ambos extremos del rango."""
        self.s = create_services(':memory:')
        preguntas = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
        self.s.auth.create_master('Responsable Prueba', 'V-12345678', 'Prueba#2026', preguntas)
        self.actor = self.s.auth.authenticate('V-12345678', 'Prueba#2026')
        for dia in (1, 15, 28):
            self.s.periodicos.save_record(self.actor, (NATIONAL[0], 'Nacional', 'Matutina', 2020, 2, dia, str(dia), '1', '', 'Disponible'))

    def tearDown(self):
        """Libera la colección temporal."""
        self.s.close()

    def test_rango_inclusivo_con_periodo_complementario(self):
        """El periodo reciente se suma a las fechas de publicación sin reemplazarlas."""
        resultado = self.s.periodicos.search_issues(self.actor, desde='2020-02-01', hasta='2020-02-15', period='Último día (24h)')
        self.assertEqual(resultado['total'], 2)

    def test_rangos_invalidos(self):
        """Rechaza orden invertido, fechas imposibles y años anteriores a 1970."""
        for desde, hasta in (('2020-03-01', '2020-02-01'), ('2021-02-29', None), ('1969-01-01', None)):
            with self.assertRaises(ValueError):
                issue_search_query(desde=desde, hasta=hasta)

    def test_eliminados_usan_fecha_real_de_eliminacion_para_atajos(self):
        """Los ejemplares antiguos eliminados hoy aparecen en el atajo de 24 horas."""
        self.s.periodicos.delete_issue(self.actor, 1)
        fecha = self.s.connection.execute("SELECT substr(instante_evento(at),1,10) FROM audit WHERE action='Ejemplar eliminado: #1'").fetchone()[0]
        resultado = self.s.periodicos.buscar_eliminados(self.actor, desde=fecha, hasta=fecha, periodo='24h')
        self.assertEqual(resultado['total'], 1)

    def test_fechas_sin_publicacion_aceptan_rango_y_periodico(self):
        """El rango se aplica a la anotación y conserva el filtro de periódico."""
        self.s.periodicos.save_record(self.actor, (NATIONAL[1], 'Nacional', 2020, 3, 1, 'Sin circulación'), absent=True)
        resultado = self.s.periodicos.buscar_fechas_ausentes(self.actor, title=NATIONAL[1], desde='2020-03-01', hasta='2020-03-01')
        self.assertEqual(resultado['total'], 1)
