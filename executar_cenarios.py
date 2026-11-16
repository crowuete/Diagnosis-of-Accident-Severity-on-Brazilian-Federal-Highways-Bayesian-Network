from __future__ import annotations
import json
from pathlib import Path
from inferencia import BayesianNetwork

BASE = Path(__file__).resolve().parent
model = json.loads((BASE / "modelo.json").read_text(encoding="utf-8"))
network = BayesianNetwork(model)
network.validate_cpts()
results = []
for scenario in model["scenarios"]:
    probabilities = network.query(scenario["query"], scenario["evidence"])
    results.append({
        "id": scenario["id"],
        "name": scenario["name"],
        "question": scenario["question"],
        "evidence": scenario["evidence"],
        "query": scenario["query"],
        "probabilities": {state: round(value, 6) for state, value in probabilities.items()},
        "interpretation": "Resultado da inferência com os parâmetros manuais atuais; não representa frequência observada da PRF nem estimativa aprendida dos dados.",
    })
out = BASE / "data" / "resultados_cenarios.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
for item in results:
    print(f"\n{item['id']} — {item['name']}")
    for state, value in item["probabilities"].items():
        print(f"  {state}: {value:.2%}")
print(f"\nResultados salvos em {out}")
