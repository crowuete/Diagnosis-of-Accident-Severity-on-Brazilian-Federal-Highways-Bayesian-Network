from pathlib import Path
import csv
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preprocessar_prf import transform_row, group_weather, group_accident_type, group_phase, OUTPUT_FIELDS


class TestPreprocessamentoPRFCompacto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "fixtures" / "exemplo_prf_sintetico.csv"
        with path.open(encoding="utf-8-sig", newline="") as source:
            cls.rows = list(csv.DictReader(source, delimiter=";"))

    def test_saida_contem_exatamente_dez_variaveis_do_modelo(self):
        row = transform_row(self.rows[0])
        self.assertEqual(len(row), 10)
        self.assertEqual(set(row), set(OUTPUT_FIELDS))
        self.assertNotIn("CAUSA", row)

    def test_mapeia_registro_sintetico(self):
        row = transform_row(self.rows[0])
        self.assertEqual(row["DIA_SEMANA"], "Dia útil")
        self.assertEqual(row["REGIAO"], "Sul")
        self.assertEqual(row["METEOROLOGIA"], "Céu claro/sol")
        self.assertEqual(row["GRAVIDADE"], "Com vítimas feridas")

    def test_amanhecer_e_anoitecer_sao_agrupados_em_transicao(self):
        self.assertEqual(group_phase("Amanhecer"), "Transição")
        self.assertEqual(group_phase("Anoitecer"), "Transição")
        self.assertEqual(group_phase("Pleno dia"), "Pleno dia")
        self.assertEqual(group_phase("Plena noite"), "Plena noite")
        self.assertEqual(group_phase(""), "Ignorada")

    def test_saida_de_leito_carrocavel_e_agrupada(self):
        row = transform_row(self.rows[1])
        self.assertEqual(row["TIPO_ACIDENTE"], "Saída de pista/capotamento/tombamento")

    def test_gravidade_ignorada_e_excluida(self):
        row = transform_row(self.rows[4])
        self.assertIsNone(row)

    def test_uso_solo_prf_sim_significa_urbano(self):
        from preprocessar_prf import group_land
        self.assertEqual(group_land("Sim"), "Urbano")
        self.assertEqual(group_land("Não"), "Rural")

    def test_colisao_frontal_e_traseira_sao_separadas(self):
        self.assertEqual(group_accident_type("Colisão frontal"), "Colisão frontal")
        self.assertEqual(group_accident_type("Colisão traseira"), "Colisão traseira")
        self.assertEqual(group_accident_type("Colisão transversal"), "Outras colisões")

    def test_meteorologia_preserva_categorias_distintas(self):
        self.assertEqual(group_weather("Céu claro"), "Céu claro/sol")
        self.assertEqual(group_weather("Nublado"), "Nublado")
        self.assertEqual(group_weather("Chuva"), "Chuva/garoa")
        self.assertEqual(group_weather("Neblina"), "Neblina/nevoeiro")


if __name__ == "__main__":
    unittest.main(verbosity=2)
