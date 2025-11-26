from __future__ import annotations

from typing import Iterable, List, Tuple

Point = Tuple[float, float]  # (time_total_s, emissions_g)


def pareto_filter_2d_min(points: Iterable[Point]) -> List[Point]:
    """Filtra pontos dominados em 2D para minimização."""
    pts = sorted({(float(x), float(y)) for x, y in points}, key=lambda p: (p[0], p[1]))
    nd: List[Point] = []
    best_y = float("inf")
    for x, y in pts:
        if y < best_y:
            nd.append((x, y))
            best_y = y
    return nd


def hypervolume_2d_min(points: Iterable[Point], ref: Point) -> float:
    """
    Hipervolume em 2D para minimização.
    `ref` deve ser pior (maior) do que todos os pontos.
    """
    rx, ry = float(ref[0]), float(ref[1])
    front = pareto_filter_2d_min(points)
    if not front:
        return 0.0

    front.sort(key=lambda p: p[0])  # tempo ascendente

    hv = 0.0
    prev_y = ry
    for x, y in front:
        if x > rx or y > ry:
            # ponto fora do referencial -> ignora
            continue
        hv += (rx - x) * (prev_y - y)
        prev_y = y

    return max(0.0, hv)


def make_reference_from_union(a: Iterable[Point], b: Iterable[Point], margin: float = 1.10) -> Point:
    """Cria um ponto de referência (ref) a partir da união de dois conjuntos."""
    pts = list(a) + list(b)
    if not pts:
        return (1.0, 1.0)
    max_x = max(p[0] for p in pts)
    max_y = max(p[1] for p in pts)
    return (
        (max_x * margin) if max_x > 0 else 1.0,
        (max_y * margin) if max_y > 0 else 1.0,
    )
