import difflib
import json
import math
import os
import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

import networkx as nx
import pandas as pd

from constants import (
    EMISSION_METRO_G_PER_KM,
    EMISSION_STCP_G_PER_KM,
    PENALTY,
    WALK_SPEED_M_S,
)
from loader import BRIDGE_RULES, PROJECT_ROOT, load_bridge_rules

WALK_RADIUS_METERS = 400
METRO_CRUISE_SPEED_KMH = 40.0
STCP_CRUISE_SPEED_KMH = 30.0

# Bounding box aproximado do Douro na zona urbana (Porto-Gaia)
DOURO_MIN_LAT = 41.12
DOURO_MAX_LAT = 41.16
DOURO_MIN_LON = -8.65
DOURO_MAX_LON = -8.56
# Linha média aproximada do rio: latitudes superiores ≈ margem norte (Porto),
# inferiores ≈ margem sul (Gaia).
DOURO_MID_LAT = 41.138

_DOURO_DEBUG_COUNT = 0
_BRIDGES_GEOMETRY_CACHE: Optional[List[dict]] = None
BRIDGES_GEOMETRY_PATH = os.path.join(
    PROJECT_ROOT, "data", "bridges", "bridges_geometry.json"
)


def to_seconds(hms: str) -> int:
    h, m, s = map(int, str(hms).split(":"))
    return h * 3600 + m * 60 + s


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Versão explícita de Haversine que devolve a distância em metros.

    Nota: a função `haversine` existente já devolve metros; esta é apenas
    uma *wrapper* com nome mais expressivo para reutilização noutros módulos.
    """
    return float(haversine(lat1, lon1, lat2, lon2))


def point_to_segment_distance_m(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """
    Distância mínima (em metros) entre um ponto P e o segmento AB definido em lat/lon.

    Usa uma projecção aproximada (equirectangular) adequada para distâncias locais
    na área do Grande Porto. Para segmentos muito grandes a aproximação deixa de ser
    rigorosa, mas é suficiente para modelar travessias de pontes.
    """
    lat_p, lon_p = p
    lat_a, lon_a = a
    lat_b, lon_b = b

    # Se A e B coincidirem, devolve distância ponto–ponto.
    if lat_a == lat_b and lon_a == lon_b:
        return haversine_m(lat_p, lon_p, lat_a, lon_a)

    # Conversão aproximada lat/lon → metros numa projecção local.
    ref_lat = (lat_a + lat_b + lat_p) / 3.0
    meters_per_deg_lat = 111_000.0
    cos_lat = math.cos(math.radians(ref_lat))
    if abs(cos_lat) < 1e-6:
        cos_lat = 1e-6
    meters_per_deg_lon = 111_000.0 * cos_lat

    def to_xy(lat: float, lon: float) -> tuple[float, float]:
        x = (lon - lon_a) * meters_per_deg_lon
        y = (lat - lat_a) * meters_per_deg_lat
        return x, y

    ax, ay = 0.0, 0.0
    bx, by = to_xy(lat_b, lon_b)
    px, py = to_xy(lat_p, lon_p)

    abx, aby = bx - ax, by - ay
    ab_len2 = abx * abx + aby * aby
    if ab_len2 == 0.0:
        # Segmento degenerado, já tratado acima mas fica aqui por segurança.
        dx, dy = px - ax, py - ay
        return math.hypot(dx, dy)

    # Projecção de AP sobre AB (parâmetro t em [0,1] ao longo do segmento).
    apx, apy = px - ax, py - ay
    t = (apx * abx + apy * aby) / ab_len2
    t = max(0.0, min(1.0, t))

    closest_x = ax + t * abx
    closest_y = ay + t * aby

    dx = px - closest_x
    dy = py - closest_y
    return math.hypot(dx, dy)


def remove_cycles(path: Iterable[str]) -> List[str]:
    """
    Remove ciclos simples de um caminho mantendo apenas a primeira ocorrência
    de cada nó e cortando loops intermédios.

    Exemplo:
        [A, B, C, B, D] -> [A, B, D]
        [A, B, C, D]    -> igual
    """
    result: List[str] = []
    last_index: Dict[str, int] = {}

    for node in path:
        if node in last_index:
            idx = last_index[node]
            # remover nós após idx no resultado e do mapa de índices
            for removed in result[idx + 1 :]:
                last_index.pop(removed, None)
            result = result[: idx + 1]
        else:
            last_index[node] = len(result)
            result.append(node)

    return result


def _in_douro_bbox(lat: float, lon: float) -> bool:
    """
    Verifica se o ponto está dentro de uma bounding box aproximada para o Douro
    na zona urbana Porto–Gaia.
    """
    return (
        DOURO_MIN_LAT <= lat <= DOURO_MAX_LAT
        and DOURO_MIN_LON <= lon <= DOURO_MAX_LON
    )


def is_douro_walk_crossing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> bool:
    """
    Heurística simples: uma aresta walk "cruza o Douro" se ligar dois pontos
    dentro da bounding box do rio mas em lados opostos da latitude média.

    Não tenta modelar o traçado exacto do rio — apenas distingue de forma
    robusta "margem norte" vs "margem sul" na zona urbana.
    """
    # Ambos os pontos têm de estar na zona do rio; caso contrário não é travessia.
    if not (_in_douro_bbox(lat1, lon1) and _in_douro_bbox(lat2, lon2)):
        return False

    side1_north = lat1 >= DOURO_MID_LAT
    side2_north = lat2 >= DOURO_MID_LAT

    # Se estão em lados diferentes da linha média, consideramos travessia.
    return side1_north != side2_north


def crosses_douro(
    p1: tuple[float, float],
    p2: tuple[float, float],
    debug: bool = False,
) -> bool:
    """
    Devolve True se o segmento walk entre P1 e P2 ligar lados opostos do Douro
    dentro da zona urbana (bounding box aproximada).

    Se `debug=True`, imprime até 5 exemplos de travessias detetadas para
    validação manual.
    """
    global _DOURO_DEBUG_COUNT

    lat1, lon1 = p1
    lat2, lon2 = p2
    crossed = is_douro_walk_crossing(lat1, lon1, lat2, lon2)

    if debug and crossed and _DOURO_DEBUG_COUNT < 5:
        _DOURO_DEBUG_COUNT += 1
        print(
            f"[douro-debug] crossing detected (#{_DOURO_DEBUG_COUNT}): "
            f"P1=({lat1:.6f},{lon1:.6f}) P2=({lat2:.6f},{lon2:.6f})"
        )

    return crossed


def _load_bridges_geometry() -> List[dict]:
    """
    Carrega e faz cache da geometria de pontes a partir de
    `data/bridges/bridges_geometry.json`.
    """
    global _BRIDGES_GEOMETRY_CACHE
    if _BRIDGES_GEOMETRY_CACHE is not None:
        return _BRIDGES_GEOMETRY_CACHE

    try:
        with open(BRIDGES_GEOMETRY_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                _BRIDGES_GEOMETRY_CACHE = data
            else:
                _BRIDGES_GEOMETRY_CACHE = []
    except (OSError, json.JSONDecodeError):
        _BRIDGES_GEOMETRY_CACHE = []

    return _BRIDGES_GEOMETRY_CACHE


def nearest_bridge_for_walk_edge(
    p1: tuple[float, float],
    p2: tuple[float, float],
    bridges_geometry: Optional[List[dict]] = None,
) -> Optional[str]:
    """
    Dado um segmento walk P1->P2, devolve o `bridge_id` da ponte mais próxima
    do ponto médio do segmento, respeitando o `snap_radius_m` da ponte.

    Se não houver nenhuma ponte suficientemente próxima, devolve None.
    """
    if bridges_geometry is None:
        bridges_geometry = _load_bridges_geometry()

    if not bridges_geometry:
        return None

    lat1, lon1 = p1
    lat2, lon2 = p2
    mid_lat = 0.5 * (lat1 + lat2)
    mid_lon = 0.5 * (lon1 + lon2)

    best_id: Optional[str] = None
    best_dist: Optional[float] = None
    best_radius: float = 0.0

    for bridge in bridges_geometry:
        try:
            b_id = str(bridge.get("id") or "").strip()
            b_lat = float(bridge.get("midpoint_lat"))
            b_lon = float(bridge.get("midpoint_lon"))
            snap_radius = float(bridge.get("snap_radius_m", 0.0))
        except (TypeError, ValueError):
            continue
        if not b_id or snap_radius <= 0.0:
            continue

        d = haversine_m(mid_lat, mid_lon, b_lat, b_lon)
        if best_dist is None or d < best_dist:
            best_dist = d
            best_id = b_id
            best_radius = snap_radius

    if best_dist is None or best_id is None:
        return None

    if best_dist > best_radius:
        return None

    return best_id


def is_walk_edge_allowed(
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> bool:
    """
    Regra de conveniência: usa a heurística do Douro + regras globais de pontes.

    Mantida para compatibilidade, mas a lógica principal está agora em
    `_add_walking_edges`, `add_virtual_point` e `add_direct_walk_edge`.
    """
    if not crosses_douro(p1, p2):
        return True
    if not BRIDGE_RULES:
        load_bridge_rules()
    bridge_id = nearest_bridge_for_walk_edge(p1, p2)
    if bridge_id is None:
        return False
    return bool(BRIDGE_RULES.get(bridge_id))


def add_direct_walk_edge(
    graph,
    origin_id: str,
    dest_id: str,
    origin_latlon: tuple[float, float],
    dest_latlon: tuple[float, float],
    config: Optional[dict] = None,
) -> bool:
    """
    Adiciona uma aresta pedonal direta ORIGIN→DEST (e o inverso) se:

    - respeitar um eventual limite global de tempo a pé (`wmax_s`, em segundos);
    - respeitar as regras de travessia do Douro/pontes, quando aplicáveis.

    Retorna True se a aresta foi realmente adicionada, False caso contrário.
    """
    if config is None:
        config = {}

    wmax_s = config.get("wmax_s")

    lat_o, lon_o = origin_latlon
    lat_d, lon_d = dest_latlon

    # distância e tempo a pé
    dist_m = haversine_m(lat_o, lon_o, lat_d, lon_d)
    walk_time_s = dist_m / WALK_SPEED_M_S

    # respeitar limite global de caminhada se existir
    if wmax_s is not None:
        try:
            wmax_val = float(wmax_s)
        except (TypeError, ValueError):
            wmax_val = None
        if wmax_val is not None and walk_time_s > wmax_val:
            return False

    p1 = (lat_o, lon_o)
    p2 = (lat_d, lon_d)

    bridge_attr = None
    # aplicar regras do Douro/pontes se atravessar a zona do rio
    if crosses_douro(p1, p2):
        if not BRIDGE_RULES:
            load_bridge_rules()
        bridge_id = nearest_bridge_for_walk_edge(p1, p2)
        allowed = bool(bridge_id and BRIDGE_RULES.get(bridge_id))
        if not allowed:
            if hasattr(graph, "blocked_douro_walk_edges"):
                graph.blocked_douro_walk_edges += 1
            return False
        bridge_attr = bridge_id

    # obter o objeto networkx interno (MultimodalGraph ou DiGraph cru)
    G_obj = graph.G if hasattr(graph, "G") else graph

    if origin_id not in G_obj or dest_id not in G_obj:
        return False

    attrs = {
        "mode": "walk",
        "transit": False,
        "time_s": walk_time_s,
        "time": walk_time_s,
        "distance_m": dist_m,
        "route_id": None,
        "trip_id": None,
    }
    if bridge_attr is not None:
        attrs["bridge_id"] = bridge_attr

    G_obj.add_edge(origin_id, dest_id, **attrs)
    G_obj.add_edge(dest_id, origin_id, **attrs)

    return True


def _fallback_speed(mode: str) -> float:
    if mode == "metro":
        return METRO_CRUISE_SPEED_KMH * 1000 / 3600
    return STCP_CRUISE_SPEED_KMH * 1000 / 3600


def _normalize_text(value: str) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


class MultimodalGraph:
    def __init__(self, data, walk_radius_m=WALK_RADIUS_METERS):
        self.walk_radius = walk_radius_m
        self.metro = data.get("metro", {})
        self.stcp = data.get("stcp", {})
        self.networks = {
            "metro": self.metro,
            "stcp": self.stcp,
        }

        self.fare_attributes = pd.DataFrame()
        self.fare_rules = pd.DataFrame()
        self._prepare_fares()

        self.route_headways: Dict[Tuple[str, str], float] = {}
        self.headway_by_route: Dict[str, float] = {}
        self.virtual_nodes: set[str] = set()
        self.blocked_douro_walk_edges: int = 0
        self.G = nx.DiGraph()
        self.node_lookup: Dict[Tuple[str, str], str] = {}
        self._build_nodes()
        self._build_edges()
        self._compute_route_headways()

    # ---------------------- construção do grafo ---------------------- #

    def _ensure_state_compatibility(self):
        if not hasattr(self, "route_headways"):
            self.route_headways = {}
        if not hasattr(self, "fare_attributes"):
            self.fare_attributes = pd.DataFrame()
        if not hasattr(self, "fare_rules"):
            self.fare_rules = pd.DataFrame()

    def _prepare_stops(self, system: dict, mode: str) -> pd.DataFrame:
        stops = system.get("stops")
        if stops is None or stops.empty:
            return pd.DataFrame(columns=["node_id", "stop_id", "mode", "prefix", "zone_id", "stop_lat", "stop_lon"])
        df = stops.copy()
        prefix = system.get("prefix", mode.upper())
        df["mode"] = mode
        df["prefix"] = prefix
        df["stop_id"] = df["stop_id"].astype(str)
        if "stop_name" not in df.columns:
            df["stop_name"] = None
        df["stop_name"] = df["stop_name"].fillna("").astype(str)
        if "zone_id" not in df.columns:
            df["zone_id"] = None
        df["node_id"] = df.apply(lambda r: f"{prefix}_{r['stop_id']}", axis=1)
        for _, row in df.iterrows():
            self.node_lookup[(mode, row["stop_id"])] = row["node_id"]
        return df[["node_id", "stop_id", "stop_name", "mode", "prefix", "zone_id", "stop_lat", "stop_lon"]]

    def _build_nodes(self):
        frames = []
        for mode, system in self.networks.items():
            frames.append(self._prepare_stops(system, mode))
        if frames:
            self.stops = pd.concat(frames, ignore_index=True)
        else:
            self.stops = pd.DataFrame(columns=["node_id", "stop_id", "mode", "prefix", "zone_id", "stop_lat", "stop_lon"])
        for _, row in self.stops.iterrows():
            self.G.add_node(
                row["node_id"],
                lat=float(row["stop_lat"]),
                lon=float(row["stop_lon"]),
                mode=row["mode"],
                zone_id=row.get("zone_id"),
                stop_id=row["stop_id"],
                prefix=row["prefix"],
                stop_name=row.get("stop_name"),
            )

    def _build_edges(self):
        for mode, system in self.networks.items():
            self._add_transit_edges(system, mode)
            self._add_transfer_edges(system, mode)
        self._add_walking_edges()

    def _add_transit_edges(self, system: dict, mode: str):
        stop_times = system.get("stop_times")
        trips = system.get("trips")
        if stop_times is None or trips is None or stop_times.empty or trips.empty:
            return

        merge_cols = ["trip_id"]
        if "route_id" in trips.columns:
            merge_cols.append("route_id")
        trip_info = trips[merge_cols].copy()
        merged = stop_times.merge(trip_info, on="trip_id", how="left")
        merged = merged.sort_values(by=["trip_id", "stop_sequence"])
        prev = None
        for _, row in merged.iterrows():
            if prev is not None and prev["trip_id"] == row["trip_id"]:
                u = self.node_lookup.get((mode, str(prev["stop_id"])))
                v = self.node_lookup.get((mode, str(row["stop_id"])))
                if not u or not v or u == v or u not in self.G or v not in self.G:
                    prev = row
                    continue
                lat1, lon1 = self.G.nodes[u]["lat"], self.G.nodes[u]["lon"]
                lat2, lon2 = self.G.nodes[v]["lat"], self.G.nodes[v]["lon"]
                dist = haversine(lat1, lon1, lat2, lon2)
                time_s = self._edge_time_seconds(prev, row, dist, mode)
                route_id = row.get("route_id")
                attrs = {
                    "mode": mode,
                    "operator": system.get("prefix", mode.upper()),
                    "transit": True,
                    "distance_m": dist,
                    "time_s": time_s,
                    "time": time_s,
                    "route_id": None if pd.isna(route_id) else str(route_id),
                    "trip_id": str(row["trip_id"]),
                }
                self.G.add_edge(u, v, **attrs)
            prev = row

    def _edge_time_seconds(self, prev_row, curr_row, dist_m: float, mode: str) -> float:
        time_s: Optional[float] = None
        try:
            arr = to_seconds(str(curr_row["arrival_time"]))
            dep = to_seconds(str(prev_row["departure_time"]))
            candidate = arr - dep
            if candidate > 0:
                time_s = float(candidate)
        except Exception:
            time_s = None
        if time_s is None:
            speed = _fallback_speed(mode)
            time_s = max(dist_m / speed, 1.0)
        return float(time_s)

    def _add_transfer_edges(self, system: dict, mode: str):
        transfers = system.get("transfers")
        if transfers is None or transfers.empty:
            return

        for _, row in transfers.iterrows():
            from_stop = row.get("from_stop_id")
            to_stop = row.get("to_stop_id")
            if pd.isna(from_stop) or pd.isna(to_stop):
                continue

            from_id = self.node_lookup.get((mode, str(from_stop)))
            to_id = self.node_lookup.get((mode, str(to_stop)))
            if not from_id or not to_id or from_id not in self.G or to_id not in self.G:
                continue

            transfer_type = row.get("transfer_type")
            try:
                transfer_type_int = int(transfer_type) if not pd.isna(transfer_type) else None
            except (TypeError, ValueError):
                transfer_type_int = None

            # GTFS: 3 = transferência não permitida → ignorar
            if transfer_type_int == 3:
                continue

            transfer_time = 0.0
            if "min_transfer_time" in transfers.columns:
                val = row.get("min_transfer_time")
                try:
                    transfer_time = float(val) if not pd.isna(val) else 0.0
                except (TypeError, ValueError):
                    transfer_time = 0.0

            attrs = {
                "mode": "transfer",
                "transit": False,
                "time_s": transfer_time,
                "time": transfer_time,
                "distance_m": 0.0,
                "route_id": None,
                "trip_id": None,
                "transfer_type": transfer_type_int,
            }
            self.G.add_edge(from_id, to_id, **attrs)

    def _walk_cell_index(self):
        """
        Constrói um índice espacial em grelha para as paragens de modo a
        limitar a procura de vizinhos a células próximas.
        """
        stops_list = self.stops[["node_id", "stop_lat", "stop_lon"]].values.tolist()
        if not stops_list:
            return {}, 0.0, 0.0

        # Aproximação: 1 grau de latitude ~ 111 km
        lats = [float(lat) for _, lat, _ in stops_list]
        ref_lat = sum(lats) / len(lats)
        meters_per_deg_lat = 111_000.0
        cos_lat = math.cos(math.radians(ref_lat))
        if abs(cos_lat) < 1e-6:
            cos_lat = 1e-6
        meters_per_deg_lon = 111_000.0 * cos_lat

        cell_size_deg_lat = self.walk_radius / meters_per_deg_lat
        cell_size_deg_lon = self.walk_radius / meters_per_deg_lon

        grid: Dict[Tuple[int, int], List[Tuple[str, float, float]]] = {}
        for node_id, lat, lon in stops_list:
            lat_f = float(lat)
            lon_f = float(lon)
            cy = int(math.floor(lat_f / cell_size_deg_lat))
            cx = int(math.floor(lon_f / cell_size_deg_lon))
            grid.setdefault((cx, cy), []).append((node_id, lat_f, lon_f))

        return grid, cell_size_deg_lat, cell_size_deg_lon

    def _add_walking_edges(self):
        grid, _, _ = self._walk_cell_index()
        if not grid:
            return

        seen_pairs: set[Tuple[str, str]] = set()

        for (cx, cy), items in grid.items():
            for node_id, lat, lon in items:
                for nx_cell in (cx - 1, cx, cx + 1):
                    for ny_cell in (cy - 1, cy, cy + 1):
                        for other_id, other_lat, other_lon in grid.get((nx_cell, ny_cell), []):
                            if other_id == node_id:
                                continue
                            pair = (node_id, other_id) if node_id < other_id else (other_id, node_id)
                            if pair in seen_pairs:
                                continue
                            seen_pairs.add(pair)

                            d = haversine(lat, lon, other_lat, other_lon)
                            if d <= self.walk_radius:
                                p1 = (float(lat), float(lon))
                                p2 = (float(other_lat), float(other_lon))

                                # Classifica travessias do Douro e conta bloqueios.
                                if crosses_douro(p1, p2):
                                    if not BRIDGE_RULES:
                                        load_bridge_rules()
                                    bridge_id = nearest_bridge_for_walk_edge(p1, p2)
                                    allowed = bool(bridge_id and BRIDGE_RULES.get(bridge_id))
                                    if not allowed:
                                        self.blocked_douro_walk_edges += 1
                                        continue
                                    bridge_attr = bridge_id
                                else:
                                    allowed = True
                                    bridge_attr = None

                                if not allowed:
                                    continue

                                walk_time = d / WALK_SPEED_M_S
                                attrs_forward = {
                                    "mode": "walk",
                                    "transit": False,
                                    "time_s": walk_time,
                                    "time": walk_time,
                                    "distance_m": d,
                                }
                                if bridge_attr is not None:
                                    attrs_forward["bridge_id"] = bridge_attr
                                attrs_backward = attrs_forward.copy()
                                u, v = pair
                                if not self.G.has_edge(u, v) or not self.G[u][v].get("transit", False):
                                    self.G.add_edge(u, v, **attrs_forward)
                                if not self.G.has_edge(v, u) or not self.G[v][u].get("transit", False):
                                    self.G.add_edge(v, u, **attrs_backward)

    # ---------------------- headways e tarifas ---------------------- #

    def nearest_stops(self, lat: float, lon: float, radius_m: float = 600.0, k: int = 8):
        candidates = []
        for node_id, attrs in self.G.nodes(data=True):
            if attrs.get("mode") in ("metro", "stcp"):
                dist = haversine(lat, lon, float(attrs.get("lat")), float(attrs.get("lon")))
                if radius_m is None or dist <= radius_m:
                    candidates.append((node_id, dist))
        if not candidates and radius_m is not None:
            # fallback sem raio para garantir k resultados
            for node_id, attrs in self.G.nodes(data=True):
                if attrs.get("mode") in ("metro", "stcp"):
                    dist = haversine(lat, lon, float(attrs.get("lat")), float(attrs.get("lon")))
                    candidates.append((node_id, dist))
        candidates.sort(key=lambda x: x[1])
        if k is not None and k > 0:
            candidates = candidates[:k]
        return candidates

    def add_virtual_point(
        self,
        node_id: str,
        lat: float,
        lon: float,
        radius_m: float = 600.0,
        k: int = 8,
    ) -> str:
        base_id = str(node_id)
        candidate_id = base_id
        counter = 1
        while self.G.has_node(candidate_id):
            candidate_id = f"{base_id}_{counter}"
            counter += 1
        node_id = candidate_id

        neighbors = self.nearest_stops(lat, lon, radius_m=radius_m, k=k)
        if not neighbors:
            raise ValueError("Nenhuma paragem encontrada para ligar o ponto virtual.")

        self.G.add_node(
            node_id,
            lat=float(lat),
            lon=float(lon),
            mode="virtual",
            zone_id=None,
            stop_id=node_id,
            prefix="virtual",
        )
        self.virtual_nodes.add(node_id)

        for neighbor_id, dist in neighbors:
            n_attrs = self.G.nodes.get(neighbor_id, {})
            n_lat = float(n_attrs.get("lat"))
            n_lon = float(n_attrs.get("lon"))
            p1 = (float(lat), float(lon))
            p2 = (n_lat, n_lon)

            bridge_attr = None
            if crosses_douro(p1, p2):
                if not BRIDGE_RULES:
                    load_bridge_rules()
                bridge_id = nearest_bridge_for_walk_edge(p1, p2)
                allowed = bool(bridge_id and BRIDGE_RULES.get(bridge_id))
                if not allowed:
                    self.blocked_douro_walk_edges += 1
                    continue
                bridge_attr = bridge_id

            walk_time = dist / WALK_SPEED_M_S
            attrs = {
                "mode": "walk",
                "transit": False,
                "time_s": walk_time,
                "time": walk_time,
                "distance_m": dist,
                "route_id": None,
                "trip_id": None,
            }
            if bridge_attr is not None:
                attrs["bridge_id"] = bridge_attr
            self.G.add_edge(node_id, neighbor_id, **attrs)
            self.G.add_edge(neighbor_id, node_id, **attrs)

        return node_id

    def _compute_route_headways(self):
        self.route_headways = {}
        self.headway_by_route = {}
        for mode, system in self.networks.items():
            headways = self._headways_for_system(system, mode)
            for key, value in headways.items():
                self.route_headways[key] = value
                _, route_id = key
                if route_id not in self.headway_by_route:
                    self.headway_by_route[route_id] = value

    def _compute_headway_by_route(self, stop_times: pd.DataFrame, trips: pd.DataFrame) -> Dict[str, float]:
        if stop_times is None or stop_times.empty or trips is None or trips.empty:
            return {}
        merged = stop_times.merge(trips[["trip_id", "route_id"]], on="trip_id", how="left")
        merged = merged.dropna(subset=["route_id", "stop_sequence"])
        if merged.empty:
            return {}
        idx = merged.groupby("trip_id")["stop_sequence"].idxmin()
        first_stops = merged.loc[idx].copy()
        if "departure_time" not in first_stops.columns:
            return {}

        def _safe_seconds(value):
            try:
                return to_seconds(value)
            except Exception:
                return None

        first_stops["dep_s"] = first_stops["departure_time"].map(_safe_seconds)
        first_stops = first_stops.dropna(subset=["dep_s"])
        if first_stops.empty:
            return {}

        headway: Dict[str, float] = {}
        for route_id, group in first_stops.groupby("route_id"):
            if pd.isna(route_id):
                continue
            departures = group["dep_s"].astype(float).sort_values().values
            if departures.size >= 2:
                diffs = departures[1:] - departures[:-1]
                if diffs.size:
                    headway[str(route_id)] = float(diffs.mean())
        return headway

    def _headways_for_system(self, system: dict, mode: str) -> Dict[Tuple[str, str], float]:
        result: Dict[Tuple[str, str], float] = {}
        trips = system.get("trips")
        stop_times = system.get("stop_times")
        frequencies = system.get("frequencies")
        if trips is None or trips.empty:
            return result
        trip_routes = trips[["trip_id", "route_id"]].dropna(subset=["trip_id"])

        if frequencies is not None and not frequencies.empty:
            freq = frequencies.merge(trip_routes, on="trip_id", how="left")
            if "headway_secs" in freq.columns:
                freq["headway_secs"] = pd.to_numeric(freq["headway_secs"], errors="coerce")
                freq = freq.dropna(subset=["route_id", "headway_secs"])
                grouped = freq.groupby("route_id")["headway_secs"].mean()
                for route_id, headway in grouped.items():
                    if pd.notna(headway):
                        result[(mode, str(route_id))] = float(headway)

        if stop_times is not None and not stop_times.empty:
            fallback = self._compute_headway_by_route(stop_times, trips)
            for route_id, headway in fallback.items():
                key = (mode, str(route_id))
                if key not in result:
                    result[key] = headway
        return result

    def _safe_to_seconds(self, value) -> Optional[int]:
        try:
            return to_seconds(str(value))
        except Exception:
            return None

    def _prepare_fares(self):
        attrs = []
        rules = []
        for system in self.networks.values():
            prefix = system.get("prefix")
            fare_attrs = system.get("fare_attributes")
            fare_rules = system.get("fare_rules")
            if fare_attrs is not None and not fare_attrs.empty:
                df = fare_attrs.copy()
                df["prefix"] = prefix
                attrs.append(df)
            if fare_rules is not None and not fare_rules.empty:
                df = fare_rules.copy()
                if "contains_id" not in df.columns:
                    df["contains_id"] = None
                df["prefix"] = prefix
                rules.append(df)
        if attrs:
            self.fare_attributes = pd.concat(attrs, ignore_index=True)
        if rules:
            self.fare_rules = pd.concat(rules, ignore_index=True)

    # ---------------------- API pública ---------------------- #

    def shortest_path_between(self, start, end, weight="time_s"):
        return nx.shortest_path(self.G, start, end, weight=weight)

    def random_walk(self, start, end, max_steps=100):
        import random

        path = [start]
        current = start
        for _ in range(max_steps):
            if current == end:
                break
            neighbors = list(self.G.successors(current))
            if not neighbors:
                break
            current = random.choice(neighbors)
            path.append(current)
        if path[-1] != end:
            return None
        return path

    def search_stops_by_name(self, query: str, max_results: Optional[int] = None):
        """
        Procura paragens cujo nome corresponda (total ou parcialmente) a `query`.

        Retorna uma lista de dicionários com `node_id`, `name`, `mode` e `degree`,
        ordenada por correspondência exacta, prioridade de modo e grau (desc).
        """
        if not query:
            return []
        q = str(query).strip().lower()
        q_norm = _normalize_text(query)
        results: List[dict] = []
        for node_id, data in self.G.nodes(data=True):
            name = data.get("stop_name")
            if not name:
                continue
            lowered = str(name).lower()
            normalized = _normalize_text(name)
            if lowered == q or (q_norm and normalized == q_norm):
                match_type = 0
            elif (q and q in lowered) or (q_norm and q_norm in normalized):
                match_type = 1
            elif q_norm:
                ratio = difflib.SequenceMatcher(None, normalized, q_norm).ratio()
                if ratio < 0.6:
                    continue
                match_type = 2
            else:
                continue
            mode = data.get("mode")
            mode_priority = {"metro": 0, "stcp": 1}.get(mode, 2)
            degree = self.G.degree(node_id)
            results.append(
                {
                    "node_id": node_id,
                    "name": name,
                    "mode": mode,
                    "degree": degree,
                    "match_priority": match_type,
                    "mode_priority": mode_priority,
                }
            )

        results.sort(
            key=lambda item: (
                item["match_priority"],
                item["mode_priority"],
                -item["degree"],
                item["name"],
            )
        )
        if max_results is not None:
            return results[:max_results]
        return results

    def path_metrics(self, path: Iterable[str]):
        self._ensure_state_compatibility()
        from collections import defaultdict

        total_travel_time = 0.0
        waiting_time = 0.0
        total_emissions = 0.0
        walking_distance = 0.0
        waits_by_route = defaultdict(float)
        distance_km_by_mode = defaultdict(float)
        routes_used: set[Tuple[str, str]] = set()
        segments: List[dict] = []
        zones_passed: List[str] = []

        def _push_zone(zone_value):
            if zone_value and (not zones_passed or zones_passed[-1] != zone_value):
                zones_passed.append(zone_value)

        prev_transit_route: Optional[Tuple[str, str]] = None
        prev_block: Optional[Tuple[str, str, str]] = None
        transfers = 0
        last_was_transfer = False

        nodes = remove_cycles(list(path))
        if not nodes:
            return self._penalised_metrics()

        origin_zone = self.G.nodes[nodes[0]].get("zone_id") if nodes[0] in self.G else None
        dest_zone = self.G.nodes[nodes[-1]].get("zone_id") if nodes[-1] in self.G else None

        for node in nodes:
            if node not in self.G:
                return self._penalised_metrics()

        for u, v in zip(nodes[:-1], nodes[1:]):
            if not self.G.has_edge(u, v):
                return self._penalised_metrics()
            data = self.G[u][v]
            mode = data.get("mode", "unknown")
            transit = data.get("transit", False)
            distance_m = float(data.get("distance_m", 0.0))
            time_s = float(data.get("time_s", data.get("time", 0.0)))
            route_id = data.get("route_id")
            trip_id = data.get("trip_id")

            is_transit = mode in ("metro", "stcp")
            route_id_str = "" if route_id is None else str(route_id)
            block_key = (mode, route_id_str, str(trip_id)) if is_transit else None
            route_key = (mode, route_id_str)

            if is_transit and block_key != prev_block:
                headway = None
                if route_id_str:
                    headway = self.headway_by_route.get(route_id_str)
                    if headway is None:
                        headway = self.route_headways.get((mode, route_id_str))
                if headway:
                    wait_s = 0.5 * headway
                    route_wait_key = route_id_str or "unknown"
                    waits_by_route[route_wait_key] += wait_s
                    segments.append(
                        {
                            "from_stop": u,
                            "to_stop": u,
                            "mode": "wait",
                            "route_id": route_id,
                            "time_s": wait_s,
                            "distance_m": 0.0,
                            "transit": False,
                        }
                    )
                    waiting_time += wait_s
                if not last_was_transfer and prev_transit_route is not None and route_key != prev_transit_route:
                    transfers += 1
                prev_block = block_key
                last_was_transfer = False

            total_travel_time += time_s
            segment = {
                "from_stop": u,
                "to_stop": v,
                "mode": mode,
                "route_id": route_id,
                "time_s": time_s,
                "distance_m": distance_m,
                "transit": transit,
            }
            segments.append(segment)

            if transit:
                routes_used.add(route_key)
                emission_factor = EMISSION_METRO_G_PER_KM if mode == "metro" else EMISSION_STCP_G_PER_KM
                total_emissions += (distance_m / 1000.0) * emission_factor
                distance_km_by_mode[mode] += distance_m / 1000.0
                prev_transit_route = route_key

                zone_u = self.G.nodes[u].get("zone_id")
                zone_v = self.G.nodes[v].get("zone_id")
                _push_zone(zone_u)
                _push_zone(zone_v)
            else:
                if mode == "walk":
                    walking_distance += distance_m
                    distance_km_by_mode[mode] += distance_m / 1000.0
                elif mode == "transfer":
                    transfers += 1
                    last_was_transfer = True
                else:
                    distance_km_by_mode[mode] += distance_m / 1000.0
                prev_block = None

        # Determinar se houve ou não qualquer segmento de trânsito no caminho.
        has_transit = any(isinstance(seg, dict) and seg.get("transit") for seg in segments)

        if not has_transit:
            # Percurso 100% walk/transfer → não há tarifa de transporte aplicada.
            fare_cost = 0.0
            fare_selected = None
            zones_passed = []
        else:
            fare_cost, fare_selected = self._estimate_fare(
                zones_passed,
                origin_zone,
                dest_zone,
                routes_used,
            )
        metrics = {
            "time_total_s": total_travel_time + waiting_time,
            "travel_time_s": total_travel_time,
            "waiting_time_s": waiting_time,
            "wait_s_total": waiting_time,
            "emissions_g": total_emissions,
            "walk_m": walking_distance,
            "fare_cost": fare_cost,
            "fare_selected": fare_selected,
            "n_transfers": transfers,
            "zones_passed": zones_passed,
            "segments": segments,
            "waits": dict(waits_by_route),
            "distance_km_by_mode": dict(distance_km_by_mode),
            "path_simplified": nodes,
        }
        return metrics

    def _penalised_metrics(self):
        return {
            "time_total_s": PENALTY,
            "travel_time_s": PENALTY,
            "waiting_time_s": PENALTY,
            "wait_s_total": PENALTY,
            "emissions_g": PENALTY,
            "walk_m": PENALTY,
            "fare_cost": PENALTY,
            "fare_selected": None,
            "n_transfers": PENALTY,
            "zones_passed": [],
            "segments": [],
            "waits": {},
            "distance_km_by_mode": {},
        }

    def _estimate_fare(
        self,
        zones_passed: List[str],
        origin_zone: Optional[str],
        dest_zone: Optional[str],
        routes_used: Iterable[Tuple[str, str]],
    ) -> Tuple[float, Optional[dict]]:
        self._ensure_state_compatibility()
        if self.fare_attributes.empty:
            return 0.0, None
        candidate_ids = set()
        zones_set = {str(z) for z in zones_passed if z is not None}
        routes_plain = {route_id for _, route_id in routes_used if route_id}

        if not self.fare_rules.empty:
            for _, rule in self.fare_rules.iterrows():
                fare_id = rule.get("fare_id")
                if pd.isna(fare_id):
                    continue
                route_id = rule.get("route_id")
                origin_id = rule.get("origin_id")
                destination_id = rule.get("destination_id")
                contains_id = rule.get("contains_id")

                if pd.notna(route_id) and routes_plain and str(route_id) not in routes_plain:
                    continue
                if pd.notna(origin_id) and origin_zone and str(origin_zone) != str(origin_id):
                    continue
                if pd.notna(destination_id) and dest_zone and str(dest_zone) != str(destination_id):
                    continue
                if pd.notna(contains_id) and str(contains_id) not in zones_set:
                    continue
                candidate_ids.add(str(fare_id))

        if not candidate_ids:
            candidate_ids = set(self.fare_attributes.get("fare_id", []))

        fares = self.fare_attributes[self.fare_attributes["fare_id"].isin(candidate_ids)]
        if fares.empty:
            zone_count = max(1, len(zones_set) if zones_set else 1)
            best_price: Optional[float] = None
            for _, row in self.fare_attributes.iterrows():
                fare_id = str(row.get("fare_id"))
                match = re.search(r"(\d+)", fare_id)
                if not match:
                    continue
                try:
                    covered_zones = int(match.group(1))
                except ValueError:
                    continue
                if covered_zones >= zone_count:
                    price = row.get("price")
                    if pd.notna(price):
                        best_price = price if best_price is None else min(best_price, price)
            if best_price is None:
                return 0.0, None
            return float(best_price), {
                "fare_id": None,
                "price": float(best_price),
                "currency": "EUR",
                "source": "fallback",
            }

        fares = fares.dropna(subset=["price"])
        if fares.empty:
            return 0.0, None
        idx = fares["price"].astype(float).idxmin()
        row = fares.loc[idx]
        price = float(row.get("price", 0.0))
        currency = row.get("currency_type")
        currency = str(currency) if pd.notna(currency) else "EUR"
        fare_info = {
            "fare_id": str(row.get("fare_id")) if pd.notna(row.get("fare_id")) else None,
            "price": price,
            "currency": currency,
            "source": "gtfs",
        }
        return price, fare_info
