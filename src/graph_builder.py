import difflib
import math
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

WALK_RADIUS_METERS = 400
METRO_CRUISE_SPEED_KMH = 40.0
STCP_CRUISE_SPEED_KMH = 30.0


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

    def _add_walking_edges(self):
        stops_list = self.stops[["node_id", "stop_lat", "stop_lon"]].values.tolist()
        for i in range(len(stops_list)):
            id1, lat1, lon1 = stops_list[i]
            for j in range(i + 1, len(stops_list)):
                id2, lat2, lon2 = stops_list[j]
                d = haversine(float(lat1), float(lon1), float(lat2), float(lon2))
                if d <= self.walk_radius:
                    walk_time = d / WALK_SPEED_M_S
                    attrs_forward = {
                        "mode": "walk",
                        "transit": False,
                        "time_s": walk_time,
                        "time": walk_time,
                        "distance_m": d,
                    }
                    attrs_backward = attrs_forward.copy()
                    if not self.G.has_edge(id1, id2) or not self.G[id1][id2].get("transit", False):
                        self.G.add_edge(id1, id2, **attrs_forward)
                    if not self.G.has_edge(id2, id1) or not self.G[id2][id1].get("transit", False):
                        self.G.add_edge(id2, id1, **attrs_backward)

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

        nodes = list(path)
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
                if prev_transit_route is not None and route_key != prev_transit_route:
                    transfers += 1
                prev_block = block_key

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
                walking_distance += distance_m
                distance_km_by_mode[mode] += distance_m / 1000.0
                prev_block = None

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
