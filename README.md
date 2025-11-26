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
- `transfers.txt`
- `frequencies.txt` (se existir)
- `fare_attributes.txt` + `fare_rules.txt` (para **custos**)

> Garante que os ficheiros GTFS estão em `data/Metro` e `data/STCP` ou fornece os caminhos via flags `--metro` e `--stcp`.

## 🧠 Abordagem

- **Grafo multimodal** (NetworkX):
  - Nós = paragens (com `zone_id` e `mode`).
  - Arestas de transporte com **tempo real** (a partir de `stop_times`) e distância Haversine.
  - Arestas de **caminhada** entre paragens a ≤ raio (ex.: 400 m, configurável).
  - Arestas de **transferência** a partir de `transfers.txt` (com tempos mínimos de troca, quando existirem).
  - **Espera inicial** por rota (0.5 × headway), estimada de `frequencies` ou de `stop_times`.
- **Métricas por caminho**:
  - `time_total_s`, `emissions_g` (Metro ≈ 40 g CO₂/km; STCP ≈ 109.9 g CO₂/km),
  - `walk_m`,
  - `fare_cost` (aplicando regras GTFS: origem, destino e zonas atravessadas),
  - `n_transfers` (mudanças de rota + arestas de transferência GTFS).
- **Optimização**:
  - **NSGA-II** (DEAP) com três ou quatro objetivos.
  - **Seeds** por Dijkstra com somas ponderadas (baseline) para iniciar a população.

## 🛠️ Requisitos e instalação

- Python 3.10+
- Instalar dependências com:

```bash
pip install -r requirements.txt
```

## ▶️ Como correr um caso simples (`main.py`)

Exemplo mínimo com IDs de paragens (usando GTFS em `data/Metro` e `data/STCP`), a partir da pasta `CIN`:

```bash
python src/main.py ^
  --metro data/Metro ^
  --stcp data/STCP ^
  --origin 5697 ^
  --dest CRG2 ^
  --walk-radius 400 ^
  --pop-size 30 ^
  --gens 40 ^
  --wmax-s 900 ^
  --tmax 2 ^
  --walk-policy minimize
```

- **`--wmax-s`**: limite máximo de tempo total a pé (segundos), por exemplo `900` ≈ 15 minutos.
- **`--tmax`**: número máximo de transbordos permitidos (0 → apenas aceita caminhos sem transbordos; 2 → até dois, etc.).
- **`--walk-policy`**:
  - `maximize` (omissão): o objetivo de caminhada é maximizado (equivalente a minimizar `walk_m` porque entra com sinal negativo no fitness).
  - `minimize`: força o algoritmo a preferir soluções com menos caminhada.

Saídas principais do `main.py`:
- `outputs/cache/graph_cache.pkl` — cache do grafo multimodal.
- `outputs/pareto/pareto_solutions.json` — soluções Pareto (não-dominadas) para o par origem–destino especificado.

## ▶️ Experiências automáticas (`experiments.py`)

Para gerar múltiplos cenários (curtos, médios, longos), correr o baseline Dijkstra-λ e o NSGA-II para cada cenário:

```bash
python src/experiments.py ^
  --metro data/Metro ^
  --stcp data/STCP ^
  --walk-radius 400 ^
  --scenarios 10 ^
  --scenario-types short,mid,long ^
  --pop-size 40 ^
  --gens 25 ^
  --wmax-s 900 ^
  --tmax 2 ^
  --walk-policy minimize
```

Por omissão, os resultados são escritos em `outputs/experiments/` com a seguinte estrutura:
- `outputs/experiments/scenarios.json` — lista de cenários gerados (origem, destino, tipo, etc.).
- `outputs/experiments/baseline_summary.json` — resumo dos resultados do baseline Dijkstra-λ.
- `outputs/experiments/<scenario_id>/baseline_pareto.json` — fronteira de Pareto do baseline para esse cenário.
- `outputs/experiments/<scenario_id>/pareto_solutions.json` — soluções Pareto encontradas pelo NSGA-II.


