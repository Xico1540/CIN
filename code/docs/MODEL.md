# Modelo / Assunções / Decisões

## Grafo multimodal
O grafo é construído a partir de GTFS (Metro + STCP):
- Nós: paragens/estações
- Arestas:
  - `metro` e `stcp`: segmentos de transporte
  - `walk`: ligações a pé entre paragens num raio `--walk-radius`
  - `transfer`: transferências GTFS quando existirem

Também podem ser criados nós virtuais para origem/destino por coordenadas, ligados às paragens mais próximas a pé.

---

## Objetivos
Objetivos principais:
- Tempo total (`time_total_s`): tempo de deslocação + esperas (quando modeladas)
- Emissões (`emissions_g`): soma por distância percorrida em transporte

Fatores usados (gCO₂ por passageiro.km):
- STCP: 109.9 gCO₂/p.km
- Metro: 40 gCO₂/p.km
- A pé: 0

Opcional:
- Caminhada como objetivo adicional (`--walk-policy`)
- Custo como objetivo adicional (`--include-cost`)

---

## Restrições
- `--tmax`: máximo de transbordos
- `--wmax-s`: máximo de tempo total a pé (segundos)

Se uma rota violar restrições, é penalizada e não entra na fronteira.

---

## “Peões podem/não podem” — travessia do Douro
Para evitar travessias pedonais irreais do Rio Douro:
- deteta-se a travessia usando uma bounding box aproximada + separação por margens
- se um segmento walk cruzar o Douro, só é permitido se:
  - a ponte correspondente for detetada (snap) em `data/bridges/bridges_geometry.json`
  - e a ponte estiver marcada como permitida em `data/bridges/bridges_pedestrian_rules.txt`

---

## Algoritmos
### Baseline (soma ponderada)
Gera soluções via soma ponderada dos objetivos (tempo vs emissões), variando λ, e filtra Pareto 2D.

### NSGA-II
Procura um conjunto de soluções não-dominadas, podendo usar seeds informadas pelo domínio.

---

## Avaliação por Hypervolume (HV)
A comparação baseline vs NSGA-II usa Hypervolume em 2D:
- pontos: `(time_total_s, emissions_g)`
- aplicado filtro Pareto 2D antes do HV
- ponto de referência `ref` calculado a partir da união das frentes (com margem)
