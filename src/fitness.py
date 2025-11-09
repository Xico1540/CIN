# fitness.py
# Fitness evaluation functions for multimodal routing

import math

# Emission factors (grams CO2 per passenger-km)
EMISSION_METRO = 1      # quase zero em operação
EMISSION_STCP = 20      # baseado na STCP (~820 g por veículo-km / ~40 passageiros)

# Walking energy/benefit factor (maximizamos a caminhada, mas o GA minimiza -> sinal negativo)
WALKING_VALUE = 1

# Avalia métricas de um caminho (lista de node IDs) no grafo
# Retorna: (tempo_segundos, emissões_gramas, -distância_caminhada)
def evaluate_route(graph, path):
    total_time = 0.0
    total_emissions = 0.0
    walking_distance = 0.0

    for u, v in zip(path[:-1], path[1:]):
        if not graph.has_edge(u, v):
            continue
        data = graph[u][v]
        mode = data.get("mode", "unknown")
        dist = data.get("distance_m", 0)
        time = data.get("time_s", 0)

        total_time += time

        if mode == "walk":
            walking_distance += dist
        elif mode == "stcp":
            total_emissions += (dist / 1000.0) * EMISSION_STCP
        elif mode == "metro":
            total_emissions += (dist / 1000.0) * EMISSION_METRO

    # Transform walking distance para fitness (negativo porque DEAP minimiza)
    return (total_time, total_emissions, -walking_distance)
