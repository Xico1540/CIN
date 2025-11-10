# Computação Inspirada na Natureza — Planeador Multi-Modal (Grande Porto)

Projeto académico que combina **GTFS** (STCP + Metro do Porto) com **meta-heurísticas** para encontrar rotas **multi-objetivo** entre dois pontos no Grande Porto.

## ✨ Objetivo
Dado um par **Origem–Destino**, encontrar um conjunto **Pareto-ótimo** de percursos que equilibrem:
- **Tempo total** de viagem;
- **Emissões de CO₂** (estimadas por modo e distância);
- **Exercício/Caminhada** (pode ser maximizado ou minimizado, consoante a política);
- **Custo do bilhete** (via `fare_attributes.txt` + `fare_rules.txt`);
- Restrições como **nº de transbordos** e **tempo máximo a pé**.

## 🗂 Dados
Usa-se o formato **GTFS (static)** de:
- **STCP** (`data/STCP/…`)
- **Metro do Porto** (`data/Metro/…`)

Ficheiros principais:
- `stops.txt` (inclui `stop_id, stop_lat, stop_lon, zone_id`)
- `trips.txt`, `stop_times.txt`, `routes.txt`
- `transfers.txt` (opcional)
- `frequencies.txt` (se existir)
- `fare_attributes.txt` + `fare_rules.txt` (para **custos**)

> Dica: garante que os ficheiros estão em `data/Metro` e `data/STCP` ou passa os caminhos via CLI.

## 🧠 Abordagem
- **Grafo multimodal** (NetworkX):
  - Nós = paragens (com `zone_id` e `mode`).
  - Arestas de transporte com **tempo real** (a partir de `stop_times`) e distância Haversine.
  - Arestas de **caminhada** entre paragens a ≤ raio (ex.: 400 m).
  - **Espera inicial** por rota (0.5 × headway), estimada de `frequencies` ou de `stop_times`.
- **Métricas por caminho**:
  - `time_total_s`, `emissions_g` (Metro ≈ 40 g CO₂/km; STCP ≈ 109.9 g CO₂/km),
  - `walk_m`,
  - `fare_cost` (aplicando regras GTFS: origem, destino e zonas atravessadas),
  - `n_transfers` (mudanças de `(mode, route_id)`).
- **Optimização**:
  - **NSGA-II** (DEAP) com três ou quatro objetivos.
  - **Seeds** por Dijkstra com somas ponderadas (baseline) para iniciar a população.

## 🛠️ Requisitos
- Python 3.10+
- `pip install deap networkx pandas numpy`

*(Sugestão de `requirements.txt`: `deap\nnetworkx\npandas\nnumpy\n`)*

## ▶️ Como correr
```bash
# Exemplo básico
python src/main.py 
  --metro data/Metro 
  --stcp data/STCP 
  --origin 5697 
  --dest CRG2 
  --walk-radius 400 
  --pop-size 30 
  --gens 40
