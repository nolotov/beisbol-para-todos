"""Láminas de carrusel por bloques (1080x1350) para especiales armados a mano.

Cada lámina es un dict con "tipo" y su contenido; sirven para previas, duelos y piezas de
datos que no salen de un resultado del día. Tipos:

  - portada:     dos equipos frente a frente con sus datos clave y una franja de remate.
  - cifras:      filas de "cifra grande + explicación" (historia, datos ocultos, etc.).
  - barras:      barras horizontales (nóminas, totales) con una conclusión debajo.
  - cara_a_cara: tabla de estadísticas de los dos equipos con su puesto en MLB.
  - camino:      cómo llegó cada equipo (récord y series de postemporada).
  - figuras:     los jugadores a seguir de cada equipo, en dos columnas.

Los equipos se nombran en el bloque "equipos" del especial ({"A": {...}, "B": {...}}) con su
nombre y color. Venezolanos en verde LVBP (regla de marca). Sin logos.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from bpt import theme

W, H = 10.8, 13.5
X0, X1 = 0.06, 0.94
ANCHO = X1 - X0


def es_venezolano(item: dict) -> bool:
    return bool(item.get("venezolano")) or (item.get("pais") or "").strip().lower() == "venezuela"


def _caja(fig, x, y, w, h, color, r=0.012, **kw):
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                  transform=fig.transFigure, color=color, linewidth=0, **kw))


def _cabecera(fig, num, l: dict, color=theme.ACCENT) -> float:
    """Etiqueta, título y subtítulo. Devuelve la altura (fracción) donde empieza el cuerpo."""
    fig.text(X0, 0.955, l.get("etiqueta", "MBP  ·  SERIE MUNDIAL 2026"), fontsize=14,
             color=color, va="top", family=num)
    titulo = l["titulo"]
    fig.text(X0, 0.927, titulo, fontsize=l.get("tamano_titulo", 44), weight="bold",
             color=theme.TEXT, va="top", linespacing=0.95)
    lineas = titulo.count("\n") + 1
    y = 0.927 - 0.052 * lineas - 0.016
    if l.get("subtitulo"):
        fig.text(X0, y, l["subtitulo"], fontsize=17, color=theme.MUTED, va="top",
                 linespacing=1.3)
        y -= 0.026 * (l["subtitulo"].count("\n") + 1) + 0.014
    return y - 0.016


def _pie(fig, num, l: dict, pagina: str, fuente: str, handle: str):
    if l.get("nota"):
        fig.text(X0, 0.068, l["nota"], fontsize=11.5, color=theme.MUTED, va="center",
                 linespacing=1.3)
    fig.text(X0, 0.034, l.get("fuente", fuente), fontsize=10, color=theme.MUTED, va="center",
             family=num)
    if pagina:
        fig.text(0.5, 0.034, pagina, fontsize=11, color=theme.MUTED, va="center",
                 ha="center", family=num)
    fig.text(X1, 0.034, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")


# --- Tipos de lámina -----------------------------------------------------------------------

def _portada(fig, num, l, eq):
    fig.text(X0, 0.905, l.get("etiqueta", "MBP  ·  PREVIA"), fontsize=15, color=theme.ACCENT,
             va="top", family=num)
    fig.text(X0, 0.870, l["titulo"], fontsize=66, weight="bold", color=theme.TEXT, va="top",
             linespacing=0.92)
    lineas = l["titulo"].count("\n") + 1
    y = 0.870 - 0.074 * lineas - 0.022
    if l.get("subtitulo"):
        fig.text(X0, y, l["subtitulo"], fontsize=19, color=theme.MUTED, va="top",
                 linespacing=1.35)
        y -= 0.031 * (l["subtitulo"].count("\n") + 1) + 0.03

    # Dos bloques, uno por equipo, con "VS" al medio
    alto, w = 0.335, 0.405
    base = y - alto
    for i, clave in enumerate(("A", "B")):
        e = eq[clave]
        x = X0 if i == 0 else X1 - w
        _caja(fig, x, base, w, alto, theme.SURFACE)
        _caja(fig, x, base + alto - 0.010, w, 0.010, e["color"], r=0.004)
        fig.text(x + 0.03, base + alto - 0.045, e["nombre"].upper(), fontsize=30,
                 weight="bold", color=e["color"], va="center")
        fig.text(x + 0.03, base + alto - 0.078, e.get("liga", ""), fontsize=13,
                 color=theme.MUTED, va="center")
        yy = base + alto - 0.125
        for d in l.get("datos", {}).get(clave, [])[:3]:
            fig.text(x + 0.03, yy, d["cifra"], fontsize=30, weight="bold", family=num,
                     color=theme.TEXT, va="center")
            fig.text(x + 0.03, yy - 0.029, d["texto"], fontsize=13.5, color=theme.MUTED,
                     va="center")
            yy -= 0.076
    fig.text(0.5, base + alto / 2, "VS", fontsize=26, weight="bold", color=theme.MUTED,
             va="center", ha="center", family=num)

    if l.get("remate"):
        r = l["remate"]
        alto_r = 0.13
        y_r = base - 0.035 - alto_r
        _caja(fig, X0, y_r, ANCHO, alto_r, theme.ACCENT)
        fig.text(X0 + 0.035, y_r + alto_r - 0.040, r["cifra"], fontsize=46, weight="bold",
                 color=theme.BG, va="center", family=num)
        fig.text(X0 + 0.035, y_r + 0.036, r["texto"], fontsize=17, color=theme.BG,
                 va="center", linespacing=1.3)


def _cifras(fig, num, l, eq, y):
    items = l["items"]
    disponible = y - 0.10
    paso = min(0.14, disponible / max(len(items), 1))
    ancho_cifra = l.get("ancho_cifra", 0.25)
    for it in items:
        alto = paso - 0.014
        _caja(fig, X0, y - alto, ANCHO, alto, theme.SURFACE)
        color = (theme.LVBP if es_venezolano(it)
                 else eq[it["equipo"]]["color"] if it.get("equipo") in eq else theme.ACCENT)
        _caja(fig, X0, y - alto, 0.008, alto, color, r=0.003)
        fig.text(X0 + 0.03, y - alto / 2, it["cifra"], fontsize=it.get("tamano", 40),
                 weight="bold", color=color, va="center", family=num)
        fig.text(X0 + 0.03 + ancho_cifra, y - alto / 2, it["texto"], fontsize=15.5,
                 color=theme.TEXT, va="center", linespacing=1.3)
        y -= paso


def _barras(fig, num, l, eq, y):
    barras = l["barras"]
    tope = max(b["valor"] for b in barras)
    paso = 0.115
    y -= 0.045
    for b in barras:
        color = eq[b["equipo"]]["color"] if b.get("equipo") in eq else theme.MUTED
        fig.text(X0, y + 0.010, b["etiqueta"], fontsize=22, weight="bold", color=theme.TEXT,
                 va="center")
        if b.get("detalle"):
            fig.text(X0, y - 0.020, b["detalle"], fontsize=13, color=theme.MUTED,
                     va="center")
        largo = 0.44 * b["valor"] / tope
        _caja(fig, 0.33, y - 0.026, largo, 0.052, color, r=0.006)
        fig.text(0.33 + largo + 0.015, y, b["texto"], fontsize=23, weight="bold",
                 color=theme.TEXT, va="center", family=num)
        y -= paso
    if l.get("conclusion"):
        c = l["conclusion"]
        alto = 0.15
        y -= 0.03
        _caja(fig, X0, y - alto, ANCHO, alto, theme.SURFACE)
        fig.text(X0 + 0.035, y - alto / 2, c["cifra"], fontsize=48, weight="bold",
                 color=theme.ACCENT, va="center", family=num)
        fig.text(X0 + 0.035 + l.get("ancho_cifra", 0.24), y - alto / 2, c["texto"],
                 fontsize=16, color=theme.TEXT, va="center", linespacing=1.3)


def _cara_a_cara(fig, num, l, eq, y):
    xa, xb = 0.60, 0.84             # centros de las columnas de cada equipo
    for clave, x in (("A", xa), ("B", xb)):
        fig.text(x, y, eq[clave]["nombre"].upper(), fontsize=17, weight="bold",
                 color=eq[clave]["color"], va="center", ha="center")
    y -= 0.040
    filas = l["filas"]
    paso = min(0.064, (y - 0.10) / max(len(filas), 1))
    for i, f in enumerate(filas):
        if i % 2 == 0:
            _caja(fig, X0 - 0.01, y - paso / 2, ANCHO + 0.02, paso, theme.SURFACE, r=0.008)
        fig.text(X0 + 0.01, y + 0.008, f["stat"], fontsize=16.5, color=theme.TEXT,
                 va="center", weight="bold")
        if f.get("ayuda"):
            fig.text(X0 + 0.01, y - 0.014, f["ayuda"], fontsize=10.5, color=theme.MUTED,
                     va="center")
        for clave, x in (("A", xa), ("B", xb)):
            gana = f.get("mejor") in (clave, "ambos")
            fig.text(x, y + 0.007, f[clave], fontsize=21, weight="bold", family=num,
                     color=eq[clave]["color"] if gana else theme.TEXT, va="center",
                     ha="center")
            if f.get("rank_" + clave):
                fig.text(x, y - 0.016, f["rank_" + clave], fontsize=10.5, family=num,
                         color=theme.MUTED, va="center", ha="center")
        y -= paso


def _camino(fig, num, l, eq, y):
    w = 0.425
    for i, clave in enumerate(("A", "B")):
        e, c = eq[clave], l["equipos"][clave]
        x = X0 if i == 0 else X1 - w
        yy = y
        fig.text(x, yy, e["nombre"].upper(), fontsize=22, weight="bold", color=e["color"],
                 va="center")
        yy -= 0.058
        fig.text(x, yy, c["record"], fontsize=48, weight="bold", family=num,
                 color=theme.TEXT, va="center")
        yy -= 0.045
        fig.text(x, yy, c["record_nota"], fontsize=14, color=theme.MUTED, va="top",
                 linespacing=1.35)
        yy -= 0.040 + 0.021 * c["record_nota"].count("\n")
        for s in c["series"]:
            alto = 0.118
            _caja(fig, x, yy - alto, w, alto, theme.SURFACE)
            fig.text(x + 0.022, yy - 0.026, s["ronda"].upper(), fontsize=12.5, family=num,
                     color=e["color"], va="center")
            fig.text(x + w - 0.022, yy - 0.030, s["resultado"], fontsize=24, weight="bold",
                     family=num, color=theme.TEXT, va="center", ha="right")
            fig.text(x + 0.022, yy - 0.060, s["rival"], fontsize=21, weight="bold",
                     color=theme.TEXT, va="center")
            if s.get("juegos"):
                fig.text(x + 0.022, yy - 0.093, "  ".join(s["juegos"]), fontsize=13,
                         family=num, color=theme.MUTED, va="center")
            yy -= alto + 0.018
        if c.get("cierre"):
            fig.text(x, yy - 0.012, c["cierre"], fontsize=15, color=theme.TEXT, va="top",
                     linespacing=1.4)


def _figuras(fig, num, l, eq, y):
    w = 0.425
    for i, clave in enumerate(("A", "B")):
        e = eq[clave]
        x = X0 if i == 0 else X1 - w
        fig.text(x, y, e["nombre"].upper(), fontsize=20, weight="bold", color=e["color"],
                 va="center")
        yy = y - 0.030
        jugadores = l["jugadores"][clave]
        paso = min(0.128, (yy - 0.095) / max(len(jugadores), 1))
        for j in jugadores:
            alto = paso - 0.012
            _caja(fig, x, yy - alto, w, alto, theme.SURFACE)
            ven = es_venezolano(j)
            _caja(fig, x, yy - alto, 0.007, alto, theme.LVBP if ven else e["color"], r=0.003)
            fig.text(x + 0.022, yy - 0.020, j["rol"].upper(), fontsize=10, family=num,
                     color=theme.MUTED, va="center")
            if j.get("pais"):
                fig.text(x + w - 0.016, yy - 0.020, j["pais"], fontsize=10.5,
                         color=theme.LVBP if ven else theme.MUTED, va="center", ha="right")
            fig.text(x + 0.022, yy - 0.046, j["nombre"], fontsize=18, weight="bold",
                     color=theme.LVBP if ven else theme.TEXT, va="center")
            fig.text(x + 0.022, yy - 0.072, j["linea"], fontsize=12, family=num,
                     color=theme.TEXT, va="center")
            if j.get("nota"):
                fig.text(x + 0.022, yy - 0.095, j["nota"], fontsize=11, color=theme.MUTED,
                         va="center")
            yy -= paso


TIPOS = {"cifras": _cifras, "barras": _barras, "cara_a_cara": _cara_a_cara,
         "camino": _camino, "figuras": _figuras}


def tipos_validos() -> set[str]:
    return set(TIPOS) | {"portada"}


def render_lamina(l: dict, equipos: dict, out_path: Path, pagina: str = "",
                  fuente: str = "Datos: MLB Stats API", handle: str = theme.HANDLE) -> Path:
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    if l["tipo"] == "portada":
        _portada(fig, num, l, equipos)
    else:
        y = _cabecera(fig, num, l)
        TIPOS[l["tipo"]](fig, num, l, equipos, y)
    _pie(fig, num, l, pagina, fuente, handle)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
