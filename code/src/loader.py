# python
import os
import pandas as pd
import math
from typing import Dict

PREFIX_METRO = "METRO"
PREFIX_STCP = "STCP"

# local do root do projeto (assume estrutura project/src)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# caminho por omissão para regras de pontes
DEFAULT_BRIDGES_RULES_PATH = os.path.join(
    PROJECT_ROOT, "data", "bridges", "bridges_pedestrian_rules.txt"
)

# cache em memória das regras carregadas
BRIDGE_RULES: Dict[str, bool] = {}


def load_bridge_rules(path: str | None = None) -> Dict[str, bool]:
    """
    Carrega regras de atravessabilidade pedonal de pontes a partir de um ficheiro
    de texto simples com o formato:

        id;name;walk_allowed;why

    - Linhas começadas por '#' ou vazias são ignoradas.
    - Esperam-se exatamente 4 colunas separadas por ';'.
    - `walk_allowed` deve ser '1' (True) ou '0' (False).

    Devolve um dicionário {bridge_id: walk_allowed}.
    """
    global BRIDGE_RULES

    rules: Dict[str, bool] = {}

    if path is None:
        path = DEFAULT_BRIDGES_RULES_PATH

    if not path or not os.path.exists(path):
        BRIDGE_RULES = rules
        return rules

    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(";")]
                if len(parts) != 4:
                    # linha mal formada → ignora silenciosamente
                    continue
                bridge_id, _name, walk_allowed, _why = parts
                if not bridge_id:
                    continue
                if walk_allowed not in ("0", "1"):
                    continue
                rules[bridge_id] = walk_allowed == "1"
    except OSError:
        # Se houver erro de IO, mantém regras vazias
        rules = {}

    BRIDGE_RULES = rules
    return rules

def _candidate_paths(folder: str, filename: str):
    folder_norm = os.path.normpath(folder)
    if os.path.isabs(folder_norm):
        return [os.path.join(folder_norm, filename)]
    return [
        os.path.join(os.getcwd(), folder_norm, filename),
        os.path.join(PROJECT_ROOT, folder_norm, filename),
        os.path.join(folder_norm, filename),
        os.path.join(folder, filename)
    ]

def find_file(folder: str, filename: str):
    """
    Retorna o primeiro caminho existente para `filename` dentro de `folder`,
    ou None se não existir.
    """
    if folder is None:
        return None
    for p in _candidate_paths(folder, filename):
        p_norm = os.path.normpath(p)
        if os.path.exists(p_norm):
            return p_norm
    return None

def _load_csv_if_exists(folder: str, filename: str, required=False, required_cols=None):
    path = find_file(folder, filename)
    if path is None:
        if required:
            attempts = _candidate_paths(folder, filename)
            raise FileNotFoundError(
                f"GTFS file not found: tried the following paths for {filename}:\n"
                + "\n".join(attempts)
                + f"\nCurrent working directory: {os.getcwd()}"
            )
        return None, None
    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise RuntimeError(f"Failed to read {path}: {e}")
    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            if required:
                raise ValueError(f"{filename} missing required columns: {missing} (file: {path})")
            for col in missing:
                df[col] = pd.NA
    if filename == "fare_attributes.txt" and "price" in df.columns:
        try:
            df["price"] = pd.to_numeric(df["price"], errors="raise").astype(float)
        except Exception as e:
            raise ValueError(f"Failed to convert fare price to float in {path}: {e}")
    return df, path

def to_seconds(hms: str) -> int:
    """
    Converte string HH:MM:SS para segundos inteiros, suportando horas >= 24.
    """
    if hms is None or (isinstance(hms, float) and math.isnan(hms)):
        raise ValueError("Tempo inválido: valor nulo/nan.")
    if not isinstance(hms, str):
        hms = str(hms)
    hms = hms.strip()
    parts = hms.split(":")
    if len(parts) != 3:
        raise ValueError(f"Tempo inválido (esperado HH:MM:SS): {hms}")
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except ValueError:
        raise ValueError(f"Tempo inválido (componentes não inteiros): {hms}")
    if not (0 <= minutes < 60 and 0 <= seconds < 60):
        raise ValueError(f"Tempo inválido (minutos/segundos fora do intervalo 0-59): {hms}")
    if hours < 0:
        raise ValueError(f"Tempo inválido (horas negativas): {hms}")
    return hours * 3600 + minutes * 60 + seconds

def load_gtfs(folder: str, prefix: str):
    """
    Carrega os ficheiros GTFS mais relevantes de `folder`.
    Devolve um dict com chaves para cada ficheiro lido (DataFrames ou None),
    um sub-dict `paths` com os caminhos encontrados, e `prefix`.
    """
    # se não for passado, tenta localizar em `data/Metro` ou `data/STCP` relativos ao projecto
    if folder is None:
        # tenta nome padrão baseado no prefix
        if prefix == PREFIX_METRO:
            folder = os.path.join(PROJECT_ROOT, "data", "Metro")
        else:
            folder = os.path.join(PROJECT_ROOT, "data", "STCP")

    data = {}
    paths = {}

    # ficheiros obrigatórios
    data['stops'], paths['stops'] = _load_csv_if_exists(folder, "stops.txt", required=True,
                                                        required_cols=["stop_id", "stop_lat", "stop_lon"])
    data['stop_times'], paths['stop_times'] = _load_csv_if_exists(
        folder, "stop_times.txt", required=True,
        required_cols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]
    )
    data['trips'], paths['trips'] = _load_csv_if_exists(folder, "trips.txt", required=True,
                                                        required_cols=["trip_id"])

    # ficheiros opcionais
    optional_files = {
        "routes.txt": None,
        "shapes.txt": None,
        "transfers.txt": None,
        "agency.txt": None,
        "calendar.txt": None,
        "calendar_dates.txt": None,
        "frequencies.txt": ["trip_id", "start_time", "end_time", "headway_secs"],
        "fare_attributes.txt": ["fare_id", "price", "currency_type", "transfers", "transfer_duration"],
        "fare_rules.txt": ["fare_id", "route_id", "origin_id", "destination_id", "contains_id"]
    }
    for fname, required_cols in optional_files.items():
        df, p = _load_csv_if_exists(folder, fname, required=False, required_cols=required_cols)
        key = os.path.splitext(fname)[0]  # e.g. routes
        data[key] = df
        paths[key] = p

    return {
        "prefix": prefix,
        "data": data,
        "paths": paths
    }

def load_system(metro_folder: str = None, stcp_folder: str = None):
    metro = load_gtfs(metro_folder, PREFIX_METRO)
    stcp = load_gtfs(stcp_folder, PREFIX_STCP)
    # compatibilidade com código que espera metro['stops'] etc.
    # Mantemos também a estrutura original para facilidade de uso
    def flatten(gtfs):
        out = gtfs["data"].copy()
        out["prefix"] = gtfs["prefix"]
        out["paths"] = gtfs["paths"]
        return out

    return {"metro": flatten(metro), "stcp": flatten(stcp)}
