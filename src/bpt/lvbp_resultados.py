"""Pipeline de resultados LVBP: un carrusel por jornada.

Lámina 1: marcadores de la jornada (récord y decisiones).
Lámina 2: destacados de la jornada (al bate por bases ganadas, en la loma por Game Score con
3+ entradas) y los jonrones.
Extras (para historias): resultado y figuras de cada juego, en verde LVBP.

Mismo resumen.json que MLB, con "formato": "jornada" para el redactor y Telegram.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bpt import theme
from bpt.data import mlb_box, mlb_stats
from bpt.data.lvbp import season_label
from bpt.viz.figures_card import render_figures_card
from bpt.viz.jornada_card import render_destacados_card, render_jornada_card
from bpt.viz.result_card import render_result_card, titular

TZ_VEN = ZoneInfo("America/Caracas")
# gameType de la API -> fase (los playoffs de la LVBP se nombran distinto según la zafra)
FASES_LVBP = {"R": "Temporada regular", "F": "Comodín", "D": "Postemporada",
              "L": "Semifinal", "W": "Final"}
TOP_BATEO, TOP_PITCHEO = 5, 3
# Para ser "destacado" hay que destacar: sin mínimo, una salida de Game Score 28 saldría
# como lo mejor del día en la loma.
MIN_BASES_GANADAS, MIN_GAME_SCORE = 3, 50
CRITERIOS = {
    "bateo": "Bases ganadas (3 o más) = bases totales + boletos + pelotazos + robos; desempata "
             "impulsadas, luego anotadas, luego menos turnos",
    "pitcheo": "Game Score v2 (Tango) de 50 o más, solo quienes lanzaron 3+ entradas",
}


def ayer_ven(ahora: datetime | None = None) -> str:
    ahora = ahora or datetime.now(TZ_VEN)
    return (ahora.astimezone(TZ_VEN).date() - timedelta(days=1)).isoformat()


def temporada_de(fecha: str) -> int:
    """La zafra arranca en octubre: enero de 2027 sigue siendo la temporada 2026(-27)."""
    d = date.fromisoformat(fecha)
    return d.year if d.month >= 7 else d.year - 1


def destacados(juegos: list[mlb_stats.Juego], boxes: dict[int, dict]) -> dict:
    rival = {}
    for j in juegos:
        rival[(j.game_pk, j.visitante.abrev)] = j.local.abrev
        rival[(j.game_pk, j.local.abrev)] = j.visitante.abrev
    bates, lomas, hrs = [], [], []
    for j in juegos:
        box = boxes.get(j.game_pk)
        if not box:
            continue
        for lado in ("away", "home"):
            for b in mlb_box.bateo(box, lado):
                bates.append((b, j.game_pk))
                if b.hr:
                    hrs.append({"nombre": b.nombre, "equipo": b.equipo, "cantidad": b.hr})
            for p in mlb_box.pitcheo(box, lado):
                lomas.append((p, j.game_pk))

    bates = [x for x in bates if x[0].bases_ganadas >= MIN_BASES_GANADAS]
    bates.sort(key=lambda x: x[0].puntaje, reverse=True)
    largos = [x for x in lomas if x[0].outs >= mlb_box.MIN_OUTS_SALIDA
              and x[0].game_score >= MIN_GAME_SCORE]
    largos.sort(key=lambda x: (x[0].game_score, x[0].outs), reverse=True)

    def fila(linea, pk, valor):
        return {"nombre": linea.nombre, "equipo": linea.equipo,
                "rival": rival.get((pk, linea.equipo), "?"), "linea": linea.texto(),
                "valor": valor, "game_pk": pk}

    return {
        "bateo": [fila(b, pk, b.bases_ganadas) for b, pk in bates[:TOP_BATEO]],
        "pitcheo": [fila(p, pk, p.game_score) for p, pk in largos[:TOP_PITCHEO]],
        "jonrones": hrs,
        "criterios": CRITERIOS,
    }


def generar(fecha: str, salida: Path = Path("output/resultados/lvbp"),
            handle: str = theme.HANDLE, refresh: bool = True, schedule: dict | None = None,
            boxscores: dict[int, dict] | None = None, extras: bool = True) -> dict:
    date.fromisoformat(fecha)
    temp = temporada_de(fecha)
    etiqueta = season_label(temp)
    if schedule is None:
        schedule = mlb_stats.fetch_lvbp_dia(fecha, refresh=refresh)
    del_dia = [j for j in mlb_stats.all_games(schedule) if j.fecha == fecha]
    finales = [j for j in del_dia if j.final]
    pendientes = [{"game_pk": j.game_pk, "partido": f"{j.visitante.abrev} @ {j.local.abrev}",
                   "estado": j.estado} for j in del_dia if not j.final]
    tipos = {j.tipo for j in del_dia}
    fase = FASES_LVBP.get(next(iter(tipos)), "Postemporada") if len(tipos) == 1 else "Temporada"
    cabecera = f"{etiqueta}  ·  {fase.upper()}"
    carpeta = Path(salida) / fecha
    carpeta.mkdir(parents=True, exist_ok=True)

    boxes: dict[int, dict] = {}
    for j in finales:
        try:
            boxes[j.game_pk] = (boxscores or {}).get(j.game_pk) or mlb_box.fetch_boxscore(j.game_pk)
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] Sin box score para {j.game_pk}: {e}", file=sys.stderr)

    tarjetas, extras_png, items = [], [], []
    dest = destacados(finales, boxes)
    with theme.acento(theme.LVBP):
        if finales:
            tarjetas.append(render_jornada_card(finales, fecha, cabecera,
                                                carpeta / "lvbp_1_jornada.png",
                                                pendientes=pendientes, handle=handle).name)
            if dest["bateo"] or dest["pitcheo"]:
                tarjetas.append(render_destacados_card(dest, fecha, cabecera,
                                                       carpeta / "lvbp_2_destacados.png",
                                                       handle=handle).name)
        for j in finales:
            base = f"lvbp_extra_{j.visitante.abrev}-{j.local.abrev}"
            enc = f"MBP  ·  LVBP {cabecera}"
            sub = f"{j.visitante.nombre} en {j.local.nombre}"
            figs = mlb_box.figuras(boxes[j.game_pk]) if j.game_pk in boxes else None
            if extras:
                extras_png.append(render_result_card(
                    j, None, carpeta / f"{base}_resultado.png", handle=handle,
                    encabezado=enc, titulo="RESULTADO", subtitulo=sub,
                    fuente=mlb_stats.FUENTE_LVBP).name)
                if figs:
                    extras_png.append(render_figures_card(
                        j, figs, carpeta / f"{base}_figuras.png", handle=handle,
                        encabezado=enc,
                        subtitulo=f"{j.visitante.abrev} {j.visitante.carreras}, "
                                  f"{j.local.abrev} {j.local.carreras}",
                        fuente=mlb_stats.FUENTE_LVBP).name)
            d = j.to_dict()
            d.update({"titular": titular(j), "ganador": j.ganador.abrev,
                      "perdedor": j.perdedor.abrev,
                      "figuras": figs.to_dict() if figs else None})
            items.append(d)

    resumen = {
        "liga": "LVBP",
        "formato": "jornada",
        "fecha": fecha,
        "temporada": temp,
        "temporada_label": etiqueta,
        "fase": fase,
        "fuente": mlb_stats.FUENTE_LVBP,
        "generado_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "juegos": items,
        "pendientes": pendientes,
        "destacados": dest,
        "tarjetas": tarjetas,
        "extras": extras_png,
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    return resumen
