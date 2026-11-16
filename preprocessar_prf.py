"""Padroniza o CSV oficial da PRF nas dez variáveis discretas do modelo compacto.

O script descreve e prepara os dados para contextualização. Ele NÃO estima
estrutura, parâmetros ou CPTs da Rede Bayesiana.
"""
from __future__ import annotations

import argparse
import csv
import json
import io
import re
import unicodedata
from collections import Counter
from pathlib import Path

UF_REGIAO = {
    **dict.fromkeys(["AC", "AP", "AM", "PA", "RO", "RR", "TO"], "Norte"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
    **dict.fromkeys(["DF", "GO", "MT", "MS"], "Centro-Oeste"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "Sul"),
}

OUTPUT_FIELDS = [
    "DIA_SEMANA", "FASE_DIA", "METEOROLOGIA", "REGIAO", "USO_SOLO",
    "TIPO_PISTA", "TRACADO_VIA", "TIPO_ACIDENTE", "VEICULOS", "GRAVIDADE"
]


def norm(value) -> str:
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_column(name: str) -> str:
    return norm(name).replace(" ", "_")


def get(row, *names, default=""):
    # Os CSVs oficiais usam nomes estáveis; a busca direta evita normalizar
    # todas as colunas repetidamente em centenas de milhares de registros.
    for name in names:
        if name in row:
            return row.get(name, default)
    normalized = {normalize_column(k): v for k, v in row.items()}
    for name in names:
        key = normalize_column(name)
        if key in normalized:
            return normalized[key]
    return default


def group_day(value: str) -> str:
    v = norm(value)
    if any(x in v for x in ["sabado", "domingo"]):
        return "Fim de semana"
    if not v:
        return "Ignorado"
    return "Dia útil"


def group_phase(value: str) -> str:
    """Agrupa amanhecer/anoitecer em Transição para reduzir estados."""
    v = norm(value)
    if "amanhecer" in v or "anoitecer" in v:
        return "Transição"
    if "pleno dia" in v or v == "dia":
        return "Pleno dia"
    if "noite" in v:
        return "Plena noite"
    return "Ignorada"


def group_weather(value: str) -> str:
    """Separa chuva de neblina, pois a literatura sugere mecanismos distintos."""
    v = norm(value)
    if not v or "ignorado" in v or "nao informado" in v:
        return "Ignorada"
    if any(x in v for x in ["nevoeiro", "neblina"]):
        return "Neblina/nevoeiro"
    if any(x in v for x in ["chuva", "garoa", "chuvisco"]):
        return "Chuva/garoa"
    if any(x in v for x in ["granizo", "neve", "vento", "tempestade"]):
        return "Outras adversas"
    if any(x in v for x in ["ceu claro", "ceu limpo", "sol"]):
        return "Céu claro/sol"
    if "nublado" in v:
        return "Nublado"
    return "Ignorada"


def group_land(value: str) -> str:
    """A PRF codifica uso_solo como Sim=Urbano e Não=Rural."""
    v = norm(value)
    if v in ("sim", "urbano", "area urbana") or "urbano" in v:
        return "Urbano"
    if v in ("nao", "rural", "area rural") or "rural" in v:
        return "Rural"
    return "Ignorado"


def group_road_type(value: str) -> str:
    v = norm(value)
    if "simples" in v:
        return "Simples"
    if "dupla" in v:
        return "Dupla"
    if "multipla" in v:
        return "Múltipla"
    return "Ignorada"


def group_geometry(value: str) -> str:
    v = norm(value)
    if "reta" in v:
        return "Reta"
    if "curva" in v:
        return "Curva"
    if any(x in v for x in ["cruzamento", "intersecao", "entroncamento", "rotatoria"]):
        return "Cruzamento"
    return "Outros/ignorado"


def group_accident_type(value: str) -> str:
    """Preserva colisão frontal e atropelamento de pedestre em estados próprios."""
    v = norm(value)
    if "atropelamento de pedestre" in v or "atropelamento de pessoa" in v:
        return "Atropelamento de pedestre"
    if "atropelamento de animal" in v:
        return "Atropelamento de animal"
    if "colisao frontal" in v:
        return "Colisão frontal"
    if "colisao traseira" in v:
        return "Colisão traseira"
    if "colisao" in v:
        return "Outras colisões"
    if any(x in v for x in ["saida de pista", "saida de leito carrocavel", "leito carrocavel", "capotamento", "tombamento", "derrapagem"]):
        return "Saída de pista/capotamento/tombamento"
    return "Outros/ignorado"


def group_vehicles(value: str) -> str:
    if not str(value).strip():
        return "Ignorada"
    try:
        n = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return "Ignorada"
    if n <= 1:
        return "1"
    if n == 2:
        return "2"
    return "3 ou mais"


def group_severity(value: str):
    v = norm(value)
    if "sem vitima" in v:
        return "Sem vítimas"
    if "fatal" in v or "vitimas fatais" in v:
        return "Com vítimas fatais"
    if "ferid" in v or "vitimas feridas" in v:
        return "Com vítimas feridas"
    return None


def transform_row(row: dict):
    uf = str(get(row, "uf", "estado", default="")).strip().upper()
    severity = group_severity(get(row, "classificacao_acidente", "classificação_acidente"))
    if severity is None:
        return None
    return {
        "DIA_SEMANA": group_day(get(row, "dia_semana")),
        "FASE_DIA": group_phase(get(row, "fase_dia")),
        "METEOROLOGIA": group_weather(get(row, "condicao_metereologica", "condicao_meteorologica", "condição_meteorológica")),
        "REGIAO": UF_REGIAO.get(uf, "Ignorada"),
        "USO_SOLO": group_land(get(row, "uso_solo")),
        "TIPO_PISTA": group_road_type(get(row, "tipo_pista")),
        "TRACADO_VIA": group_geometry(get(row, "tracado_via")),
        "TIPO_ACIDENTE": group_accident_type(get(row, "tipo_acidente")),
        "VEICULOS": group_vehicles(get(row, "veiculos", "quantidade_veiculos")),
        "GRAVIDADE": severity,
    }


def open_csv(path: Path):
    # Tenta UTF-8 e recua para Latin-1; o delimitador é detectado automaticamente.
    raw = path.read_bytes()
    text = None
    encoding_used = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            encoding_used = encoding
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise UnicodeError("Não foi possível decodificar o CSV como UTF-8 ou Latin-1.")
    sample = text[:50000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    return csv.DictReader(io.StringIO(text), dialect=dialect), encoding_used, dialect.delimiter


def main():
    parser = argparse.ArgumentParser(description="Prepara acidentes PRF (uma linha por ocorrência) para a rede bayesiana.")
    parser.add_argument("--input", nargs="+", required=True, help="Um ou mais CSVs originais baixados do portal da PRF.")
    parser.add_argument("--output", default="data/ocorrencias_tratadas.csv")
    parser.add_argument("--summary", default="data/resumo_descritivo.json")
    args = parser.parse_args()
    input_paths = [Path(item) for item in args.input]
    output_path, summary_path = Path(args.output), Path(args.summary)
    missing = [str(path) for path in input_paths if not path.exists()]
    if missing:
        parser.error("Arquivos de entrada não encontrados: " + ", ".join(missing))

    counts = {field: Counter() for field in OUTPUT_FIELDS}
    total = used = excluded = 0
    per_year = Counter()
    source_summaries = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as target:
        writer = csv.DictWriter(target, fieldnames=OUTPUT_FIELDS, delimiter=";")
        writer.writeheader()
        for input_path in input_paths:
            reader, encoding, delimiter = open_csv(input_path)
            source_total = source_used = source_excluded = 0
            for row in reader:
                total += 1
                source_total += 1
                date_value = str(get(row, "data_inversa", default="")).strip()
                year = date_value[:4] if re.match(r"^\d{4}-\d{2}-\d{2}$", date_value) else "Ano não identificado"
                per_year[(year, "lidas")] += 1
                transformed = transform_row(row)
                if transformed is None:
                    excluded += 1
                    source_excluded += 1
                    per_year[(year, "excluidas")] += 1
                    continue
                used += 1
                source_used += 1
                per_year[(year, "utilizadas")] += 1
                writer.writerow(transformed)
                for field, value in transformed.items():
                    counts[field][value] += 1
            source_summaries.append({
                "arquivo": input_path.name,
                "codificacao_detectada": encoding,
                "delimitador_detectado": delimiter,
                "linhas_lidas": source_total,
                "linhas_utilizadas": source_used,
                "linhas_excluidas": source_excluded,
            })

    years = sorted({year for year, kind in per_year if year != "Ano não identificado"})
    summary = {
        "periodo": f"{years[0]}-{years[-1]}" if years else None,
        "fontes": source_summaries,
        "linhas_lidas": total,
        "linhas_utilizadas": used,
        "linhas_excluidas_por_gravidade_ausente_ou_ignorada": excluded,
        "contagens_por_ano": {
            year: {
                "linhas_lidas": per_year[(year, "lidas")],
                "linhas_utilizadas": per_year[(year, "utilizadas")],
                "linhas_excluidas": per_year[(year, "excluidas")],
            }
            for year in years
        },
        "observacao": "Resumo descritivo; as frequências não alimentam nem estimam as CPTs manuais. A versão compacta utiliza dez variáveis e agrupa amanhecer/anoitecer em Transição.",
        "frequencias": {
            variable: {state: {"quantidade": n, "proporcao": round(n / used, 6) if used else 0.0} for state, n in counter.items()}
            for variable, counter in counts.items()
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["periodo", "linhas_lidas", "linhas_utilizadas", "linhas_excluidas_por_gravidade_ausente_ou_ignorada", "contagens_por_ano"]}, ensure_ascii=False, indent=2))
    print(f"Dados tratados: {output_path}\nResumo descritivo: {summary_path}")


if __name__ == "__main__":
    main()
