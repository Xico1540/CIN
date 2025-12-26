import json
import math
import os
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st  # type: ignore[import]

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.constants import PENALTY
from src.loader import PROJECT_ROOT as PROJECT_ROOT_CONST
from src.main import GRAPH_CACHE_FILE, PARETO_DIR, run_example

PROJECT_ROOT = PROJECT_ROOT_CONST

PARETO_FILE = Path(PARETO_DIR) / "pareto_solutions.json"
PRESET_WEIGHTS: Dict[str, Tuple[float, float, float]] = {
    "Tempo": (0.7, 0.2, 0.1),
    "CO₂": (0.2, 0.7, 0.1),
    "Exercício": (0.2, 0.1, 0.7),
    "Equilíbrio": (1 / 3, 1 / 3, 1 / 3),
}


def _load_pareto_solutions() -> List[dict]:
    if not PARETO_FILE.exists():
        return []
    try:
        with open(PARETO_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        return []
    return []


def _classify_stop_input(value: str) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    value = value.strip()
    if "," in value:
        return value, None
    if any(ch.isdigit() for ch in value) and " " not in value:
        return value, None
    return None, value


def _ensure_graph_cache(reset: bool = False):
    if reset and "graph_cache" in st.session_state:
        st.session_state.pop("graph_cache", None)
    if "graph_cache" not in st.session_state:
        if os.path.exists(GRAPH_CACHE_FILE):
            try:
                with open(GRAPH_CACHE_FILE, "rb") as fh:
                    st.session_state["graph_cache"] = pickle.load(fh)
            except (OSError, pickle.UnpicklingError):
                st.session_state["graph_cache"] = None
        else:
            st.session_state["graph_cache"] = None
    return st.session_state.get("graph_cache")


def _node_label(node_id: Optional[str]) -> str:
    if not node_id:
        return "?"
    graph = _ensure_graph_cache()
    if graph and hasattr(graph, "G") and node_id in graph.G:
        data = graph.G.nodes[node_id]
        stop_name = data.get("stop_name")
        prefix = data.get("prefix")
        if stop_name:
            return f"{stop_name} ({prefix})"
        return node_id
    return node_id


def _format_minutes(seconds: Optional[float]) -> str:
    if seconds in (None, PENALTY):
        return "-"
    minutes = float(seconds) / 60.0
    return f"{minutes:.1f}"


def _normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if math.isclose(min_v, max_v):
        return [0.0 for _ in values]
    span = max_v - min_v
    return [(v - min_v) / span for v in values]


def _auto_select_route(
    solutions: List[dict],
    preference: str,
    weights: Tuple[float, float, float],
) -> Optional[int]:
    if not solutions:
        return None
    times = [sol["metrics"].get("time_total_s", PENALTY) for sol in solutions]
    co2 = [sol["metrics"].get("emissions_g", PENALTY) for sol in solutions]
    walks = [sol["metrics"].get("walk_m", 0.0) for sol in solutions]

    if preference == "Tempo":
        return min(range(len(times)), key=lambda i: times[i])
    if preference == "CO₂":
        return min(range(len(co2)), key=lambda i: co2[i])
    if preference == "Exercício":
        return max(range(len(walks)), key=lambda i: walks[i])

    norm_time = _normalize(times)
    norm_co2 = _normalize(co2)
    if walks and not math.isclose(max(walks), min(walks)):
        walk_cost = [1.0 - val for val in _normalize(walks)]
    else:
        walk_cost = [0.0 for _ in walks]

    w_time, w_co2, w_walk = weights
    if math.isclose(w_time + w_co2 + w_walk, 0.0):
        w_time = 1.0
    scores = []
    for idx in range(len(solutions)):
        score = (
            w_time * norm_time[idx]
            + w_co2 * norm_co2[idx]
            + w_walk * walk_cost[idx]
        )
        scores.append(score)
    return min(range(len(scores)), key=lambda i: scores[i])


def _segment_description(seg: dict) -> str:
    mode = seg.get("mode")
    start = _node_label(seg.get("from_stop"))
    end = _node_label(seg.get("to_stop"))
    time_min = _format_minutes(seg.get("time_s"))
    distance_m = seg.get("distance_m", 0.0) or 0.0
    route = seg.get("route_id")

    if mode == "walk":
        km = distance_m / 1000.0
        return f"Andar {km:.2f} km ({time_min} min) de {start} até {end}"
    if mode == "transfer":
        return f"Transferência em {start} ({time_min} min)"
    if mode == "wait":
        return f"Esperar em {start} ({time_min} min) pela próxima ligação"
    label = f"{mode or 'modo'}"
    if route:
        label += f" · {route}"
    return f"{label}: {start} → {end} ({time_min} min)"


def _metrics_to_dataframe(solutions: List[dict]) -> pd.DataFrame:
    rows = []
    for idx, sol in enumerate(solutions):
        metrics = sol.get("metrics", {})
        rows.append(
            {
                "Rota": idx + 1,
                "Tempo total (min)": float(metrics.get("time_total_s", 0.0)) / 60.0,
                "CO₂ (g)": metrics.get("emissions_g", 0.0),
                "Caminhada (m)": metrics.get("walk_m", 0.0),
                "Esperas (min)": float(metrics.get("waiting_time_s", 0.0)) / 60.0,
                "Transbordos": metrics.get("n_transfers", 0),
            }
        )
    return pd.DataFrame(rows)


def _prepare_run_args(origin_input: str, dest_input: str) -> Dict[str, str]:
    origin_id, origin_name = _classify_stop_input(origin_input)
    dest_id, dest_name = _classify_stop_input(dest_input)
    if not origin_id and not origin_name:
        raise ValueError("Indica a origem (nome, ID ou coordenadas).")
    if not dest_id and not dest_name:
        raise ValueError("Indica o destino (nome, ID ou coordenadas).")

    args: Dict[str, str] = {}
    if origin_id:
        args["origin"] = origin_id
    else:
        args["origin_name"] = origin_name
    if dest_id:
        args["dest"] = dest_id
    else:
        args["dest_name"] = dest_name
    return args


def _render_selected_route(solution: dict, idx: int):
    metrics = solution.get("metrics", {})
    segments = solution.get("segments") or []
    st.subheader(f"Rota selecionada #{idx + 1}")
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Tempo total", f"{metrics.get('time_total_s', 0)/60:.1f} min")
    col_b.metric("CO₂", f"{metrics.get('emissions_g', 0):.0f} g")
    col_c.metric("Caminhada", f"{metrics.get('walk_m', 0)/1000:.2f} km")
    col_d.metric("Transbordos", int(metrics.get("n_transfers", 0)))

    st.markdown("**Passos da rota**")
    if not segments:
        st.write("Sem segmentos detalhados disponíveis.")
        return
    for i, seg in enumerate(segments, start=1):
        st.write(f"{i}. {_segment_description(seg)}")


def main():
    st.set_page_config(
        page_title="Planeador CIN",
        page_icon="🧭",
        layout="wide",
    )
    st.title("Planeador multimodal CIN")
    st.caption(
        "Explora combinações tempo/CO₂/caminhada geradas pelo algoritmo "
        "multiobjetivo e recebe instruções passo a passo."
    )

    preference = st.radio(
        "Preferência principal",
        options=list(PRESET_WEIGHTS.keys()),
        horizontal=True,
        help="Escolhe o preset inicial dos pesos (podes ajustar os sliders a seguir).",
    )
    preset = PRESET_WEIGHTS[preference]

    if "weight_time_slider" not in st.session_state:
        st.session_state["weight_time_slider"] = float(preset[0])
        st.session_state["weight_co2_slider"] = float(preset[1])
        st.session_state["weight_walk_slider"] = float(preset[2])
        st.session_state["last_preference"] = preference
    elif st.session_state.get("last_preference") != preference:
        st.session_state["weight_time_slider"] = float(preset[0])
        st.session_state["weight_co2_slider"] = float(preset[1])
        st.session_state["weight_walk_slider"] = float(preset[2])
        st.session_state["last_preference"] = preference

    w_col1, w_col2, w_col3 = st.columns(3)
    w_time = w_col1.slider(
        "Peso tempo",
        0.0,
        1.0,
        step=0.05,
        key="weight_time_slider",
        help="Quanto queres penalizar rotas lentas (valor alto favorece trajetos rápidos).",
    )
    w_co2 = w_col2.slider(
        "Peso CO₂",
        0.0,
        1.0,
        step=0.05,
        key="weight_co2_slider",
        help="Quanto queres dar prioridade a emissões baixas (valor alto evita CO₂ elevado).",
    )
    w_walk = w_col3.slider(
        "Peso exercício",
        0.0,
        1.0,
        step=0.05,
        key="weight_walk_slider",
        help="Importância do exercício: alto favorece percursos com mais caminhada.",
    )

    with st.form("planner_form"):
        col1, col2 = st.columns(2)
        origin_input = col1.text_input(
            "Origem",
            help="Aceita nome de paragem (ex.: Trindade), ID (ex.: 803) "
            "ou coordenadas 'lat,lon'.",
        )
        dest_input = col2.text_input(
            "Destino",
            help="Aceita nome de paragem (ex.: Câmara de Gaia), ID ou coordenadas.",
        )

        with st.expander("Opções avançadas"):
            pop_size = st.slider(
                "Tamanho da população",
                20,
                120,
                60,
                step=10,
                help="Mais indivíduos exploram melhor o espaço, mas demoram mais.",
            )
            generations = st.slider(
                "N.º de gerações",
                10,
                80,
                35,
                step=5,
                help="Mais gerações aumentam a qualidade mas levam mais tempo.",
            )
            wmax = st.slider(
                "Limite total a pé (min)",
                0,
                60,
                30,
                step=5,
                help="Limite opcional (0 = sem limite) para o tempo total a pé.",
            )
            tmax = st.slider(
                "Transbordos máximos",
                0,
                6,
                3,
                step=1,
                help="0 = sem limite; valores positivos limitam o número de trocas.",
            )
            walk_policy = st.selectbox(
                "Política de caminhada",
                options=["maximize", "minimize"],
                index=0,
                help="`maximize` prefere mais caminhada, `minimize` prefere menos.",
            )
            include_cost = st.checkbox("Incluir custo como objetivo extra", value=False)

        submitted = st.form_submit_button("Gerar rotas")

    if submitted:
        try:
            args = _prepare_run_args(origin_input, dest_input)
        except ValueError as exc:
            st.error(str(exc))
        else:
            with st.spinner("A calcular rotas ótimas (NSGA-II)..."):
                try:
                    run_example(
                        **args,
                        pop_size=pop_size,
                        generations=generations,
                    wmax_s=wmax * 60,
                    tmax=tmax if tmax > 0 else None,
                    walk_policy=walk_policy,
                    include_cost=include_cost,
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Falha ao gerar rotas: {exc}")
                else:
                    _ensure_graph_cache(reset=True)
                    solutions = _load_pareto_solutions()
                    if not solutions:
                        st.warning("Nenhuma solução válida encontrada.")
                    else:
                        st.session_state["solutions"] = solutions
                        st.session_state["weights"] = (w_time, w_co2, w_walk)
                        st.session_state["preference"] = preference
                        st.session_state["selected_idx"] = None

    solutions = st.session_state.get("solutions")
    if not solutions:
        st.info("Ainda não há rotas para mostrar. Introduz origem/destino e gera primeiras soluções.")
        return

    weights = st.session_state.get("weights", (1 / 3, 1 / 3, 1 / 3))
    preference = st.session_state.get("preference", "Equilíbrio")
    auto_idx = _auto_select_route(solutions, preference, weights)
    if st.session_state.get("selected_idx") is None:
        st.session_state["selected_idx"] = auto_idx

    df = _metrics_to_dataframe(solutions)
    st.markdown("### Pareto: compara opções")
    st.dataframe(
        df.style.format(
            {
                "Tempo total (min)": "{:.1f}",
                "CO₂ (g)": "{:.0f}",
                "Caminhada (m)": "{:.0f}",
                "Esperas (min)": "{:.1f}",
            }
        ),
        use_container_width=True,
    )

    st.markdown("### Seleciona rota")
    btn_cols = st.columns(min(4, len(solutions)))
    for idx, sol in enumerate(solutions):
        col = btn_cols[idx % len(btn_cols)]
        if col.button(f"Rota #{idx + 1}", key=f"select_{idx}"):
            st.session_state["selected_idx"] = idx

    chosen_idx = st.session_state.get("selected_idx") or 0
    chosen_idx = min(chosen_idx, len(solutions) - 1)
    _render_selected_route(solutions[chosen_idx], chosen_idx)
    try:
        rel_path = PARETO_FILE.relative_to(Path(PROJECT_ROOT))
    except ValueError:
        rel_path = PARETO_FILE
    st.caption(f"Dados carregados de `{rel_path}`.")


if __name__ == "__main__":
    main()

