"""Tercera lámina del carrusel: latinos en el juego (1080x1350).

Todos los latinos que participaron, con su línea. Los destacados (jonrón, figura de su
equipo, Game Score 60+, 2+ hits o 2+ impulsadas, victoria o salvado) van arriba y con el
motivo escrito. Los venezolanos llevan el código en verde LVBP.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from bpt import theme
from bpt.data.mlb_box import ActuacionLatina
from bpt.data.mlb_stats import FUENTE, Juego
from bpt.viz.result_card import W, H, _panel, fecha_es

MAX_FILAS = 8          # entre loma y bate
PASO = 0.062           # alto de cada fila
CABECERA = 0.07        # título del panel + margen inferior


def resumen_paises(lista: list[ActuacionLatina]) -> str:
    """'5 peloteros · VEN 2 · DOM 2 · PUR 1' (cada pelotero cuenta una vez)."""
    por_jugador = {(a.nombre, a.equipo): a.codigo for a in lista}
    c = Counter(por_jugador.values())
    n = len(por_jugador)
    partes = [f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]
    return f"{n} pelotero{'s' if n != 1 else ''}  ·  " + "  ·  ".join(partes)


def _tag(fig, x, y, codigo, num):
    color = theme.LVBP if codigo == "VEN" else theme.MUTED
    fig.add_artist(FancyBboxPatch((x, y - 0.011), 0.062, 0.022,
                                  boxstyle="round,pad=0,rounding_size=0.005",
                                  transform=fig.transFigure, color=color, alpha=0.9))
    fig.text(x + 0.031, y, codigo, fontsize=10.5, weight="bold", color=theme.BG,
             ha="center", va="center", family=num)


def _seccion(fig, rect, titulo, filas, maximo, etiqueta_valor, num):
    """Panel con hasta `maximo` filas de alto fijo (PASO)."""
    x0, y0, w, h = rect
    _panel(fig, rect)
    fig.text(x0 + 0.03, y0 + h - 0.025, titulo, fontsize=11, color=theme.MUTED, va="top",
             family=num)
    fig.text(x0 + w - 0.03, y0 + h - 0.025, etiqueta_valor, fontsize=9, color=theme.MUTED,
             va="top", ha="right", family=num)
    if not filas:
        fig.text(x0 + 0.03, y0 + h / 2 - 0.01, "Sin latinos en este rol", fontsize=15,
                 color=theme.MUTED, va="center")
        return
    top = y0 + h - 0.075
    for i, a in enumerate(filas[:maximo]):
        y = top - i * PASO
        _tag(fig, x0 + 0.03, y + 0.004, a.codigo, num)
        color = theme.TEXT if a.destacada else theme.MUTED
        fig.text(x0 + 0.105, y + 0.008, a.nombre, fontsize=16 if a.destacada else 14,
                 weight="bold" if a.destacada else "normal", color=color, va="center")
        sub = f"{a.equipo}  ·  {a.linea}"
        fig.text(x0 + 0.105, y - 0.017, sub, fontsize=10.5, color=theme.MUTED, va="center",
                 family=num)
        fig.text(x0 + w - 0.03, y + 0.008, str(a.valor), fontsize=17, weight="bold",
                 color=theme.ACCENT if a.destacada else theme.MUTED, va="center", ha="right",
                 family=num)
        if a.motivo:
            fig.text(x0 + w - 0.03, y - 0.017, a.motivo, fontsize=9.5, color=theme.ACCENT,
                     va="center", ha="right", family=num)
    if len(filas) > maximo:
        fig.text(x0 + 0.03, y0 + 0.012, f"y {len(filas) - maximo} más (en el resumen.json)",
                 fontsize=9.5, color=theme.MUTED, ha="left", va="bottom", family=num)


def render_latinos_card(j: Juego, lista: list[ActuacionLatina], out_path: Path,
                        handle: str = theme.HANDLE, temporada: int | None = None) -> Path:
    if not lista:
        raise ValueError("No hay latinos en el juego")
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    temporada = temporada or int(j.fecha[:4])
    v, l = j.visitante, j.local

    fig.text(0.06, 0.955, f"MBP  ·  MLB POSTEMPORADA {temporada}  ·  {j.serie_corto}",
             fontsize=14, color=theme.ACCENT, va="top", family=num)
    fig.text(0.06, 0.915, "LATINOS", fontsize=56, weight="bold", color=theme.TEXT, va="top")
    fig.text(0.06, 0.838, f"en el Juego {j.juego_n}  ·  {v.abrev} {v.carreras}, "
             f"{l.abrev} {l.carreras}", fontsize=17, color=theme.MUTED, va="top")
    fig.text(0.06, 0.803, resumen_paises(lista), fontsize=12, color=theme.TEXT, va="top",
             family=num)

    loma = [a for a in lista if a.rol == "pitcheo"]
    bate = [a for a in lista if a.rol == "bateo"]
    # Reparto de filas: hasta 3 en la loma y el resto al bate (o al revés si sobra)
    n_loma = min(len(loma), 3, MAX_FILAS)
    n_bate = min(len(bate), MAX_FILAS - n_loma)
    n_loma = min(len(loma), MAX_FILAS - n_bate)
    px, pw, top = 0.04, 0.92, 0.775
    h_loma = CABECERA + max(n_loma, 1) * PASO
    h_bate = CABECERA + max(n_bate, 1) * PASO
    _seccion(fig, [px, top - h_loma, pw, h_loma], "EN LA LOMA", loma, n_loma, "GAME SCORE", num)
    _seccion(fig, [px, top - h_loma - 0.02 - h_bate, pw, h_bate], "AL BATE", bate, n_bate,
             "BASES GANADAS", num)

    fig.text(0.06, 0.085, "En color: actuación destacada (jonrón, figura del equipo, Game Score "
             "60+, 2+ hits o 2+ CI, victoria o salvado).", fontsize=9.5, color=theme.MUTED,
             va="center", family=num)
    fig.text(0.06, 0.055, f"{fecha_es(j.fecha)}  ·  {FUENTE}", fontsize=10,
             color=theme.MUTED, va="center", family=num)
    fig.text(0.94, 0.055, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
