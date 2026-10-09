"""Tarjeta de equipo: récord + bateo y pitcheo vs. el resto de la liga (1080x1350)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from bpt import glossary, theme
from bpt.data.lvbp import TEAM_BATTING, TEAM_PITCHING, team_rank

W, H = 10.8, 13.5


def _rank_color(rank: int, n: int):
    # 1 = mejor (rojo élite) ... n = peor (azul); medio gris
    return theme.percentile_color(100 * (n - rank) / max(n - 1, 1))


def _panel(fig, rect, title: str, t: pd.DataFrame, idx: int, specs, fonts, etiquetas: str):
    x0, y0, w, h = rect
    bg = fig.add_axes(rect)
    bg.set_axis_off()
    bg.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.025",
                                transform=bg.transAxes, color=theme.SURFACE))
    fig.text(x0 + 0.03, y0 + h - 0.022, title, fontsize=17, weight="bold",
             color=theme.TEXT, va="top")
    fig.text(x0 + w - 0.03, y0 + h - 0.024, "PUESTO", fontsize=10, color=theme.MUTED,
             va="top", ha="right", family=fonts["number"])

    n = len(t)
    rows = len(specs)
    top, bottom = y0 + h - 0.055, y0 + 0.018
    step = (top - bottom) / rows
    strip_l, strip_w = x0 + 0.40, 0.33

    for i, (col, key, fmt, higher) in enumerate(specs):
        yc = top - step * (i + 0.5)
        vals = t[col].astype(float)
        ranks = team_rank(t, col, higher)
        v, r = vals.iloc[idx], int(ranks.iloc[idx])

        main, secondary = glossary.label(key, etiquetas)
        if secondary:
            fig.text(x0 + 0.03, yc + 0.0015, main, fontsize=14, color=theme.TEXT, va="bottom")
            fig.text(x0 + 0.03, yc - 0.0015, secondary, fontsize=9.5, color=theme.MUTED,
                     va="top", family=fonts["number"])
        else:
            fig.text(x0 + 0.03, yc, main, fontsize=14, color=theme.TEXT, va="center")
        txt = fmt.format(v)
        if fmt == "{:.3f}" and txt.startswith("0."):  # estilo béisbol: .272
            txt = txt[1:]
        fig.text(x0 + 0.37, yc, txt, fontsize=14, color=theme.TEXT, va="center",
                 ha="right", family=fonts["number"], weight="bold")

        ax = fig.add_axes([strip_l, yc - step * 0.35, strip_w, step * 0.7])
        ax.set_axis_off()
        lo, hi = vals.min(), vals.max()
        span = (hi - lo) or 1.0
        norm = ((vals - lo) / span) if higher else ((hi - vals) / span)  # derecha = mejor
        ax.set_xlim(-0.06, 1.06)
        ax.set_ylim(-1, 1)
        ax.plot([0, 1], [0, 0], color=theme.BG, lw=6, solid_capstyle="round", zorder=1)
        mean = ((vals.mean() - lo) / span) if higher else ((hi - vals.mean()) / span)
        ax.plot([mean, mean], [-0.6, 0.6], color=theme.MUTED, lw=1, ls=(0, (2, 2)), zorder=2)
        others = norm.drop(norm.index[idx])
        ax.scatter(others, [0] * len(others), s=70, color=theme.MUTED, alpha=0.55,
                   edgecolor=theme.SURFACE, linewidth=1.5, zorder=3)
        ax.scatter([norm.iloc[idx]], [0], s=330, color=_rank_color(r, n),
                   edgecolor=theme.TEXT, linewidth=2, zorder=4)

        fig.text(x0 + w - 0.03, yc, f"{r}º", fontsize=15, weight="bold", va="center",
                 ha="right", color=theme.TEXT, family=fonts["number"])


def _tile(fig, x, y, w, h, label, value, sub, fonts, value_color=theme.TEXT):
    ax = fig.add_axes([x, y, w, h])
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.06",
                                transform=ax.transAxes, color=theme.SURFACE))
    fig.text(x + 0.02, y + h - 0.014, label, fontsize=10, color=theme.MUTED, va="top",
             family=fonts["number"])
    fig.text(x + 0.02, y + h * 0.48, value, fontsize=25, weight="bold", color=value_color,
             va="center", family=fonts["number"])
    fig.text(x + 0.02, y + 0.012, sub, fontsize=10, color=theme.MUTED, va="bottom")


def render_team_card(t: pd.DataFrame, equipo: str, season_label: str, out_path: Path,
                     handle: str = theme.HANDLE,
                     source: str = "Datos: LVBP / TuJonrón",
                     etiquetas: str = "mixto") -> Path:
    fonts = theme.apply()
    idx = int(t.index[t["equipo"] == equipo][0])
    row = t.iloc[idx]

    fig = plt.figure(figsize=(W, H), dpi=100)

    fig.text(0.06, 0.955, str(row["nombre"]).upper(), fontsize=34, weight="bold",
             color=theme.TEXT, va="top")
    fig.text(0.06, 0.905, f"LVBP {season_label}  ·  TEMPORADA REGULAR  ·  VS. LOS 8 EQUIPOS",
             fontsize=14, color=theme.LVBP, va="top", family=fonts["number"])

    # KPIs
    g, p = int(row["G"]), int(row["P"])
    dif = int(row["dif"])
    pg, pp = int(row["pyth_G"]), int(row["pyth_P"])
    luck = g - pg
    tw, th, ty, gap = 0.28, 0.1, 0.78, 0.03
    _tile(fig, 0.06, ty, tw, th, "RÉCORD", f"{g}-{p}", f"{row['pct']:.3f}".lstrip("0"), fonts)
    _tile(fig, 0.06 + tw + gap, ty, tw, th, "DIF. DE CARRERAS", f"{dif:+d}",
          f"{int(row['CA'])} anotadas · {int(row['CP'])} permitidas", fonts,
          value_color=theme.HOT if dif > 0 else (theme.COLD if dif < 0 else theme.TEXT))
    _tile(fig, 0.06 + 2 * (tw + gap), ty, tw, th, "RÉCORD PITAGÓRICO", f"{pg}-{pp}",
          ("justo lo que merecía" if luck == 0 else
           f"ganó {abs(luck)} {'más' if luck > 0 else 'menos'} de lo esperado"), fonts)

    _panel(fig, [0.04, 0.418, 0.92, 0.345], "BATEO", t, idx, TEAM_BATTING, fonts, etiquetas)
    _panel(fig, [0.04, 0.062, 0.92, 0.345], "PITCHEO", t, idx, TEAM_PITCHING, fonts, etiquetas)

    fig.text(0.06, 0.04, "Cada punto es un equipo  ·  a la derecha = mejor  ·  "
             "línea punteada = promedio de la liga", fontsize=10.5, color=theme.MUTED,
             va="bottom")
    fig.text(0.06, 0.016, source, fontsize=10.5, color=theme.MUTED,
             family=fonts["number"], va="bottom")
    fig.text(0.94, 0.016, handle, fontsize=13, color=theme.LVBP, ha="right",
             weight="bold", va="bottom")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
