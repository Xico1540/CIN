from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, Tuple


Metric = Dict[str, float]


def _safe_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def _load_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _extract_metrics(entry: Dict[str, object]) -> Metric | None:
    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        return None
    result: Dict[str, float] = {}
    for key in ("time_total_s", "emissions_g", "walk_m"):
        val = _safe_float(metrics.get(key))
        if val is None:
            return None
        result[key] = val
    return result


def dominates(candidate: Metric, reference: Metric, walk_policy: str) -> bool:
    comparisons: Iterable[Tuple[bool, bool]] = []

    comparisons = list(comparisons) + [
        (
            candidate["time_total_s"] <= reference["time_total_s"],
            candidate["time_total_s"] < reference["time_total_s"],
        ),
        (
            candidate["emissions_g"] <= reference["emissions_g"],
            candidate["emissions_g"] < reference["emissions_g"],
        ),
    ]

    if walk_policy == "minimize":
        comparisons.append(
            (
                candidate["walk_m"] <= reference["walk_m"],
                candidate["walk_m"] < reference["walk_m"],
            )
        )
    else:
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

    if not baseline_path.exists() or not pareto_path.exists():
        return 0, 0

    baseline = _load_json(baseline_path).get("solutions", [])
    pareto = _load_json(pareto_path)

    pareto_metrics = [
        metric
        for metric in (_extract_metrics(entry) for entry in pareto)
        if metric is not None
    ]

    dominated = 0
    total = 0
    for sol in baseline:
        metrics = _extract_metrics(sol)
        if metrics is None:
            continue
        total += 1
        if any(dominates(candidate, metrics, walk_policy) for candidate in pareto_metrics):
            dominated += 1

    return dominated, total


def main():
    parser = argparse.ArgumentParser(
        description="Conta quantas soluções do baseline são dominadas pelas soluções NSGA-II."
    )
    parser.add_argument(
        "--root",
        default=str(Path("outputs") / "experiments"),
        help="Diretório com as execuções (default: outputs/experiments).",
    )
    parser.add_argument(
        "--walk-policy",
        choices=["maximize", "minimize"],
        default="maximize",
        help="Política usada no NSGA-II para interpretar o objetivo caminhada.",
    )

    args = parser.parse_args()
    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"Diretório {root} não existe.")

    total_dom = 0
    total_baseline = 0

    for scenario_dir in sorted(root.iterdir()):
        if not scenario_dir.is_dir():
            continue
        dominated, baseline_total = analyse_scenario(scenario_dir, args.walk_policy)
        if baseline_total == 0:
            print(f"{scenario_dir.name}: sem soluções baseline para comparar.")
            continue
        percent = dominated / baseline_total * 100.0
        print(f"{scenario_dir.name}: {dominated}/{baseline_total} dominados ({percent:.1f}%)")
        total_dom += dominated
        total_baseline += baseline_total

    if total_baseline:
        percent_total = total_dom / total_baseline * 100.0
        print(f"\nTotal: {total_dom}/{total_baseline} ({percent_total:.1f}%)")
    else:
        print("Nenhuma solução baseline encontrada.")


if __name__ == "__main__":
    main()



