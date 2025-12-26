# Planeador Multimodal (Grande Porto) — CIN

Projeto em Python que constrói um **grafo multimodal** (Metro + STCP + a pé) a partir de dados **GTFS** e encontra rotas entre origem e destino com **otimização multi-objetivo**.

## Constituição do Grupo



- Elemento 1: Francisco Costa PG60387
- Elemento 2: João Mendes PG60388
- Elemetno 3: Simão Silva PG60393
- Elemento 4: Vasco Macedo PG60394 

## Estrutura do Repositório

```
CIN/code/
├── app/                    # Interface web Streamlit
│   └── streamlit_app.py   # Aplicação web interativa
├── data/                   # Dados GTFS e regras
│   ├── bridges/            # Regras e geometria de pontes
│   ├── Metro/              # Dados GTFS do Metro do Porto
│   └── STCP/               # Dados GTFS da STCP
├── docs/                   # Documentação técnica
│   ├── CLI.md             # Guia de linha de comandos
│   ├── MODEL.md            # Modelo e decisões do projeto
│   └── OUTPUTS.md          # Descrição dos outputs gerados
├── outputs/                # Resultados e cache
│   ├── cache/              # Cache do grafo multimodal
│   ├── experiments/        # Resultados de experiências
│   └── pareto/             # Soluções Pareto geradas
├── src/                    # Código fonte principal
│   ├── baselines.py        # Algoritmos baseline (Dijkstra-λ)
│   ├── constants.py         # Constantes do projeto
│   ├── evolution.py         # NSGA-II e evolução
│   ├── experiments.py       # Execução de experiências
│   ├── fitness.py           # Funções de fitness
│   ├── graph_builder.py     # Construção do grafo multimodal
│   ├── hypervolume.py       # Cálculo de hipervolume
│   ├── loader.py            # Carregamento de dados GTFS
│   ├── main.py              # Script principal CLI
│   └── scenarios.py         # Geração de cenários
├── README.md                # Este ficheiro
├── requirements.txt         # Dependências Python
└── PROJETO.md              # Apresentação do projeto (relatório + manual)
```

## Objetivos e restrições
Objetivos principais (multi-objetivo):
- Minimizar **tempo total** (`time_total_s`)
- Minimizar **CO₂** (`emissions_g`)  
  - STCP: 109.9 gCO₂/p.km  
  - Metro: 40 gCO₂/p.km
- (Opcional) Caminhada: maximizar exercício ou minimizar caminhada (`--walk-policy`)
- (Opcional) Custo de tarifa como 4º objetivo (`--include-cost`)

Restrições:
- `--tmax`: máximo de transbordos
- `--wmax-s`: máximo de tempo total a pé (segundos)

Além disso, travessias pedonais do Douro são controladas por regras de pontes em:
- `data/bridges/bridges_pedestrian_rules.txt`
- `data/bridges/bridges_geometry.json`

## Dados (GTFS)
Coloca os dados em:
- `data/Metro/` (GTFS Metro do Porto)
- `data/STCP/` (GTFS STCP)

Ou indica paths com `--metro` e `--stcp`.

## Instalação
Requer Python 3.10+.

```bash
pip install -r requirements.txt
```

## Interface Web (Streamlit)
- Executa `streamlit run app/streamlit_app.py`.
- Introduz origem/destino (nome, ID ou coordenadas) e escolhe prioridades (tempo, CO₂, exercício, equilíbrio).
- A app gera o Pareto atual, mostra tabela comparativa e descreve passo a passo da rota selecionada.

## Documentação
- [CLI / Como executar](docs/CLI.md)
- [Outputs / Ficheiros gerados](docs/OUTPUTS.md)
- [Modelo e decisões do projeto](docs/MODEL.md)
