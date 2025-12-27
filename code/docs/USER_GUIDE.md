# Manual do Utilizador — Planeador Multimodal CIN

Este manual explica como utilizar a interface web do planeador multimodal para encontrar rotas otimizadas no Grande Porto.

---

## 1. Como Escolher Origem e Destino

A aplicação aceita três formatos para definir origem e destino:

### 1.1. Nome da Paragem
Escreve o nome completo ou parcial da paragem. A aplicação procura automaticamente correspondências.

**Exemplos**:
- `Trindade`
- `Hospital São João`
- `Câmara de Gaia`

**Dica**: Se houver múltiplas correspondências, a aplicação escolhe a mais relevante (geralmente a primeira). Podes verificar o ID da paragem selecionada na mensagem de informação.

### 1.2. ID da Paragem
Escreve o identificador numérico ou alfanumérico da paragem.

**Exemplos**:
- `803`
- `5697`
- `CRG2`

**Nota**: Os IDs podem variar entre Metro e STCP. Se não souberes o ID, usa o nome da paragem.

### 1.3. Coordenadas Geográficas
Escreve as coordenadas no formato `latitude,longitude` (sem espaços).

**Exemplos**:
- `41.1496,-8.6109`
- `41.1579,-8.6291`

**Quando usar**: Útil para pontos que não são paragens oficiais (ex.: tua casa, um restaurante). A aplicação cria um "ponto virtual" e liga-o às paragens mais próximas.

---

## 2. O que Fazem os Sliders (Pesos)

Os **pesos** controlam como a aplicação escolhe automaticamente a "melhor rota" entre todas as soluções do Pareto geradas pelo algoritmo.

### 2.1. Peso Tempo
- **O que faz**: Define a importância de minimizar o tempo total de viagem
- **Valores altos (ex.: 0.7-1.0)**: Prioriza rotas rápidas, mesmo que emitam mais CO₂ ou exijam mais caminhada
- **Valores baixos (ex.: 0.0-0.3)**: Dá menos importância ao tempo, permitindo rotas mais lentas se forem melhores noutros aspetos

**Exemplo**: Com peso tempo = 0.8, a aplicação escolhe rotas que demoram menos, mesmo que isso signifique usar mais autocarros (mais CO₂) ou caminhar mais.

### 2.2. Peso CO₂
- **O que faz**: Define a importância de minimizar as emissões de dióxido de carbono
- **Valores altos (ex.: 0.7-1.0)**: Prioriza rotas com menos emissões, favorecendo Metro (40 gCO₂/km) sobre STCP (109.9 gCO₂/km)
- **Valores baixos (ex.: 0.0-0.3)**: Dá menos importância às emissões, permitindo rotas mais poluentes se forem mais rápidas

**Exemplo**: Com peso CO₂ = 0.9, a aplicação escolhe rotas que usam principalmente Metro, mesmo que isso signifique mais transbordos ou mais tempo.

### 2.3. Peso Exercício
- **O que faz**: Define a importância da caminhada (exercício físico)
- **Valores altos (ex.: 0.7-1.0)**: Prioriza rotas com mais caminhada, incentivando exercício
- **Valores baixos (ex.: 0.0-0.3)**: Minimiza a caminhada, preferindo usar transporte público sempre que possível

**Exemplo**: Com peso exercício = 0.8, a aplicação escolhe rotas que incluem mais segmentos a pé, mesmo que demorem mais tempo.

### 2.4. Presets (Preferência Principal)

Em vez de ajustar manualmente os pesos, podes escolher um preset:

- **Tempo**: Peso tempo = 0.7, CO₂ = 0.2, Exercício = 0.1
- **CO₂**: Peso tempo = 0.2, CO₂ = 0.7, Exercício = 0.1
- **Exercício**: Peso tempo = 0.2, CO₂ = 0.1, Exercício = 0.7
- **Equilíbrio**: Peso tempo = 0.33, CO₂ = 0.33, Exercício = 0.33 (igual importância)

**Nota**: Os presets apenas definem valores iniciais. Podes ajustar os sliders manualmente depois.

---

## 3. O que Significam Wmax e Tmax

### 3.1. Wmax (Limite Total a Pé)

**O que é**: Tempo máximo total que podes caminhar durante toda a viagem, em minutos.

**Como funciona**:
- Se definires Wmax = 15 minutos, a aplicação só considera rotas onde a soma de todos os segmentos a pé não exceda 15 minutos
- Se uma rota exigir 20 minutos a pé, é automaticamente rejeitada
- Valor 0 = sem limite (permite qualquer quantidade de caminhada)

**Quando usar**:
- Se tiveres limitações físicas ou preferires evitar caminhadas longas
- Se quiseres garantir que a viagem não exige mais de X minutos a pé
- Para testar diferentes cenários (ex.: "quais rotas existem se só puder caminhar 10 minutos?")

**Exemplo**: Wmax = 20 significa que, mesmo que exista uma rota excelente que exija 25 minutos a pé, ela não será considerada.

### 3.2. Tmax (Transbordos Máximos)

**O que é**: Número máximo de transbordos (mudanças de linha/veículo) permitidos na viagem.

**Como funciona**:
- Cada vez que mudas de linha de Metro, de autocarro STCP, ou entre Metro e STCP, conta como 1 transbordo
- Se definires Tmax = 2, a aplicação só considera rotas com 0, 1 ou 2 transbordos
- Rotas com 3 ou mais transbordos são automaticamente rejeitadas

**Quando usar**:
- Se preferires viagens diretas ou com poucas mudanças
- Para evitar rotas complexas com muitos transbordos
- Para comparar soluções simples vs complexas

**Exemplo**: Tmax = 1 significa que só aceitas rotas diretas ou com apenas 1 transbordo. Uma rota que exija 2 transbordos não será considerada, mesmo que seja mais rápida ou ecológica.

**Nota**: Transbordos dentro da mesma linha (ex.: mudar de autocarro 201 para autocarro 202) também contam.

---

## 4. Como Interpretar a Fronteira Pareto

A **fronteira Pareto** é o conjunto de todas as rotas "não-dominadas" encontradas pelo algoritmo. Uma rota é "não-dominada" se não existe outra rota que seja melhor em todos os objetivos simultaneamente.

### 4.1. O que Significa "Não-Dominada"

Uma rota A domina uma rota B se:
- A é melhor (menor) em pelo menos um objetivo (tempo, CO₂, ou caminhada)
- E A não é pior em nenhum outro objetivo

**Exemplo**:
- Rota 1: 30 min, 50 g CO₂, 500 m a pé
- Rota 2: 35 min, 50 g CO₂, 500 m a pé
- Rota 3: 30 min, 60 g CO₂, 500 m a pé

A Rota 1 domina a Rota 2 (mesmo CO₂ e caminhada, mas menos tempo).  
A Rota 1 não domina a Rota 3 (menos tempo, mas mais CO₂).

### 4.2. Tabela Comparativa

A aplicação mostra uma tabela com todas as rotas do Pareto:

| Rota | Tempo total (min) | CO₂ (g) | Caminhada (m) | Esperas (min) | Transbordos |
|------|-------------------|---------|---------------|---------------|-------------|
| 1    | 25.3              | 45      | 800           | 3.2           | 1           |
| 2    | 28.1              | 38      | 1200          | 4.5           | 2           |
| 3    | 32.5              | 35      | 1500          | 5.1           | 1           |

**Como ler**:
- Cada linha é uma rota diferente
- Não existe uma rota "perfeita" — cada uma tem trade-offs
- A rota 1 é mais rápida, mas emite mais CO₂
- A rota 3 é mais ecológica, mas demora mais e exige mais caminhada

### 4.3. Escolher uma Rota

**Método automático**:
- A aplicação escolhe automaticamente a rota com melhor "score" segundo os pesos definidos
- Esta rota aparece destacada com os passos detalhados

**Método manual**:
- Clica em "Selecionar esta rota" na linha da tabela que preferes
- Os passos detalhados atualizam-se automaticamente

**Dicas para escolher**:
- Se priorizas velocidade: escolhe a rota com menor tempo total
- Se priorizas ambiente: escolhe a rota com menor CO₂
- Se queres exercício: escolhe a rota com mais caminhada
- Se queres simplicidade: escolhe a rota com menos transbordos

### 4.4. Passos Detalhados

Cada rota mostra uma lista passo a passo:

1. **Andar 0.5 km (6 min) de Trindade até Campanhã**
2. **metro · Linha D: Campanhã → Hospital São João (12 min)**
3. **Esperar em Hospital São João (2 min) pela próxima ligação**

**Como interpretar**:
- **Andar**: Segmento a pé (distância e tempo)
- **metro/stcp**: Viagem de transporte público (linha, paragens, tempo)
- **Esperar**: Tempo de espera estimado (metade do headway da linha)
- **Transferência**: Mudança entre linhas/paragens

### 4.5. Trade-offs Comuns

**Tempo vs CO₂**:
- Rotas mais rápidas tendem a usar mais autocarros (mais CO₂)
- Rotas mais ecológicas tendem a usar mais Metro (pode ser mais lento devido a transbordos)

**Tempo vs Caminhada**:
- Rotas com mais caminhada podem ser mais diretas (menos transbordos)
- Rotas com menos caminhada podem exigir mais transbordos (mais tempo total)

**Caminhada vs CO₂**:
- Rotas com mais caminhada emitem menos CO₂ (menos transporte)
- Rotas com menos caminhada podem emitir mais CO₂ (mais transporte público)

---

## 5. Exemplos Práticos

### Exemplo 1: Viagem Rápida
**Objetivo**: Chegar o mais rápido possível

1. Origem: `Trindade`
2. Destino: `Hospital São João`
3. Preferência: **Tempo**
4. Wmax: 15 min (limite razoável de caminhada)
5. Tmax: 2 (permite alguns transbordos)

**Resultado esperado**: Rota com menor tempo total, possivelmente usando autocarros diretos ou poucos transbordos.

### Exemplo 2: Viagem Ecológica
**Objetivo**: Minimizar emissões de CO₂

1. Origem: `Câmara de Gaia`
2. Destino: `Aeroporto`
3. Preferência: **CO₂**
4. Wmax: 20 min
5. Tmax: 3 (permite transbordos para usar Metro)

**Resultado esperado**: Rota que privilegia Metro sobre STCP, mesmo que exija mais transbordos ou mais tempo.

### Exemplo 3: Viagem com Exercício
**Objetivo**: Incluir caminhada na viagem

1. Origem: `41.1496,-8.6109` (coordenadas)
2. Destino: `Hospital São João`
3. Preferência: **Exercício**
4. Wmax: 30 min (permite bastante caminhada)
5. Tmax: 1 (preferência por rotas simples)

**Resultado esperado**: Rota com segmentos a pé significativos, possivelmente combinando caminhada com transporte público.

---

## 6. Resolução de Problemas

### "Nenhuma rota encontrada"
- **Causa**: Restrições muito apertadas (Wmax muito baixo, Tmax muito baixo) ou origem/destino muito distantes
- **Solução**: Aumenta Wmax e/ou Tmax, ou verifica se os pontos estão na área coberta pelos dados GTFS

### "Stop not found"
- **Causa**: ID ou nome da paragem incorreto
- **Solução**: Usa coordenadas ou verifica o nome exato da paragem

### Aplicação muito lenta
- **Causa**: Primeira execução constrói o grafo (pode demorar minutos)
- **Solução**: Aguarda; execuções seguintes usam cache e são mais rápidas

---

*Última atualização: [Data]*

