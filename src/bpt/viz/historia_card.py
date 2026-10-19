"""Historia del día (1080x1920): cartelera de juegos de hoy de la MLB y la LVBP.

Respeta las zonas seguras de las historias: arriba (~13 %) va la barra de perfil de
Instagram y abajo (~14 %) la de respuesta, así que ahí solo hay fondo y la firma.
MLB en ámbar, LVBP en verde, como el resto de la marca.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from bpt import theme
from bpt.historia import JuegoHoy, fecha_larga

W, H = 10.8, 19.2
ARRIBA, ABAJO = 0.80, 0.16          # zona de contenido (fracción de la altura)
COLOR = {"MLB": theme.ACCENT, "LVBP": theme.LVBP}
FUENTE = "Datos: MLB Stats API"


def _caja(fig, x, y, w, h, color, r=0.012):
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                  transform=fig.transFigure, color=color, linewidth=0))


def _modo(n_juegos: int, n_secciones: int) -> tuple[str, float]:
    """Cuánto cabe: 'completo' (3 líneas), 'medio' (2) o 'compacto' (1)."""
    disponible = (ARRIBA - 0.050) - (ABAJO + 0.010) - n_secciones * 0.045
    alto = min(0.105, disponible / max(n_juegos, 1))
    if alto >= 0.085:
        return "completo", alto
    if alto >= 0.055:
        return "medio", alto
    return "compacto", alto


def _fila(fig, num, j: JuegoHoy, y_top: float, alto: float, modo: str, color: str):
    x, w = 0.05, 0.90
    gap = min(0.010, alto * 0.12)
    y0 = y_top - alto + gap
    h = alto - gap
    _caja(fig, x, y0, w, h, theme.SURFACE)
    _caja(fig, x, y0, 0.010, h, color, r=0.004)
    escala = {"completo": 1.0, "medio": 0.85, "compacto": 0.68}[modo]
    distinto = j.estado not in ("Programado", "En juego")
    hora = j.estado if distinto else j.hora

    if modo == "compacto":
        yc = y0 + h / 2
        fig.text(x + 0.035, yc, hora, fontsize=20 * escala, family=num, color=theme.TEXT,
                 va="center")
        fig.text(x + 0.30, yc, f"{j.visitante}  @  {j.local}", fontsize=30 * escala,
                 weight="bold", color=theme.TEXT, va="center")
        if j.abridores:
            fig.text(x + w - 0.025, yc, j.abridores, fontsize=15 * escala, color=theme.MUTED,
                     va="center", ha="right")
        return

    lineas = 3 if modo == "completo" else 2
    paso = h / (lineas + 0.6)
    y1 = y0 + h - paso * 0.95
    fig.text(x + 0.035, y1, f"{j.visitante}  @  {j.local}", fontsize=40 * escala,
             weight="bold", color=theme.TEXT, va="center")
    fig.text(x + w - 0.025, y1, hora, fontsize=24 * escala, family=num, va="center",
             ha="right", color=theme.MUTED if distinto else color, weight="bold")
    y2 = y1 - paso
    fig.text(x + 0.035, y2, j.detalle or f"{j.visitante_nombre} vs. {j.local_nombre}",
             fontsize=17 * escala, color=theme.TEXT, va="center")
    if modo == "completo":
        fig.text(x + 0.035, y2 - paso,
                 f"Abridores: {j.abridores}" if j.abridores else "Abridores por anunciar",
                 fontsize=15.5, color=theme.MUTED, va="center")
    elif j.abridores:
        fig.text(x + w - 0.025, y2, j.abridores, fontsize=15 * escala, color=theme.MUTED,
                 va="center", ha="right")


def render_historia(por_liga: dict[str, list[JuegoHoy]], fases: dict[str, str], fecha: str,
                    out_path: Path, handle: str = theme.HANDLE) -> Path:
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)

    ligas = [liga for liga in ("MLB", "LVBP") if por_liga.get(liga)]
    total = sum(len(por_liga[liga]) for liga in ligas)

    # Cabecera (bajo la barra de perfil de Instagram)
    fig.text(0.05, 0.868, "MBP  ·  HOY SE JUEGA", fontsize=17, family=num,
             color=COLOR[ligas[0]] if len(ligas) == 1 else theme.ACCENT, va="center")
    fig.text(0.05, 0.853, "JUEGOS DE HOY", fontsize=62, weight="bold", color=theme.TEXT,
             va="top")
    fig.text(0.05, ARRIBA + 0.003, f"{fecha_larga(fecha).capitalize()}  ·  Hora de Venezuela",
             fontsize=19, color=theme.MUTED, va="top")

    modo, alto = _modo(total, len(ligas))
    y = ARRIBA - 0.050
    for liga in ligas:
        juegos = por_liga[liga]
        rotulo = liga + (f"  ·  {fases[liga]}" if fases.get(liga) else "")
        n = len(juegos)
        fig.text(0.05, y - 0.012, rotulo.upper(), fontsize=19, weight="bold",
                 color=COLOR[liga], va="center")
        fig.text(0.95, y - 0.012, f"{n} juego{'s' if n != 1 else ''}", fontsize=15,
                 family=num, color=theme.MUTED, va="center", ha="right")
        y -= 0.032
        for j in juegos:
            _fila(fig, num, j, y, alto, modo, COLOR[liga])
            y -= alto
        y -= 0.013

    # Pie: firma por encima de la barra de respuesta
    fig.text(0.05, ABAJO - 0.020, FUENTE, fontsize=12, color=theme.MUTED, family=num,
             va="center")
    fig.text(0.95, ABAJO - 0.020, handle, fontsize=20, weight="bold", color=theme.TEXT,
             va="center", ha="right")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
