import random
from typing import Iterable, List, Sequence

from deap import base, creator, tools
from constants import EMISSION_METRO_G_PER_KM, EMISSION_STCP_G_PER_KM, PENALTY
from fitness import fitness_from_metrics
TIME_NORM_FACTOR = 3600.0  # normalização heurística (1 hora)
EMISSION_NORM_FACTOR = 100.0  # normalização heurística

if not hasattr(creator, 'FitnessMultiObj'):
    creator.create('FitnessMultiObj', base.Fitness, weights=(-1.0, -1.0, -1.0))
if not hasattr(creator, 'IndividualPath'):
    creator.create('IndividualPath', list, fitness=creator.FitnessMultiObj)
if not hasattr(creator, 'FitnessMultiObjCost'):
    creator.create('FitnessMultiObjCost', base.Fitness, weights=(-1.0, -1.0, -1.0, -1.0))
if not hasattr(creator, 'IndividualPathCost'):
    creator.create('IndividualPathCost', list, fitness=creator.FitnessMultiObjCost)

ACTIVE_INDIVIDUAL_CLASS = creator.IndividualPath


def set_active_individual(include_cost: bool):
    global ACTIVE_INDIVIDUAL_CLASS
    ACTIVE_INDIVIDUAL_CLASS = creator.IndividualPathCost if include_cost else creator.IndividualPath


def individual_from_path(path: Iterable):
    return ACTIVE_INDIVIDUAL_CLASS(list(path))


def _penalty_tuple(include_cost: bool):
    return (PENALTY,) * (4 if include_cost else 3)


def evaluate_individual(graph, individual, walk_policy=None, w_max=None, t_max=None, include_cost=False):
    try:
        metrics = graph.path_metrics(list(individual))
    except Exception:
        return _penalty_tuple(include_cost)

    if not isinstance(metrics, dict):
        return _penalty_tuple(include_cost)

    if metrics.get("time_total_s", PENALTY) >= PENALTY or metrics.get("emissions_g", PENALTY) >= PENALTY:
        return _penalty_tuple(include_cost)

    segments = metrics.get("segments") or []
    walk_time_total = 0.0
    for seg in segments:
        if isinstance(seg, dict) and seg.get("mode") == "walk":
            walk_time_total += float(seg.get("time_s", 0.0))

    if w_max is not None and walk_time_total > w_max:
        return _penalty_tuple(include_cost)

    transfers = metrics.get("n_transfers")
    if t_max is not None and transfers is not None and transfers > t_max:
        return _penalty_tuple(include_cost)

    fitness_values = fitness_from_metrics(metrics, walk_policy=walk_policy)

    if include_cost:
        fare_cost = metrics.get("fare_cost", PENALTY)
        try:
            fare_cost = float(fare_cost)
        except (TypeError, ValueError):
            fare_cost = PENALTY
        return (*fitness_values, fare_cost)

    return fitness_values


def cx_path(p1, p2):
    set1 = set(p1); set2 = set(p2)
    commons = list(set1 & set2)
    if not commons:
        return individual_from_path(p1[:]),
    cut = random.choice(commons)
    i1 = p1.index(cut); i2 = p2.index(cut)
    child = p1[:i1] + p2[i2:]
    seen = set(); cleaned = []
    for n in child:
        if n in seen:
            continue
        seen.add(n); cleaned.append(n)
    return individual_from_path(cleaned),


def mut_path(graph, path, mut_rate=0.5):
    if random.random() > mut_rate or len(path) < 4:
        return individual_from_path(path),
    a = random.randrange(0, len(path) - 2)
    b = random.randrange(a + 2, min(len(path), a + 6))
    start, end = path[a], path[b]

    lam = random.random()  # mistura objetivos

    def w(u, v, d):
        t = d.get("time", 1.0)
        dist_km = d.get("distance_m", 0.0) / 1000.0
        mode = d.get("mode")
        if mode == "stcp":
            ef = EMISSION_STCP_G_PER_KM
        elif mode == "metro":
            ef = EMISSION_METRO_G_PER_KM
        else:
            ef = 0.0
        emis = dist_km * ef
        return lam * t + (1 - lam) * emis

    try:
        sub = graph.shortest_path_between(start, end, weight=w)
        newp = path[:a] + sub + path[b + 1 :]
        seen = set(); cleaned = []
        for n in newp:
            if n in seen:
                continue
            seen.add(n); cleaned.append(n)
        if cleaned == path:  # ainda igual? tenta outra vez uma vez
            return mut_path(graph, path, mut_rate)
        return individual_from_path(cleaned),
    except Exception:
        return individual_from_path(path),


def initialize_toolbox(graph, origin, dest, include_cost=False, walk_policy=None, w_max=None, t_max=None):
    set_active_individual(include_cost)
    toolbox = base.Toolbox()

    def noisy_weight(u, v, d):
        base_time = d.get("time", 1.0)
        return base_time * (1.0 + 0.3 * (random.random() - 0.5))

    def random_valid_path():
        if random.random() < 0.5:
            sp = graph.shortest_path_between(origin, dest, weight=noisy_weight)
            return individual_from_path(sp)
        p = graph.random_walk(origin, dest)
        if not p:
            p = graph.shortest_path_between(origin, dest)
        return individual_from_path(p)

    toolbox.register('individual', random_valid_path)
    toolbox.register('population', tools.initRepeat, list, toolbox.individual)
    toolbox.register('mate', cx_path)
    toolbox.register('mutate', lambda ind: mut_path(graph, list(ind)))
    toolbox.register('select', tools.selNSGA2)
    toolbox.register(
        'evaluate',
        lambda ind: evaluate_individual(
            graph,
            ind,
            walk_policy=walk_policy,
            w_max=w_max,
            t_max=t_max,
            include_cost=include_cost,
        ),
    )
    return toolbox


def _edge_emissions(data: dict) -> float:
    dist_km = float(data.get("distance_m", 0.0)) / 1000.0
    mode = data.get("mode")
    if mode == "stcp":
        return dist_km * EMISSION_STCP_G_PER_KM
    if mode == "metro":
        return dist_km * EMISSION_METRO_G_PER_KM
    return 0.0


def _lambda_weight(lam: float):
    def weight(u, v, data):
        time_s = float(data.get("time_s", data.get("time", 1.0)))
        emissions = _edge_emissions(data)
        time_norm = time_s / TIME_NORM_FACTOR
        emis_norm = emissions / EMISSION_NORM_FACTOR
        return lam * time_norm + (1.0 - lam) * emis_norm

    return weight


def generate_seed_paths(graph, origin, dest, lambdas: Sequence[float]) -> List[List]:
    seeds: List[List] = []
    seen = set()
    for lam in lambdas:
        try:
            path = graph.shortest_path_between(origin, dest, weight=_lambda_weight(lam))
        except Exception:
            continue
        tpl = tuple(path)
        if tpl in seen:
            continue
        seen.add(tpl)
        seeds.append(list(path))
    return seeds


def run_nsga2(
    graph,
    origin,
    dest,
    pop_size=50,
    ngen=30,
    cxpb=0.6,
    mutpb=0.3,
    walk_policy=None,
    w_max=None,
    t_max=None,
    include_cost=False,
    seed_lambdas: Sequence[float] | None = None,
):
    if pop_size % 4 != 0:
        pop_size += 4 - (pop_size % 4)

    if seed_lambdas is None:
        seed_lambdas = [i / 20.0 for i in range(21)]  # 0.0, 0.05, ..., 1.0

    toolbox = initialize_toolbox(
        graph,
        origin,
        dest,
        include_cost=include_cost,
        walk_policy=walk_policy,
        w_max=w_max,
        t_max=t_max,
    )

    seed_paths = generate_seed_paths(graph, origin, dest, seed_lambdas)
    random.shuffle(seed_paths)

    pop: List = [individual_from_path(path) for path in seed_paths[:pop_size]]

    while len(pop) < pop_size:
        pop.append(toolbox.individual())

    uniq = {}
    for ind in pop:
        uniq[tuple(ind)] = ind
    pop = list(uniq.values())
    while len(pop) < pop_size:
        pop.append(toolbox.individual())

    for ind in pop:
        ind.fitness.values = toolbox.evaluate(ind)

    for g in range(1, ngen + 1):
        offspring = toolbox.select(pop, len(pop))
        offspring = [individual_from_path(list(ind)) for ind in offspring]

        for i in range(0, len(offspring) - 1, 2):
            if random.random() < cxpb:
                c1, = toolbox.mate(list(offspring[i]), list(offspring[i + 1]))
                offspring[i] = c1

        for i in range(len(offspring)):
            if random.random() < mutpb:
                m1, = toolbox.mutate(offspring[i])
                offspring[i] = m1

        for i in range(0, len(offspring) - 1, 2):
            if list(offspring[i]) == list(offspring[i + 1]):
                m1, = toolbox.mutate(offspring[i])
                offspring[i] = m1

        uniq = {}
        for ind in offspring:
            uniq[tuple(ind)] = ind
        offspring = list(uniq.values())

        while len(offspring) < pop_size:
            offspring.append(toolbox.individual())

        for ind in offspring:
            ind.fitness.values = toolbox.evaluate(ind)

        pop = toolbox.select(pop + offspring, pop_size)
        print(f'Generation {g} completed')

    return pop
