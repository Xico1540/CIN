# TODO — Planner Multi-Modal (Porto)

> Roadmap detalhado para evoluir o projeto: tempos reais do GTFS, tarifas, transbordos, espera/headway, JSON enriquecido e baselines.

---

## 1) `loader.py`
**Objetivo:** garantir que todo o GTFS (incluindo tarifas) fica disponível.

- [x] **Validar tarifas (fare\_attributes/rules)**
  - [x] Ler `fare_attributes.txt` com colunas: `fare_id, price, currency_type, transfers, transfer_duration`.
  - [x] Ler `fare_rules.txt` com colunas: `fare_id, route_id, origin_id, destination_id, contains_id`.
  - [x] Converter `price` para `float`.
- [x] **Helper de tempo (HH:MM:SS → segundos)**
  - [x] Função `to_seconds(hms: str) -> int` com suporte a horas ≥ 24 (overnight).
- [x] **(Opcional, útil)** Ler `frequencies.txt` (se existir) para headways por linha/período.

---

## 2) `graph_builder.py`
**Objetivo:** grafo rico com tempos reais, zonas, espera/headway, custo e transbordos.

### 2.1 Nós (stops)
- [x] Concatenar paragens preservando o operador:
  - [x] `metro['stops'].assign(mode='metro')`, `stcp['stops'].assign(mode='stcp')`.
- [x] Em `add_node(...)` guardar também `zone_id` (se existir).

### 2.2 Arestas de transporte (metro/STCP)
- [x] Merge `stop_times` ↔ `trips` (para `route_id`), ordenar por `trip_id, stop_sequence`.
- [x] Para pares consecutivos do mesmo `trip_id`:
  - [x] **Tempo real**: `time_s = to_seconds(arrival_curr) - to_seconds(departure_prev)` (corrigir overnight).
  - [x] **Fallback**: se não houver horários válidos, usar velocidade média:
        metro 40 km/h; STCP 30 km/h (mín. 1 s).
  - [x] **Guardar atributos**: `mode, transit=True, distance_m (haversine), time_s, route_id, trip_id`.

### 2.3 Arestas de caminhada
- [x] Para pares de paragens a ≤ `walk_radius`:
  - [x] `mode='walk'`, `transit=False`, `time_s=d/WALK_SPEED_M_S`, `distance_m=d`.
  - [x] Criar arestas bidirecionais.

### 2.4 Espera inicial (headway)
- [x] **Estimar headway** por `route_id`:
  - [x] Se existir `frequencies.txt`: usar `headway_secs`.
  - [x] Senão: média de intervalos entre partidas em `stop_times` na primeira paragem da rota.
- [x] **Aplicar na métrica**: ao iniciar sequência contínua numa rota/mode, somar `0.5*headway` ao tempo.

### 2.5 Tarifas (custo do bilhete)
- [x] Implementar `_estimate_fare(zones_passed, origin_zone, dest_zone, routes_used) -> float`:
  - [x] Construir conjunto de zonas atravessadas (inclui origem/destino).
  - [x] Selecionar `fare_id` candidatos de `fare_rules` compatíveis com `route_id`, `origin_id`, `destination_id` e `contains_id` contidos nas zonas.
  - [x] Incluir tarifas **sem regras** (todas de `fare_attributes`).
  - [x] Escolher o **menor preço** de `fare_attributes` entre os candidatos.
  - [x] **Fallback**: mapear nº de zonas → tarifas tipo “Z2”, “Z3”… e escolher a mais barata que cubra `len(zones_passed)`.

### 2.6 Métricas e segmentos
- [x] Reescrever `path_metrics(path)` para devolver:
  - [x] `time_total_s` (inclui espera/headway e caminhada),
  - [x] `emissions_g` (STCP 109.9 g/km; Metro 40 g/km),
  - [x] `walk_m`,
  - [x] `fare_cost`,
  - [x] `n_transfers` (contar mudança de `(mode, route_id)`; ignorar troços “walk” se preferires).
  - [x] `zones_passed` (lista ordenada ou set).
  - [x] `segments` (lista com `from_stop, to_stop, mode, route_id, time_s, distance_m`).

---

## 3) `fitness.py`
**Objetivo:** alinhar objetivos com o que queres optimizar.

- [x] **Escolha de política para caminhada**:
  - [x] **Maximizar exercício** → devolver `-walk_m`.
  - [x] **Minimizar caminhada** → devolver `walk_m`.
- [x] **Evitar duplicação**: idealmente, pedir tudo a `graph_builder.path_metrics` e extrair (tempo, emissões, ±caminhada).

---

## 4) `evolution.py` (NSGA-II)
**Objetivo:** restrições (W\_max, T\_max), objetivos extra e seeds inteligentes.

### 4.1 Restrições duras (recomendado)
- [x] Em `evaluate_individual`: obter `time_s, emissions_g, walk_m, fare_cost, n_transfers = graph.path_metrics(...)`.
- [x] Se `walk_time_total > W_max` **ou** `n_transfers > T_max` → devolver `(PENALTY, PENALTY, PENALTY)`.

### 4.2 Objetivos extra (opcional)
- [x] Para optimizar **custo** também:
  - [x] Mudar `creator` para 4 objetivos: `weights=(-1,-1,-1,-1)`.
  - [x] Devolver `(time, emissions, ±walk, fare_cost)`.

### 4.3 Inicialização informada
- [x] Criar `seed_paths` via Dijkstra com custo `λ·tempo_norm + (1-λ)·emissões_norm` para `λ` em `{0.0, 0.05, …, 1.0}`.
- [x] Preencher parte da população com estes seeds + indivíduos aleatórios.
- [x] Mutação “subcaminho com reparação” (já tens) e cruzamento por nó comum (já tens).

---

## 5) `main.py`
**Objetivo:** CLI completa e JSON enriquecido.

- [ ] Novos argumentos:
  - [ ] `--wtime-max-s` (limite total de tempo a pé),
  - [ ] `--tmax` (máx. transbordos),
  - [ ] `--cost-as-constraint` (p.ex. teto €),
  - [ ] `--include-cost` (se for objetivo).
- [ ] Guardar `pareto_solutions.json` com:
  - [ ] `path`, `time_s`, `emissions_g`, `walk_m`, `fare_cost`, `n_transfers`, `has_walk`, `zones_passed`, `segments`.

---

## 6) Testes mínimos
- [ ] **Unit**:
  - [ ] `to_seconds("25:10:00") == 25*3600+10*60`.
  - [ ] `_estimate_fare` (caso 2–3 zonas).
- [ ] **Smoke test**:
  - [ ] Executar um O-D curto e confirmar flags/contagens e custo > 0 quando há transporte.

---

## 7) Extras (se houver tempo)
- [ ] **Unir paragens co-localizadas** (nó virtual de estação).
- [ ] **Baseline Dijkstra-λ** e guardar `baseline_pareto.json`.
- [ ] **Export GeoJSON** dos melhores caminhos.
