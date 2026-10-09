"""Ingesta de estadísticas LVBP desde stats.lvbp.com (datos de TuJonrón).

El sitio carga las tablas vía POST a resources/views/leaders.php, que devuelve
un fragmento HTML con varias tablas (tradicionales, avanzadas, batazos),
paginado de a 30 jugadores. Aquí se recorren todas las páginas, se unen las
tablas por jugador y se guarda un CSV en caché.

Uso responsable: una petición por segundo, caché local y crédito a la fuente.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

LEADERS_URL = "https://stats.lvbp.com/resources/views/leaders.php"
CACHE_DIR = Path("data/raw/lvbp")
USER_AGENT = "beisbol-para-todos/0.1 (analisis sabermetrico; contacto via GitHub nolotov)"
SOURCE_LABEL = "Datos: LVBP / TuJonrón"

TEAMS = {
    "AGU": 692, "BRA": 697, "CAR": 693, "ANZ": 694,
    "LEO": 695, "MAG": 696, "TIB": 698, "TIG": 699,
}
GAME_TYPES = {"regular": "R", "comodin": "D", "semifinal": "L", "final": "W"}
KINDS = {"bateo": "hittings", "pitcheo": "pitchings"}

_HAND = {"*": "Z", "#": "A"}  # zurdo / ambidiestro; sin símbolo = derecho
_PAGE_RE = re.compile(r"loadPage\((\d+)\)")


def season_label(season: int) -> str:
    """2025 -> '2025-26' (la temporada arranca en octubre del año indicado)."""
    return f"{season}-{str(season + 1)[-2:]}"


# --- Parseo -----------------------------------------------------------------

def _to_number(text: str):
    t = text.strip()
    if not t or set(t) <= set(".-"):
        return None
    if re.fullmatch(r"-?\.?-+", t) or "--" in t:
        return None
    try:
        if t.endswith("%"):
            return float(t[:-1]) / 100
        return float(t)
    except ValueError:
        return t


def _parse_player_cell(td) -> dict:
    pos_tag = td.find("span")
    pos = pos_tag.get_text(strip=True) if pos_tag else None
    if pos_tag:
        pos_tag.extract()
    raw = " ".join(td.get_text(" ", strip=True).split())
    hand = "D"
    if raw[:1] in _HAND:
        hand = _HAND[raw[0]]
        raw = raw[1:].strip()
    return {"jugador": raw, "posicion": pos, "mano": hand}


def parse_leaders(html: str) -> pd.DataFrame:
    """Une todas las tablas del fragmento en un DataFrame (una fila por jugador)."""
    soup = BeautifulSoup(html, "html.parser")
    merged: pd.DataFrame | None = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find("thead").find_all(["th", "td"])]
        rows = []
        for tr in table.find("tbody").find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != len(headers):
                continue
            rec = _parse_player_cell(tds[0])
            rec["equipo"] = tds[1].get_text(strip=True)
            for h, td in zip(headers[2:], tds[2:]):
                rec[h] = _to_number(td.get_text())
            rows.append(rec)
        df = pd.DataFrame(rows)
        if df.empty:
            continue
        if merged is None:
            merged = df
        else:
            key = ["jugador", "equipo"]
            new_cols = [c for c in df.columns if c not in merged.columns]
            merged = merged.merge(df[key + new_cols], on=key, how="left")
    if merged is None:
        return pd.DataFrame()
    for col in merged.columns.difference(["jugador", "equipo", "posicion", "mano"]):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    return merged


def last_page(html: str) -> int:
    pages = [int(n) for n in _PAGE_RE.findall(html)]
    return max(pages, default=1)


# --- Descarga ---------------------------------------------------------------

def _payload(season: int, kind: str, page: int, team_id: int,
             game_type: str, split: str, qualified: bool) -> dict:
    return {
        "season_id": season, "team_id": team_id, "game_type": game_type,
        "type": KINDS[kind], "split": split,
        "qualified": "true" if qualified else "false", "page": page,
    }


def fetch_leaders(season: int, kind: str = "bateo", *, team: str | None = None,
                  game_type: str = "regular", split: str = "none",
                  qualified: bool = False, refresh: bool = False,
                  delay: float = 1.0, session: requests.Session | None = None) -> pd.DataFrame:
    """Descarga (o lee de caché) todas las páginas de líderes de una temporada."""
    if kind not in KINDS:
        raise ValueError(f"kind debe ser uno de {list(KINDS)}")
    team_id = TEAMS[team.upper()] if team else 0
    gt = GAME_TYPES[game_type]
    tag = f"{kind}_{season}_{gt}_{team or 'LVBP'}_{split}{'_calif' if qualified else ''}"
    cache = CACHE_DIR / f"{tag}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache)

    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"})

    frames, page, total = [], 1, 1
    while page <= total:
        r = s.post(LEADERS_URL, data=_payload(season, kind, page, team_id, gt, split, qualified),
                   timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
        df = parse_leaders(r.text)
        if df.empty:
            break
        frames.append(df)
        total = max(total, last_page(r.text))
        page += 1
        if page <= total:
            time.sleep(delay)

    if not frames:
        raise LookupError(f"Sin datos para la temporada {season_label(season)} ({kind}).")
    out = (pd.concat(frames, ignore_index=True)
             .drop_duplicates(subset=["jugador", "equipo"])
             .reset_index(drop=True))
    out.insert(0, "temporada", season_label(season))
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cache, index=False)
    return out


# --- Percentiles vs. la liga -------------------------------------------------

def innings(ip) -> float:
    """'45.2' (45 y 2/3) -> 45.667"""
    if ip is None or pd.isna(ip):
        return 0.0
    whole, _, frac = f"{float(ip):.1f}".partition(".")
    return int(whole) + int(frac) / 3


# columna -> (etiqueta, mayor_es_mejor)
BATTER_METRICS = {
    "wOBA": ("wOBA", True),
    "OPS": ("OPS", True),
    "AVE": ("AVG", True),
    "PEB": ("OBP", True),
    "SLG": ("SLG", True),
    "ISO": ("ISO", True),
    "BB%": ("BB%", True),
    "K%": ("K%", False),
    "LD%": ("Line Drive%", True),
    "HR/AL": ("HR por turno", True),
}
# OJO: en las tablas de pitcheo de stats.lvbp.com la columna "K%" es en realidad
# el % de strikes (S/NP). El K% real (ponches / bateadores enfrentados) es "K/AL".
PITCHER_METRICS = {
    "EFE": ("ERA", False),
    "FIP": ("FIP", False),
    "WHIP": ("WHIP", False),
    "K/AL": ("K%", True),
    "BB/AL": ("BB%", False),
    "K%": ("Strike%", True),
    "K/BB": ("K/BB", True),
    "HR/9": ("HR/9", False),
    "AVE": ("AVG permitido", False),
}


def qualified_pool(df: pd.DataFrame, kind: str, min_pa: int = 100,
                   min_ip: float = 20.0) -> pd.DataFrame:
    """Jugadores con muestra suficiente para comparar."""
    if kind == "bateo":
        return df[pd.to_numeric(df["AL"], errors="coerce").fillna(0) >= min_pa]
    ip = df["IP"].map(innings)
    return df[ip >= min_ip]


def percentiles(df: pd.DataFrame, row: pd.Series, kind: str,
                **pool_kwargs) -> list[tuple[str, float]]:
    """Percentil (0-100, 100 = mejor) del jugador en cada métrica vs. el pool calificado."""
    pool = qualified_pool(df, kind, **pool_kwargs)
    mapping = BATTER_METRICS if kind == "bateo" else PITCHER_METRICS
    out = []
    for col, (label, higher_better) in mapping.items():
        if col not in df.columns or pd.isna(row.get(col)):
            continue
        vals = pd.to_numeric(pool[col], errors="coerce").dropna()
        if len(vals) < 5:
            continue
        v = float(row[col])
        share = ((vals < v).sum() + 0.5 * (vals == v).sum()) / len(vals)
        pct = share * 100 if higher_better else (1 - share) * 100
        out.append((label, round(max(1.0, min(100.0, pct)))))
    return out
