# CLI — Como executar

Este projeto tem dois scripts principais:

- `src/main.py`: corre um caso único (origem → destino) e grava a fronteira Pareto.
- `src/experiments.py`: corre baterias de cenários (short/mid/long), compara o **baseline Dijkstra-λ** vs **NSGA-II** e calcula **hypervolume**.

---

## `python src/main.py` — caso único (NSGA-II)

### Argumentos principais
- `--metro <pasta>`: pasta GTFS do Metro (ex.: `data/Metro`)
- `--stcp <pasta>`: pasta GTFS da STCP (ex.: `data/STCP`)
- `--origin <id|lat,lon>`: origem (ID de paragem/estação ou coordenadas `lat,lon`)
- `--dest <id|lat,lon>`: destino (ID de paragem/estação ou coordenadas `lat,lon`)
- `--walk-radius <m>`: raio (metros) para criar arestas a pé entre paragens (ex.: 400)
- `--pop-size <n>`: tamanho da população do NSGA-II
- `--gens <n>`: número de gerações do NSGA-II

### Restrições
- `--wmax-s <seg>`: tempo total máximo a pé (segundos)
- `--tmax <n>`: máximo de transbordos

### Opções (objetivos)
- `--walk-policy minimize|maximize`:
  - `minimize`: preferir menos caminhada
  - `maximize`: preferir mais caminhada (exercício)
- `--include-cost`: inclui custo tarifário como objetivo adicional (quando disponível)

### Exemplos
**Por IDs**
```bash
python src/main.py --metro data/Metro --stcp data/STCP --origin 5697 --dest CRG2 --walk-radius 400 --pop-size 30 --gens 40 --wmax-s 900 --tmax 2 --walk-policy minimize
```

**Por coordenadas**
```bash
python src/main.py --metro data/Metro --stcp data/STCP --origin "41.1496,-8.6109" --dest "41.1579,-8.6291" --walk-radius 400 --pop-size 40 --gens 30
```

---

## `python src/experiments.py` — cenários + baseline vs NSGA-II + hypervolume

Executa baterias de cenários e compara baseline vs NSGA-II usando hipervolume 2D (tempo vs emissões).

### Argumentos de cenários
- `--scenarios <n>`: número de cenários por tipo (ex.: 10)
- `--scenario-types short,mid,long`: tipos de cenários a gerar
- `--random-seed <n>`: seed para reproduzir os cenários
- `--output-dir <pasta>`: onde gravar resultados (default `outputs/experiments`)
- `--graph-cache <ficheiro>` / `--no-cache`: opções para reutilizar ou reconstruir o grafo

### Argumentos dos algoritmos
- `--pop-size <n>` / `--gens <n>`: parâmetros do NSGA-II
- `--wmax-s <seg>` / `--tmax <n>`: restrições sobre caminhada e transbordos
- `--walk-policy maximize|minimize` / `--include-cost`: opções de objetivos
- `--lambdas ...`: valores de λ para o baseline (default 0.0,0.05,…,1.0)
- `--seed-lambdas ...`: λ usados como seeds no NSGA-II (por omissão usa os mesmos do baseline)

### Exemplo completo
```bash
python src/experiments.py --metro data/Metro --stcp data/STCP --walk-radius 400 --scenarios 5 --scenario-types short,mid,long --random-seed 42 --pop-size 50 --gens 30 --wmax-s 900 --tmax 2 --walk-policy minimize
```