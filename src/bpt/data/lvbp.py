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


# columna -> (clave del glosario, mayor_es_mejor). Primero lo tradicional, luego lo nuevo.
BATTER_METRICS = {
    "AVE": ("avg", True),
    "PEB": ("obp", True),
    "SLG": ("slg", True),
    "OPS": ("ops", True),
    "wOBA": ("woba", True),
    "ISO": ("iso", True),
    "BB%": ("bb_pct", True),
    "K%": ("k_pct", False),
    "LD%": ("ld_pct", True),
    "HR/AL": ("hr_pa", True),
}
# OJO: en las tablas de pitcheo de stats.lvbp.com la columna "K%" es en realidad
# el % de strikes (S/NP). El K% real (ponches / bateadores enfrentados) es "K/AL".
PITCHER_METRICS = {
    "EFE": ("era", False),
    "FIP": ("fip", False),
    "WHIP": ("whip", False),
    "AVE": ("avg_opp", False),
    "K/AL": ("k_pct", True),
    "BB/AL": ("bb_pct", False),
    "K/BB": ("k_bb", True),
    "HR/9": ("hr9", False),
    "K%": ("strike_pct", True),
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
    for col, (key, higher_better) in mapping.items():
        if col not in df.columns or pd.isna(row.get(col)):
            continue
        vals = pd.to_numeric(pool[col], errors="coerce").dropna()
        if len(vals) < 5:
            continue
        v = float(row[col])
        share = ((vals < v).sum() + 0.5 * (vals == v).sum()) / len(vals)
        pct = share * 100 if higher_better else (1 - share) * 100
        out.append((key, round(max(1.0, min(100.0, pct)))))
    return out


# --- Estadísticas colectivas por equipo ---------------------------------------

COLLECTIVES_URL = "https://stats.lvbp.com/resources/views/collectives.php"

TEAM_NAMES = {
    "Águilas": "Águilas del Zulia", "Bravos": "Bravos de Margarita",
    "Cardenales": "Cardenales de Lara", "Caribes": "Caribes de Anzoátegui",
    "Leones": "Leones del Caracas", "Navegantes": "Navegantes del Magallanes",
    "Tiburones": "Tiburones de La Guaira", "Tigres": "Tigres de Aragua",
}
PYTH_EXP = 1.83

TEAM_CODES = {"Águilas": "AGU", "Bravos": "BRA", "Cardenales": "CAR", "Caribes": "ANZ",
              "Leones": "LEO", "Navegantes": "MAG", "Tiburones": "TIB", "Tigres": "TIG"}


def parse_collectives(html: str, panes: tuple[str, ...]) -> pd.DataFrame:
    """Une las tablas de los paneles indicados (p. ej. totales + avanzadas) por EQUIPO.

    Se ignoran los paneles de En Casa / Visitante.
    """
    soup = BeautifulSoup(html, "html.parser")
    merged: pd.DataFrame | None = None
    for pane_id in panes:
        pane = soup.find(id=pane_id)
        table = pane.find("table") if pane else None
        if table is None:
            continue
        headers = [th.get_text(strip=True) for th in table.find("thead").find_all(["th", "td"])]
        rows = []
        for tr in table.find("tbody").find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) != len(headers):
                continue
            rec = {"equipo": cells[0]}
            rec.update({h: _to_number(c) for h, c in zip(headers[1:], cells[1:])})
            rows.append(rec)
        df = pd.DataFrame(rows)
        if merged is None:
            merged = df
        else:
            new_cols = [c for c in df.columns if c not in merged.columns]
            merged = merged.merge(df[["equipo"] + new_cols], on="equipo", how="left")
    if merged is None:
        return pd.DataFrame()
    for col in merged.columns.drop("equipo"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    return merged


def build_team_table(bat: pd.DataFrame, pit: pd.DataFrame) -> pd.DataFrame:
    """Une bateo y pitcheo por equipo y calcula métricas derivadas."""
    b = bat.add_prefix("bat_").rename(columns={"bat_equipo": "equipo"})
    p = pit.add_prefix("pit_").rename(columns={"pit_equipo": "equipo"})
    t = b.merge(p, on="equipo", how="inner")
    t["G"] = t["pit_G"]
    t["P"] = t["pit_P"]
    t["pct"] = t["G"] / (t["G"] + t["P"])
    t["CA"] = t["bat_CA"]          # carreras anotadas
    t["CP"] = t["pit_CP"]          # carreras permitidas
    t["dif"] = t["CA"] - t["CP"]
    t["bat_K%"] = t["bat_K"] / t["bat_AL"]
    # En la fuente, 'K%' de pitcheo es Strike%. Se recalcula con bateadores enfrentados (BE).
    t["pit_Strike%"] = t["pit_K%"]
    t["pit_K%"] = t["pit_K"] / t["pit_BE"]
    t["pit_BB%"] = t["pit_BB"] / t["pit_BE"]
    # Récord pitagórico (exponente 1.83): lo que "merecía" según carreras a favor y en contra
    jj = t["G"] + t["P"]
    t["pyth_pct"] = t["CA"] ** PYTH_EXP / (t["CA"] ** PYTH_EXP + t["CP"] ** PYTH_EXP)
    t["pyth_G"] = (t["pyth_pct"] * jj).round().astype(int)
    t["pyth_P"] = (jj - t["pyth_G"]).astype(int)
    t["nombre"] = t["equipo"].map(TEAM_NAMES).fillna(t["equipo"])
    t["codigo"] = t["equipo"].map(TEAM_CODES)
    # Orden por récord y diferencial (no replica los desempates oficiales de la LVBP)
    return t.sort_values(["pct", "dif"], ascending=False).reset_index(drop=True)


def fetch_team_stats(season: int, *, game_type: str = "regular", refresh: bool = False,
                     session: requests.Session | None = None) -> pd.DataFrame:
    """Bateo + pitcheo por equipo de una temporada (con caché)."""
    gt = GAME_TYPES[game_type]
    cache = CACHE_DIR / f"equipos_{season}_{gt}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache)

    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest"})
    html = {}
    for kind in ("hittings", "pitchings"):
        r = s.post(COLLECTIVES_URL, data={"season_id": season, "game_type": gt, "type": kind},
                   timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
        html[kind] = r.text
        time.sleep(0.5)
    bat = parse_collectives(html["hittings"], ("bat-tab-pane", "adv_bat-tab-pane"))
    pit = parse_collectives(html["pitchings"], ("pit-tab-pane", "adv_pit-tab-pane"))
    if bat.empty or pit.empty:
        raise LookupError(f"Sin estadísticas de equipos para {season_label(season)}.")
    t = build_team_table(bat, pit)
    t.insert(0, "temporada", season_label(season))
    cache.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(cache, index=False)
    return t


# columna -> (clave del glosario, formato, mayor_es_mejor)
TEAM_BATTING = [
    ("bat_AVE", "avg", "{:.3f}", True),
    ("bat_PEB", "obp", "{:.3f}", True),
    ("bat_SLG", "slg", "{:.3f}", True),
    ("bat_wOBA", "woba", "{:.3f}", True),
    ("bat_HR", "hr", "{:.0f}", True),
    ("bat_BB%", "bb_pct", "{:.1%}", True),
    ("bat_K%", "k_pct", "{:.1%}", False),
    ("bat_BR", "sb", "{:.0f}", True),
]
TEAM_PITCHING = [
    ("pit_EFE", "era", "{:.2f}", False),
    ("pit_FIP", "fip", "{:.2f}", False),
    ("pit_WHIP", "whip", "{:.2f}", False),
    ("pit_K%", "k_pct", "{:.1%}", True),
    ("pit_BB%", "bb_pct", "{:.1%}", False),
    ("pit_HR/9", "hr9", "{:.2f}", False),
    ("pit_AVE", "avg_opp", "{:.3f}", False),
    ("pit_SV", "sv", "{:.0f}", True),
]


def team_rank(t: pd.DataFrame, col: str, higher_better: bool) -> pd.Series:
    """Puesto 1..N (1 = mejor); empates comparten el mejor puesto."""
    return t[col].rank(ascending=not higher_better, method="min").astype(int)
