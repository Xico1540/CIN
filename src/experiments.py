import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Dict, List, Sequence

from baselines import baseline_for_scenarios, DEFAULT_LAMBDAS
from evolution import PENALTY, run_nsga2
from graph_builder import MultimodalGraph
from loader import load_system
from scenarios import generate_scenarios


GRAPH_CACHE_FILE = "graph_cache.pkl"


def load_or_build_graph(
    metro_folder: str | None,
    stcp_folder: str | None,
    walk_radius: int,
    cache_file: str | None = GRAPH_CACHE_FILE,
    use_cache: bool = True,
) -> MultimodalGraph:
    if use_cache and cache_file and os.path.exists(cache_file):
        with open(cache_file, "rb") as fh:
            return pickle.load(fh)

    data = load_system(metro_folder, stcp_folder)
    graph = MultimodalGraph(data, walk_radius_m=walk_radius)

    if use_cache and cache_file:
        with open(cache_file, "wb") as fh:
            pickle.dump(graph, fh)

    return graph


def serialize_population(graph: MultimodalGraph, population, include_cost: bool = False) -> List[dict]:
    solutions: List[dict] = []
    seen = set()
    for ind in population:
        path = list(ind)
        key = tuple(path)
        if key in seen:
            continue
        seen.add(key)

        if any(val >= PENALTY for val in ind.fitness.values):
            continue

        try:
            metrics = graph.path_metrics(path)
        except Exception:
            continue
        if not isinstance(metrics, dict):
            continue
        if metrics.get("time_total_s", PENALTY) >= PENALTY or metrics.get("emissions_g", PENALTY) >= PENALTY:
            continue

        segments = metrics.get("segments") or []
        info = {
            "path": path,
            "metrics": {
                "time_total_s": metrics.get("time_total_s"),
                "travel_time_s": metrics.get("travel_time_s"),
                "waiting_time_s": metrics.get("waiting_time_s"),
                "wait_s_total": metrics.get("wait_s_total"),
                "emissions_g": metrics.get("emissions_g"),
                "walk_m": metrics.get("walk_m"),
                "n_transfers": metrics.get("n_transfers"),
                "fare_cost": metrics.get("fare_cost"),
                "fare_selected": metrics.get("fare_selected"),
                "waits": metrics.get("waits"),
                "distance_km_by_mode": metrics.get("distance_km_by_mode"),
            },
            "segments": segments,
            "zones_passed": metrics.get("zones_passed"),
            "has_walk": any(isinstance(seg, dict) and seg.get("mode") == "walk" for seg in segments),
        }
        solutions.append(info)
    return solutions


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def parse_types(value: str) -> Sequence[str]:
    return tuple(filter(None, [item.strip() for item in value.split(",")]))


def main():
    parser = argparse.ArgumentParser(description="Runner para experiências com cenários e baseline Dijkstra-λ.")
    parser.add_argument("--metro", default=None, help="Pasta com os ficheiros GTFS do Metro.")
    parser.add_argument("--stcp", default=None, help="Pasta com os ficheiros GTFS da STCP.")
    parser.add_argument("--walk-radius", type=int, default=400, help="Raio de caminhada em metros.")
    parser.add_argument("--scenarios", type=int, default=10, help="Número de cenários por tipo.")
    parser.add_argument(
        "--scenario-types",
        default="short,mid,long",
        help="Tipos de cenários (separados por vírgulas).",
    )
    parser.add_argument("--random-seed", type=int, default=None, help="Seed para geração de cenários.")
    parser.add_argument("--output-dir", default="experiments", help="Diretório onde guardar os resultados.")
    parser.add_argument("--graph-cache", default=GRAPH_CACHE_FILE, help="Ficheiro para cache do grafo.")
    parser.add_argument("--no-cache", action="store_true", help="Não utilizar cache do grafo.")
    parser.add_argument("--pop-size", type=int, default=50, help="Tamanho da população NSGA-II.")
    parser.add_argument("--gens", type=int, default=30, help="Número de gerações NSGA-II.")
    parser.add_argument("--walk-policy", choices=["maximize", "minimize"], default=None, help="Política para objetivo caminhada.")
    parser.add_argument("--wmax-s", type=float, default=None, help="Limite total de tempo a pé (segundos).")
    parser.add_argument("--tmax", type=int, default=None, help="Número máximo de transbordos.")
    parser.add_argument("--include-cost", action="store_true", help="Incluir custo tarifário como quarto objetivo.")
    parser.add_argument(
        "--lambdas",
        default=None,
        help="Valores de λ separados por vírgula para o baseline (por omissão usa 0.0,0.05,...,1.0).",
    )
    parser.add_argument("--seed-lambdas", default=None, help="Valores de λ para seeds NSGA-II (por omissão usa baseline).")

    args = parser.parse_args()

    scenario_types = parse_types(args.scenario_types)
    if not scenario_types:
        raise ValueError("Deve indicar pelo menos um tipo de cenário.")

    lambdas = (
        tuple(float(x) for x in args.lambdas.split(","))
        if args.lambdas
        else DEFAULT_LAMBDAS
    )
    seed_lambdas = (
        tuple(float(x) for x in args.seed_lambdas.split(","))
        if args.seed_lambdas
        else None
    )

    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    graph = load_or_build_graph(
        args.metro,
        args.stcp,
        args.walk_radius,
        cache_file=args.graph_cache,
        use_cache=not args.no_cache,
    )

    scenarios = generate_scenarios(
        graph,
        n=args.scenarios,
        types=scenario_types,
        random_seed=args.random_seed,
        include_walk_path=True,
    )

    scenario_records: List[Dict[str, object]] = []
    for scenario_type, items in scenarios.items():
        for index, scenario in enumerate(items):
            scenario_id = f"{scenario_type}_{index:03d}"
            scenario["id"] = scenario_id
            scenario["index"] = index
            scenario_records.append(scenario)
        print(f"[cenários] {scenario_type}: {len(items)} gerados.")

    save_json(output_dir / "scenarios.json", scenario_records)

    baseline_results = baseline_for_scenarios(graph, scenarios, lambdas=lambdas)
    for entry in baseline_results:
        scenario_dir = output_dir / entry["id"]
        ensure_dir(scenario_dir)
        save_json(scenario_dir / "baseline_pareto.json", entry)
    save_json(output_dir / "baseline_summary.json", baseline_results)

    for scenario in scenario_records:
        scenario_id = scenario["id"]
        origin = scenario["origin"]
        dest = scenario["destination"]
        print(f"[NSGA-II] {scenario_id}: {origin} -> {dest}")
        pop = run_nsga2(
            graph,
            origin,
            dest,
            pop_size=args.pop_size,
            ngen=args.gens,
            walk_policy=args.walk_policy,
            w_max=args.wmax_s,
            t_max=args.tmax,
            include_cost=args.include_cost,
            seed_lambdas=seed_lambdas if seed_lambdas is not None else lambdas,
        )
        solutions = serialize_population(graph, pop, include_cost=args.include_cost)
        scenario_dir = output_dir / scenario_id
        ensure_dir(scenario_dir)
        save_json(scenario_dir / "pareto_solutions.json", solutions)


if __name__ == "__main__":
    main()


