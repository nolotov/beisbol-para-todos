"""Identidad visual "Dashboard de dugout": paleta y estilo de matplotlib."""
from __future__ import annotations

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

# --- Paleta de marca --------------------------------------------------------
BG = "#0B1426"          # azul noche (fondo)
SURFACE = "#16233D"     # tarjetas
TEXT = "#F2F4F7"        # blanco hueso
MUTED = "#8A94A6"       # gris / promedio
COLD = "#2F6FDE"        # percentil bajo
HOT = "#E2463C"         # percentil élite
ACCENT = "#F5B700"      # ámbar: el dato clave
LVBP = "#1FA36B"        # verde campo: contenido LVBP

# Escala de percentiles estilo Savant: frío -> gris -> rojo
PERCENTILE_CMAP = LinearSegmentedColormap.from_list(
    "bpt_percentile", [(0.0, COLD), (0.5, MUTED), (1.0, HOT)]
)

# Fuentes preferidas (si no están instaladas, cae en DejaVu Sans)
TITLE_FONTS = ["Barlow Condensed", "Inter", "Segoe UI", "DejaVu Sans"]
NUMBER_FONTS = ["JetBrains Mono", "Consolas", "DejaVu Sans Mono"]


def _first_available(candidates: list[str]) -> str:
    installed = {f.name for f in font_manager.fontManager.ttflist}
    return next((c for c in candidates if c in installed), candidates[-1])


def percentile_color(pct: float):
    return PERCENTILE_CMAP(max(0.0, min(100.0, pct)) / 100.0)


def apply() -> dict[str, str]:
    """Aplica el estilo global y devuelve las fuentes elegidas."""
    title_font = _first_available(TITLE_FONTS)
    number_font = _first_available(NUMBER_FONTS)
    mpl.rcParams.update(
        {
            "figure.facecolor": BG,
            "axes.facecolor": BG,
            "savefig.facecolor": BG,
            "text.color": TEXT,
            "axes.labelcolor": TEXT,
            "xtick.color": MUTED,
            "ytick.color": TEXT,
            "axes.edgecolor": BG,
            "font.family": title_font,
        }
    )
    return {"title": title_font, "number": number_font}
