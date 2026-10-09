"""Tarjeta de percentiles (formato vertical 1080x1350 para IG/X)."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import blended_transform_factory

from bpt import glossary, theme


def render_card(player: str, kind: str, year: int,
                metrics: list[tuple[str, float]], out_path: Path,
                handle: str = theme.HANDLE,
                source: str = "Datos: Baseball Savant",
                subtitle: str | None = None,
                accent: str = theme.ACCENT,
                etiquetas: str = "mixto") -> Path:
    """`metrics`: lista de (clave del glosario, percentil 0-100)."""
    if not metrics:
        raise ValueError("No hay métricas para graficar.")
    fonts = theme.apply()

    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)  # 1080x1350 px

    # Encabezado
    fig.text(0.06, 0.94, player.upper(), fontsize=40, weight="bold",
             color=theme.TEXT, va="top")
    if subtitle is None:
        role = "LANZADOR" if kind == "pitcher" else "BATEADOR"
        subtitle = f"{role}  ·  MLB {year}  ·  PERCENTILES STATCAST"
    fig.text(0.06, 0.885, subtitle,
             fontsize=15, color=accent, va="top", family=fonts["number"])

    # Panel
    panel = fig.add_axes([0.04, 0.09, 0.92, 0.76])
    panel.set_axis_off()
    panel.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.02",
                                   transform=panel.transAxes, color=theme.SURFACE, zorder=0))

    ax = fig.add_axes([0.30, 0.12, 0.62, 0.70])
    labels = [glossary.label(m[0], etiquetas) for m in metrics][::-1]
    values = [m[1] for m in metrics][::-1]
    y = range(len(values))

    ax.barh(y, [100] * len(values), color=theme.BG, height=0.5, zorder=1)
    ax.barh(y, values, color=[theme.percentile_color(v) for v in values],
            height=0.5, zorder=2)
    ax.axvline(50, color=theme.MUTED, lw=1, ls=(0, (2, 3)), zorder=3)

    for yi, v in zip(y, values):
        ax.scatter(v, yi, s=900, color=theme.percentile_color(v),
                   edgecolor=theme.TEXT, linewidth=2, zorder=4)
        ax.text(v, yi, f"{v:.0f}", ha="center", va="center", fontsize=13,
                weight="bold", color=theme.TEXT, zorder=5, family=fonts["number"])

    ax.set_yticks([])
    tr = blended_transform_factory(ax.transAxes, ax.transData)
    for yi, (main, secondary) in zip(y, labels):
        if secondary:
            ax.text(-0.03, yi + 0.05, main, transform=tr, ha="right", va="bottom",
                    fontsize=15, color=theme.TEXT)
            ax.text(-0.03, yi - 0.05, secondary, transform=tr, ha="right", va="top",
                    fontsize=11, color=theme.MUTED, family=fonts["number"])
        else:
            ax.text(-0.03, yi, main, transform=tr, ha="right", va="center",
                    fontsize=16, color=theme.TEXT)
    ax.set_xlim(-4, 104)
    ax.set_xticks([0, 50, 100], ["MALO", "PROMEDIO", "ÉLITE"], fontsize=11)
    ax.tick_params(length=0, pad=12)
    for s in ax.spines.values():
        s.set_visible(False)

    # Pie
    fig.text(0.06, 0.045, source, fontsize=12, color=theme.MUTED,
             family=fonts["number"])
    fig.text(0.94, 0.045, handle, fontsize=14, color=accent,
             ha="right", weight="bold")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
