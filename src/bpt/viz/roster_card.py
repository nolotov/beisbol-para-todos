"""Láminas de "roster" (1080x1350): un equipo ideal dibujado sobre el diamante.

Pensadas para especiales ("los mejores latinos en la Serie Mundial", etc.): cada jugador va
en su posición del campo con país, equipo y una nota corta; el relevo y el bateador
designado van en la banca, abajo. Los venezolanos se marcan en verde LVBP (regla de marca).
Sin logos ni nada que imite material oficial.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Wedge

from bpt import theme

W, H = 10.8, 13.5

# Posición en el campo (coordenadas del diamante: home en 0,0; la segunda en 0,0.64)
CAMPO = {
    "C": (0.0, -0.18), "SP": (0.0, 0.25),
    "1B": (0.52, 0.42), "3B": (-0.52, 0.42),
    "2B": (0.30, 0.74), "SS": (-0.30, 0.74),
    "LF": (-0.60, 1.07), "CF": (0.0, 1.27), "RF": (0.60, 1.07),
}
BANCA = ["RP", "DH"]
NOMBRE_POS = {"C": "C", "SP": "Abridor", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
              "LF": "LF", "CF": "CF", "RF": "RF", "RP": "Cerrador", "DH": "Bateador designado"}
ANCHO, ALTO = 0.50, 0.195           # tamaño de cada ficha (en unidades del diamante)


def es_venezolano(j: dict) -> bool:
    return (j.get("pais") or "").strip().lower() == "venezuela"


def _diamante(ax):
    """Campo esquemático: territorio bueno, cuadro y bases."""
    ax.add_patch(Wedge((0, 0), 1.40, 45, 135, color=theme.SURFACE, alpha=0.55, lw=0))
    ax.add_patch(Wedge((0, 0), 0.86, 45, 135, color=theme.SURFACE, alpha=0.9, lw=0))
    ax.add_patch(Polygon([(0, 0), (0.32, 0.32), (0, 0.64), (-0.32, 0.32)], closed=True,
                         facecolor=theme.BG, edgecolor=theme.MUTED, lw=1.2, alpha=0.9))
    for x, y in [(0.32, 0.32), (0, 0.64), (-0.32, 0.32)]:
        ax.add_patch(Polygon([(x - .025, y), (x, y + .025), (x + .025, y), (x, y - .025)],
                             closed=True, color=theme.TEXT, alpha=0.8, lw=0))
    ax.add_patch(Polygon([(-.025, .0), (.025, .0), (.025, -.02), (0, -.04), (-.025, -.02)],
                         closed=True, color=theme.TEXT, alpha=0.8, lw=0))
    ax.add_patch(Circle((0, 0.25), 0.05, color=theme.MUTED, alpha=0.35, lw=0))
    for s in (1, -1):
        ax.plot([0, s * 0.99], [0, 0.99], color=theme.MUTED, lw=1, alpha=0.5)


def _ficha(ax, x, y, j: dict, num: str, ancho=ANCHO, alto=ALTO):
    acento = theme.LVBP if es_venezolano(j) else theme.ACCENT
    ax.add_patch(FancyBboxPatch((x - ancho / 2, y - alto / 2), ancho, alto,
                                boxstyle="round,pad=0,rounding_size=0.02",
                                facecolor=theme.BG, edgecolor=acento, lw=1.8, zorder=3))
    izq = x - ancho / 2 + 0.025
    ax.text(izq, y + alto * 0.30, NOMBRE_POS.get(j["pos"], j["pos"]).upper(), fontsize=10.5,
            color=acento, weight="bold", family=num, va="center", zorder=4)
    ax.text(izq, y + alto * 0.07, j["nombre"], fontsize=17.5, color=theme.TEXT, weight="bold",
            va="center", zorder=4)
    ax.text(izq, y - alto * 0.16, f"{j['pais']} · {j['equipo']}", fontsize=11,
            color=theme.LVBP if es_venezolano(j) else theme.TEXT, va="center", zorder=4)
    if j.get("nota"):
        ax.text(izq, y - alto * 0.34, j["nota"], fontsize=10, color=theme.MUTED, va="center",
                zorder=4)


def render_roster(titulo: str, subtitulo: str, jugadores: list[dict], out_path: Path,
                  etiqueta: str = "MBP  ·  ESPECIAL", nota_pie: str | None = None,
                  fuente: str = "Datos: Baseball-Reference", handle: str = theme.HANDLE) -> Path:
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.text(0.06, 0.955, etiqueta, fontsize=14, color=theme.ACCENT, va="top", family=num)
    fig.text(0.06, 0.925, titulo, fontsize=50, weight="bold", color=theme.TEXT, va="top")
    fig.text(0.06, 0.858, subtitulo, fontsize=17, color=theme.MUTED, va="top")

    por_pos = {j["pos"]: j for j in jugadores}
    banca = [por_pos[p] for p in BANCA if p in por_pos]

    # El diamante: ejes con la misma escala en x e y
    ax = fig.add_axes([0.03, 0.19 if banca else 0.12, 0.94, 0.64])
    ancho_px, alto_px = 0.94 * W, 0.64 * H
    ax.set_xlim(-1, 1)
    alto_datos = 2 * alto_px / ancho_px
    ax.set_ylim(-0.30, -0.30 + alto_datos)
    ax.set_axis_off()
    _diamante(ax)
    for pos, (x, y) in CAMPO.items():
        if pos in por_pos:
            _ficha(ax, x, y, por_pos[pos], num)

    # Banca: cerrador y bateador designado
    if banca:
        bx = fig.add_axes([0.03, 0.075, 0.94, 0.11])
        bx.set_xlim(-1, 1)
        bx.set_ylim(-0.5 * 0.11 * H / (0.94 * W) * 2, 0.5 * 0.11 * H / (0.94 * W) * 2)
        bx.set_axis_off()
        n = len(banca)
        ancho = 0.62 if n == 2 else 0.70
        xs = [-0.34, 0.34] if n == 2 else [0.0]
        for x, j in zip(xs, banca):
            _ficha(bx, x, 0, j, num, ancho=ancho, alto=0.22)

    if nota_pie:
        fig.text(0.06, 0.058, nota_pie, fontsize=10, color=theme.MUTED, va="center")
    fig.text(0.06, 0.032, fuente, fontsize=10, color=theme.MUTED, va="center", family=num)
    fig.text(0.94, 0.032, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")
    return _guardar(fig, out_path)


def render_portada(titulo: str, subtitulo: str, paises: list[tuple[str, int]], total: int,
                   out_path: Path, etiqueta: str = "MBP  ·  ESPECIAL", pie: str | None = None,
                   fuente: str = "Datos: Baseball-Reference", handle: str = theme.HANDLE) -> Path:
    """Portada con el conteo por país (barras), Venezuela en verde."""
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.text(0.06, 0.92, etiqueta, fontsize=15, color=theme.ACCENT, va="top", family=num)
    fig.text(0.06, 0.885, titulo, fontsize=60, weight="bold", color=theme.TEXT, va="top",
             linespacing=0.95)
    fig.text(0.06, 0.70, subtitulo, fontsize=19, color=theme.MUTED, va="top", linespacing=1.3)

    fig.text(0.06, 0.585, f"{total}", fontsize=86, weight="bold", color=theme.ACCENT,
             va="top", family=num)
    fig.text(0.30, 0.555, "peloteros", fontsize=22, color=theme.TEXT, va="center")
    fig.text(0.30, 0.525, f"{len(paises)} países", fontsize=18, color=theme.MUTED, va="center")

    tope = max(n for _, n in paises)
    y, paso = 0.44, 0.052
    for pais, n in paises:
        color = theme.LVBP if pais.lower() == "venezuela" else theme.ACCENT
        fig.text(0.06, y, pais, fontsize=18, color=theme.TEXT, va="center")
        largo = 0.46 * n / tope
        fig.add_artist(FancyBboxPatch((0.36, y - 0.013), largo, 0.026,
                                      boxstyle="round,pad=0,rounding_size=0.006",
                                      transform=fig.transFigure, color=color, lw=0))
        fig.text(0.36 + largo + 0.015, y, str(n), fontsize=18, color=theme.TEXT, va="center",
                 family=num, weight="bold")
        y -= paso

    if pie:
        fig.text(0.06, 0.075, pie, fontsize=12, color=theme.MUTED, va="center")
    fig.text(0.06, 0.04, fuente, fontsize=10, color=theme.MUTED, va="center", family=num)
    fig.text(0.94, 0.04, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")
    return _guardar(fig, out_path)


def _guardar(fig, out_path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
