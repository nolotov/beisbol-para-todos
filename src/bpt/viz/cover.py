"""Portada del carrusel de equipos (1080x1350): récord y diferencial de carreras de los 8."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from bpt import theme
from bpt.viz.team_card import LOGOS_DIR

W, H = 10.8, 13.5


def _logo(fig, path: Path, cx: float, cy: float, size_px: int = 64):
    img = plt.imread(str(path))
    h_px, w_px = img.shape[:2]
    scale = min(1.0, size_px / max(h_px, w_px))
    w, h = w_px * scale / (W * 100), h_px * scale / (H * 100)
    ax = fig.add_axes([cx - w / 2, cy - h / 2, w, h])
    ax.imshow(img, interpolation="lanczos")
    ax.set_axis_off()


def render_season_cover(t: pd.DataFrame, season_label: str, out_path: Path,
                        handle: str = theme.HANDLE,
                        source: str = "Datos: LVBP / TuJonrón",
                        logos_dir: Path | None = LOGOS_DIR) -> Path:
    """`t`: tabla de lvbp.build_team_table / fetch_team_stats (ordenada por récord)."""
    fonts = theme.apply()
    t = t.sort_values(["pct", "dif"], ascending=False).reset_index(drop=True)
    fig = plt.figure(figsize=(W, H), dpi=100)

    # Encabezado
    fig.text(0.06, 0.955, f"MBP  ·  LVBP {season_label}  ·  TEMPORADA REGULAR", fontsize=14,
             color=theme.LVBP, va="top", family=fonts["number"])
    fig.text(0.06, 0.915, "ASÍ TERMINARON", fontsize=52, weight="bold", color=theme.TEXT,
             va="top")
    fig.text(0.06, 0.845, "LOS 8 EQUIPOS", fontsize=52, weight="bold", color=theme.ACCENT,
             va="top")
    fig.text(0.06, 0.772, "Récord y diferencial de carreras. En cada tarjeta, su bateo y su "
             "pitcheo contra toda la liga.", fontsize=14, color=theme.MUTED, va="top")

    # Panel
    px, py, pw, ph = 0.04, 0.115, 0.92, 0.625
    bg = fig.add_axes([px, py, pw, ph])
    bg.set_axis_off()
    bg.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.025",
                                transform=bg.transAxes, color=theme.SURFACE))
    head_y = py + ph - 0.03
    fig.text(px + 0.155, head_y, "EQUIPO", fontsize=10, color=theme.MUTED, va="center",
             family=fonts["number"])
    fig.text(px + 0.47, head_y, "RÉCORD", fontsize=10, color=theme.MUTED, va="center",
             ha="right", family=fonts["number"])
    fig.text(px + 0.725, head_y, "DIF. DE CARRERAS", fontsize=10, color=theme.MUTED,
             va="center", ha="center", family=fonts["number"])

    n = len(t)
    top, bottom = head_y - 0.025, py + 0.02
    step = (top - bottom) / n
    lim = max(abs(t["dif"]).max(), 1) * 1.15
    bar_l, bar_w = px + 0.53, 0.39
    center = bar_l + bar_w / 2

    # eje del cero
    zero = fig.add_axes([center - 0.0005, bottom, 0.001, top - bottom])
    zero.set_axis_off()
    zero.add_patch(plt.Rectangle((0, 0), 1, 1, transform=zero.transAxes, color=theme.MUTED,
                                 alpha=0.5))

    for i, row in t.iterrows():
        yc = top - step * (i + 0.5)
        code = str(row.get("codigo", "")).lower()
        logo = Path(logos_dir) / f"{code}.png" if logos_dir else None
        if logo is not None and logo.exists():
            _logo(fig, logo, px + 0.08, yc)
        else:
            fig.text(px + 0.08, yc, code.upper(), fontsize=13, weight="bold", ha="center",
                     va="center", color=theme.TEXT, family=fonts["number"])
        fig.text(px + 0.155, yc, str(row["equipo"]).upper(), fontsize=19, weight="bold",
                 color=theme.TEXT, va="center")
        fig.text(px + 0.47, yc, f"{int(row['G'])}-{int(row['P'])}", fontsize=19,
                 color=theme.TEXT, va="center", ha="right", family=fonts["number"],
                 weight="bold")

        dif = float(row["dif"])
        ax = fig.add_axes([bar_l, yc - step * 0.22, bar_w, step * 0.44])
        ax.set_axis_off()
        ax.set_xlim(-lim, lim)
        ax.set_ylim(0, 1)
        color = theme.HOT if dif > 0 else (theme.COLD if dif < 0 else theme.MUTED)
        ax.barh(0.5, dif, height=0.8, color=color, left=0)
        label = f"{int(dif):+d}" if dif else "0"
        ha = "left" if dif >= 0 else "right"
        off = lim * 0.03 * (1 if dif >= 0 else -1)
        ax.text(dif + off, 0.5, label, ha=ha, va="center", fontsize=14, weight="bold",
                color=theme.TEXT, family=fonts["number"])

    # Gancho
    lucky = t.assign(luck=t["G"] - t["pyth_G"]).sort_values("luck", ascending=False).iloc[0]
    if lucky["luck"] > 0:
        hook = (f"¿Quién ganó más de lo que merecía? Pista: {int(lucky['G'])}-{int(lucky['P'])} "
                f"con {int(lucky['dif']):+d} de diferencial.")
        fig.text(0.06, 0.082, hook, fontsize=14, color=theme.ACCENT, va="center")

    fig.text(0.06, 0.035, source, fontsize=11, color=theme.MUTED, family=fonts["number"],
             va="center")
    fig.text(0.94, 0.035, "DESLIZA  →", fontsize=16, weight="bold", color=theme.TEXT,
             ha="right", va="center")
    fig.text(0.94, 0.082, handle, fontsize=14, color=theme.LVBP, weight="bold", ha="right",
             va="center")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
