# Execução do `main.py`

Este documento resume todas as flags disponíveis no módulo principal (`src/main.py`), incluindo as restrições atualmente suportadas sobre transbordos e tempo a pé, e fornece exemplos de utilização.

## Flags principais

| Flag | Descrição |
| --- | --- |
| `--metro PATH` | Caminho para a pasta GTFS do Metro (por omissão usa `data/Metro`). |
| `--stcp PATH` | Caminho para a pasta GTFS da STCP (por omissão usa `data/STCP`). |
| `--origin STOP_ID` | Identificador da paragem de origem (ex.: `METRO_5791`). |
| `--dest STOP_ID` | Identificador da paragem de destino. |
| `--origin "lat,lon"` | Coordenadas da origem em graus decimais. Cria um nó virtual ligado às paragens mais próximas (ex.: `--origin "41.1777,-8.5982"`). |
| `--dest "lat,lon"` | Coordenadas do destino em graus decimais, com comportamento idêntico ao anterior. |
| `--origin-name "texto"` | Nome (ou parte do nome) da paragem de origem; tem prioridade sobre `--origin`. Aceita pesquisas fuzzy case-insensitive. |
| `--dest-name "texto"` | Nome (ou parte do nome) da paragem de destino; tem prioridade sobre `--dest`. |
| `--walk-radius METROS` | Raio máximo para ligações a pé ao construir o grafo (default: 400 m). |
| `--pop-size N` | Tamanho da população do NSGA-II (default: 50). Deve ser múltiplo de 4 (ajustado automaticamente). |
| `--gens N` | Número de gerações do NSGA-II (default: 30). |
| `--walk-policy {maximize,minimize}` | Orientação do objetivo de caminhada (por omissão “maximize”, que corresponde a minimizar a distância a pé porque o terceiro objetivo é o valor negativo de `walk_m`). |
| `--wmax-s SEGUNDOS` | **Limite máximo de tempo a pé**. Indivíduos que excedem este valor recebem penalização. |
| `--tmax N` | **Limite de transbordos**. Indivíduos com número de transbordos ≥ `tmax` são penalizados. |
| `--include-cost` | Ativa objetivo adicional com custo tarifário estimado. |

## Restrições suportadas

- **Número de transbordos (`--tmax`)**: passado para `run_nsga2`, que desclassifica indivíduos cujo `n_transfers` seja igual ou superior ao limite indicado.
- **Tempo total a pé (`--wmax-s`)**: idem; se a soma dos segmentos `walk` exceder o limite, o indivíduo recebe `PENALTY`.

Ambas as restrições são aplicadas durante a avaliação de cada indivíduo no algoritmo, garantindo que as soluções finais respeitam os limites definidos.

## Exemplo completo

```bash
python src\main.py ^
  --metro data/Metro ^
  --stcp data/STCP ^
  --origin-name "São João" ^
  --dest-name "Campanhã" ^
  --walk-radius 500 ^
  --pop-size 40 ^
  --gens 25 ^
  --walk-policy minimize ^
  --wmax-s 600 ^
  --tmax 2
```

Este comando:

- Procura automaticamente “São João” e “Campanhã” nas paragens, utilizando a melhor correspondência encontrada.
- Limita as soluções a 10 minutos de caminhada (`--wmax-s 600`) e no máximo 2 transbordos (`--tmax 2`).
- Ajusta parâmetros evolutivos (`--pop-size`, `--gens`) e o raio de caminhada usado na construção do grafo.

## Saídas

Após a execução, o ficheiro `pareto_solutions.json` contém as soluções não dominadas com métricas agregadas (`time_total_s`, `emissions_g`, `walk_m`, `wait_s_total`, `fare_cost`, `fare_selected`, etc.). Se desejar comparar com um baseline determinístico ou gerar cenários múltiplos, utilize antes `src/experiments.py` (ver `docs/experiments.md`).


