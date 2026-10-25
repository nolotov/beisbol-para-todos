"""Identidad visual "Dashboard de dugout": paleta y estilo de matplotlib."""
from __future__ import annotations

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

# --- Marca -------------------------------------------------------------------
HANDLE = "@mbp.deportes"

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


from contextlib import contextmanager

# --- Paletas por deporte (MBP Deportes) ----------------------------------------------------
# El béisbol es la casa: su paleta es la de arriba. Los eventos especiales de otros deportes
# cambian fondo, tarjetas y acento para que se note de un vistazo que es "otra cancha", sin
# dejar de ser MBP (misma tipografía, mismo esqueleto de lámina, misma firma). El acento debe
# leerse con texto oscuro encima (franjas de remate y "lo que viene").
_CLAVES_PALETA = ("BG", "SURFACE", "TEXT", "MUTED", "ACCENT")
DEPORTES: dict[str, dict[str, str]] = {
    "beisbol": {"BG": BG, "SURFACE": SURFACE, "TEXT": TEXT, "MUTED": MUTED, "ACCENT": ACCENT},
    # Noche de estadio: verde césped profundo con acento lima (no confunde con el verde LVBP)
    "futbol": {"BG": "#07170F", "SURFACE": "#11291C", "TEXT": TEXT, "MUTED": "#8FA597",
               "ACCENT": "#A6E22E"},
    # Duela de noche: berenjena oscuro con el naranja del balón
    "nba": {"BG": "#120E14", "SURFACE": "#22192A", "TEXT": TEXT, "MUTED": "#9A8FA3",
            "ACCENT": "#F7882F"},
    # Grama y cuero: verde oscuro con el tostado del ovoide
    "nfl": {"BG": "#0E1611", "SURFACE": "#1A2A20", "TEXT": TEXT, "MUTED": "#93A398",
            "ACCENT": "#D9B26F"},
    # Fibra de carbono con el rojo del semáforo de salida
    "f1": {"BG": "#0D0D0F", "SURFACE": "#1C1C21", "TEXT": TEXT, "MUTED": "#9696A0",
           "ACCENT": "#FF3B30"},
    # Pista azul con la pelota amarillo flúor
    "padel": {"BG": "#0A1830", "SURFACE": "#14284A", "TEXT": TEXT, "MUTED": "#8C9CB8",
              "ACCENT": "#D7F205"},
}
_ALIAS_DEPORTE = {"béisbol": "beisbol", "baseball": "beisbol", "fútbol": "futbol",
                  "soccer": "futbol", "basket": "nba", "baloncesto": "nba",
                  "básquetbol": "nba", "football": "nfl", "formula 1": "f1",
                  "fórmula 1": "f1", "pádel": "padel"}
# Nombre para antetítulos y etiquetas ("MBP · FÚTBOL")
NOMBRE_DEPORTE = {"beisbol": "BÉISBOL", "futbol": "FÚTBOL", "nba": "NBA", "nfl": "NFL",
                  "f1": "FÓRMULA 1", "padel": "PÁDEL"}


def normalizar_deporte(nombre: str | None) -> str:
    """'Fútbol', 'soccer' o 'futbol' -> 'futbol'. Sin nombre es béisbol (la casa)."""
    clave = (nombre or "beisbol").strip().lower()
    clave = _ALIAS_DEPORTE.get(clave, clave)
    if clave not in DEPORTES:
        raise ValueError(f"deporte desconocido '{nombre}' (válidos: {', '.join(DEPORTES)})")
    return clave


@contextmanager
def deporte(nombre: str | None):
    """Pinta con la paleta del deporte mientras se dibuja y deja la de béisbol al salir."""
    paleta = DEPORTES[normalizar_deporte(nombre)]
    g = globals()
    previo = {k: g[k] for k in _CLAVES_PALETA}
    g.update(paleta)
    try:
        yield paleta
    finally:
        g.update(previo)


@contextmanager
def acento(color: str):
    """Cambia el color de acento mientras se dibuja (verde LVBP vs. ámbar MLB)."""
    global ACCENT
    previo, ACCENT = ACCENT, color
    try:
        yield
    finally:
        ACCENT = previo


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
