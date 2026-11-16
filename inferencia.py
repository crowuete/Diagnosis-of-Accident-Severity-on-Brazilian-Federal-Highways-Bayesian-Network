"""Motor de inferência exata por eliminação de variáveis para redes discretas."""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


@dataclass
class Factor:
    variables: Tuple[str, ...]
    table: Dict[Tuple[str, ...], float]

    def restrict(self, evidence: Mapping[str, str]) -> "Factor":
        keep = tuple(v for v in self.variables if v not in evidence)
        idx_evidence = {self.variables.index(v): value for v, value in evidence.items() if v in self.variables}
        idx_keep = [self.variables.index(v) for v in keep]
        reduced = {}
        for assignment, value in self.table.items():
            if all(assignment[i] == state for i, state in idx_evidence.items()):
                reduced[tuple(assignment[i] for i in idx_keep)] = value
        return Factor(keep, reduced)

    def sum_out(self, variable: str) -> "Factor":
        if variable not in self.variables:
            return self
        idx = self.variables.index(variable)
        keep = tuple(v for v in self.variables if v != variable)
        result: Dict[Tuple[str, ...], float] = {}
        for assignment, value in self.table.items():
            reduced = assignment[:idx] + assignment[idx + 1:]
            result[reduced] = result.get(reduced, 0.0) + value
        return Factor(keep, result)

    def multiply(self, other: "Factor", domains: Mapping[str, Sequence[str]]) -> "Factor":
        union = self.variables + tuple(v for v in other.variables if v not in self.variables)
        if not union:
            left = self.table.get((), 0.0)
            right = other.table.get((), 0.0)
            return Factor((), {(): left * right})
        result: Dict[Tuple[str, ...], float] = {}
        self_indices = [union.index(v) for v in self.variables]
        other_indices = [union.index(v) for v in other.variables]
        state_lists = [domains[v] for v in union]
        for assignment in itertools.product(*state_lists):
            left_key = tuple(assignment[i] for i in self_indices)
            right_key = tuple(assignment[i] for i in other_indices)
            left = self.table.get(left_key, 0.0)
            if left == 0.0:
                continue
            right = other.table.get(right_key, 0.0)
            if right != 0.0:
                result[tuple(assignment)] = left * right
        return Factor(union, result)


class BayesianNetwork:
    def __init__(self, model: Mapping):
        self.model = model
        self.variables = {v["id"]: v for v in model["variables"]}
        self.domains = {v: meta["states"] for v, meta in self.variables.items()}
        self.parents = {v: list(meta["parents"]) for v, meta in self.variables.items()}
        self.cpts = model["cpts"]
        self.validate_structure()

    @classmethod
    def from_json(cls, path: str | Path) -> "BayesianNetwork":
        model = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(model)

    def validate_structure(self) -> None:
        if len(self.variables) < 10:
            raise ValueError("A rede precisa ter pelo menos 10 variáveis.")
        for variable, parents in self.parents.items():
            if variable not in self.cpts:
                raise ValueError(f"CPT ausente para {variable}")
            for parent in parents:
                if parent not in self.variables:
                    raise ValueError(f"Pai desconhecido: {parent}")
        # Kahn: valida se o grafo é acíclico.
        indegree = {v: len(ps) for v, ps in self.parents.items()}
        children = {v: [] for v in self.variables}
        for child, parents in self.parents.items():
            for parent in parents:
                children[parent].append(child)
        queue = [v for v, degree in indegree.items() if degree == 0]
        seen = 0
        while queue:
            node = queue.pop()
            seen += 1
            for child in children[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if seen != len(self.variables):
            raise ValueError("A estrutura contém ciclo; não é um DAG.")

    def validate_cpts(self) -> None:
        for variable, metadata in self.variables.items():
            parents = metadata["parents"]
            parent_states = [self.domains[p] for p in parents]
            expected = set(itertools.product(*parent_states)) if parents else {()}
            seen = set()
            rows = self.cpts.get(variable, [])
            for row in rows:
                when = row.get("when", {})
                if set(when) != set(parents):
                    raise ValueError(f"Configuração de pais incompleta/incorreta em {variable}: {when}")
                key = tuple(when[p] for p in parents)
                if key in seen:
                    raise ValueError(f"Configuração de pais duplicada em {variable}: {when}")
                seen.add(key)
                probabilities = row.get("probabilities", {})
                if set(probabilities) != set(self.domains[variable]):
                    raise ValueError(f"Estados de probabilidade incompletos em {variable}: {when}")
                values = list(probabilities.values())
                if any(not isinstance(x, (int, float)) or x < 0 or x > 1 for x in values):
                    raise ValueError(f"Probabilidade fora de [0,1] em {variable}: {when}")
                if abs(sum(values) - 1.0) > 1e-6:
                    raise ValueError(f"Probabilidades não somam 1 em {variable}: {when}")
            if seen != expected:
                raise ValueError(f"CPT incompleta em {variable}: esperadas {len(expected)}, recebidas {len(seen)}")

    def _factors(self) -> List[Factor]:
        factors = []
        for variable, metadata in self.variables.items():
            parents = metadata["parents"]
            scope = tuple(parents + [variable])
            table = {}
            for row in self.cpts[variable]:
                parent_assignment = tuple(row["when"][p] for p in parents)
                for state, probability in row["probabilities"].items():
                    table[parent_assignment + (state,)] = float(probability)
            factors.append(Factor(scope, table))
        return factors

    def _choose_elimination_variable(self, candidates: Iterable[str], factors: List[Factor]) -> str:
        best_variable = None
        best_cost = None
        for variable in candidates:
            related = [factor for factor in factors if variable in factor.variables]
            union = set(v for factor in related for v in factor.variables)
            cost = 1
            for item in union:
                if item != variable:
                    cost *= len(self.domains[item])
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_variable = variable
        return best_variable  # type: ignore[return-value]

    def query(self, query_variable: str, evidence: Mapping[str, str] | None = None) -> Dict[str, float]:
        evidence = dict(evidence or {})
        if query_variable not in self.variables:
            raise ValueError(f"Variável de consulta desconhecida: {query_variable}")
        for variable, value in evidence.items():
            if variable not in self.variables:
                raise ValueError(f"Evidência desconhecida: {variable}")
            if value not in self.domains[variable]:
                raise ValueError(f"Estado inválido para {variable}: {value!r}. Estados válidos: {self.domains[variable]}")
        if query_variable in evidence:
            return {state: float(state == evidence[query_variable]) for state in self.domains[query_variable]}

        factors = [factor.restrict(evidence) for factor in self._factors()]
        eliminate = set(self.variables) - set(evidence) - {query_variable}

        while eliminate:
            variable = self._choose_elimination_variable(eliminate, factors)
            related = [factor for factor in factors if variable in factor.variables]
            factors = [factor for factor in factors if variable not in factor.variables]
            if related:
                product = related[0]
                for factor in related[1:]:
                    product = product.multiply(factor, self.domains)
                factors.append(product.sum_out(variable))
            eliminate.remove(variable)

        if not factors:
            raise RuntimeError("Não foi possível construir fatores para a inferência.")
        result = factors[0]
        for factor in factors[1:]:
            result = result.multiply(factor, self.domains)
        # Remover variáveis residuais, caso a consulta esteja desconectada de alguma evidência.
        for variable in list(result.variables):
            if variable != query_variable:
                result = result.sum_out(variable)
        probabilities = {state: result.table.get((state,), 0.0) for state in self.domains[query_variable]}
        total = sum(probabilities.values())
        if total <= 0:
            raise ValueError("As evidências têm probabilidade conjunta zero no modelo.")
        return {state: value / total for state, value in probabilities.items()}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Executa uma consulta em uma Rede Bayesiana da PRF.")
    parser.add_argument("--model", default="modelo.json")
    parser.add_argument("--query", default="GRAVIDADE")
    parser.add_argument("--evidence", nargs="*", default=[], help="Pares VARIAVEL=ESTADO")
    args = parser.parse_args()
    evidence = {}
    for item in args.evidence:
        if "=" not in item:
            parser.error(f"Evidência malformada: {item}")
        key, value = item.split("=", 1)
        evidence[key] = value
    network = BayesianNetwork.from_json(args.model)
    network.validate_cpts()
    result = network.query(args.query, evidence)
    print(json.dumps({"query": args.query, "evidence": evidence, "probabilities": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
