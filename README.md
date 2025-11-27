# Planeador Multimodal (Grande Porto) — CIN

Projeto em Python que constrói um **grafo multimodal** (Metro + STCP + a pé) a partir de dados **GTFS** e encontra rotas entre origem e destino com **otimização multi-objetivo**.

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
