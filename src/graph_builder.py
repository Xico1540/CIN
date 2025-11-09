import math
import networkx as nx
import pandas as pd

WALK_RADIUS_METERS = 400
WALK_SPEED_M_S = 1.4  # ~5 km/h average walking

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

class MultimodalGraph:
    def __init__(self, data, walk_radius_m=WALK_RADIUS_METERS):
        self.walk_radius = walk_radius_m
        self.metro = data['metro']
        self.stcp = data['stcp']

        # Concat all stops
        self.stops = pd.concat([self.metro['stops'], self.stcp['stops']], ignore_index=True)

        self.G = nx.DiGraph()
        self.build_graph()

    def build_graph(self):
        # Add nodes
        for _, row in self.stops.iterrows():
            self.G.add_node(row['stop_id'], lat=row['stop_lat'], lon=row['stop_lon'],
                            mode=row.get('mode', 'unknown'))

        # Add transit edges with placeholder time/distance if missing
        self._add_transit_edges(self.metro['stop_times'], self.metro['trips'], mode='metro')
        self._add_transit_edges(self.stcp['stop_times'], self.stcp['trips'], mode='stcp')

        # Walking edges
        self._add_walking_edges()

    def _add_transit_edges(self, stop_times, trips, mode):
        merged = stop_times.merge(trips, on='trip_id')
        merged = merged.sort_values(by=['trip_id', 'stop_sequence'])
        prev = None
        for _, r in merged.iterrows():
            if prev is not None and prev['trip_id'] == r['trip_id']:
                # calcular distância aproximada
                lat1, lon1 = self.G.nodes[prev['stop_id']]['lat'], self.G.nodes[prev['stop_id']]['lon']
                lat2, lon2 = self.G.nodes[r['stop_id']]['lat'], self.G.nodes[r['stop_id']]['lon']
                dist = haversine(lat1, lon1, lat2, lon2)
                time = max(dist / 10, 1)  # placeholder: assume 10 m/s = 36 km/h ou 1s mínimo
                self.G.add_edge(prev['stop_id'], r['stop_id'], mode=mode, transit=True, distance_m=dist, time=time)
            prev = r

    def _add_walking_edges(self):
        stops_list = self.stops[['stop_id', 'stop_lat', 'stop_lon']].values.tolist()
        for i in range(len(stops_list)):
            id1, lat1, lon1 = stops_list[i]
            for j in range(i+1, len(stops_list)):
                id2, lat2, lon2 = stops_list[j]
                d = haversine(lat1, lon1, lat2, lon2)
                if d <= self.walk_radius:
                    walk_time = d / WALK_SPEED_M_S
                    self.G.add_edge(id1, id2, mode='walk', time=walk_time, distance_m=d, transit=False)
                    self.G.add_edge(id2, id1, mode='walk', time=walk_time, distance_m=d, transit=False)

    def shortest_path_between(self, start, end, weight='time'):
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

    def path_metrics(self, path):
        total_time = 0.0
        total_emissions = 0.0
        walking_distance = 0.0
        for u, v in zip(path[:-1], path[1:]):
            if not self.G.has_edge(u, v):
                # Caminho inválido: devolve penalidade alta
                return 1e9, 1e9, 1e9
            data = self.G[u][v]
            mode = data.get("mode", "unknown")
            dist = data.get("distance_m", 0)
            time = data.get("time", 1)
            total_time += time
            if mode == "walk":
                walking_distance += dist
            elif mode == "stcp":
                total_emissions += (dist / 1000.0) * 20
            elif mode == "metro":
                total_emissions += (dist / 1000.0) * 1
        return total_time, total_emissions, walking_distance
