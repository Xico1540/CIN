from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from constants import EMISSION_METRO_G_PER_KM, EMISSION_STCP_G_PER_KM, PENALTY
from evolution import EMISSION_NORM_FACTOR, TIME_NORM_FACTOR


DEFAULT_LAMBDAS: Tuple[float, ...] = tuple(i / 20.0 for i in range(21))


@dataclass(frozen=True)
class BaselineSolution:
    lam: float
    path: List[str]
    metrics: Dict[str, float]
    weight_value: float


def _edge_emissions(edge_data: dict) -> float:
    distance_m = float(edge_data.get("distance_m", 0.0))
    mode = edge_data.get("mode")
    if mode == "stcp":
        factor = EMISSION_STCP_G_PER_KM
    elif mode == "metro":
        factor = EMISSION_METRO_G_PER_KM
    else:
        factor = 0.0
    return (distance_m / 1000.0) * factor


def _lambda_weight(lam: float):
    def weight(u, v, data):
        time_s = float(data.get("time_s", data.get("time", 1.0)))
        emissions = _edge_emissions(data)
        time_norm = time_s / TIME_NORM_FACTOR
        emis_norm = emissions / EMISSION_NORM_FACTOR
        return lam * time_norm + (1.0 - lam) * emis_norm

    return weight


def _accumulate_weight(path: Iterable[str], graph, lam: float) -> float:
    weight_fn = _lambda_weight(lam)
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = graph.G[u][v] if hasattr(graph, "G") else graph[u][v]
        total += weight_fn(u, v, data)
    return total


def _pareto_filter_solutions(solutions: List[BaselineSolution]) -> List[BaselineSolution]:
    """
    Filtra a lista de soluções baseline, removendo entradas dominadas em 2D
    (minimização de time_total_s e emissions_g).
    """
    if not solutions:
        return []

    points: List[Tuple[float, float]] = []
    for sol in solutions:
        m = sol.metrics
        t = float(m.get("time_total_s", float("inf")))
        e = float(m.get("emissions_g", float("inf")))
        points.append((t, e))

    pareto: List[BaselineSolution] = []
    for i, (ti, ei) in enumerate(points):
        dominated = False
        for j, (tj, ej) in enumerate(points):
            if j == i:
                continue
            if tj <= ti and ej <= ei and (tj < ti or ej < ei):
                dominated = True
                break
        if not dominated:
            pareto.append(solutions[i])
    return pareto


def run_baseline_dijkstra(
    graph,
    origin: str,
    dest: str,
    lambdas: Sequence[float] | None = None,
) -> List[BaselineSolution]:
    if lambdas is None:
        lambdas = DEFAULT_LAMBDAS

    solutions: List[BaselineSolution] = []
    seen_paths: set[Tuple[str, ...]] = set()

    for lam in lambdas:
        try:
            path = graph.shortest_path_between(origin, dest, weight=_lambda_weight(lam))
        except Exception:
            continue
        if not path or len(path) < 2:
            continue

        key = tuple(path)
        if key in seen_paths:
            continue

        try:
            metrics = graph.path_metrics(path)
        except Exception:
            continue
        if not isinstance(metrics, dict):
            continue

        # Aplicar a mesma regra de tarifa usada no NSGA-II:
        # se não houver qualquer segmento de trânsito, não há tarifa aplicada.
        segments = metrics.get("segments") or []
        has_transit = any(
            isinstance(seg, dict) and seg.get("transit")
            for seg in segments
        )
        if not has_transit:
            metrics = metrics.copy()
            metrics["fare_cost"] = 0.0
            metrics["fare_selected"] = None

        time_total = metrics.get("time_total_s")
        emissions = metrics.get("emissions_g")
        walk_m = metrics.get("walk_m")

        def _safe_float(value) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        if any(
            value is None or _safe_float(value) >= PENALTY
            for value in (time_total, emissions, walk_m)
        ):
            continue

        record = {
            "time_total_s": _safe_float(time_total),
            "emissions_g": _safe_float(emissions),
            "walk_m": _safe_float(walk_m),
            "travel_time_s": _safe_float(metrics.get("travel_time_s")),
            "waiting_time_s": _safe_float(metrics.get("waiting_time_s")),
            "fare_cost": _safe_float(metrics.get("fare_cost")),
            "n_transfers": int(_safe_float(metrics.get("n_transfers"))),
            "wait_s_total": _safe_float(metrics.get("wait_s_total")),
            "waits": metrics.get("waits"),
            "distance_km_by_mode": metrics.get("distance_km_by_mode"),
            "fare_selected": metrics.get("fare_selected"),
        }
        weight_value = _accumulate_weight(path, graph, lam)

        solutions.append(BaselineSolution(lam=lam, path=list(path), metrics=record, weight_value=weight_value))
        seen_paths.add(key)

    return solutions


def baseline_for_scenarios(
    graph,
    scenarios: Dict[str, List[Dict[str, object]]],
    lambdas: Sequence[float] | None = None,
) -> List[Dict[str, object]]:
    collected: List[Dict[str, object]] = []
    for scenario_type, items in scenarios.items():
        for index, scenario in enumerate(items):
            origin = scenario.get("origin")
            dest = scenario.get("destination")
            if origin is None or dest is None:
                continue

            solutions = run_baseline_dijkstra(graph, origin, dest, lambdas=lambdas)

            # Aplicar filtro Pareto 2D (tempo total, emissões) às soluções baseline.
            pareto_solutions = _pareto_filter_solutions(solutions)

            # Identificar extremos (mínimo tempo, mínimo emissões) dentro do conjunto.
            min_time_idx = None
            min_emis_idx = None
            if pareto_solutions:
                times = [float(sol.metrics.get("time_total_s", float("inf"))) for sol in pareto_solutions]
                emis = [float(sol.metrics.get("emissions_g", float("inf"))) for sol in pareto_solutions]
                min_time_idx = min(range(len(pareto_solutions)), key=lambda i: times[i])
                min_emis_idx = min(range(len(pareto_solutions)), key=lambda i: emis[i])

            serialized = []
            for idx, sol in enumerate(pareto_solutions):
                extreme: Optional[str] = None
                if min_time_idx is not None and idx == min_time_idx and idx == min_emis_idx:
                    extreme = "min_time_and_emissions"
                elif min_time_idx is not None and idx == min_time_idx:
                    extreme = "min_time"
                elif min_emis_idx is not None and idx == min_emis_idx:
                    extreme = "min_emissions"

                serialized.append(
                    {
                        "lambda": sol.lam,
                        "path": sol.path,
                        "metrics": sol.metrics,
                        "weight_value": sol.weight_value,
                        "extreme": extreme,
                    }
                )
            scenario_id = scenario.get("id")
            if not scenario_id:
                scenario_id = f"{scenario_type}_{index:03d}"
            collected.append(
                {
                    "type": scenario_type,
                    "id": scenario_id,
                    "index": index,
                    "origin": origin,
                    "destination": dest,
                    "length_edges_walk": scenario.get("length_edges_walk"),
                    "length_edges_shortest": scenario.get("length_edges_shortest"),
                    "solutions": serialized,
                }
            )
    return collected


