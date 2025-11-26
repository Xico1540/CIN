import argparse
import os
import pickle
from typing import Optional
from loader import load_system, PREFIX_METRO, PREFIX_STCP, PROJECT_ROOT
from graph_builder import MultimodalGraph, add_direct_walk_edge
from constants import PENALTY
from evolution import run_nsga2

OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
CACHE_DIR = os.path.join(OUTPUTS_DIR, "cache")
PARETO_DIR = os.path.join(OUTPUTS_DIR, "pareto")
GRAPH_CACHE_FILE = os.path.join(CACHE_DIR, "graph_cache.pkl")


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
def run_example(origin=None, dest=None, origin_name=None, dest_name=None,
                metro_folder=None, stcp_folder=None,
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

    # Garante estrutura de outputs/cache
    os.makedirs(CACHE_DIR, exist_ok=True)

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

    def resolve_stop_name(name: Optional[str], label: str) -> str:
        if not name:
            raise ValueError(f"Nome de paragem vazio para {label}")
        if not hasattr(G, "search_stops_by_name"):
            raise ValueError("Grafo não suporta pesquisa por nome de paragem. Recrie o cache com --no-cache.")
        matches = G.search_stops_by_name(name)
        if not matches:
            raise ValueError(f"Nenhuma paragem encontrada para '{name}'.")
        chosen = matches[0]
        if len(matches) > 1:
            preview_matches = ", ".join(
                f"{m['name']} [{m['node_id']}]" for m in matches[1:5]
            )
            print(f"[info] {label}: múltiplas correspondências para '{name}', a escolher {chosen['name']} [{chosen['node_id']}].")
            if preview_matches:
                print(f"[info] Outras correspondências: {preview_matches}")
        else:
            print(f"[info] {label}: '{name}' → {chosen['name']} [{chosen['node_id']}]")
        return chosen["node_id"]

    def resolve_input(stop_value, stop_name, label):
        if stop_value is not None:
            return resolve_with_virtual(stop_value, label)
        if stop_name:
            node_id = resolve_stop_name(stop_name, label)
            nodes.add(node_id)
            return node_id
        raise ValueError(f"É necessário indicar {label.lower()} via ID/coords ou nome.")

    origin_node = resolve_input(origin, origin_name, "ORIGIN")
    dest_node = resolve_input(dest, dest_name, "DEST")

    print(f"Origin resolved: {origin_node}, Destination resolved: {dest_node}")

    # Tentar adicionar aresta pedonal direta ORIGIN↔DEST se respeitar wmax_s e regras do Douro.
    try:
        nx_graph = G.G if hasattr(G, "G") else G
        o_data = nx_graph.nodes[origin_node]
        d_data = nx_graph.nodes[dest_node]
        origin_latlon = (float(o_data.get("lat")), float(o_data.get("lon")))
        dest_latlon = (float(d_data.get("lat")), float(d_data.get("lon")))
    except Exception:
        origin_latlon = None
        dest_latlon = None

    if origin_latlon and dest_latlon:
        added = add_direct_walk_edge(
            G,
            origin_node,
            dest_node,
            origin_latlon,
            dest_latlon,
            {"wmax_s": wmax_s},
        )
        if added:
            print("[info] Added direct walk edge ORIGIN↔DEST within wmax_s and bridge rules.")
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
    os.makedirs(PARETO_DIR, exist_ok=True)
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
        path_simplified = metrics.get("path_simplified")
        if isinstance(path_simplified, list) and path_simplified:
            path_out = path_simplified
        else:
            path_out = list(ind)
        solutions.append({
            "path": path_out,
            "time_s": time_total,
            "emissions_g": metrics.get("emissions_g"),
            "walk_m": metrics.get("walk_m"),
            "fare_cost": metrics.get("fare_cost"),
            "fare_selected": metrics.get("fare_selected"),
            "n_transfers": metrics.get("n_transfers"),
            "wait_s_total": metrics.get("wait_s_total"),
            "waits": metrics.get("waits"),
            "distance_km_by_mode": metrics.get("distance_km_by_mode"),
            "zones_passed": metrics.get("zones_passed"),
            "segments": segs,
            "has_walk": any(seg.get("mode") == "walk" for seg in segs),
        })
    pareto_path = os.path.join(PARETO_DIR, "pareto_solutions.json")
    with open(pareto_path, "w") as f:
        json.dump(solutions, f, indent=2)
    print("Pareto solutions saved to", pareto_path)



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--metro", default=None, help="Path to Metro GTFS folder")
    parser.add_argument("--stcp", default=None, help="Path to STCP GTFS folder")
    parser.add_argument("--origin", default=None, help="Origin stop ID")
    parser.add_argument("--dest", default=None, help="Destination stop ID")
    parser.add_argument("--origin-name", default=None,
                        help="Nome da paragem de origem (substitui --origin se usado).")
    parser.add_argument("--dest-name", default=None,
                        help="Nome da paragem de destino (substitui --dest se usado).")
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

    if not args.origin and not args.origin_name:
        parser.error("É obrigatório indicar origem (--origin ou --origin-name).")
    if not args.dest and not args.dest_name:
        parser.error("É obrigatório indicar destino (--dest ou --dest-name).")

    run_example(origin=args.origin,
                dest=args.dest,
                origin_name=args.origin_name,
                dest_name=args.dest_name,
                metro_folder=args.metro, stcp_folder=args.stcp,
                walk_radius=args.walk_radius,
                pop_size=args.pop_size,
                generations=args.gens,
                wmax_s=args.wmax_s,
                tmax=args.tmax,
                walk_policy=args.walk_policy,
                include_cost=args.include_cost)
