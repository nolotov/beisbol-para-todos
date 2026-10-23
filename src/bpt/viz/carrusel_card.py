"""Láminas de carrusel por bloques (1080x1350) para especiales armados a mano.

Cada lámina es un dict con "tipo" y su contenido; sirven para previas, duelos y piezas de
datos que no salen de un resultado del día. Tipos:

  - portada:     dos equipos frente a frente con sus datos clave y una franja de remate.
  - cifras:      filas de "cifra grande + explicación" (historia, datos ocultos, etc.).
  - barras:      barras horizontales (nóminas, totales) con una conclusión debajo.
  - cara_a_cara: tabla de estadísticas de los dos equipos con su puesto en MLB.
  - camino:      cómo llegó cada equipo (récord y series de postemporada).
  - figuras:     los jugadores a seguir de cada equipo, en dos columnas.
  - portada_tema: portada de un tema que no es un duelo (un jugador, una liga, una racha):
                 titular, dato grande y hasta 3 datos de apoyo. No usa "equipos".

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


def _envolver(texto: str, por_linea: int) -> str:
    """Parte en líneas de hasta `por_linea` caracteres, respetando los \n del autor."""
    import textwrap
    return "\n".join(textwrap.fill(p, max(por_linea, 8)) if len(p) > por_linea else p
                     for p in texto.split("\n"))


def _ajustado(fig, x, y, texto, ancho, alto=None, fontsize=15.5, minimo=9.0, **kw):
    """Texto que cabe en su caja: se parte en líneas y, si aun así no cabe en `ancho` (y
    `alto`, en fracción de la figura), se achica la letra hasta `minimo`. Así una
    explicación larga ("percentil 99 en velocidad de salida…") no se sale del recuadro."""
    renderer = fig.canvas.get_renderer()
    tam = fontsize
    while True:
        # caracteres por línea estimados con el ancho medio de un carácter (~0,5 em)
        por_linea = int(ancho * W * 72 / (tam * 0.5))
        t = fig.text(x, y, _envolver(texto, por_linea), fontsize=tam, **kw)
        caja = t.get_window_extent(renderer).transformed(fig.transFigure.inverted())
        cabe = caja.width <= ancho + 1e-6 and (alto is None or caja.height <= alto + 1e-6)
        if cabe or tam <= minimo:
            return t
        t.remove()
        tam = max(minimo, tam - 1)


def _ancho(fig, t) -> float:
    return t.get_window_extent(fig.canvas.get_renderer()).transformed(
        fig.transFigure.inverted()).width


def _cifra_y_texto(fig, x, y, cifra, texto, ancho_total, alto, ancho_cifra, tam_cifra,
                   tam_texto, color_cifra, color_texto, num, sep=0.025):
    """Cifra grande a la izquierda y su explicación a la derecha, sin pisarse.

    `ancho_cifra` es el espacio reservado (para que las filas queden alineadas); si la cifra
    real mide más ("2.27 vs. 1.30"), el texto se corre a su derecha y, si con eso al texto
    le queda menos del 40 % del ancho, la cifra se achica."""
    tam = tam_cifra
    while True:
        tc = fig.text(x, y, cifra, fontsize=tam, weight="bold", color=color_cifra,
                      va="center", family=num)
        w = _ancho(fig, tc)
        if w <= ancho_total * 0.6 or tam <= 18:
            break
        tc.remove()
        tam -= 2
    x_texto = x + max(ancho_cifra, w + sep)
    _ajustado(fig, x_texto, y, texto, x + ancho_total - x_texto, alto, fontsize=tam_texto,
              color=color_texto, va="center", linespacing=1.3)
    return tc


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
        _ajustado(fig, X0, 0.068, l["nota"], ANCHO, 0.04, fontsize=11.5, minimo=9,
                  color=theme.MUTED, va="center", linespacing=1.3)
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
            _ajustado(fig, x + 0.03, yy - 0.029, d["texto"], w - 0.05, 0.03, fontsize=13.5,
                      color=theme.MUTED, va="center")
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
        _ajustado(fig, X0 + 0.035, y_r + 0.036, r["texto"], ANCHO - 0.07, 0.06, fontsize=17,
                  color=theme.BG, va="center", linespacing=1.3)


def _portada_tema(fig, num, l, eq):
    fig.text(X0, 0.905, l.get("etiqueta", "MBP"), fontsize=15, color=theme.ACCENT, va="top",
             family=num)
    fig.text(X0, 0.870, l["titulo"], fontsize=l.get("tamano_titulo", 66), weight="bold",
             color=theme.TEXT, va="top", linespacing=0.92)
    lineas = l["titulo"].count("\n") + 1
    y = 0.870 - 0.074 * lineas - 0.022
    if l.get("subtitulo"):
        fig.text(X0, y, l["subtitulo"], fontsize=19, color=theme.MUTED, va="top",
                 linespacing=1.35)
        y -= 0.031 * (l["subtitulo"].count("\n") + 1) + 0.03
    d = l.get("dato")
    if d:
        alto = 0.20
        y -= alto
        color = theme.LVBP if es_venezolano(d) else theme.ACCENT
        _caja(fig, X0, y, ANCHO, alto, color)
        fig.text(X0 + 0.04, y + alto * 0.62, d["cifra"], fontsize=d.get("tamano", 72),
                 weight="bold", color=theme.BG, va="center", family=num)
        _ajustado(fig, X0 + 0.04, y + alto * 0.20, d["texto"], ANCHO - 0.08, 0.075,
                  fontsize=17, color=theme.BG, va="center", linespacing=1.3)
        y -= 0.03
    puntos = l.get("puntos", [])[:3]
    if puntos:
        n = len(puntos)
        sep = 0.02
        w = (ANCHO - sep * (n - 1)) / n
        alto = 0.17
        for i, p in enumerate(puntos):
            x = X0 + i * (w + sep)
            _caja(fig, x, y - alto, w, alto, theme.SURFACE)
            color = theme.LVBP if es_venezolano(p) else theme.ACCENT
            _caja(fig, x, y - 0.008, w, 0.008, color, r=0.003)
            fig.text(x + 0.025, y - 0.06, p["cifra"], fontsize=p.get("tamano", 34),
                     weight="bold", color=theme.TEXT, va="center", family=num)
            _ajustado(fig, x + 0.025, y - 0.12, p["texto"], w - 0.04, 0.08, fontsize=13,
                      color=theme.MUTED, va="center", linespacing=1.3)


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
        _cifra_y_texto(fig, X0 + 0.03, y - alto / 2, it["cifra"], it["texto"],
                       ANCHO - 0.05, alto - 0.014, ancho_cifra, it.get("tamano", 40), 15.5,
                       color, theme.TEXT, num)
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
            _ajustado(fig, X0, y - 0.020, b["detalle"], 0.33 - X0 - 0.01, 0.025, fontsize=13,
                      color=theme.MUTED, va="center")
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
        _cifra_y_texto(fig, X0 + 0.035, y - alto / 2, c["cifra"], c["texto"], ANCHO - 0.06,
                       alto - 0.02, l.get("ancho_cifra", 0.24), 48, 16, theme.ACCENT,
                       theme.TEXT, num)


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
            _ajustado(fig, X0 + 0.01, y - 0.014, f["ayuda"], 0.48 - X0, 0.02, fontsize=10.5,
                      minimo=8, color=theme.MUTED,
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
            _ajustado(fig, x, yy - 0.012, c["cierre"], w, max(yy - 0.11, 0.04), fontsize=15,
                      color=theme.TEXT, va="top", linespacing=1.4)


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
            _ajustado(fig, x + 0.022, yy - 0.072, j["linea"], w - 0.035, 0.02, fontsize=12,
                      minimo=8.5, family=num, color=theme.TEXT, va="center")
            if j.get("nota"):
                _ajustado(fig, x + 0.022, yy - 0.095, j["nota"], w - 0.035, 0.02, fontsize=11,
                          minimo=8, color=theme.MUTED, va="center")
            yy -= paso


TIPOS = {"cifras": _cifras, "barras": _barras, "cara_a_cara": _cara_a_cara,
         "camino": _camino, "figuras": _figuras}


# Tipos que dibujan a los dos equipos del duelo: necesitan "equipos" con A y B.
CON_EQUIPOS = {"portada", "cara_a_cara", "camino", "figuras"}


def tipos_validos() -> set[str]:
    return set(TIPOS) | {"portada", "portada_tema"}


def textos_encimados(fig, margen: float = 0.004) -> list[str]:
    """Control de diseño: textos que se pisan entre sí o que se salen de la lámina.
    Devuelve una descripción corta de cada choque (vacío = todo en orden)."""
    renderer = fig.canvas.get_renderer()
    inv = fig.transFigure.inverted()
    cajas = []
    for t in fig.texts:
        texto = t.get_text().strip()
        if texto:
            cajas.append((texto, t.get_window_extent(renderer).transformed(inv)))
    corto = lambda x: x.replace("\n", " ")[:28]  # noqa: E731
    problemas = []
    for texto, c in cajas:
        if c.x0 < -margen or c.x1 > 1 + margen or c.y0 < -margen or c.y1 > 1 + margen:
            problemas.append(f"«{corto(texto)}» se sale de la lámina")
    for i in range(len(cajas)):
        for j in range(i + 1, len(cajas)):
            (ta, a), (tb, b) = cajas[i], cajas[j]
            ancho = min(a.x1, b.x1) - max(a.x0, b.x0)
            alto = min(a.y1, b.y1) - max(a.y0, b.y0)
            if ancho > margen and alto > margen:
                problemas.append(f"«{corto(ta)}» pisa a «{corto(tb)}»")
    return problemas


def render_lamina(l: dict, equipos: dict, out_path: Path, pagina: str = "",
                  fuente: str = "Datos: MLB Stats API", handle: str = theme.HANDLE,
                  problemas: list | None = None) -> Path:
    """Dibuja la lámina. Con `problemas` (una lista), le agrega los textos encimados."""
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    equipos = equipos or {}
    if l["tipo"] == "portada":
        _portada(fig, num, l, equipos)
    elif l["tipo"] == "portada_tema":
        _portada_tema(fig, num, l, equipos)
    else:
        y = _cabecera(fig, num, l)
        TIPOS[l["tipo"]](fig, num, l, equipos, y)
    _pie(fig, num, l, pagina, fuente, handle)
    if problemas is not None:
        problemas.extend(textos_encimados(fig))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
