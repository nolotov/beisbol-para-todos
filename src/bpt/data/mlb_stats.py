"""Resultados de MLB desde la MLB Stats API (statsapi.mlb.com), empezando por la postemporada.

Una sola llamada al calendario de la postemporada trae todos los juegos con pizarra
(linescore), decisiones de pitcheo y equipos. Con eso armamos:
- `Juego`: el resultado de un partido, listo para tarjeta y para el resumen.json.
- `estado_series`: cómo va cada serie (contamos nosotros las victorias a partir de los
  juegos finalizados, en lugar de depender del texto en inglés de la API).

La respuesta cruda se cachea en data/raw/mlb/. Fuente a citar: "MLB Stats API".
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path("data/raw/mlb")
FUENTE = "Datos: MLB Stats API"

# gameType de la API -> fase
FASES = {
    "F": "Comodín",
    "D": "Serie Divisional",
    "L": "Serie de Campeonato",
    "W": "Serie Mundial",
}

# Nombre largo de cada serie en español (clave: seriesDescription de la API)
SERIES_ES = {
    "AL Championship Series": "Serie de Campeonato de la Liga Americana",
    "NL Championship Series": "Serie de Campeonato de la Liga Nacional",
    "AL Division Series": "Serie Divisional de la Liga Americana",
    "NL Division Series": "Serie Divisional de la Liga Nacional",
    "AL Wild Card Series": "Serie del Comodín de la Liga Americana",
    "NL Wild Card Series": "Serie del Comodín de la Liga Nacional",
    "World Series": "Serie Mundial",
}
SERIES_CORTO = {
    "AL Championship Series": "SCLA",
    "NL Championship Series": "SCLN",
    "AL Division Series": "SDLA",
    "NL Division Series": "SDLN",
    "AL Wild Card Series": "Comodín LA",
    "NL Wild Card Series": "Comodín LN",
    "World Series": "Serie Mundial",
}

HYDRATE = "linescore,decisions,team"


@dataclass
class Equipo:
    id: int
    nombre: str
    abrev: str
    carreras: int | None
    hits: int | None
    errores: int | None
    ganador: bool


@dataclass
class Juego:
    game_pk: int
    fecha: str                 # fecha oficial (YYYY-MM-DD)
    inicio_utc: str
    tipo: str                  # gameType: F, D, L, W
    serie: str                 # seriesDescription de la API (clave estable)
    serie_es: str
    serie_corto: str
    juego_n: int
    juegos_en_serie: int
    estado: str                # "Final", "Programado", "En juego", "Pospuesto", "Suspendido"
    estadio: str
    visitante: Equipo
    local: Equipo
    entradas: list[tuple[int, int | None, int | None]] = field(default_factory=list)
    ganador_pitcher: str | None = None
    perdedor_pitcher: str | None = None
    salvado_pitcher: str | None = None
    si_es_necesario: bool = False

    @property
    def final(self) -> bool:
        return self.estado == "Final"

    @property
    def ganador(self) -> Equipo | None:
        if not self.final:
            return None
        return self.local if self.local.ganador else self.visitante

    @property
    def perdedor(self) -> Equipo | None:
        g = self.ganador
        if g is None:
            return None
        return self.visitante if g is self.local else self.local

    @property
    def extra_innings(self) -> int:
        return max(0, len(self.entradas) - 9)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["final"] = self.final
        d["extra_innings"] = self.extra_innings
        return d


# --- Descarga -----------------------------------------------------------------

def _get(path: str, params: dict, retries: int = 3) -> dict:
    url = f"{BASE}/{path}"
    for intento in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30,
                             headers={"User-Agent": "beisbol-para-todos (@mbp.deportes)"})
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if intento == retries - 1:
                raise
            time.sleep(2 * (intento + 1))
    raise RuntimeError("inalcanzable")


def fetch_postseason(season: int, refresh: bool = False,
                     cache_dir: Path = CACHE_DIR) -> dict:
    """Calendario completo de la postemporada (todas las fases) con pizarras y decisiones.

    Con `refresh=False` usa la caché si existe; para resultados del día conviene `refresh=True`
    (los juegos cambian de estado).
    """
    cache = cache_dir / f"postemporada_{season}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    data = _get("schedule", {
        "sportId": 1,
        "season": season,
        "gameType": ",".join(FASES),
        "hydrate": HYDRATE,
    })
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


# --- Parseo -------------------------------------------------------------------

_ESTADOS = {
    "Final": "Final",
    "Live": "En juego",
    "Preview": "Programado",
}


def _estado(status: dict) -> str:
    detalle = status.get("detailedState", "")
    if detalle.startswith("Postponed"):
        return "Pospuesto"
    if detalle.startswith("Suspended"):
        return "Suspendido"
    if detalle.startswith("Cancelled"):
        return "Cancelado"
    return _ESTADOS.get(status.get("abstractGameState", ""), detalle or "Desconocido")


def _equipo(side: dict, line: dict) -> Equipo:
    t = side.get("team", {})
    return Equipo(
        id=t.get("id"),
        nombre=t.get("name", "?"),
        abrev=t.get("abbreviation") or t.get("teamCode", "?").upper(),
        carreras=line.get("runs", side.get("score")),
        hits=line.get("hits"),
        errores=line.get("errors"),
        ganador=bool(side.get("isWinner", False)),
    )


def _nombre(d: dict | None) -> str | None:
    return (d or {}).get("fullName")


def parse_game(g: dict) -> Juego:
    ls = g.get("linescore", {}) or {}
    lt = ls.get("teams", {}) or {}
    dec = g.get("decisions", {}) or {}
    serie = g.get("seriesDescription", "")
    entradas = [
        (inn["num"], inn.get("away", {}).get("runs"), inn.get("home", {}).get("runs"))
        for inn in ls.get("innings", [])
    ]
    return Juego(
        game_pk=g["gamePk"],
        fecha=g.get("officialDate", g.get("gameDate", "")[:10]),
        inicio_utc=g.get("gameDate", ""),
        tipo=g.get("gameType", ""),
        serie=serie,
        serie_es=SERIES_ES.get(serie, serie),
        serie_corto=SERIES_CORTO.get(serie, serie),
        juego_n=int(g.get("seriesGameNumber") or 0),
        juegos_en_serie=int(g.get("gamesInSeries") or 0),
        estado=_estado(g.get("status", {})),
        estadio=g.get("venue", {}).get("name", ""),
        visitante=_equipo(g["teams"]["away"], lt.get("away", {})),
        local=_equipo(g["teams"]["home"], lt.get("home", {})),
        entradas=entradas,
        ganador_pitcher=_nombre(dec.get("winner")),
        perdedor_pitcher=_nombre(dec.get("loser")),
        salvado_pitcher=_nombre(dec.get("save")),
        si_es_necesario=g.get("ifNecessary") == "Y",
    )


def all_games(schedule: dict) -> list[Juego]:
    """Todos los juegos, deduplicados por gamePk (un juego pospuesto aparece en dos fechas:
    nos quedamos con la última aparición)."""
    by_pk: dict[int, Juego] = {}
    for d in schedule.get("dates", []):
        for g in d.get("games", []):
            by_pk[g["gamePk"]] = parse_game(g)
    return sorted(by_pk.values(), key=lambda j: (j.inicio_utc, j.game_pk))


def games_on(schedule: dict, fecha: str, tipo: str | None = None) -> list[Juego]:
    return [j for j in all_games(schedule)
            if j.fecha == fecha and (tipo is None or j.tipo == tipo)]


# --- Estado de la serie -------------------------------------------------------

@dataclass
class EstadoSerie:
    serie: str
    serie_es: str
    serie_corto: str
    equipos: dict[str, int]        # abrev -> victorias
    para_ganar: int
    lider: str | None
    ganador: str | None
    texto: str                     # "LAD lidera 2-1", "Empatada 1-1", "LAD gana 4-2"

    def to_dict(self) -> dict:
        return asdict(self)


def _victorias_para_ganar(juegos: list[Juego]) -> int:
    n = max((j.juegos_en_serie for j in juegos), default=7) or 7
    return n // 2 + 1


def estado_series(schedule: dict, hasta: str | None = None,
                  tipo: str | None = None) -> dict[str, EstadoSerie]:
    """Estado de cada serie contando solo juegos finalizados con fecha <= `hasta`."""
    juegos = all_games(schedule)
    por_serie: dict[str, list[Juego]] = {}
    for j in juegos:
        if tipo and j.tipo != tipo:
            continue
        por_serie.setdefault(j.serie, []).append(j)

    out: dict[str, EstadoSerie] = {}
    for serie, js in por_serie.items():
        abrevs = sorted({j.local.abrev for j in js} | {j.visitante.abrev for j in js})
        wins = {a: 0 for a in abrevs}
        for j in js:
            if j.final and (hasta is None or j.fecha <= hasta):
                wins[j.ganador.abrev] += 1
        meta = _victorias_para_ganar(js)
        orden = sorted(wins.items(), key=lambda kv: -kv[1])
        (a1, w1), (a2, w2) = orden[0], orden[1] if len(orden) > 1 else ("?", 0)
        ganador = a1 if w1 >= meta else None
        if ganador:
            texto = f"{a1} gana la serie {w1}-{w2}"
        elif w1 == w2:
            texto = f"Serie empatada {w1}-{w2}"
        else:
            texto = f"{a1} lidera {w1}-{w2}"
        j0 = js[0]
        out[serie] = EstadoSerie(serie, j0.serie_es, j0.serie_corto, wins, meta,
                                 a1 if w1 > w2 else None, ganador, texto)
    return out
