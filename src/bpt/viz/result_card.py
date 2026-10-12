"""Tarjeta de resultado de un juego de postemporada MLB (1080x1350).

Pizarra por entradas, decisiones de pitcheo y cómo queda la serie. Sin logos ni gráfica
que imite material oficial de MLB: solo la identidad "Dashboard de dugout" de MBP.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch

from bpt import theme
from bpt.data.mlb_stats import FUENTE, EstadoSerie, Juego

W, H = 10.8, 13.5
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_es(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def _panel(fig, rect, rounding=0.025):
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle=f"round,pad=0,rounding_size={rounding}",
                                transform=ax.transAxes, color=theme.SURFACE))
    return ax


def titular(j: Juego) -> str:
    """Frase corta del resultado: 'LAD le gana 5-3 a MIL' (con extrainnings si aplica)."""
    g, p = j.ganador, j.perdedor
    extra = f" en {len(j.entradas)} entradas" if j.extra_innings else ""
    return f"{g.abrev} le gana {g.carreras}-{p.carreras} a {p.abrev}{extra}"


def render_result_card(j: Juego, serie: EstadoSerie | None, out_path: Path,
                       handle: str = theme.HANDLE, temporada: int | None = None,
                       encabezado: str | None = None, titulo: str | None = None,
                       subtitulo: str | None = None, fuente: str = FUENTE) -> Path:
    """`encabezado`/`titulo`/`subtitulo` permiten usarla fuera de la postemporada (LVBP).
    Sin `serie`, si los equipos traen récord, el panel de abajo muestra el récord."""
    if not j.final:
        raise ValueError(f"El juego {j.game_pk} no ha terminado (estado: {j.estado})")
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    temporada = temporada or int(j.fecha[:4])

    # --- Encabezado ---------------------------------------------------------
    fig.text(0.06, 0.955, encabezado or f"MBP  ·  MLB POSTEMPORADA {temporada}  ·  {j.serie_corto}",
             fontsize=14, color=theme.ACCENT, va="top", family=num)
    fig.text(0.06, 0.915, titulo or f"JUEGO {j.juego_n}", fontsize=56, weight="bold",
             color=theme.TEXT, va="top")
    fig.text(0.06, 0.838, subtitulo or j.serie_es, fontsize=17, color=theme.MUTED, va="top")

    # --- Marcador -------------------------------------------------------------
    px, pw = 0.04, 0.92
    sy, sh = 0.565, 0.24
    _panel(fig, [px, sy, pw, sh])
    for k, (eq, rol) in enumerate([(j.visitante, "VISITANTE"), (j.local, "LOCAL")]):
        yc = sy + sh * (0.72 - 0.44 * k)
        color = theme.TEXT if eq.ganador else theme.MUTED
        if eq.ganador:
            fig.add_artist(FancyBboxPatch((px + 0.02, yc - 0.042), 0.008, 0.084,
                                          boxstyle="round,pad=0,rounding_size=0.004",
                                          transform=fig.transFigure, color=theme.ACCENT))
        fig.text(px + 0.05, yc + 0.006, eq.abrev, fontsize=50, weight="bold", color=color,
                 va="center")
        fig.text(px + 0.25, yc + 0.014, eq.nombre, fontsize=17, color=color, va="center")
        fig.text(px + 0.25, yc - 0.018, rol, fontsize=10, color=theme.MUTED, va="center",
                 family=num)
        fig.text(px + pw - 0.05, yc, str(eq.carreras), fontsize=72, weight="bold",
                 color=theme.ACCENT if eq.ganador else theme.MUTED, va="center", ha="right",
                 family=num)

    # --- Pizarra por entradas -------------------------------------------------
    ly, lh = 0.39, 0.155
    _panel(fig, [px, ly, pw, lh])
    n_inn = max(9, len(j.entradas))
    cols = n_inn + 3                              # entradas + C H E
    x_left, x_right = px + 0.13, px + pw - 0.03
    step = (x_right - x_left) / cols
    y_head, y_rows = ly + lh - 0.032, [ly + lh * 0.54, ly + lh * 0.30]
    fs = 15 if n_inn <= 10 else 12

    def cx(i):  # centro de la columna i
        return x_left + step * (i + 0.5)

    for i in range(n_inn):
        fig.text(cx(i), y_head, str(i + 1), fontsize=11, color=theme.MUTED, ha="center",
                 va="center", family=num)
    for i, lab in enumerate(["C", "H", "E"]):
        fig.text(cx(n_inn + i), y_head, lab, fontsize=11, color=theme.ACCENT, ha="center",
                 va="center", family=num, weight="bold")
    # separador antes de C H E
    sep_x = x_left + step * n_inn
    fig.add_artist(plt.Line2D([sep_x, sep_x], [ly + 0.018, ly + lh - 0.015],
                              transform=fig.transFigure, color=theme.BG, lw=2))

    entradas = {n: (a, h) for n, a, h in j.entradas}
    for r, eq in enumerate([j.visitante, j.local]):
        y = y_rows[r]
        fig.text(px + 0.03, y, eq.abrev, fontsize=16, weight="bold", color=theme.TEXT,
                 va="center")
        for i in range(n_inn):
            runs = entradas.get(i + 1, (None, None))[r]
            # Inning no jugado (el local no batea en la baja de la novena si va ganando)
            txt = "x" if runs is None and (i + 1) in entradas else ("" if runs is None else str(runs))
            fig.text(cx(i), y, txt, fontsize=fs, ha="center", va="center", family=num,
                     color=theme.TEXT if runs else theme.MUTED)
        for i, v in enumerate([eq.carreras, eq.hits, eq.errores]):
            fig.text(cx(n_inn + i), y, "" if v is None else str(v), fontsize=fs + 1,
                     ha="center", va="center", family=num, weight="bold", color=theme.TEXT)
    fig.text(px + 0.03, ly + 0.008, "C: carreras  ·  H: hits  ·  E: errores", fontsize=9,
             color=theme.MUTED, va="bottom", family=num)

    # --- Decisiones -----------------------------------------------------------
    dy, dh = 0.225, 0.145
    _panel(fig, [px, dy, pw, dh])
    decisiones = [("GANADOR", j.ganador_pitcher), ("PERDEDOR", j.perdedor_pitcher),
                  ("SALVADO", j.salvado_pitcher)]
    decisiones = [(k, v) for k, v in decisiones if v]
    fig.text(px + 0.03, dy + dh - 0.025, "DECISIONES DE PITCHEO", fontsize=11,
             color=theme.MUTED, va="top", family=num)
    rows_y = dy + dh - 0.057
    for i, (k, v) in enumerate(decisiones):
        y = rows_y - i * 0.03
        fig.text(px + 0.03, y, k, fontsize=11, color=theme.ACCENT, va="center", family=num)
        fig.text(px + 0.20, y, v, fontsize=17, color=theme.TEXT, va="center")

    # --- Estado de la serie ---------------------------------------------------
    if serie:
        by, bh = 0.095, 0.115
        _panel(fig, [px, by, pw, bh])
        fig.text(px + 0.03, by + bh - 0.025, "ASÍ VA LA SERIE", fontsize=11, color=theme.MUTED,
                 va="top", family=num)
        fig.text(px + 0.03, by + 0.035, serie.texto, fontsize=24, weight="bold",
                 color=theme.TEXT, va="center")
        # Puntos: victorias de cada equipo hacia las necesarias
        orden = [j.visitante.abrev, j.local.abrev]
        r = 0.0085
        for k, ab in enumerate(orden):
            y = by + bh * (0.55 - 0.32 * k)
            fig.text(px + 0.60, y, ab, fontsize=13, color=theme.TEXT, va="center",
                     ha="right", family=num, weight="bold")
            for i in range(serie.para_ganar):
                lleno = i < serie.equipos.get(ab, 0)
                fig.add_artist(Ellipse((px + 0.635 + i * 0.065, y), 2 * r, 2 * r * W / H,
                                       transform=fig.transFigure,
                                      color=theme.ACCENT if lleno else theme.BG))
        fig.text(px + pw - 0.03, by + bh - 0.025, f"GANA EL PRIMERO EN LLEGAR A {serie.para_ganar}",
                 fontsize=9, color=theme.MUTED, ha="right", va="top", family=num)

    # --- Récord (temporada regular) ------------------------------------------
    if not serie and j.visitante.record and j.local.record:
        by, bh = 0.095, 0.115
        _panel(fig, [px, by, pw, bh])
        fig.text(px + 0.03, by + bh - 0.025, "RÉCORD EN LA TEMPORADA", fontsize=11,
                 color=theme.MUTED, va="top", family=num)
        for k, eq in enumerate([j.visitante, j.local]):
            x = px + 0.03 + k * 0.45
            fig.text(x, by + 0.04, eq.abrev, fontsize=22, weight="bold", color=theme.TEXT,
                     va="center")
            fig.text(x + 0.12, by + 0.04, eq.record, fontsize=24, weight="bold",
                     color=theme.ACCENT if eq.ganador else theme.MUTED, va="center", family=num)

    # --- Pie ------------------------------------------------------------------
    fig.text(0.06, 0.06, f"{fecha_es(j.fecha)}  ·  {j.estadio}", fontsize=11,
             color=theme.MUTED, va="center", family=num)
    fig.text(0.06, 0.035, fuente, fontsize=10, color=theme.MUTED, va="center", family=num)
    fig.text(0.94, 0.045, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path

