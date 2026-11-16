"""Gera modelo.json para a Rede Bayesiana compacta da PRF.

A estrutura e os parâmetros são especificados manualmente em código/configuração.
O DATATRAN é usado para contextualização e descrição, não para estimar CPTs.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARAMS_PATH = ROOT / "config" / "parametros_cpt.json"

VARIABLES = {
    "DIA_SEMANA": {
        "name": "Dia da semana",
        "description": "Dia útil, fim de semana ou informação ignorada.",
        "states": ["Dia útil", "Fim de semana", "Ignorado"],
        "parents": [],
    },
    "FASE_DIA": {
        "name": "Fase do dia",
        "description": "Fase temporal agrupada em pleno dia, transição (amanhecer/anoitecer), plena noite ou ignorada.",
        "states": ["Pleno dia", "Transição", "Plena noite", "Ignorada"],
        "parents": ["DIA_SEMANA"],
    },
    "METEOROLOGIA": {
        "name": "Condição meteorológica",
        "description": "Céu claro/sol, nublado, chuva/garoa, neblina/nevoeiro, outras adversas ou ignorada.",
        "states": ["Céu claro/sol", "Nublado", "Chuva/garoa", "Neblina/nevoeiro", "Outras adversas", "Ignorada"],
        "parents": [],
    },
    "REGIAO": {
        "name": "Região geográfica",
        "description": "Macrorregião brasileira derivada da UF registrada pela PRF.",
        "states": ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Ignorada"],
        "parents": [],
    },
    "USO_SOLO": {
        "name": "Uso do solo",
        "description": "Classificação do local como urbano, rural ou ignorado; no dicionário PRF, Sim corresponde a urbano e Não a rural.",
        "states": ["Urbano", "Rural", "Ignorado"],
        "parents": ["REGIAO"],
    },
    "TIPO_PISTA": {
        "name": "Tipo de pista",
        "description": "Tipo de pista registrado pela PRF: simples, dupla, múltipla ou ignorada.",
        "states": ["Simples", "Dupla", "Múltipla", "Ignorada"],
        "parents": ["USO_SOLO"],
    },
    "TRACADO_VIA": {
        "name": "Traçado da via",
        "description": "Traçado agrupado em reta, curva, cruzamento ou outros/ignorado.",
        "states": ["Reta", "Curva", "Cruzamento", "Outros/ignorado"],
        "parents": ["TIPO_PISTA"],
    },
    "TIPO_ACIDENTE": {
        "name": "Tipo de acidente",
        "description": "Categoria da ocorrência, preservando colisões frontais e traseiras, outras colisões, saída de pista/capotamento/tombamento, atropelamentos de pedestre/animal e outros/ignorado.",
        "states": ["Colisão frontal", "Colisão traseira", "Outras colisões", "Saída de pista/capotamento/tombamento", "Atropelamento de pedestre", "Atropelamento de animal", "Outros/ignorado"],
        "parents": ["TIPO_PISTA", "TRACADO_VIA"],
    },
    "VEICULOS": {
        "name": "Quantidade de veículos",
        "description": "Quantidade de veículos envolvidos, agrupada em um, dois, três ou mais, ou ignorada. Funciona como evidência diagnóstica indireta sobre o tipo de acidente.",
        "states": ["1", "2", "3 ou mais", "Ignorada"],
        "parents": ["TIPO_ACIDENTE"],
    },
    "GRAVIDADE": {
        "name": "Gravidade do acidente",
        "description": "Classificação da ocorrência na PRF: sem vítimas, com vítimas feridas ou com vítimas fatais.",
        "states": ["Sem vítimas", "Com vítimas feridas", "Com vítimas fatais"],
        "parents": ["TIPO_ACIDENTE", "METEOROLOGIA", "FASE_DIA"],
    },
}

EDGES = [
    {"from": parent, "to": child}
    for child, metadata in VARIABLES.items()
    for parent in metadata["parents"]
]

SCENARIOS = [
    {
        "id": "C1_colisao_frontal_tempo_claro_dia",
        "name": "Colisão frontal em céu claro durante o dia",
        "question": "Qual é a distribuição da gravidade para uma ocorrência classificada como colisão frontal, sob céu claro/sol e durante o pleno dia?",
        "evidence": {"TIPO_ACIDENTE": "Colisão frontal", "METEOROLOGIA": "Céu claro/sol", "FASE_DIA": "Pleno dia"},
        "query": "GRAVIDADE",
        "expected_result": None,
        "relevance": "Demonstra a consulta da variável-alvo para um tipo de colisão destacado na literatura nacional.",
    },
    {
        "id": "C2_atropelamento_pedestre",
        "name": "Atropelamento de pedestre",
        "question": "Como a rede distribui a gravidade para um atropelamento de pedestre durante o dia, sob céu claro/sol?",
        "evidence": {"TIPO_ACIDENTE": "Atropelamento de pedestre", "METEOROLOGIA": "Céu claro/sol", "FASE_DIA": "Pleno dia"},
        "query": "GRAVIDADE",
        "expected_result": None,
        "relevance": "Permite discutir o envolvimento de pedestres, fator associado à maior severidade em estudo brasileiro.",
    },
    {
        "id": "C3_saida_pista_neblina_noite",
        "name": "Saída de pista sob neblina durante a noite",
        "question": "Qual é a distribuição da gravidade quando o tipo de ocorrência é saída de pista/capotamento/tombamento, sob neblina e à noite?",
        "evidence": {"TIPO_ACIDENTE": "Saída de pista/capotamento/tombamento", "METEOROLOGIA": "Neblina/nevoeiro", "FASE_DIA": "Plena noite"},
        "query": "GRAVIDADE",
        "relevance": "Explora a combinação de baixa visibilidade, período noturno e tipo de ocorrência.",
    },
    {
        "id": "C4_diagnostico_veiculos_sem_tipo",
        "name": "Diagnóstico com apenas a evidência de múltiplos veículos",
        "question": "Sem informar o tipo de acidente, a meteorologia, a região ou a fase do dia, qual distribuição de gravidade a rede estima quando sabemos apenas que a ocorrência envolveu três ou mais veículos?",
        "evidence": {"VEICULOS": "3 ou mais"},
        "query": "GRAVIDADE",
        "relevance": "Demonstra inferência diagnóstica com informação parcial: a evidência sobre veículos atualiza os tipos de acidente possíveis, enquanto as distribuições iniciais de região e meteorologia também participam da inferência.",
    },
]


def normalize(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        raise ValueError("Distribuição com soma não positiva")
    return [float(value) / total for value in values]


def validate_vector(values: list[float], length: int, label: str, *, normalized: bool = False) -> None:
    if not isinstance(values, list) or len(values) != length:
        raise ValueError(f"{label}: esperados {length} números")
    if any(not isinstance(x, (int, float)) or x < 0 for x in values) or sum(values) <= 0:
        raise ValueError(f"{label}: valores devem ser números não negativos e soma positiva")
    if normalized and abs(sum(values) - 1.0) > 1e-8:
        raise ValueError(f"{label}: a distribuição-âncora deve somar 1")


def load_parameters() -> dict:
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    validate_parameters(params)
    return params


def validate_parameters(params: dict) -> None:
    for name, length in {"DIA_SEMANA": 3, "METEOROLOGIA": 6, "REGIAO": 6}.items():
        validate_vector(params["root_priors"][name], length, f"root_priors.{name}", normalized=True)
    mappings = [
        ("fase_dia_by_day", params["fase_dia_by_day"], 4, True),
        ("uso_solo_by_region", params["uso_solo_by_region"], 3, True),
        ("tipo_pista_by_land", params["tipo_pista_by_land"], 4, True),
        ("tracado_by_tipo_pista", params["tracado_by_tipo_pista"], 4, True),
        ("type_base", {"base": params["type_base"]}, 7, True),
        ("vehicles_by_type", params["vehicles_by_type"], 4, True),
        ("severity_base_by_type", params["severity_base_by_type"], 3, True),
    ]
    for label, mapping, length, normalized in mappings:
        for key, values in mapping.items():
            validate_vector(values, length, f"{label}.{key}", normalized=normalized)
    for group in ("type_geometry_multipliers", "tipo_pista_multipliers"):
        for key, values in params[group].items():
            validate_vector(values, 7, f"{group}.{key}")
    for variable, mapping in params["severity_multipliers"].items():
        for state, values in mapping.items():
            validate_vector(values, 3, f"severity_multipliers.{variable}.{state}")
    # Validar que os mapas cubrem exatamente os estados usados na rede.
    expected_keys = {
        "fase_dia_by_day": VARIABLES["DIA_SEMANA"]["states"],
        "uso_solo_by_region": VARIABLES["REGIAO"]["states"],
        "tipo_pista_by_land": VARIABLES["USO_SOLO"]["states"],
        "tracado_by_tipo_pista": VARIABLES["TIPO_PISTA"]["states"],
        "vehicles_by_type": VARIABLES["TIPO_ACIDENTE"]["states"],
        "severity_base_by_type": VARIABLES["TIPO_ACIDENTE"]["states"],
    }
    for key, states in expected_keys.items():
        if set(params[key]) != set(states):
            raise ValueError(f"{key}: chaves devem corresponder aos estados: {states}")
    if set(params["severity_multipliers"]) != {"METEOROLOGIA", "FASE_DIA"}:
        raise ValueError("severity_multipliers deve conter apenas METEOROLOGIA e FASE_DIA")
    for variable in ("METEOROLOGIA", "FASE_DIA"):
        if set(params["severity_multipliers"][variable]) != set(VARIABLES[variable]["states"]):
            raise ValueError(f"Multiplicadores incompletos para {variable}")


def make_cpt(variable: str, probability_function):
    parents = VARIABLES[variable]["parents"]
    parent_states = [VARIABLES[parent]["states"] for parent in parents]
    combinations = itertools.product(*parent_states) if parents else [()]
    rows = []
    for combination in combinations:
        parent_values = dict(zip(parents, combination))
        probabilities = normalize(probability_function(parent_values))
        states = VARIABLES[variable]["states"]
        rows.append({
            "when": parent_values,
            "probabilities": {state: round(prob, 10) for state, prob in zip(states, probabilities)},
        })
    return rows


def multiply(left: list[float], right: list[float]) -> list[float]:
    return [x * y for x, y in zip(left, right)]


def build_probability_functions(params: dict):
    def p_phase(p):
        return params["fase_dia_by_day"][p["DIA_SEMANA"]]

    def p_type_accident(p):
        scores = list(params["type_base"])
        scores = multiply(scores, params["type_geometry_multipliers"][p["TRACADO_VIA"]])
        scores = multiply(scores, params["tipo_pista_multipliers"][p["TIPO_PISTA"]])
        return scores

    def p_vehicles(p):
        return params["vehicles_by_type"][p["TIPO_ACIDENTE"]]

    def p_severity(p):
        scores = list(params["severity_base_by_type"][p["TIPO_ACIDENTE"]])
        for variable in ("METEOROLOGIA", "FASE_DIA"):
            scores = multiply(scores, params["severity_multipliers"][variable][p[variable]])
        return scores

    return {
        "DIA_SEMANA": lambda p: params["root_priors"]["DIA_SEMANA"],
        "FASE_DIA": p_phase,
        "METEOROLOGIA": lambda p: params["root_priors"]["METEOROLOGIA"],
        "REGIAO": lambda p: params["root_priors"]["REGIAO"],
        "USO_SOLO": lambda p: params["uso_solo_by_region"][p["REGIAO"]],
        "TIPO_PISTA": lambda p: params["tipo_pista_by_land"][p["USO_SOLO"]],
        "TRACADO_VIA": lambda p: params["tracado_by_tipo_pista"][p["TIPO_PISTA"]],
        "TIPO_ACIDENTE": p_type_accident,
        "VEICULOS": p_vehicles,
        "GRAVIDADE": p_severity,
    }


SCENARIO_LIST = SCENARIOS


def build_model():
    params = load_parameters()
    functions = build_probability_functions(params)
    cpts = {variable: make_cpt(variable, functions[variable]) for variable in VARIABLES}
    model = {
        "project": {
            "title": "Diagnóstico da Gravidade de Acidentes nas Rodovias Federais Brasileiras com Redes Bayesianas — modelo compacto",
            "version": "3.1.0",
            "dataset": "Dados Abertos de Acidentes da Polícia Rodoviária Federal (PRF), DATATRAN, agrupados por ocorrência",
            "dataset_years": [2021, 2022, 2023, 2024, 2025],
            "dataset_period": "2021-2025",
            "unit_of_analysis": "Uma linha por ocorrência de acidente registrada pela PRF",
            "source_url": "https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf",
            "dictionary_url": "https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dicionario-acidentes",
            "analysis_type": ["diagnóstica", "preditiva condicionada a evidências já registradas"],
            "main_question": "Dadas as características registradas da ocorrência, especialmente o tipo de acidente, a condição meteorológica e a fase do dia, qual é a distribuição de probabilidade entre acidente sem vítimas, com vítimas feridas e com vítimas fatais?",
            "probability_basis": "CPTs especificadas manualmente por âncoras, multiplicadores e distribuições condicionais editáveis. Os priors de METEOROLOGIA e REGIAO foram escolhidos manualmente como aproximações críticas das frequências descritivas PRF 2021–2025; as demais CPTs permanecem hipóteses manuais. Nenhuma estrutura ou CPT é aprendida/estimada automaticamente por algoritmo a partir dos CSVs.",
            "cpt_parameter_file": "config/parametros_cpt.json",
            "root_prior_definition": {
                "METEOROLOGIA": {
                    "states_order": ["Céu claro/sol", "Nublado", "Chuva/garoa", "Neblina/nevoeiro", "Outras adversas", "Ignorada"],
                    "observed_percent_2021_2025": [68.3382, 15.7641, 13.5759, 0.8282, 0.1786, 1.3150],
                    "selected_prior_percent": [66, 15, 15, 2, 1, 1],
                    "basis": "Aproximação manual crítica das frequências observadas; redistribui pequena parcela para chuva, neblina e outras condições adversas. Não é estimação automática da CPT."
                },
                "REGIAO": {
                    "states_order": ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul", "Ignorada"],
                    "observed_percent_2021_2025": [5.4132, 21.6649, 12.0176, 31.3049, 29.5995, 0.0],
                    "selected_prior_percent": [6, 20, 12, 32, 28, 2],
                    "basis": "Aproximação manual das frequências observadas; 2% são reservados ao estado Ignorada, embora não tenha ocorrido na base tratada. Não é frequência observada."
                }
            },
            "dataset_summary": {
                "records_read": 342670,
                "records_with_valid_severity": 342665,
                "records_excluded": 5,
                "years": [2021, 2022, 2023, 2024, 2025],
                "unit": "ocorrência de acidente"
            },
            "cpt_generation_method": "A CPT de GRAVIDADE parte de uma distribuição-âncora manual por tipo de acidente, aplica multiplicadores manuais de meteorologia e fase do dia e normaliza cada linha. Possui 7 × 6 × 4 = 168 configurações. A rede contém 10 variáveis e 10 arestas, totalizando 210 linhas de CPT. Os priors de meteorologia e região foram ajustados manualmente para aproximações críticas das frequências descritivas PRF 2021–2025; os outros parâmetros seguem hipóteses manuais. O modelo reduzido assume independências condicionais explícitas documentadas no README.md.",
            "research_sources": [
                {"citation": "FRANCESCHI, L. et al. (2022). Fatores relacionados à severidade de acidentes em rodovias no Brasil através de um modelo de regressão logística multinomial. Transportes, 30(1).", "url": "https://doi.org/10.14295/transportes.v30i1.2566", "use": "Fundamenta qualitativamente a importância do tipo de ocorrência/pedestre e a necessidade de distinguir condições de tempo; não fornece probabilidades absolutas para as CPTs deste projeto."},
                {"citation": "BARROSO JUNIOR, G. T.; BERTHO, A. C. S.; VEIGA, A. C. (2019). A letalidade dos acidentes de trânsito nas rodovias federais brasileiras em 2016. Revista Brasileira de Estudos de População, 36.", "url": "https://doi.org/10.20947/S0102-3098a0074", "use": "Oferece associações observacionais sobre letalidade, ambiente, período e via; a unidade de análise é vítima, distinta da gravidade por ocorrência usada aqui."},
                {"citation": "OBSERVATÓRIO NACIONAL DE SEGURANÇA VIÁRIA / UFPR (2026). Estudo revela o perfil da sinistralidade nas rodovias federais brasileiras.", "url": "https://www.onsv.org.br/comunicacao/materias/estudo-revela-o-perfil-da-sinistralidade-nas-rodovias-federais-brasileiras", "use": "Fonte contextual para diferenças entre colisões frontais/traseiras; não é uma CPT diretamente transferível."},
                {"citation": "ANDRIOLA, C. L.; TORRES, T. B.; GARCÍA, D. S. P. (2019). Influência dos parâmetros geométricos de rodovias na frequência e severidade de acidentes viários em curvas: o caso da BR 116. Transportes, 27(3).", "url": "https://doi.org/10.14295/transportes.v27i3.1997", "use": "Demonstra que o efeito de curvas depende de características geométricas específicas; sustenta cautela na interpretação da categoria agregada."},
                {"citation": "PRF. Dicionário de dados de acidentes (sistema BAT).", "url": "https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dicionario-acidentes", "use": "Fundamenta os significados operacionais dos campos DATATRAN."}
            ],
            "limitations": [
                "A rede estima a distribuição de gravidade entre ocorrências já registradas pela PRF em rodovias federais; não estima risco de acidente por trecho, veículo-quilômetro ou pessoa exposta.",
                "A CPT é manual e didática. As fontes sustentam direções qualitativas, mas não fornecem probabilidades absolutas para todas as configurações desta rede.",
                "As frequências descritivas dos 342.665 registros válidos de 2021-2025 não foram usadas para estimar automaticamente as CPTs; apenas os priors-raiz de METEOROLOGIA e REGIAO foram definidos manualmente como aproximações críticas dessas frequências, com redistribuições explicitadas no README.md.",
                "O modelo possui simplificações de independência condicional. Em particular, assume GRAVIDADE independente de TIPO_PISTA, TRACADO_VIA, USO_SOLO e VEICULOS uma vez conhecidos TIPO_ACIDENTE, METEOROLOGIA e FASE_DIA.",
                "DIA_SEMANA influencia FASE_DIA na fatoração, mas não é pai direto de GRAVIDADE; essa dependência compacta deve ser interpretada como associação da distribuição temporal, não causalidade.",
                "Os estudos citados são observacionais. Associação não comprova causalidade; odds ratios não foram convertidos diretamente em probabilidades absolutas.",
                "A classificação de gravidade é por ocorrência e não equivale à letalidade individual por vítima.",
                "Categorias agregadas não representam detalhes como velocidade efetiva, raio de curva, superelevação, declividade, volume de tráfego ou tempo de resposta do socorro.",
                "Os priors de METEOROLOGIA e REGIAO são aproximações manuais das frequências descritivas; o prior de DIA_SEMANA e as CPTs intermediárias continuam sendo hipóteses manuais. A massa de 2% atribuída a REGIAO=Ignorada não foi observada nos registros tratados e funciona como reserva manual para informação desconhecida. Todos os parâmetros exigem justificativa e análise de sensibilidade."
            ],
        },
        "variables": [{"id": variable, **metadata} for variable, metadata in VARIABLES.items()],
        "edges": EDGES,
        "cpts": cpts,
        "scenarios": SCENARIOS,
        "execution_metadata": {
            "language": "Python 3.10+",
            "libraries": ["biblioteca padrão do Python (json, itertools, csv, unittest)"],
            "inference": "Eliminação de variáveis exata, implementada manualmente; nenhuma aprendizagem automática da estrutura ou estimação automática das CPTs.",
            "model_version": "3.1.0",
            "cpt_parameter_file": "config/parametros_cpt.json",
        },
    }
    return model


if __name__ == "__main__":
    model = build_model()
    out = ROOT / "modelo.json"
    out.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    total_rows = sum(len(table) for table in model["cpts"].values())
    print(f"Modelo escrito em {out}")
    print(f"Variáveis: {len(model['variables'])}; arestas: {len(model['edges'])}; linhas de CPT: {total_rows}")
    print("Linhas de CPT por variável:")
    for variable, table in model["cpts"].items():
        print(f"  {variable}: {len(table)}")
