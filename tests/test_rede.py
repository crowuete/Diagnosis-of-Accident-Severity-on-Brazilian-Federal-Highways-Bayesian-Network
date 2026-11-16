from pathlib import Path
import copy
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inferencia import BayesianNetwork
from modelo_builder import build_model, load_parameters


class TestRedeBayesianaPRFCompacta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads((ROOT / "modelo.json").read_text(encoding="utf-8"))
        cls.network = BayesianNetwork(cls.model)
        cls.network.validate_cpts()

    def test_minimo_de_variaveis_e_dag(self):
        self.assertEqual(len(self.network.variables), 10)
        self.assertEqual(len(self.model["edges"]), 10)
        self.network.validate_structure()

    def test_variaveis_causa_removida_e_gravidade_preservada(self):
        self.assertNotIn("CAUSA", self.network.variables)
        self.assertIn("GRAVIDADE", self.network.variables)
        self.assertEqual(self.network.domains["GRAVIDADE"], [
            "Sem vítimas", "Com vítimas feridas", "Com vítimas fatais"
        ])

    def test_cpts_completas_e_quantidades_de_linhas(self):
        expected = {
            "DIA_SEMANA": 1,
            "FASE_DIA": 3,
            "METEOROLOGIA": 1,
            "REGIAO": 1,
            "USO_SOLO": 6,
            "TIPO_PISTA": 3,
            "TRACADO_VIA": 4,
            "TIPO_ACIDENTE": 16,
            "VEICULOS": 7,
            "GRAVIDADE": 168,
        }
        self.assertEqual({key: len(value) for key, value in self.network.cpts.items()}, expected)
        self.assertEqual(sum(expected.values()), 210)
        self.network.validate_cpts()

    def test_cpt_gravidade_tem_tres_pais_e_168_configuracoes(self):
        metadata = self.network.variables["GRAVIDADE"]
        self.assertEqual(metadata["parents"], ["TIPO_ACIDENTE", "METEOROLOGIA", "FASE_DIA"])
        self.assertEqual(len(self.network.cpts["GRAVIDADE"]), 7 * 6 * 4)

    def test_dag_contem_dependencias_planejadas(self):
        expected = {
            ("DIA_SEMANA", "FASE_DIA"),
            ("REGIAO", "USO_SOLO"),
            ("USO_SOLO", "TIPO_PISTA"),
            ("TIPO_PISTA", "TRACADO_VIA"),
            ("TIPO_PISTA", "TIPO_ACIDENTE"),
            ("TRACADO_VIA", "TIPO_ACIDENTE"),
            ("TIPO_ACIDENTE", "VEICULOS"),
            ("TIPO_ACIDENTE", "GRAVIDADE"),
            ("METEOROLOGIA", "GRAVIDADE"),
            ("FASE_DIA", "GRAVIDADE"),
        }
        actual = {(edge["from"], edge["to"]) for edge in self.model["edges"]}
        self.assertEqual(actual, expected)

    def test_consulta_marginal_normalizada(self):
        result = self.network.query("GRAVIDADE")
        self.assertAlmostEqual(sum(result.values()), 1.0, places=8)
        self.assertEqual(set(result), set(self.network.domains["GRAVIDADE"]))

    def test_quatro_cenarios_executam_e_sao_distintos(self):
        scenarios = self.model["scenarios"]
        self.assertEqual(len(scenarios), 4)
        self.assertEqual(len({item["id"] for item in scenarios}), 4)
        for scenario in scenarios:
            result = self.network.query(scenario["query"], scenario["evidence"])
            self.assertAlmostEqual(sum(result.values()), 1.0, places=8)
            self.assertTrue(all(0.0 <= value <= 1.0 for value in result.values()))

    def test_evidencia_invalida_rejeitada(self):
        with self.assertRaises(ValueError):
            self.network.query("GRAVIDADE", {"FASE_DIA": "Madrugada que não existe"})

    def test_colisao_frontal_tem_ancora_fatal_maior_que_traseira(self):
        frontal = self.network.query("GRAVIDADE", {"TIPO_ACIDENTE": "Colisão frontal"})
        rear = self.network.query("GRAVIDADE", {"TIPO_ACIDENTE": "Colisão traseira"})
        self.assertGreater(frontal["Com vítimas fatais"], rear["Com vítimas fatais"])

    def test_atropelamento_pedestre_tem_ancora_fatal_elevada(self):
        pedestrian = self.network.query("GRAVIDADE", {"TIPO_ACIDENTE": "Atropelamento de pedestre"})
        rear = self.network.query("GRAVIDADE", {"TIPO_ACIDENTE": "Colisão traseira"})
        self.assertGreater(pedestrian["Com vítimas fatais"], rear["Com vítimas fatais"])

    def test_pista_simples_aumenta_peso_de_colisao_frontal_no_tipo(self):
        single = self.network.query("TIPO_ACIDENTE", {"TIPO_PISTA": "Simples", "TRACADO_VIA": "Reta"})
        double = self.network.query("TIPO_ACIDENTE", {"TIPO_PISTA": "Dupla", "TRACADO_VIA": "Reta"})
        self.assertGreater(single["Colisão frontal"], double["Colisão frontal"])

    def test_neblina_tem_ajuste_fatal_maior_que_nublado(self):
        base = {"TIPO_ACIDENTE": "Outras colisões", "FASE_DIA": "Plena noite"}
        fog = self.network.query("GRAVIDADE", {**base, "METEOROLOGIA": "Neblina/nevoeiro"})
        cloudy = self.network.query("GRAVIDADE", {**base, "METEOROLOGIA": "Nublado"})
        self.assertGreater(fog["Com vítimas fatais"], cloudy["Com vítimas fatais"])

    def test_fase_noturna_tem_ajuste_fatal_maior_que_pleno_dia(self):
        base = {"TIPO_ACIDENTE": "Outras colisões", "METEOROLOGIA": "Nublado"}
        night = self.network.query("GRAVIDADE", {**base, "FASE_DIA": "Plena noite"})
        day = self.network.query("GRAVIDADE", {**base, "FASE_DIA": "Pleno dia"})
        self.assertGreater(night["Com vítimas fatais"], day["Com vítimas fatais"])

    def test_veiculos_atualiza_diagnostico_de_gravidade_indiretamente(self):
        many = self.network.query("GRAVIDADE", {"VEICULOS": "3 ou mais"})
        one = self.network.query("GRAVIDADE", {"VEICULOS": "1"})
        self.assertNotAlmostEqual(many["Com vítimas fatais"], one["Com vítimas fatais"], places=5)

    def test_veiculos_nao_tem_efeito_residual_dado_tipo_e_contexto(self):
        common = {
            "TIPO_ACIDENTE": "Colisão frontal",
            "METEOROLOGIA": "Céu claro/sol",
            "FASE_DIA": "Pleno dia",
        }
        one = self.network.query("GRAVIDADE", {**common, "VEICULOS": "1"})
        three = self.network.query("GRAVIDADE", {**common, "VEICULOS": "3 ou mais"})
        for state in self.network.domains["GRAVIDADE"]:
            self.assertAlmostEqual(one[state], three[state], places=8)

    def test_tipo_pista_nao_tem_efeito_residual_se_tipo_acidente_ja_evidenciado(self):
        common = {"TIPO_ACIDENTE": "Colisão frontal", "METEOROLOGIA": "Nublado", "FASE_DIA": "Pleno dia"}
        single = self.network.query("GRAVIDADE", {**common, "TIPO_PISTA": "Simples"})
        double = self.network.query("GRAVIDADE", {**common, "TIPO_PISTA": "Dupla"})
        for state in self.network.domains["GRAVIDADE"]:
            self.assertAlmostEqual(single[state], double[state], places=8)

    def test_parametros_editaveis_geram_mesmo_modelo(self):
        generated = build_model()
        self.assertEqual(generated["cpts"], self.model["cpts"])
        params = load_parameters()
        self.assertIn("severity_base_by_type", params)
        self.assertIn("severity_multipliers", params)

    def test_priors_raiz_somam_um(self):
        for variable in ("DIA_SEMANA", "METEOROLOGIA", "REGIAO"):
            row = self.network.cpts[variable][0]
            self.assertAlmostEqual(sum(row["probabilities"].values()), 1.0, places=8)

    def test_priors_meteorologia_correspondem_a_distribuicao_aprovada_pela_equipe(self):
        params = load_parameters()
        self.assertEqual(params["root_priors"]["METEOROLOGIA"], [0.66, 0.15, 0.15, 0.02, 0.01, 0.01])
        row = self.network.cpts["METEOROLOGIA"][0]["probabilities"]
        self.assertAlmostEqual(row["Céu claro/sol"], 0.66)
        self.assertAlmostEqual(row["Neblina/nevoeiro"], 0.02)

    def test_priors_regiao_correspondem_a_distribuicao_aprovada_pela_equipe(self):
        params = load_parameters()
        self.assertEqual(params["root_priors"]["REGIAO"], [0.06, 0.20, 0.12, 0.32, 0.28, 0.02])
        row = self.network.cpts["REGIAO"][0]["probabilities"]
        self.assertAlmostEqual(row["Norte"], 0.06)
        self.assertAlmostEqual(row["Ignorada"], 0.02)

    def test_metadata_dos_priors_registra_frequencias_observadas(self):
        project = self.model["project"]
        self.assertEqual(project["version"], "3.1.0")
        weather = project["root_prior_definition"]["METEOROLOGIA"]
        region = project["root_prior_definition"]["REGIAO"]
        self.assertEqual(weather["selected_prior_percent"], [66, 15, 15, 2, 1, 1])
        self.assertEqual(region["selected_prior_percent"], [6, 20, 12, 32, 28, 2])
        self.assertEqual(region["observed_percent_2021_2025"][-1], 0.0)
        self.assertIn("não é frequência observada", region["basis"].lower())

    def test_priors_de_clima_e_regiao_somam_um(self):
        params = load_parameters()
        for variable in ("METEOROLOGIA", "REGIAO"):
            self.assertAlmostEqual(sum(params["root_priors"][variable]), 1.0, places=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
