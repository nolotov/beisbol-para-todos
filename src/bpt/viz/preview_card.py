"""Tarjeta previa de temporada por equipo (1080x1350).

Combina los números de la temporada anterior (calculados) con el contenido editorial
(mánager, qué cambió, la pregunta) de un JSON como content/previas_2026-27.json.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from bpt import theme
from bpt.data.lvbp import team_rank
from bpt.viz.team_card import LOGOS_DIR, _draw_logo

W, H = 10.8, 13.5


def _box(fig, rect, color, radius=0.04):
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle=f"round,pad=0,rounding_size={radius}",
                                transform=ax.transAxes, color=color))
    return ax


def _tile(fig, x, y, w, h, label, value, sub, fonts, value_color=theme.TEXT):
    _box(fig, [x, y, w, h], theme.SURFACE, 0.08)
    fig.text(x + 0.018, y + h - 0.014, label, fontsize=10, color=theme.MUTED, va="top",
             family=fonts["number"])
    fig.text(x + 0.018, y + h * 0.47, value, fontsize=26, weight="bold", color=value_color,
             va="center", family=fonts["number"])
    fig.text(x + 0.018, y + 0.012, sub, fontsize=10, color=theme.MUTED, va="bottom")


def season_summary(t: pd.DataFrame, codigo: str) -> dict:
    """Números de la temporada anterior para un equipo (por código: CAR, MAG...)."""
    idx = int(t.index[t["codigo"] == codigo][0])
    row = t.iloc[idx]
    return {
        "nombre": row["nombre"],
        "G": int(row["G"]), "P": int(row["P"]), "pct": float(row["pct"]),
        "dif": int(row["dif"]),
        "ofensiva_rank": int(team_rank(t, "bat_wOBA", True).iloc[idx]),
        "pitcheo_rank": int(team_rank(t, "pit_EFE", False).iloc[idx]),
        "n": len(t),
    }


def render_preview_card(t: pd.DataFrame, codigo: str, contenido: dict, temporada: str,
                        temporada_anterior: str, out_path: Path,
                        handle: str = theme.HANDLE,
                        source: str = "Datos: LVBP / TuJonrón · Novedades: prensa venezolana",
                        logos_dir: Path | None = LOGOS_DIR) -> Path:
    fonts = theme.apply()
    s = season_summary(t, codigo)
    fig = plt.figure(figsize=(W, H), dpi=100)

    logo = Path(logos_dir) / f"{codigo.lower()}.png" if logos_dir else None
    if logo is not None and logo.exists():
        _draw_logo(fig, logo)

    # Encabezado
    fig.text(0.06, 0.955, f"PREVIA  ·  LVBP {temporada}", fontsize=14, color=theme.LVBP,
             va="top", family=fonts["number"])
    fig.text(0.06, 0.92, str(s["nombre"]).upper(), fontsize=34, weight="bold",
             color=theme.TEXT, va="top")
    fig.text(0.06, 0.862, f"Mánager: {contenido['manager']}", fontsize=17,
             color=theme.MUTED, va="top")

    # Lo que dejó la temporada anterior
    fig.text(0.06, 0.805, f"LO QUE DEJÓ LA {temporada_anterior}", fontsize=13,
             color=theme.MUTED, va="center", family=fonts["number"])
    n = s["n"]
    gap, th, ty = 0.016, 0.105, 0.68
    tw = (0.92 - 3 * gap) / 4
    xs = [0.04 + i * (tw + gap) for i in range(4)]
    _tile(fig, xs[0], ty, tw, th, "RÉCORD", f"{s['G']}-{s['P']}",
          f"{s['pct']:.3f}".lstrip("0"), fonts)
    dif = s["dif"]
    _tile(fig, xs[1], ty, tw, th, "DIFERENCIAL", f"{dif:+d}", "carreras", fonts,
          value_color=theme.HOT if dif > 0 else (theme.COLD if dif < 0 else theme.TEXT))
    _tile(fig, xs[2], ty, tw, th, "OFENSIVA", f"{s['ofensiva_rank']}º",
          f"de {n} · por wOBA", fonts,
          value_color=theme.percentile_color(100 * (n - s["ofensiva_rank"]) / (n - 1)))
    _tile(fig, xs[3], ty, tw, th, "PITCHEO", f"{s['pitcheo_rank']}º",
          f"de {n} · por efectividad", fonts,
          value_color=theme.percentile_color(100 * (n - s["pitcheo_rank"]) / (n - 1)))

    # Qué cambió
    py, ph = 0.36, 0.29
    _box(fig, [0.04, py, 0.92, ph], theme.SURFACE, 0.03)
    fig.text(0.075, py + ph - 0.03, "QUÉ CAMBIÓ", fontsize=17, weight="bold",
             color=theme.TEXT, va="top")
    items = [textwrap.wrap(item, width=60) for item in contenido["cambios"][:3]]
    line_h = 0.029
    top, bottom = py + ph - 0.085, py + 0.03
    used = line_h * sum(len(l) for l in items)
    gap = max(0.015, min(0.045, (top - bottom - used) / max(len(items) - 1, 1)))
    y = top
    for lines in items:
        fig.text(0.075, y, "•", fontsize=18, color=theme.LVBP, va="top", weight="bold")
        for j, line in enumerate(lines):
            fig.text(0.105, y - j * line_h, line, fontsize=18, color=theme.TEXT, va="top")
        y -= line_h * len(lines) + gap

    # La pregunta
    qy, qh = 0.085, 0.245
    _box(fig, [0.04, qy, 0.92, qh], theme.ACCENT, 0.03)
    fig.text(0.075, qy + qh - 0.03, "LA PREGUNTA", fontsize=13, weight="bold",
             color=theme.BG, va="top", family=fonts["number"])
    q_lines = textwrap.wrap(contenido["pregunta"], width=52)
    for j, line in enumerate(q_lines[:4]):
        fig.text(0.075, qy + qh - 0.075 - j * 0.038, line, fontsize=23, weight="bold",
                 color=theme.BG, va="top")

    fig.text(0.06, 0.04, source, fontsize=10.5, color=theme.MUTED, family=fonts["number"],
             va="center")
    fig.text(0.94, 0.04, handle, fontsize=14, color=theme.LVBP, weight="bold", ha="right",
             va="center")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
