# python
import os
import pandas as pd

PREFIX_METRO = "METRO"
PREFIX_STCP = "STCP"

# local do root do projeto (assume estrutura project/src)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

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
            raise ValueError(f"{filename} missing required columns: {missing} (file: {path})")
    return df, path

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
    optional_files = [
        "routes.txt", "shapes.txt", "transfers.txt", "agency.txt",
        "calendar.txt", "calendar_dates.txt", "fare_attributes.txt", "fare_rules.txt"
    ]
    for fname in optional_files:
        df, p = _load_csv_if_exists(folder, fname, required=False)
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
