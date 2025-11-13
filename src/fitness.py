"""
Funções de avaliação de fitness para o planeador multimodal.
"""

from __future__ import annotations

import os
from typing import Iterable, Tuple

from constants import EMISSION_METRO_G_PER_KM, EMISSION_STCP_G_PER_KM, PENALTY

WALK_POLICY_MAXIMIZE = "maximize"
WALK_POLICY_MINIMIZE = "minimize"
DEFAULT_WALK_POLICY = os.environ.get("CIN_WALK_POLICY", WALK_POLICY_MAXIMIZE).lower()


def _resolve_walk_policy(policy: str | None) -> str:
    if policy is None:
        policy = DEFAULT_WALK_POLICY
    policy = policy.lower()
    if policy not in {WALK_POLICY_MAXIMIZE, WALK_POLICY_MINIMIZE}:
        policy = WALK_POLICY_MAXIMIZE
    return policy


def _objective_from_walk(walk_m: float, policy: str) -> float:
    if policy == WALK_POLICY_MINIMIZE:
        return walk_m
    return -walk_m


def fitness_from_metrics(metrics: dict, walk_policy: str | None = None) -> Tuple[float, float, float]:
    policy = _resolve_walk_policy(walk_policy)
    return _tuple_from_metrics(metrics, policy)


def evaluate_route(graph, path: Iterable[str], walk_policy: str | None = None) -> Tuple[float, float, float]:
    """
    Calcula o fitness para um caminho.

    Se `graph` for uma instância de `MultimodalGraph`, usa `path_metrics` para
    obter tempo total, emissões e distância a pé. Caso contrário, cai para uma
    avaliação direta sobre um grafo NetworkX (modo legacy).
    """
    try:
        if hasattr(graph, "path_metrics"):
            metrics = graph.path_metrics(list(path))
            return fitness_from_metrics(metrics, walk_policy)
        # fallback legacy
        return _evaluate_legacy_graph(graph, path, _resolve_walk_policy(walk_policy))
    except Exception:
        return PENALTY, PENALTY, PENALTY


def _tuple_from_metrics(metrics: dict, policy: str) -> Tuple[float, float, float]:
    if not isinstance(metrics, dict):
        raise TypeError("path_metrics deve devolver um dicionário com as métricas.")
    time_total = metrics.get("time_total_s", PENALTY)
    emissions = metrics.get("emissions_g", PENALTY)
    walk_m = metrics.get("walk_m", PENALTY)

    if any(val is None for val in (time_total, emissions, walk_m)):
        return PENALTY, PENALTY, PENALTY
    if time_total >= PENALTY or emissions >= PENALTY or walk_m >= PENALTY:
        return PENALTY, PENALTY, PENALTY

    return (
        float(time_total),
        float(emissions),
        float(_objective_from_walk(float(walk_m), policy)),
    )


def _evaluate_legacy_graph(graph, path: Iterable[str], policy: str) -> Tuple[float, float, float]:
    total_time = 0.0
    total_emissions = 0.0
    walking_distance = 0.0

    for u, v in zip(path[:-1], path[1:]):
        if not graph.has_edge(u, v):
            return PENALTY, PENALTY, PENALTY
        data = graph[u][v]
        mode = data.get("mode", "unknown")
        dist = float(data.get("distance_m", 0.0))
        time = float(data.get("time_s", data.get("time", 0.0)))
        total_time += time

        if mode == "walk":
            walking_distance += dist
        elif mode == "stcp":
            total_emissions += (dist / 1000.0) * EMISSION_STCP_G_PER_KM
        elif mode == "metro":
            total_emissions += (dist / 1000.0) * EMISSION_METRO_G_PER_KM

    return total_time, total_emissions, _objective_from_walk(walking_distance, policy)
