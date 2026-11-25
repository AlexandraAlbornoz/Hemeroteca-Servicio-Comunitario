"""Regresiones de preparación de formularios y mensajes de bloqueo de Guardar."""
import unittest
from config.settings import NATIONAL, REGIONAL
from ui.validacion_formularios import preparar_ejemplar


class PruebasValidacionGuardar(unittest.TestCase):
    """Comprueba que todo bloqueo tenga explicación y respete las reglas existentes."""

    def setUp(self):
        """Prepara un formulario nacional completo y válido sin usar la base de datos."""
        self.campos = {'Periódico':NATIONAL[0], 'Fecha de publicación':'01/01/2026',
                       'Edición':'Matutina', 'Número':'12', 'Estante':'1', 'Gaveta':'', 'Estado':'Disponible'}

    def test_valido_con_estante_gaveta_o_ambos(self):
        """Las tres combinaciones permitidas de ubicación producen datos guardables."""
        for estante,gaveta in (('1',''),('','2'),('1','2')):
            self.campos.update(Estante=estante,Gaveta=gaveta)
            self.assertEqual(preparar_ejemplar(self.campos)[7:9],(estante,gaveta))

    def test_rango_comun_para_todos_los_periodicos(self):
        """Acepta ambos extremos y años recientes; explica los rechazos fuera del rango."""
        for titulo in REGIONAL + NATIONAL:
            self.campos['Periódico']=titulo
            for anio in (1970, 2022, 2026, 2100):
                self.campos['Fecha de publicación']=f'31/12/{anio}'
                self.assertEqual(preparar_ejemplar(self.campos)[3],anio)
            for anio in (1969, 2101):
                self.campos['Fecha de publicación']=f'01/01/{anio}'
                with self.assertRaises(ValueError):
                    preparar_ejemplar(self.campos)

    def test_edicion_corta_tiene_motivo(self):
        """La edición de un carácter explica su mínimo sin cambiar la regla anterior."""
        self.campos['Edición']='1'
        with self.assertRaisesRegex(ValueError,'Edición:.*2 y 50'):
            preparar_ejemplar(self.campos)

    def test_todos_los_campos_invalidos_se_explican(self):
        """Fechas, opciones, números y ubicación incompleta generan mensajes útiles."""
        casos = [('Periódico','Inventado'),('Fecha de publicación',''),('Fecha de publicación','31/02/2026'),
                 ('Fecha de publicación','01/01/1969'),('Edición',''),('Número',''),('Número','ABC'),
                 ('Estante','X'),('Estante',''),('Gaveta','X'),('Estado','Inventado')]
        for campo,valor in casos:
            with self.subTest(campo=campo,valor=valor):
                with self.assertRaises(ValueError) as error:
                    preparar_ejemplar(dict(self.campos,**{campo:valor}))
                self.assertGreater(len(str(error.exception)),15)

    def test_misma_normalizacion_para_validar_y_guardar(self):
        """Los espacios exteriores de la edición se normalizan antes de ambas operaciones."""
        self.campos['Edición']=' Matutina '
        self.assertEqual(preparar_ejemplar(self.campos)[2],'Matutina')
