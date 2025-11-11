import argparse
import os
import pickle
from loader import load_system, PREFIX_METRO, PREFIX_STCP
from graph_builder import MultimodalGraph
from evolution import PENALTY, run_nsga2

GRAPH_CACHE_FILE = "graph_cache.pkl"


def _parse_point(value):
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    if isinstance(value, str) and "," in value:
        parts = value.split(",")
        if len(parts) != 2:
            return None
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lat, lon
        except ValueError:
            return None
    return None

# python
def run_example(origin, dest, metro_folder=None, stcp_folder=None,
                walk_radius=400, pop_size=50, generations=30,
                wmax_s=None, tmax=None, walk_policy=None, include_cost=False):

    def candidate_ids(stop_id):
        s = str(stop_id)
        c = [s]
        if s.isdigit():
            c.append(int(s))
        # variantes com e sem prefixo/underscore
        c.append(PREFIX_METRO + s)
        c.append(PREFIX_STCP + s)
        c.append(PREFIX_METRO + "_" + s)
        c.append(PREFIX_STCP + "_" + s)
        # remover duplicados mantendo ordem
        return list(dict.fromkeys(c))

    # Tenta carregar grafo do cache
    if os.path.exists(GRAPH_CACHE_FILE):
        with open(GRAPH_CACHE_FILE, "rb") as f:
            G = pickle.load(f)
        print("Loading cached graph from", GRAPH_CACHE_FILE)
    else:
        print("Loading GTFS data...")
        data = load_system(metro_folder, stcp_folder)
        print("Building multimodal graph...")
        G = MultimodalGraph(data, walk_radius_m=walk_radius)
        with open(GRAPH_CACHE_FILE, "wb") as f:
            pickle.dump(G, f)
        print("Graph cached to", GRAPH_CACHE_FILE)

    # obter conjunto de nós do grafo (suporta wrapper com atributo G)
    try:
        nodes = set(G.G.nodes()) if hasattr(G, "G") else set(G.nodes())
    except Exception:
        nodes = set()

    print("Sample graph nodes (first 50):", list(nodes)[:50])

    def resolve_node(stop_id):
        tried = candidate_ids(stop_id)
        for cand in tried:
            if cand in nodes:
                return cand
        raise ValueError(
            f"Stop {stop_id} not found in graph. Tried candidates: {tried}. "
            f"Sample nodes: {list(nodes)[:50]}"
        )

    def resolve_with_virtual(value, label):
        point = _parse_point(value)
        if point:
            lat, lon = point
            node_id_base = f"{label}_VIRT"
            try:
                node_id = G.add_virtual_point(node_id_base, lat, lon)
            except ValueError as exc:
                raise ValueError(f"Não foi possível ligar o ponto virtual '{value}': {exc}") from exc
            nodes.add(node_id)
            return node_id
        return resolve_node(value)

    origin_node = resolve_with_virtual(origin, "ORIGIN")
    dest_node = resolve_with_virtual(dest, "DEST")

    print(f"Origin resolved: {origin_node}, Destination resolved: {dest_node}")
    print("Running NSGA-II...")
    pop = run_nsga2(
        G,
        origin_node,
        dest_node,
        pop_size=pop_size,
        ngen=generations,
        walk_policy=walk_policy,
        w_max=wmax_s,
        t_max=tmax,
        include_cost=include_cost,
    )
    print("NSGA-II finished.")

    import json
    solutions = []
    seen = set()
    for ind in pop:
        key = tuple(ind)
        if key in seen: 
            continue
        seen.add(key)
        if any(val >= PENALTY for val in ind.fitness.values):
            continue
        metrics = G.path_metrics(list(ind))
        segs = metrics.get("segments") or []
        time_total = sum(seg.get("time_s", 0.0) for seg in segs)
        solutions.append({
            "path": list(ind),
            "time_s": time_total,
            "emissions_g": metrics.get("emissions_g"),
            "walk_m": metrics.get("walk_m"),
            "fare_cost": metrics.get("fare_cost"),
            "n_transfers": metrics.get("n_transfers"),
            "zones_passed": metrics.get("zones_passed"),
            "segments": segs,
            "has_walk": any(seg.get("mode") == "walk" for seg in segs),
        })
    with open("pareto_solutions.json", "w") as f:
        json.dump(solutions, f, indent=2)
    print("Pareto solutions saved to pareto_solutions.json")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--metro", default=None, help="Path to Metro GTFS folder")
    parser.add_argument("--stcp", default=None, help="Path to STCP GTFS folder")
    parser.add_argument("--origin", required=True, help="Origin stop ID")
    parser.add_argument("--dest", required=True, help="Destination stop ID")
    parser.add_argument("--walk-radius", type=int, default=400, help="Walking radius in meters")
    parser.add_argument("--pop-size", type=int, default=50, help="Population size")
    parser.add_argument("--gens", type=int, default=30, help="Number of generations")
    parser.add_argument("--wmax-s", type=float, default=None,
                        help="Limite total de tempo a pé (segundos).")
    parser.add_argument("--tmax", type=int, default=None,
                        help="Máximo de transbordos permitidos.")
    parser.add_argument("--walk-policy", choices=["maximize", "minimize"], default=None,
                        help="Política para o objetivo de caminhada (maximize por omissão).")
    parser.add_argument("--include-cost", action="store_true",
                        help="Adicionar custo como quarto objetivo na otimização.")
    args = parser.parse_args()

    run_example(args.origin, args.dest,
                metro_folder=args.metro, stcp_folder=args.stcp,
                walk_radius=args.walk_radius,
                pop_size=args.pop_size,
                generations=args.gens,
                wmax_s=args.wmax_s,
                tmax=args.tmax,
                walk_policy=args.walk_policy,
                include_cost=args.include_cost)
