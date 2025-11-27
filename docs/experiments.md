# Experiências com Cenários e Baselines

Este guia explica, passo a passo, como gerar cenários (`generate_scenarios`), executar o baseline Dijkstra-λ e correr o NSGA-II com o runner `experiments.py`. Inclui também instruções para avaliar quantas soluções do baseline são dominadas.

## 1. Preparar o ambiente

- Certifica-te de que tens os dados GTFS em `data/Metro` e `data/STCP` (ou ajusta as paths nas flags `--metro` e `--stcp`).
- Recomenda-se ativar o ambiente virtual/conda com as dependências necessárias, e depois executar:

```bash
cd C:\Users\Vasco\Documents\GitHub\CIN
```

## 2. Gerar cenários e correr baseline + NSGA-II

Para gerar **3 cenários por tipo** (curto, médio, longo) e correr tanto o baseline como o NSGA-II:

```bash
python src\experiments.py --metro data/Metro --stcp data/STCP --scenarios 3 --scenario-types short,mid,long --output-dir outputs\experiments\demo 
  --walk-policy minimize --pop-size 20 --gens 10 --no-cache
```

Notas:

- Ajusta `--scenarios` para mudar o número de cenários por tipo.
- `--no-cache` garante que o grafo é reconstruído de raiz (evita erros se a cache tiver versões antigas de bibliotecas).
- Usa `--walk-policy minimize` se quiseres que o terceiro objetivo (caminhada) seja minimizado.
- `--lambdas` permite definir manualmente os valores de λ do baseline (por omissão usa 0.0, 0.05, …, 1.0).

### Estrutura dos resultados

Supondo `--output-dir outputs/experiments/demo`, ao terminar terás:

- `outputs/experiments/demo/scenarios.json`: lista dos cenários gerados (cada entrada tem `id`, `type`, `origin`, `destination`, comprimentos, etc.).
- `outputs/experiments/demo/baseline_summary.json`: resumo das soluções baseline para todos os cenários.
- Para cada cenário `ID` (por exemplo `short_000`), uma pasta `outputs/experiments/demo/ID/` com:
  - `baseline_pareto.json` — soluções do baseline Dijkstra-λ (com `segments`, `zones_passed`, `used_bridge_ids`, `blocked_walk_edges_douro` e `has_walk`, tal como no NSGA-II).
  - `final_population.json` — população final do NSGA-II (indivíduos válidos deduplicados).
  - `pareto_solutions.json` — soluções NSGA-II na frente Pareto (com caminhos completos e métricas).
  - `pareto_front.json` — fronteira 2D (tempo vs emissões) usada nos cálculos de hipervolume.

Os ficheiros `pareto_solutions.json` e `baseline_pareto.json` incluem agora agregados auditáveis:

- `wait_s_total` e `waits` (soma total de espera e por route_id).
- `distance_km_by_mode` (quilómetros percorridos por modo: metro, stcp, walk).
- `fare_cost` e `fare_selected` (identificador/preço da tarifa aplicada ou fallback).

## 3. Verificar dominação (baseline vs NSGA-II)

Criei o script `scripts/domination_check.py` que percorre as pastas de cenários e indica quantas soluções do baseline são dominadas pelas soluções NSGA-II.

### Executar o script

```bash
python src\domination_check.py --root outputs/experiments/demo --walk-policy minimize
```

Parâmetros:

- `--root`: diretório onde o runner guardou os resultados (default `outputs/experiments`).
- `--walk-policy`: política usada no NSGA-II (`maximize` é o padrão; usa `minimize` se tiveres corrido o NSGA com minimização da caminhada).

O output lista, por cenário, o número e a percentagem de soluções baseline dominadas. No fim mostra o total agregado, útil para o checklist “>50% dominados”.

## 4. Recomendações adicionais

- Guarda a mesma seed (`--random-seed`) quando quiseres repetir experiências com cenários idênticos.
- Se mudares parâmetros importantes (ex.: população, número de gerações, políticas), grava os resultados noutra pasta (`--output-dir`) para manter histórico.
- Antes de correr experiências longas, valida com um número reduzido de cenários (por exemplo `--scenarios 1`) para garantir que tudo corre sem erros.

