"""Segunda lámina del carrusel: figuras del juego (1080x1350).

Por equipo: mejor salida en la loma (Game Score) y mejor línea de bateo; abajo, los jonrones.
El criterio va impreso en la tarjeta: nada de "el mejor" sin decir por qué.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from bpt import theme
from bpt.data.mlb_box import Figuras
from bpt.data.mlb_stats import FUENTE, Juego
from bpt.viz.result_card import W, H, _panel, fecha_es


def _gs_color(gs: int):
    # 50 = promedio (gris), 30 frío, 80 élite
    return theme.percentile_color((gs - 30) * 2)


def render_figures_card(j: Juego, f: Figuras, out_path: Path,
                        handle: str = theme.HANDLE, temporada: int | None = None) -> Path:
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    temporada = temporada or int(j.fecha[:4])
    v, l = j.visitante, j.local

    fig.text(0.06, 0.955, f"MBP  ·  MLB POSTEMPORADA {temporada}  ·  {j.serie_corto}",
             fontsize=14, color=theme.ACCENT, va="top", family=num)
    fig.text(0.06, 0.915, "FIGURAS", fontsize=56, weight="bold", color=theme.TEXT, va="top")
    fig.text(0.06, 0.838, f"Juego {j.juego_n}  ·  {v.abrev} {v.carreras}, {l.abrev} {l.carreras}",
             fontsize=17, color=theme.MUTED, va="top")

    px, pw = 0.04, 0.92
    panel_h = 0.245
    tops = [0.805, 0.805 - panel_h - 0.02]
    for eq, top in zip([v, l], tops):
        y0 = top - panel_h
        _panel(fig, [px, y0, pw, panel_h])
        color_eq = theme.ACCENT if eq.ganador else theme.MUTED
        fig.text(px + 0.03, top - 0.025, eq.abrev, fontsize=22, weight="bold",
                 color=theme.TEXT, va="top")
        fig.text(px + 0.13, top - 0.031, eq.nombre.upper(), fontsize=10, color=color_eq,
                 va="top", family=num)

        # Pitcheo
        p = f.mejor_pitcheo.get(eq.abrev)
        yp = top - 0.085
        fig.text(px + 0.03, yp + 0.012, "MEJOR SALIDA EN LA LOMA", fontsize=10,
                 color=theme.MUTED, va="center", family=num)
        if p:
            rol = "abridor" if p.abridor else "relevo"
            fig.text(px + 0.03, yp - 0.017, f"{p.nombre}", fontsize=19, color=theme.TEXT,
                     va="center", weight="bold")
            fig.text(px + 0.03, yp - 0.045, f"{p.texto()}  ·  {rol}", fontsize=12,
                     color=theme.MUTED, va="center", family=num)
            # Insignia de Game Score
            bx, bw, bh = px + pw - 0.17, 0.14, 0.065
            fig.add_artist(FancyBboxPatch((bx, yp - 0.05), bw, bh,
                                          boxstyle="round,pad=0,rounding_size=0.012",
                                          transform=fig.transFigure, color=theme.BG))
            fig.text(bx + bw / 2, yp - 0.0035, str(p.game_score), fontsize=28, weight="bold",
                     color=_gs_color(p.game_score), ha="center", va="center", family=num)
            fig.text(bx + bw / 2, yp - 0.039, "GAME SCORE", fontsize=8.5, color=theme.MUTED,
                     ha="center", va="center", family=num)

        # Bateo
        b = f.mejor_bateo.get(eq.abrev)
        yb = y0 + 0.07
        fig.text(px + 0.03, yb + 0.012, "MEJOR LÍNEA AL BATE", fontsize=10,
                 color=theme.MUTED, va="center", family=num)
        if b:
            fig.text(px + 0.03, yb - 0.017, b.nombre, fontsize=19, color=theme.TEXT,
                     va="center", weight="bold")
            fig.text(px + 0.03, yb - 0.045, b.texto(), fontsize=12, color=theme.MUTED,
                     va="center", family=num)
            fig.text(px + pw - 0.03, yb - 0.017, str(b.bases_ganadas), fontsize=19,
                     color=theme.TEXT, va="center", ha="right", family=num, weight="bold")
            fig.text(px + pw - 0.03, yb - 0.045, "bases ganadas", fontsize=10,
                     color=theme.MUTED, va="center", ha="right", family=num)

    # Jonrones
    jy, jh = 0.12, 0.155
    _panel(fig, [px, jy, pw, jh])
    fig.text(px + 0.03, jy + jh - 0.025, "JONRONES", fontsize=11, color=theme.MUTED,
             va="top", family=num)
    if f.jonrones:
        filas = f.jonrones[:6]
        for i, hr in enumerate(filas):
            col, fila = divmod(i, 3)
            x = px + 0.03 + col * 0.45
            y = jy + jh - 0.065 - fila * 0.032
            extra = f"  ×{hr.cantidad}" if hr.cantidad > 1 else ""
            fig.text(x, y, hr.equipo, fontsize=12, color=theme.ACCENT, va="center",
                     family=num, weight="bold")
            fig.text(x + 0.065, y, f"{hr.nombre}{extra}", fontsize=15, color=theme.TEXT,
                     va="center")
        if len(f.jonrones) > 6:
            fig.text(px + pw - 0.03, jy + 0.015, f"y {len(f.jonrones) - 6} más", fontsize=10,
                     color=theme.MUTED, ha="right", va="bottom", family=num)
    else:
        fig.text(px + 0.03, jy + jh / 2 - 0.01, "Juego sin jonrones", fontsize=17,
                 color=theme.MUTED, va="center")

    # Pie
    fig.text(0.06, 0.085, "Game Score: nota de la salida (50 promedio, 70+ dominante).  "
             "Bases ganadas: totales + boletos + pelotazos + robos.", fontsize=9.5,
             color=theme.MUTED, va="center", family=num)
    fig.text(0.06, 0.055, f"{fecha_es(j.fecha)}  ·  {FUENTE}", fontsize=10,
             color=theme.MUTED, va="center", family=num)
    fig.text(0.94, 0.055, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
