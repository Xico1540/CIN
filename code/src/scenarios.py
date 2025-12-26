import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import networkx as nx


Scenario = Dict[str, object]


DEFAULT_LENGTH_BUCKETS: Dict[str, Tuple[int, Optional[int]]] = {
    "short": (1, 3),
    "mid": (6, 10),
    "long": (12, None),
}


def _get_nx_graph(graph) -> nx.DiGraph:
    if hasattr(graph, "G"):
        return graph.G
    if isinstance(graph, nx.DiGraph):
        return graph
    raise TypeError("graph deve ser MultimodalGraph ou nx.DiGraph")


def _candidate_nodes(G: nx.DiGraph) -> List[str]:
    nodes: List[str] = []
    for node_id, data in G.nodes(data=True):
        mode = data.get("mode")
        if mode in {"metro", "stcp"}:
            nodes.append(node_id)
    if not nodes:
        nodes = list(G.nodes())
    return nodes


def _random_walk_steps(
    G: nx.DiGraph,
    origin: str,
    steps: int,
    rng: random.Random,
    avoid_revisit: bool = True,
) -> Optional[List[str]]:
    path = [origin]
    visited = {origin}
    current = origin
    for _ in range(steps):
        successors = list(G.successors(current))
        if not successors:
            return None
        if avoid_revisit:
            candidates = [n for n in successors if n not in visited]
        else:
            candidates = successors
        if not candidates:
            return None
        current = rng.choice(candidates)
        path.append(current)
        visited.add(current)
    return path


def _length_in_bucket(length: int, bucket: Tuple[int, Optional[int]]) -> bool:
    lower, upper = bucket
    if length < lower:
        return False
    if upper is not None and length > upper:
        return False
    return True


def _shortest_path_length(
    graph,
    origin: str,
    dest: str,
    weight: str | None = "time_s",
) -> Optional[int]:
    try:
        path = graph.shortest_path_between(origin, dest, weight=weight)
    except Exception:
        return None
    if not path:
        return None
    return max(len(path) - 1, 0)


def generate_scenarios(
    graph,
    n: int = 10,
    types: Sequence[str] = ("short", "mid", "long"),
    random_seed: Optional[int] = None,
    length_buckets: Optional[Dict[str, Tuple[int, Optional[int]]]] = None,
    max_attempts_per_type: int = 10_000,
    include_walk_path: bool = False,
) -> Dict[str, List[Scenario]]:
    """
    Gera pares origem-destino categorizados por comprimento alvo.

    Para cada tipo especificado, seleciona até `n` pares O-D gerados via
    random walks no grafo. Os intervalos de comprimento (em número de arestas)
    podem ser configurados através de `length_buckets`.
    """
    if n <= 0:
        raise ValueError("n deve ser > 0")

    buckets = dict(DEFAULT_LENGTH_BUCKETS)
    if length_buckets:
        buckets.update(length_buckets)

    for t in types:
        if t not in buckets:
            raise KeyError(f"Tipo '{t}' não tem intervalo definido.")

    rng = random.Random(random_seed)
    G = _get_nx_graph(graph)
    nodes = _candidate_nodes(G)
    if not nodes:
        raise ValueError("Grafo não contém nós elegíveis para gerar cenários.")

    scenarios: Dict[str, List[Scenario]] = {t: [] for t in types}

    for t in types:
        bucket = buckets[t]
        attempts = 0
        seen_pairs: set[Tuple[str, str]] = set()

        while len(scenarios[t]) < n and attempts < max_attempts_per_type:
            attempts += 1
            origin = rng.choice(nodes)
            min_len, max_len = bucket
            if max_len is None:
                steps = rng.randint(min_len, min_len + 8)
            else:
                steps = rng.randint(min_len, max_len)

            walk_path = _random_walk_steps(G, origin, steps, rng)
            if not walk_path or len(walk_path) < 2:
                continue

            dest = walk_path[-1]
            if origin == dest:
                continue

            pair_key = (origin, dest)
            if pair_key in seen_pairs:
                continue

            actual_len = len(walk_path) - 1
            if not _length_in_bucket(actual_len, bucket):
                continue

            shortest_len = _shortest_path_length(graph, origin, dest)
            if shortest_len is None:
                continue

            scenario: Scenario = {
                "origin": origin,
                "destination": dest,
                "length_edges_walk": actual_len,
                "length_edges_shortest": shortest_len,
                "type": t,
            }
            if include_walk_path:
                scenario["walk_path"] = walk_path

            scenarios[t].append(scenario)
            seen_pairs.add(pair_key)

    return scenarios


