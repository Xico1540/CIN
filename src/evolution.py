import random
from deap import base, creator, tools
from fitness import evaluate_route

PENALTY = 1e9

creator.create('FitnessMultiObj', base.Fitness, weights=(-1.0, -1.0, -1.0))
creator.create('IndividualPath', list, fitness=creator.FitnessMultiObj)

def individual_from_path(path):
    return creator.IndividualPath(path)

def evaluate_individual(graph, individual):
    try:
        time_s, emissions_g, walk_neg = evaluate_route(graph.G, list(individual))
        return time_s, emissions_g, walk_neg
    except Exception:
        return PENALTY, PENALTY, PENALTY

def cx_path(p1, p2):
    set1 = set(p1); set2 = set(p2)
    commons = list(set1 & set2)
    if not commons:
        return creator.IndividualPath(p1[:]),
    cut = random.choice(commons)
    i1 = p1.index(cut); i2 = p2.index(cut)
    child = p1[:i1] + p2[i2:]
    seen = set(); cleaned = []
    for n in child:
        if n in seen: continue
        seen.add(n); cleaned.append(n)
    return creator.IndividualPath(cleaned),

def mut_path(graph, path, mut_rate=0.5):
    if random.random() > mut_rate or len(path) < 4:
        return creator.IndividualPath(path),
    a = random.randrange(0, len(path)-2)
    b = random.randrange(a+2, min(len(path), a+6))
    start = path[a]; end = path[b]
    try:
        sub = graph.shortest_path_between(start, end)
        newp = path[:a] + sub + path[b+1:]
        seen = set(); cleaned = []
        for n in newp:
            if n in seen: continue
            seen.add(n); cleaned.append(n)
        return creator.IndividualPath(cleaned),
    except Exception:
        return creator.IndividualPath(path),

def initialize_toolbox(graph, origin, dest):
    toolbox = base.Toolbox()

    def random_valid_path():
        try:
            sp = graph.shortest_path_between(origin, dest)
            return creator.IndividualPath(sp)
        except Exception:
            p = graph.random_walk(origin, dest)
            if p is None:
                return creator.IndividualPath([origin, dest])
            return creator.IndividualPath(p)

    def random_valid_path():
        # Tenta o caminho mais curto
        try:
            sp = graph.shortest_path_between(origin, dest)
            return creator.IndividualPath(sp)
        except Exception:
            # fallback: random walk
            p = graph.random_walk(origin, dest)
            if p is None or len(p) < 2:
                # garante que origin e dest estão presentes pelo menos
                return creator.IndividualPath([origin, dest])
            return creator.IndividualPath(p)

    toolbox.register('individual', random_valid_path)
    toolbox.register('population', tools.initRepeat, list, toolbox.individual)
    toolbox.register('mate', cx_path)
    toolbox.register('mutate', lambda ind: mut_path(graph, list(ind)))
    toolbox.register('select', tools.selNSGA2)
    toolbox.register('evaluate', lambda ind: evaluate_individual(graph, ind))
    return toolbox

def run_nsga2(graph, origin, dest, pop_size=50, ngen=30, cxpb=0.6, mutpb=0.3):
    # Ajusta pop_size para ser múltiplo de 4 para evitar erro DEAP
    if pop_size % 4 != 0:
        pop_size += 4 - (pop_size % 4)

    toolbox = initialize_toolbox(graph, origin, dest)
    pop = toolbox.population(n=pop_size)

    for ind in pop:
        ind.fitness.values = toolbox.evaluate(ind)

    for g in range(1, ngen+1):
        offspring = toolbox.select(pop, len(pop))
        offspring = [creator.IndividualPath(list(ind)) for ind in offspring]

        for i in range(0, len(offspring)-1, 2):
            if random.random() < cxpb:
                c1, = toolbox.mate(list(offspring[i]), list(offspring[i+1]))
                offspring[i] = c1

        for i in range(len(offspring)):
            if random.random() < mutpb:
                m1, = toolbox.mutate(offspring[i])
                offspring[i] = m1

        for ind in offspring:
            ind.fitness.values = toolbox.evaluate(ind)

        pop = toolbox.select(pop + offspring, pop_size)
        print(f'Generation {g} completed')

    return pop
