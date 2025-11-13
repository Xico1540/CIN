# TODO — Últimos 6 pontos para fechar o projeto

> Objetivo: implementar as últimas funcionalidades pedidas no enunciado e polir o projeto.  
> Escopo: 6 blocos de trabalho, cada um com subtarefas, ficheiros a alterar, critérios de aceitação e testes rápidos.

---

## 1) Origem/Destino a partir de QUALQUER posição (nós virtuais + “snap”)

**Porque:** o enunciado pede que o utilizador possa começar/terminar “em qualquer posição”, ligando a pé à rede.

### Subtarefas
- [x] **`graph_builder.py`** — criar utilitários:
  - [x] `nearest_stops(lat, lon, radius_m=600, k=8)`: devolve os `stop_id` das paragens mais próximas (Haversine) dentro do raio.
  - [x] `add_virtual_point(node_id, lat, lon, radius_m=600, k=8)`: adiciona nó `mode="virtual"`, liga com arestas `walk` (bidirecionais) às `k` paragens mais próximas com:
    - `time_s = distancia_m / WALK_SPEED_M_S`
    - `distance_m = distancia_m`
    - `transit = False`, `route_id = None`, `trip_id = None`
- [x] **`graph_builder.path_metrics`**:
  - [x] Garantir que **nós virtuais** não entram em `zones_passed` (continuar a contar zonas só quando `transit=True`).
- [x] **`main.py`** — parsing de origem/destino:
  - [x] Aceitar `--origin` e `--dest` tanto como **stop_id** como `"lat,lon"`.
  - [x] Helper `_parse_point("lat,lon") -> (lat,lon) | None`.
  - [x] Se vier `(lat,lon)`: criar `ORIGIN_VIRT`/`DEST_VIRT` via `add_virtual_point(...)` e usar esses IDs na execução.

### Critérios de aceitação
- Introduzindo `--origin "41.15,-8.61"` e `--dest "41.18,-8.60"`, o algoritmo gera trajetos com **segmentos `walk` iniciais/finais**.
- `zones_passed` e `fare_cost` **não** são afetados pelos troços `walk` virtuais.

### Testes rápidos
- [x] Caso com `--origin`/`--dest` em coordenadas → JSON tem pelo menos 1 segmento `"walk"` no início e/ou fim.
- [x] `time_s == sum(segments.time_s)` mantém-se.

---

## 2) Expor RESTRIÇÕES/OBJETIVOS na CLI e ligá-los ao evolutivo

**Porque:** o utilizador deve poder impor limites e decidir a política de caminhada; custo pode ser 4.º objetivo.

### Subtarefas
- [x] **`main.py`** — novas flags:
  - [x] `--wmax-s FLOAT` (limite total de tempo a pé em segundos; `None` desliga).
  - [x] `--tmax INT` (máx. transbordos; `None` desliga).
  - [x] `--walk-policy {maximize,minimize}` (definir sinal de `walk_m`).
  - [x] `--include-cost` (se presente, devolve 4 objetivos no evolutivo).
- [x] **Propagação**:
  - [x] Passar estas flags para `run_nsga2(...)`.
- [x] **`evolution.py`**:
  - [x] Garantir que `evaluate_individual(...)` já lê `segments` e:
    - [x] **conta apenas `mode=="walk"`** para `w_max`.
    - [x] **conta `n_transfers`** que veio de `path_metrics` (ou recalcula igual).
    - [x] Aplica penalização (retornar `PENALTY` nos objetivos) se exceder limites.
  - [x] Se `--include-cost`, criar/usar creator com 4 objetivos (`weights=(-1,-1,-1,-1)`).

### Critérios de aceitação
- Com `--wmax-s 120` rotas com >2 min a pé **são penalizadas** e deixam a frente de Pareto.
- Com `--tmax 2` rotas com ≥3 transbordos **são excluídas** (ou empurradas para fora da frente).
- Com `--walk-policy minimize` o conjunto Pareto tem menos caminhada.

### Testes rápidos
- [x] Executar com/sem as flags e verificar diferenças no `pareto_solutions.json`.
- [x] Confirmar que o 3.º objetivo muda de sinal ao trocar `walk-policy`.

---

## 3) Gerar CENÁRIOS (random-walk/curto–médio–longo) & BASELINE Dijkstra-λ

**Porque:** o enunciado sugere criar cenários e comparar com seeds/heurísticas (tipo MOEA/D).

### Subtarefas
- [x] **Gerador de O-D**:
  - [x] Função `generate_scenarios(G, n=10, types=("short","mid","long"))`:
    - [x] Para cada tipo, selecionar pares O-D por **`random_walk`** com comprimentos alvo (ex.: 1–3 arestas curto, 6–10 médio, 12+ longo).
    - [x] Garantir acessibilidade (existência de caminho).
- [x] **Baseline Dijkstra-λ**:
  - [x] Para cada λ ∈ {0.0, 0.05, …, 1.0}, peso `w = λ·tempo_norm + (1-λ)·emissões_norm`.
  - [x] Guardar soluções do baseline em `baseline_pareto.json` (por cenário).
- [x] **Runner**:
  - [x] Em `main.py` (flag `--scenarios N`) **ou** criar `experiments.py`:
    - [x] Para cada cenário: correr NSGA-II e baseline; guardar `pareto_solutions.json` e `baseline_pareto.json`.

### Critérios de aceitação
- Existem ficheiros `baseline_pareto.json` por cenário com 21 soluções (uma por λ).
- Comparando NSGA-II vs baseline, vê-se diversidade superior do NSGA-II (mais pontos não dominados).

### Testes rápidos
- [x] 3 cenários (curto, médio, longo) → todos geram JSONs sem erro.
- [ ] Contar quantos pontos do baseline são dominados pelo NSGA-II (espera-se >50% dominados).

---

## 4) JSON mais AUDITÁVEL (agregados de espera & custo)

**Porque:** facilita análise e apresentação.

### Subtarefas
- [x] **`main.py`** — ao construir a solução:
  - [x] Calcular `wait_s_total = sum(seg.time_s where seg.mode=="wait")`.
  - [x] `waits`: dicionário por `route_id` com a soma de espera (converter em lista de objetos para JSON).
  - [x] (Opcional) `distance_km_by_mode`: somas por `mode` (metro, stcp, walk).
- [x] **`graph_builder._estimate_fare`**:
  - [x] Se tiveres `fare_id`/`currency_type`, devolver também:
    - [x] `fare_selected = {"fare_id":..., "price":..., "currency":"EUR","source":"gtfs|fallback"}`.
- [x] **Guardar no JSON**:
  - [x] Acrescentar `wait_s_total`, `waits`, (opcional) `distance_km_by_mode` e `fare_selected`.

### Critérios de aceitação
- `time_s == sum(segments.time_s)` continua a verificar.
- `wait_s_total == sum(seg.time_s where seg.mode=="wait")`.

### Testes rápidos
- [x] Verificar que para a amostra anterior, `wait_s_total` bate com a soma manual.
- [x] Confirmar que `fare_selected` existe quando uma tarifa GTFS é aplicada.

---

## 5) Origem/Destino por **NOME** (qualidade de vida)

**Porque:** ajuda a testar/usar sem decorar IDs.

### Subtarefas
- [x] **`main.py`** — novas flags:
  - [x] `--origin-name "Hospital São João"` / `--dest-name "Campanhã"`.
- [x] **Resolver pelos `stops.txt`**:
  - [x] Carregar `stop_name` para um índice simples (case-insensitive, busca por substring).
  - [x] Se houver **uma** correspondência → usar o `stop_id`.
  - [x] Se houver várias:
    - [x] Escolher a de maior importância (heurística: mais ligações/centralidade) **ou**
    - [x] Listar matches no log e escolher a primeira (documentar).
- [x] **Prioridade**: se `--origin` (stop_id/latlon) foi passado, ignora `--origin-name` (mesmo para destino).

### Critérios de aceitação
- `--origin-name` sozinho já encontra a paragem e gera rotas.
- Em caso de múltiplas, comportamento é documentado (log + fallback determinístico).

### Testes rápidos
- [x] `--origin-name "São João" --dest-name "Campanhã"` → rota válida.
- [x] Caso sem matches → erro claro: “Nenhuma paragem encontrada para ...”.

---

## 6) Limpeza & Constantes centralizadas

**Porque:** polir o código, evitar duplicação, facilitar manutenção.

### Subtarefas
- [x] **Remover variáveis não usadas** em `graph_builder.path_metrics` (ex.: restos como `last_edge_was_transit`, etc.).
- [x] **Constantes de emissões**:
  - [x] Criar `constants.py` (ou centralizar em `fitness.py`) com:
    - `EMISSION_METRO_G_PER_KM = 40.0`
    - `EMISSION_STCP_G_PER_KM = 109.9`
    - `WALK_SPEED_M_S = 1.4`
  - [x] Importar em `graph_builder.py` e `fitness.py`; remover duplicados locais.
- [x] **Consistência de campos**:
  - [x] Arestas usam **sempre** `time_s` (se manténs `time = time_s` por compatibilidade, ok; mas lê sempre `time_s`).
- [ ] (Opcional) Básico de lint:
  - [ ] `ruff`/`flake8` e um `pre-commit` com formatação (`black`) — opcional mas ajuda.

### Critérios de aceitação
- Procura por `EMISSION_` → só num sítio.
- Sem warnings de variáveis não usadas nas funções principais.

### Testes rápidos
- [x] Corre o projeto — o output não muda (refactor puro).
- [x] Grep por `time =` nas arestas para confirmar que `time_s` é fonte de verdade.

---

## Mini-roteiro de integração (ordem sugerida)

1. **(1) Nós virtuais** → permite O-D por coordenadas (criticamente necessário para cumprir o enunciado).  
2. **(2) Flags de restrições/objetivos** → dar controlo ao utilizador.  
3. **(4) JSON auditável** → melhora análise e apresentação.  
4. **(3) Cenários & baseline** → evidências experimentais (secção de resultados).  
5. **(5) Nomes de paragens** → qualidade de vida.  
6. **(6) Limpeza & constantes** → higiene final.

---

## Dicas finais de validação

- **Reprodutibilidade**: `time_s == sum(segments.time_s)` **sempre**.  
- **Espera**: todos os headways aplicados surgem como `"mode":"wait"`.  
- **Zonas & tarifas**: `zones_passed` **só** em transporte; `fare_cost` coerente com nº de zonas (ou `fare_id`).  
- **Restrições**: casos extremos (wmax=0, tmax=0) penalizam corretamente.  
- **Diversidade**: frente Pareto com soluções diferentes (sem clones).

---

Se precisares, posso escrever os *snippets* prontos para colar em cada ficheiro (`graph_builder.py`, `main.py`, `evolution.py`) conforme fores atacando cada bloco.
