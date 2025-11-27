
# Outputs — Ficheiros gerados e formatos

Por omissão, os resultados são guardados em `outputs/`.

---

## `src/main.py`
### `outputs/pareto/pareto_solutions.json`
Lista de soluções não-dominadas (Pareto). Cada entrada inclui:
- `path`: sequência de nós (normalmente `path_simplified`)
- `metrics`:
  - `time_total_s`, `travel_time_s`, `waiting_time_s`
  - `emissions_g`
  - `walk_m`
  - `n_transfers`
  - `fare_cost` (se aplicável)
- `segments`: lista de segmentos legíveis (walk/metro/stcp/wait…), com tempo e distância
- (opcional) indicadores de debug (ex.: pontes usadas)

---

## `src/experiments.py`
### `outputs/experiments/scenarios.json`
Lista de cenários gerados (origem/destino) por random walk e metadados do cenário.

### `outputs/experiments/<scenario_id>/baseline_pareto.json`
Pareto do baseline Dijkstra-λ (com `segments`, `zones_passed`, `used_bridge_ids`, etc.)

### `outputs/experiments/<scenario_id>/final_population.json`
População final do NSGA-II (indivíduos válidos e deduplicados, formato completo).

### `outputs/experiments/<scenario_id>/pareto_solutions.json`
Fronteira Pareto do NSGA-II (sem dominados, formato igual ao baseline Dijkstra-λ).

### `outputs/experiments/<scenario_id>/pareto_front.json`
Pontos 2D (`time_total_s`, `emissions_g`) usados para hipervolume.

### `outputs/experiments/hypervolume_summary.json`
Resumo por cenário:
- Hypervolume baseline Dijkstra-λ
- Hypervolume NSGA-II
- ponto de referência (`ref`) usado
- contagens (nº de pontos após filtro Pareto 2D)

> Nota: o Hypervolume é calculado sobre a fronteira 2D (tempo total, emissões).
