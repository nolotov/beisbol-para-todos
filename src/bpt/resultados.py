"""Pipeline de resultados MLB: datos del día -> tarjetas + resumen.json.

El resumen.json es la entrada del futuro agente redactor: trae solo cifras verificables
que salen de la API (marcador, pizarra, decisiones, estado de la serie) y nada de opinión.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bpt import theme

from bpt.data import mlb_box, mlb_stats
from bpt.viz.figures_card import render_figures_card
from bpt.viz.result_card import render_result_card, titular

# La fecha oficial de MLB va en hora del Este: corremos "ayer" según Nueva York.
TZ_MLB = ZoneInfo("America/New_York")


def ayer_mlb(ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now(TZ_MLB)
    return (ahora.astimezone(TZ_MLB).date() - timedelta(days=1)).isoformat()


def generar(fecha: str, temporada: int | None = None, tipo: str | None = "L",
            salida: Path = Path("output/resultados/mlb"), handle: str = theme.HANDLE,
            refresh: bool = True, schedule: dict | None = None,
            boxscores: dict[int, dict] | None = None, con_figuras: bool = True) -> dict:
    """Genera las tarjetas de los juegos finalizados en `fecha` y escribe resumen.json.

    `tipo`: L = Series de Campeonato (por defecto), D, F, W o None para toda la postemporada.
    `schedule` / `boxscores` (gamePk -> box score): inyectables para tests/offline;
    si faltan se descargan. Si el box score falla, igual sale la tarjeta del resultado.
    """
    date.fromisoformat(fecha)  # valida formato
    temporada = temporada or int(fecha[:4])
    if schedule is None:
        schedule = mlb_stats.fetch_postseason(temporada, refresh=refresh)

    juegos = mlb_stats.games_on(schedule, fecha, tipo)
    otras_fases = sorted({j.tipo for j in mlb_stats.games_on(schedule, fecha)} - {tipo}) \
        if tipo else []
    series = mlb_stats.estado_series(schedule, hasta=fecha, tipo=tipo)
    carpeta = Path(salida) / fecha
    carpeta.mkdir(parents=True, exist_ok=True)

    items, pendientes = [], []
    for j in juegos:
        if not j.final:
            pendientes.append({"game_pk": j.game_pk, "serie": j.serie_corto,
                               "juego_n": j.juego_n, "estado": j.estado,
                               "partido": f"{j.visitante.abrev} @ {j.local.abrev}"})
            continue
        s = series.get(mlb_stats.clave_serie(j))
        base = f"{j.serie_corto.lower().replace(' ', '-')}_j{j.juego_n}_{j.visitante.abrev}-{j.local.abrev}"
        card = render_result_card(j, s, carpeta / f"{base}_1_resultado.png", handle=handle,
                                  temporada=temporada)
        tarjetas, figs = [card.name], None
        if con_figuras:
            try:
                box = (boxscores or {}).get(j.game_pk) or mlb_box.fetch_boxscore(j.game_pk)
                figs = mlb_box.figuras(box)
                f_card = render_figures_card(j, figs, carpeta / f"{base}_2_figuras.png",
                                             handle=handle, temporada=temporada)
                tarjetas.append(f_card.name)
            except Exception as e:  # noqa: BLE001 - el resultado no debe caer por las figuras
                print(f"[aviso] Sin figuras para {j.game_pk}: {e}", file=sys.stderr)
        d = j.to_dict()
        d.update({
            "titular": titular(j),
            "ganador": j.ganador.abrev,
            "perdedor": j.perdedor.abrev,
            "estado_serie": s.to_dict() if s else None,
            "tarjeta": card.name,
            "tarjetas": tarjetas,
            "figuras": figs.to_dict() if figs else None,
        })
        items.append(d)

    resumen = {
        "liga": "MLB",
        "fecha": fecha,
        "temporada": temporada,
        "fase": mlb_stats.FASES.get(tipo, "Postemporada") if tipo else "Postemporada",
        "fuente": mlb_stats.FUENTE,
        "generado_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "juegos": items,
        "pendientes": pendientes,
        "series": {k: v.to_dict() for k, v in series.items()},
        # Juegos de ese día en otras fases (p. ej. se pidió --fase D en plena SCLN)
        "otras_fases": {t: mlb_stats.FASES.get(t, t) for t in otras_fases},
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return resumen
