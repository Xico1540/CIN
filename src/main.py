import argparse
import os
import pickle
from loader import load_system, PREFIX_METRO, PREFIX_STCP
from graph_builder import MultimodalGraph
from evolution import run_nsga2

GRAPH_CACHE_FILE = "graph_cache.pkl"

# python
def run_example(origin, dest, metro_folder=None, stcp_folder=None,
                walk_radius=400, pop_size=50, generations=30):

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

    origin_node = resolve_node(origin)
    dest_node = resolve_node(dest)

    print(f"Origin resolved: {origin_node}, Destination resolved: {dest_node}")
    print("Running NSGA-II...")
    pop = run_nsga2(G, origin_node, dest_node, pop_size=pop_size, ngen=generations)
    print("NSGA-II finished.")

    import json
    solutions = []
    for ind in pop:
        t, e, w = G.path_metrics(list(ind))
        solutions.append({
            "path": list(ind),
            "time_s": t,
            "emissions_g": e,
            "walk_m": w
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
    args = parser.parse_args()

    run_example(args.origin, args.dest,
                metro_folder=args.metro, stcp_folder=args.stcp,
                walk_radius=args.walk_radius,
                pop_size=args.pop_size,
                generations=args.gens)
