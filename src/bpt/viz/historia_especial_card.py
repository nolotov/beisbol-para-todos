"""Historia especial (1080x1920): una noticia puntual, armada a mano desde un JSON.

Pensada para momentos grandes (un banderín, un título, un récord): titular, marcador final,
figuras del juego, un dato y lo que viene. Respeta las mismas zonas seguras que la historia
del día: arriba (~13 %) la barra de perfil de Instagram y abajo (~14 %) la de respuesta.
Solo texto: sin logos de equipos.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from bpt import theme

W, H = 10.8, 19.2
ARRIBA, ABAJO = 0.80, 0.16
COLORES = {"MLB": theme.ACCENT, "LVBP": theme.LVBP}


def _caja(fig, x, y, w, h, color, r=0.012):
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                  transform=fig.transFigure, color=color, linewidth=0))


def render_historia_especial(h: dict, out_path: Path, fuente: str = "Datos: MLB Stats API",
                             handle: str = theme.HANDLE) -> Path:
    """`h` es el bloque "historia" del especial:

    antetitulo, titulo (lista de 1-3 líneas), marcador {visitante, local, carreras_v,
    carreras_l, nota}, figuras [{nombre, pais, linea, venezolano?}], dato {cifra, texto},
    proximo {titulo, linea1, linea2}, liga ("MLB" por defecto).
    """
    fonts = theme.apply()
    num = fonts["number"]
    color = COLORES.get(h.get("liga", "MLB"), theme.ACCENT)
    fig = plt.figure(figsize=(W, H), dpi=100)
    x, w = 0.05, 0.90

    # Cabecera
    fig.text(x, 0.868, h.get("antetitulo", "MBP"), fontsize=17, family=num, color=color,
             va="center")
    y = 0.853
    for linea in h["titulo"][:3]:
        fig.text(x, y, linea, fontsize=64, weight="bold", color=theme.TEXT, va="top")
        y -= 0.044
    y -= 0.014

    # Marcador final
    m = h["marcador"]
    alto = 0.118
    _caja(fig, x, y - alto, w, alto, theme.SURFACE)
    _caja(fig, x, y - alto, 0.010, alto, color, r=0.004)
    fila1, fila2 = y - 0.030, y - 0.072
    gana_l = m["carreras_l"] > m["carreras_v"]
    for yy, eq, c, gana in ((fila1, m["visitante"], m["carreras_v"], not gana_l),
                            (fila2, m["local"], m["carreras_l"], gana_l)):
        tono = theme.TEXT if gana else theme.MUTED
        fig.text(x + 0.040, yy, eq, fontsize=36, weight="bold", color=tono, va="center")
        fig.text(x + w - 0.040, yy, str(c), fontsize=48, family=num, weight="bold",
                 color=color if gana else theme.MUTED, va="center", ha="right")
    fig.text(x + 0.040, y - 0.104, m.get("nota", "Final"), fontsize=17, color=theme.MUTED,
             va="center")
    y -= alto + 0.026

    # Figuras
    fig.text(x, y, "FIGURAS DEL JUEGO", fontsize=19, weight="bold", color=color,
             va="center")
    y -= 0.028
    for f in h.get("figuras", [])[:3]:
        fila = 0.056
        _caja(fig, x, y - fila + 0.006, w, fila - 0.006, theme.SURFACE)
        tono = theme.LVBP if f.get("venezolano") else theme.TEXT
        fig.text(x + 0.035, y - 0.017, f["nombre"], fontsize=26, weight="bold", color=tono,
                 va="center")
        if f.get("pais"):
            fig.text(x + w - 0.030, y - 0.017, f["pais"], fontsize=15, color=theme.MUTED,
                     va="center", ha="right")
        fig.text(x + 0.035, y - 0.038, f["linea"], fontsize=18, family=num, color=theme.TEXT,
                 va="center")
        y -= fila
    y -= 0.016

    # Dato
    if h.get("dato"):
        d = h["dato"]
        alto = 0.062
        _caja(fig, x, y - alto, w, alto, theme.SURFACE)
        fig.text(x + 0.035, y - alto / 2, d["cifra"], fontsize=50, family=num,
                 weight="bold", color=color, va="center")
        fig.text(x + 0.035 + 0.035 * max(len(d["cifra"]), 1) + 0.04, y - alto / 2, d["texto"],
                 fontsize=18, color=theme.TEXT, va="center", linespacing=1.35)
        y -= alto + 0.018

    # Próximo
    if h.get("proximo"):
        p = h["proximo"]
        alto = 0.088
        _caja(fig, x, max(y - alto, ABAJO + 0.010), w, alto, color)
        base = max(y - alto, ABAJO + 0.010)
        fig.text(x + 0.035, base + alto - 0.022, p["titulo"].upper(), fontsize=17,
                 weight="bold", color=theme.BG, va="center")
        fig.text(x + 0.035, base + alto - 0.050, p["linea1"], fontsize=27, weight="bold",
                 color=theme.BG, va="center")
        if p.get("linea2"):
            fig.text(x + 0.035, base + 0.016, p["linea2"], fontsize=17, color=theme.BG,
                     va="center")

    # Pie
    fig.text(x, ABAJO - 0.020, fuente, fontsize=12, color=theme.MUTED, family=num,
             va="center")
    fig.text(x + w, ABAJO - 0.020, handle, fontsize=20, weight="bold", color=theme.TEXT,
             va="center", ha="right")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
