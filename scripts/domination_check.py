"""
Ferramenta para avaliar quantas soluções do baseline Dijkstra-λ
são dominadas pelas soluções geradas pelo NSGA-II.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, Tuple


MetricMap = Dict[str, float]


def _safe_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Ficheiro não encontrado: {path}") from exc


def _extract_metrics(entry: Dict[str, object]) -> MetricMap | None:
    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        return None
    result: MetricMap = {}
    for key in ("time_total_s", "emissions_g", "walk_m"):
        value = _safe_float(metrics.get(key))
        if value is None:
            return None
        result[key] = value
    return result


def dominates(
    candidate: MetricMap,
    reference: MetricMap,
    walk_policy: str,
) -> bool:
    """
    Determina se `candidate` domina `reference`.

    - tempo_total e emissões: menor é melhor.
    - walk_m: depende de `walk_policy` (minimize → menor; maximize → maior).
    """
    comparisons: Iterable[Tuple[bool, bool]] = []

    # tempo total
    comparisons = list(comparisons) + [
        (candidate["time_total_s"] <= reference["time_total_s"],
         candidate["time_total_s"] < reference["time_total_s"]),
        (candidate["emissions_g"] <= reference["emissions_g"],
         candidate["emissions_g"] < reference["emissions_g"]),
    ]

    if walk_policy == "minimize":
        comparisons.append(
            (
                candidate["walk_m"] <= reference["walk_m"],
                candidate["walk_m"] < reference["walk_m"],
            )
        )
    else:  # maximize
        comparisons.append(
            (
                candidate["walk_m"] >= reference["walk_m"],
                candidate["walk_m"] > reference["walk_m"],
            )
        )

    return all(flag for flag, _ in comparisons) and any(strict for _, strict in comparisons)


def analyse_scenario(scenario_dir: Path, walk_policy: str) -> Tuple[int, int]:
    baseline_path = scenario_dir / "baseline_pareto.json"
    pareto_path = scenario_dir / "pareto_solutions.json"

    baseline_data = _load_json(baseline_path)
    pareto_data = _load_json(pareto_path)

    baseline_solutions = baseline_data.get("solutions", [])
    pareto_solutions = [
        entry for entry in pareto_data
        if isinstance(entry, dict) and _extract_metrics(entry) is not None
    ]

    pareto_metrics = [_extract_metrics(entry) for entry in pareto_solutions]
    pareto_metrics = [metrics for metrics in pareto_metrics if metrics is not None]

    dominated = 0
    for solution in baseline_solutions:
        metrics = _extract_metrics(solution)
        if metrics is None:
            continue
        if any(dominates(candidate, metrics, walk_policy) for candidate in pareto_metrics):
            dominated += 1

    return dominated, len(baseline_solutions)


def main():
    parser = argparse.ArgumentParser(
        description="Conta quantas soluções do baseline são dominadas pelo NSGA-II."
    )
    parser.add_argument(
        "--root",
        default="experiments",
        help="Diretório raiz com os cenários exportados (default: experiments).",
    )
    parser.add_argument(
        "--walk-policy",
        choices=["maximize", "minimize"],
        default="maximize",
        help="Política usada no NSGA-II para o objetivo caminhada (default: maximize).",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"Diretório {root} não existe.")

    total_dominated = 0
    total_baseline = 0

    for scenario_dir in sorted(root.iterdir()):
        if not scenario_dir.is_dir():
            continue
        try:
            dominated, baseline_total = analyse_scenario(scenario_dir, args.walk_policy)
        except FileNotFoundError as exc:
            print(f"[AVISO] {exc}")
            continue

        percentage = (dominated / baseline_total * 100.0) if baseline_total else 0.0
        print(
            f"{scenario_dir.name}: {dominated}/{baseline_total} dominados "
            f"({percentage:.1f}%)"
        )
        total_dominated += dominated
        total_baseline += baseline_total

    if total_baseline:
        overall = total_dominated / total_baseline * 100.0
        print(f"\nTotal: {total_dominated}/{total_baseline} ({overall:.1f}%)")
    else:
        print("\nNenhuma solução de baseline encontrada.")


if __name__ == "__main__":
    main()


