"""Extracción de percentiles de Baseball Savant (vía pybaseball) con caché local."""
from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

CACHE_DIR = Path("data/raw/savant")

# Columna de Savant -> clave del glosario (bpt.glossary). Solo se grafican las que vengan.
PITCHER_METRICS = {
    "xera": "xera",
    "xwoba": "xwoba_opp",
    "fb_velocity": "fb_velo",
    "fb_spin": "fb_spin",
    "k_percent": "k_pct",
    "bb_percent": "bb_pct",
    "whiff_percent": "whiff_pct",
    "chase_percent": "chase_pct",
    "exit_velocity": "ev_opp",
    "hard_hit_percent": "hardhit_opp",
    "brl_percent": "barrel_opp",
}

BATTER_METRICS = {
    "xba": "xba",
    "xslg": "xslg",
    "xwoba": "xwoba",
    "exit_velocity": "ev",
    "hard_hit_percent": "hardhit_pct",
    "brl_percent": "barrel_pct",
    "bat_speed": "bat_speed",
    "k_percent": "k_pct",
    "bb_percent": "bb_pct",
    "whiff_percent": "whiff_pct",
    "chase_percent": "chase_pct",
    "sprint_speed": "sprint_speed",
}


def _normalize(name: str) -> str:
    """'Acuña Jr., Ronald' y 'ronald acuna jr' -> misma clave."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first} {last}"
    return " ".join(name.lower().replace(".", "").split())


def display_name(savant_name: str) -> str:
    if "," in savant_name:
        last, first = savant_name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return savant_name


def load_percentiles(kind: str, year: int, refresh: bool = False,
                     source_csv: Path | None = None) -> pd.DataFrame:
    """Devuelve la tabla de percentiles. `kind` = 'pitcher' | 'batter'.

    Usa caché en data/raw/savant/. `source_csv` permite trabajar offline.
    """
    if kind not in {"pitcher", "batter"}:
        raise ValueError("kind debe ser 'pitcher' o 'batter'")
    if source_csv is not None:
        return pd.read_csv(source_csv)

    cache = CACHE_DIR / f"percentiles_{kind}_{year}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache)

    from pybaseball import (statcast_batter_percentile_ranks,
                            statcast_pitcher_percentile_ranks)

    fetch = statcast_pitcher_percentile_ranks if kind == "pitcher" else statcast_batter_percentile_ranks
    df = fetch(year)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def find_player(df: pd.DataFrame, query: str) -> pd.Series:
    key = _normalize(query)
    names = df["player_name"].map(_normalize)
    exact = df[names == key]
    if len(exact) == 1:
        return exact.iloc[0]
    partial = df[names.str.contains(key, regex=False)]
    if len(partial) == 1:
        return partial.iloc[0]
    if partial.empty:
        raise LookupError(f"No encontré a '{query}' en la tabla de percentiles.")
    options = ", ".join(display_name(n) for n in partial["player_name"].head(8))
    raise LookupError(f"'{query}' es ambiguo. Opciones: {options}")


def player_metrics(row: pd.Series, kind: str) -> list[tuple[str, float]]:
    mapping = PITCHER_METRICS if kind == "pitcher" else BATTER_METRICS
    out = []
    for col, key in mapping.items():
        if col in row.index and pd.notna(row[col]):
            out.append((key, float(row[col])))
    return out
