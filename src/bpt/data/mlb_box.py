"""Box score de un juego (MLB Stats API) y las figuras que salen de él.

Criterios, para que nadie diga "el mejor" a ojo:
- Mejor pitcheo de cada equipo: Game Score v2 de Tom Tango
  = 40 + 2·outs + K − 2·BB − 2·H − 3·C − 6·HR.
- Mejor bateo de cada equipo: "bases ganadas" = bases totales + boletos + pelotazos + robos
  (todas las bases que consiguió por su cuenta); desempata carreras impulsadas, luego
  anotadas, luego menos turnos. La tarjeta muestra ese mismo número, no otro.
- Jonrones: todos los del juego.

El box score de un juego terminado no cambia, así que se cachea sin vencimiento.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bpt.data.mlb_stats import CACHE_DIR, _get

CRITERIO_PITCHEO = "Game Score v2 (Tango): 40 + 2·outs + K − 2·BB − 2·H − 3·C − 6·HR"
CRITERIO_BATEO = ("Bases ganadas = bases totales + boletos + pelotazos + robos; "
                  "desempata impulsadas, luego anotadas, luego menos turnos")


def fetch_boxscore(game_pk: int, refresh: bool = False, cache_dir: Path = CACHE_DIR) -> dict:
    cache = cache_dir / "boxscores" / f"{game_pk}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    data = _get(f"game/{game_pk}/boxscore", {})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# --- Utilidades ---------------------------------------------------------------

def ip_a_outs(ip: str | float | None) -> int:
    """'6.2' (6 entradas y 2 outs) -> 20 outs. En béisbol el decimal son outs, no décimas."""
    if ip in (None, ""):
        return 0
    entero, _, frac = str(ip).partition(".")
    return int(entero or 0) * 3 + int(frac or 0)


def outs_a_ip(outs: int) -> str:
    return f"{outs // 3}.{outs % 3}"


def game_score(outs: int, k: int, bb: int, h: int, c: int, hr: int) -> int:
    return 40 + 2 * outs + k - 2 * bb - 2 * h - 3 * c - 6 * hr


# --- Modelos ------------------------------------------------------------------

@dataclass
class LineaBateo:
    id: int
    nombre: str
    equipo: str
    vb: int
    h: int
    dobles: int
    triples: int
    hr: int
    ci: int
    ca: int
    bb: int
    hbp: int
    k: int
    br: int

    @property
    def bases_totales(self) -> int:
        return self.h + self.dobles + 2 * self.triples + 3 * self.hr

    @property
    def bases_ganadas(self) -> int:
        return self.bases_totales + self.bb + self.hbp + self.br

    @property
    def puntaje(self) -> tuple:
        return (self.bases_ganadas, self.ci, self.ca, -self.vb)

    def texto(self) -> str:
        """Línea estilo pizarra: '3-4, 2B, HR, 3 CI, 2 CA, BB'."""
        partes = [f"{self.h}-{self.vb}"]
        for n, et in [(self.dobles, "2B"), (self.triples, "3B"), (self.hr, "HR")]:
            if n:
                partes.append(et if n == 1 else f"{n} {et}")
        for n, et in [(self.ci, "CI"), (self.ca, "CA"), (self.bb, "BB"), (self.br, "BR")]:
            if n:
                partes.append(f"{n} {et}" if (n > 1 or et in ("CI", "CA")) else et)
        return ", ".join(partes)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(bases_totales=self.bases_totales, bases_ganadas=self.bases_ganadas,
                 linea=self.texto())
        return d


@dataclass
class LineaPitcheo:
    id: int
    nombre: str
    equipo: str
    outs: int
    h: int
    c: int
    cl: int
    bb: int
    k: int
    hr: int
    lanzamientos: int | None
    abridor: bool

    @property
    def ip(self) -> str:
        return outs_a_ip(self.outs)

    @property
    def game_score(self) -> int:
        return game_score(self.outs, self.k, self.bb, self.h, self.c, self.hr)

    def texto(self) -> str:
        """'6.0 IL, 3 H, 1 C, 1 CL, 2 BB, 8 K'."""
        return f"{self.ip} IL, {self.h} H, {self.c} C, {self.cl} CL, {self.bb} BB, {self.k} K"

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(ip=self.ip, game_score=self.game_score, linea=self.texto())
        return d


@dataclass
class Jonron:
    nombre: str
    equipo: str
    cantidad: int


# --- Parseo -------------------------------------------------------------------

def _players(team: dict) -> dict[int, dict]:
    return {p["person"]["id"]: p for p in team.get("players", {}).values()}


def _abrev(team: dict) -> str:
    t = team.get("team", {})
    return t.get("abbreviation") or t.get("teamCode", "?").upper()


def bateo(box: dict, lado: str) -> list[LineaBateo]:
    team = box["teams"][lado]
    ab, players = _abrev(team), _players(team)
    out = []
    for pid in team.get("batters", []):
        p = players.get(pid)
        b = (p or {}).get("stats", {}).get("batting") or {}
        if not b:  # en la lista pero sin turnos ni acción (raro): se omite
            continue
        out.append(LineaBateo(
            id=pid, nombre=p["person"]["fullName"], equipo=ab,
            vb=b.get("atBats", 0), h=b.get("hits", 0), dobles=b.get("doubles", 0),
            triples=b.get("triples", 0), hr=b.get("homeRuns", 0), ci=b.get("rbi", 0),
            ca=b.get("runs", 0), bb=b.get("baseOnBalls", 0),  # incluye intencionales
            hbp=b.get("hitByPitch", 0), k=b.get("strikeOuts", 0),
            br=b.get("stolenBases", 0),
        ))
    return out


def pitcheo(box: dict, lado: str) -> list[LineaPitcheo]:
    team = box["teams"][lado]
    ab, players = _abrev(team), _players(team)
    out = []
    for i, pid in enumerate(team.get("pitchers", [])):
        p = players.get(pid)
        s = (p or {}).get("stats", {}).get("pitching") or {}
        if not s:
            continue
        out.append(LineaPitcheo(
            id=pid, nombre=p["person"]["fullName"], equipo=ab,
            outs=ip_a_outs(s.get("inningsPitched")), h=s.get("hits", 0), c=s.get("runs", 0),
            cl=s.get("earnedRuns", 0), bb=s.get("baseOnBalls", 0), k=s.get("strikeOuts", 0),
            hr=s.get("homeRuns", 0),
            lanzamientos=s.get("numberOfPitches", s.get("pitchesThrown")),
            abridor=(i == 0),
        ))
    return out


@dataclass
class Figuras:
    jonrones: list[Jonron]
    mejor_bateo: dict[str, LineaBateo]       # abrev -> línea
    mejor_pitcheo: dict[str, LineaPitcheo]   # abrev -> línea

    def to_dict(self) -> dict:
        return {
            "jonrones": [asdict(j) for j in self.jonrones],
            "mejor_bateo": {k: v.to_dict() for k, v in self.mejor_bateo.items()},
            "mejor_pitcheo": {k: v.to_dict() for k, v in self.mejor_pitcheo.items()},
            "criterios": {"bateo": CRITERIO_BATEO, "pitcheo": CRITERIO_PITCHEO},
        }


def figuras(box: dict) -> Figuras:
    jonrones, mb, mp = [], {}, {}
    for lado in ("away", "home"):
        bats, pits = bateo(box, lado), pitcheo(box, lado)
        jonrones += [Jonron(b.nombre, b.equipo, b.hr) for b in bats if b.hr]
        if bats:
            mb[bats[0].equipo] = max(bats, key=lambda b: b.puntaje)
        if pits:
            mp[pits[0].equipo] = max(pits, key=lambda p: (p.game_score, p.outs))
    return Figuras(jonrones, mb, mp)
