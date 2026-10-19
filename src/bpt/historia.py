"""Historia diaria de Instagram: los juegos de hoy de la MLB y la LVBP.

Una sola lámina vertical (1080x1920) con la cartelera del día en hora de Venezuela: hora,
quién juega, cómo va la serie (postemporada MLB) o el récord (LVBP) y los abridores
probables. Si ese día no hay juegos de ninguna de las dos ligas no se genera nada.

Sale a la carpeta `output/historia/<fecha>/` con su resumen.json (formato "historia"), que es
lo que lee el envío a Telegram y el botón de publicar.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bpt import theme
from bpt.data import mlb_stats as M

TZ_VEN = ZoneInfo("America/Caracas")
SALIDA = Path("output/historia")
ARCHIVO = "historia.png"
TIPOS_MLB = "R,F,D,L,W"          # temporada regular y postemporada (sin spring training)
HYDRATE = "team,linescore,probablePitcher"
FASES_LVBP = {"R": "Temporada regular", "F": "Comodín", "D": "Postemporada",
              "L": "Semifinal", "W": "Final"}
FASES_MLB = {"R": "Temporada regular", "F": "Comodín", "D": "Serie Divisional",
             "L": "Serie de Campeonato", "W": "Serie Mundial"}


def hoy_ven(ahora: datetime | None = None) -> str:
    return (ahora or datetime.now(TZ_VEN)).astimezone(TZ_VEN).date().isoformat()


@dataclass
class JuegoHoy:
    liga: str                    # "MLB" o "LVBP"
    game_pk: int
    tipo: str                    # gameType: R, F, D, L, W
    inicio_utc: str
    hora: str                    # "7:08 p. m." en hora de Venezuela, o "Por definir"
    estado: str                  # "Programado", "En juego", "Final", "Pospuesto"...
    visitante: str               # siglas
    local: str
    visitante_nombre: str
    local_nombre: str
    detalle: str                 # "Serie Mundial · Juego 3 · LAD lidera 2-1" / "12-8 vs. 10-10"
    abridores: str | None        # "Yamamoto vs. Gausman" (None si no se anunciaron)

    def to_dict(self) -> dict:
        return asdict(self)


def hora_ven(inicio_utc: str) -> str:
    """'2026-10-19T23:08:00Z' -> '7:08 p. m.' (hora de Venezuela)."""
    t = datetime.fromisoformat(inicio_utc.replace("Z", "+00:00")).astimezone(TZ_VEN)
    sufijo = "a. m." if t.hour < 12 else "p. m."
    return f"{(t.hour % 12) or 12}:{t.minute:02d} {sufijo}"


def _apellido(lado: dict) -> str | None:
    nombre = (lado.get("probablePitcher") or {}).get("fullName")
    if not nombre:
        return None
    partes = nombre.split()
    return " ".join(partes[1:]) if len(partes) > 1 else nombre


def _abridores(g: dict) -> str | None:
    v, lo = _apellido(g["teams"]["away"]), _apellido(g["teams"]["home"])
    if not v and not lo:
        return None
    return f"{v or 'Por anunciar'} vs. {lo or 'Por anunciar'}"


def _juego(g: dict, liga: str, series: dict[str, M.EstadoSerie]) -> JuegoHoy:
    j = M.parse_game(g)
    tbd = bool((g.get("status") or {}).get("startTimeTBD"))
    if liga == "MLB" and j.tipo != "R":
        partes = [j.serie_es or FASES_MLB.get(j.tipo, "")]
        if j.juego_n:
            partes.append(f"Juego {j.juego_n}")
        est = series.get(M.clave_serie(j))
        if est and sum(est.equipos.values()):
            partes.append(est.texto)
        detalle = " · ".join(p for p in partes if p)
    else:
        rv, rl = j.visitante.record, j.local.record
        detalle = f"Récords: {rv} vs. {rl}" if rv and rl else FASES_LVBP.get(j.tipo, "")
    return JuegoHoy(
        liga=liga, game_pk=j.game_pk, tipo=j.tipo, inicio_utc=j.inicio_utc,
        hora="Por definir" if tbd or not j.inicio_utc else hora_ven(j.inicio_utc),
        estado=j.estado, visitante=j.visitante.abrev, local=j.local.abrev,
        visitante_nombre=M.nombre_es(j.visitante.nombre),
        local_nombre=M.nombre_es(j.local.nombre),
        detalle=detalle, abridores=_abridores(g))


def _del_dia(schedule: dict, fecha: str) -> list[dict]:
    """Juegos crudos de la fecha (sin repetir gamePk: un pospuesto sale en dos fechas)."""
    vistos: dict[int, dict] = {}
    for d in schedule.get("dates", []):
        for g in d.get("games", []):
            if g.get("officialDate", d.get("date")) == fecha:
                vistos[g["gamePk"]] = g
    return sorted(vistos.values(), key=lambda g: (g.get("gameDate", ""), g["gamePk"]))


def juegos_de_hoy(fecha: str, mlb: dict, lvbp: dict,
                  postemporada: dict | None = None) -> dict[str, list[JuegoHoy]]:
    """Cartelera por liga a partir de los calendarios ya descargados (sin red)."""
    ayer = (date.fromisoformat(fecha) - timedelta(days=1)).isoformat()
    series = M.estado_series(postemporada, hasta=ayer) if postemporada else {}
    salida = {
        "MLB": [_juego(g, "MLB", series) for g in _del_dia(mlb, fecha)],
        "LVBP": [_juego(g, "LVBP", series) for g in _del_dia(lvbp, fecha)],
    }
    # Cancelados fuera: no hay nada que anunciar
    return {k: [j for j in v if j.estado != "Cancelado"] for k, v in salida.items()}


def fase(juegos: list[JuegoHoy], liga: str) -> str:
    """Rótulo de la sección: "Postemporada", "Temporada regular", "Semifinal"..."""
    tipos = {j.tipo for j in juegos}
    if liga == "MLB" and tipos and "R" not in tipos:
        return "Postemporada"
    if len(tipos) == 1:
        return (FASES_MLB if liga == "MLB" else FASES_LVBP).get(next(iter(tipos)), "")
    return ""


def descargar(fecha: str) -> tuple[dict, dict, dict | None]:
    """Calendarios de hoy (MLB y LVBP) y, si hay postemporada MLB, la postemporada completa
    para saber cómo van las series."""
    mlb = M._get("schedule", {"sportId": 1, "date": fecha, "gameType": TIPOS_MLB,
                              "hydrate": HYDRATE})
    lvbp = M._get("schedule", {"sportId": M.WINTER_SPORT_ID, "leagueId": M.LVBP_LEAGUE_ID,
                               "date": fecha, "hydrate": HYDRATE})
    post = None
    if any(g.get("gameType") != "R" for g in _del_dia(mlb, fecha)):
        post = M.fetch_postseason(int(fecha[:4]), refresh=True)
    return mlb, lvbp, post


def generar(fecha: str, salida: Path = SALIDA, handle: str = theme.HANDLE,
            calendarios: tuple[dict, dict, dict | None] | None = None) -> dict:
    """Arma la historia del día. Sin juegos no dibuja nada (resumen con "tarjetas": [])."""
    mlb, lvbp, post = calendarios or descargar(fecha)
    por_liga = juegos_de_hoy(fecha, mlb, lvbp, post)
    carpeta = Path(salida) / fecha
    carpeta.mkdir(parents=True, exist_ok=True)
    fases = {liga: fase(js, liga) for liga, js in por_liga.items()}
    total = sum(len(v) for v in por_liga.values())
    tarjetas = []
    if total:
        from bpt.viz.historia_card import render_historia
        render_historia(por_liga, fases, fecha, carpeta / ARCHIVO, handle=handle)
        tarjetas = [ARCHIVO]
    resumen = {
        "formato": "historia", "fecha": fecha, "total": total, "tarjetas": tarjetas,
        "ligas": {liga: {"fase": fases[liga], "juegos": [j.to_dict() for j in js]}
                  for liga, js in por_liga.items() if js},
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    return resumen


def titular(resumen: dict) -> str:
    """'Juegos de hoy · lunes 19 de octubre' (para Telegram y el botón)."""
    return f"Juegos de hoy · {fecha_larga(resumen['fecha'])}"


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"
