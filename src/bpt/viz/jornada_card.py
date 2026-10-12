"""Carrusel de la jornada LVBP (1080x1350): marcadores y destacados del día."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from bpt import theme
from bpt.data.mlb_stats import FUENTE_LVBP, Juego
from bpt.viz.result_card import W, H, _panel, fecha_es


def _apellido(nombre: str | None) -> str:
    if not nombre:
        return "—"
    partes = nombre.split()
    return " ".join(partes[1:]) if len(partes) > 1 else nombre


def _tag(fig, x, y, codigo, num, ancho=0.075):
    fig.add_artist(FancyBboxPatch((x, y - 0.012), ancho, 0.024,
                                  boxstyle="round,pad=0,rounding_size=0.005",
                                  transform=fig.transFigure, color=theme.LVBP))
    fig.text(x + ancho / 2, y, codigo, fontsize=11.5, weight="bold", color=theme.BG,
             ha="center", va="center", family=num)


def _cabecera(fig, num, temporada: str, titulo: str, subtitulo: str):
    fig.text(0.06, 0.955, f"MBP  ·  LVBP {temporada}", fontsize=14,
             color=theme.LVBP, va="top", family=num)
    fig.text(0.06, 0.915, titulo, fontsize=56, weight="bold", color=theme.TEXT, va="top")
    fig.text(0.06, 0.838, subtitulo, fontsize=17, color=theme.MUTED, va="top")


def _pie(fig, num, fecha: str, handle: str, nota: str | None = None):
    if nota:
        fig.text(0.06, 0.085, nota, fontsize=9.5, color=theme.MUTED, va="center", family=num)
    fig.text(0.06, 0.055, f"{fecha_es(fecha)}  ·  {FUENTE_LVBP}", fontsize=10,
             color=theme.MUTED, va="center", family=num)
    fig.text(0.94, 0.055, handle, fontsize=15, color=theme.TEXT, va="center", ha="right",
             weight="bold")


def _guardar(fig, out_path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path


def render_jornada_card(juegos: list[Juego], fecha: str, temporada: str, out_path: Path,
                        pendientes: list[dict] | None = None,
                        handle: str = theme.HANDLE) -> Path:
    """Lámina 1: un panel por juego terminado, con récords y decisiones."""
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    n = len(juegos)
    _cabecera(fig, num, temporada, "LA JORNADA",
              f"{n} juego{'s' if n != 1 else ''}  ·  {fecha_es(fecha)}")

    px, pw, top, bottom = 0.04, 0.92, 0.80, 0.13 if pendientes else 0.11
    gap = 0.015
    alto = min(0.165, (top - bottom - gap * (n - 1)) / max(n, 1))
    for i, j in enumerate(juegos):
        y0 = top - (i + 1) * alto - i * gap
        _panel(fig, [px, y0, pw, alto], rounding=0.02)
        for k, eq in enumerate([j.visitante, j.local]):
            y = y0 + alto * (0.72 - 0.34 * k)
            color = theme.TEXT if eq.ganador else theme.MUTED
            if eq.ganador:
                fig.add_artist(FancyBboxPatch((px + 0.018, y - 0.017), 0.006, 0.034,
                                              boxstyle="round,pad=0,rounding_size=0.003",
                                              transform=fig.transFigure, color=theme.LVBP))
            fig.text(px + 0.04, y, eq.abrev, fontsize=24, weight="bold", color=color,
                     va="center")
            fig.text(px + 0.14, y, eq.nombre, fontsize=14, color=color, va="center")
            if eq.record:
                fig.text(px + 0.60, y, f"({eq.record})", fontsize=12, color=theme.MUTED,
                         va="center", ha="right", family=num)
            fig.text(px + pw - 0.04, y, str(eq.carreras), fontsize=34, weight="bold",
                     color=theme.LVBP if eq.ganador else theme.MUTED, va="center",
                     ha="right", family=num)
        dec = f"G: {_apellido(j.ganador_pitcher)}   P: {_apellido(j.perdedor_pitcher)}"
        if j.salvado_pitcher:
            dec += f"   S: {_apellido(j.salvado_pitcher)}"
        extra = f"  ·  {len(j.entradas)} entradas" if j.extra_innings else ""
        fig.text(px + 0.04, y0 + alto * 0.11, dec + extra, fontsize=10.5, color=theme.MUTED,
                 va="center", family=num)

    if pendientes:
        txt = "  ·  ".join(f"{p['partido']}: {p['estado'].lower()}" for p in pendientes)
        fig.text(0.06, 0.112, f"Sin terminar: {txt}", fontsize=10, color=theme.MUTED,
                 va="center", family=num)
    _pie(fig, num, fecha, handle, "Entre paréntesis: récord después del juego.  "
                                  "G: ganador · P: perdedor · S: salvado.")
    return _guardar(fig, out_path)


def render_destacados_card(dest: dict, fecha: str, temporada: str, out_path: Path,
                           handle: str = theme.HANDLE) -> Path:
    """Lámina 2: los mejores de la jornada al bate y en la loma, y los jonrones."""
    fonts = theme.apply()
    num = fonts["number"]
    fig = plt.figure(figsize=(W, H), dpi=100)
    _cabecera(fig, num, temporada, "DESTACADOS", f"de la jornada  ·  {fecha_es(fecha)}")

    px, pw, paso = 0.04, 0.92, 0.062

    def seccion(top, titulo, etiqueta, filas, vacio):
        h = 0.07 + max(len(filas), 1) * paso
        y0 = top - h
        _panel(fig, [px, y0, pw, h])
        fig.text(px + 0.03, top - 0.025, titulo, fontsize=11, color=theme.MUTED, va="top",
                 family=num)
        fig.text(px + pw - 0.03, top - 0.025, etiqueta, fontsize=9, color=theme.MUTED,
                 va="top", ha="right", family=num)
        if not filas:
            fig.text(px + 0.03, y0 + h / 2 - 0.01, vacio, fontsize=14,
                     color=theme.MUTED, va="center")
        for i, f in enumerate(filas):
            y = top - 0.075 - i * paso
            _tag(fig, px + 0.03, y + 0.004, f["equipo"], num)
            fig.text(px + 0.12, y + 0.008, f["nombre"], fontsize=16, weight="bold",
                     color=theme.TEXT, va="center")
            fig.text(px + 0.12, y - 0.017, f"vs. {f['rival']}  ·  {f['linea']}", fontsize=10.5,
                     color=theme.MUTED, va="center", family=num)
            fig.text(px + pw - 0.03, y, str(f["valor"]), fontsize=20, weight="bold",
                     color=theme.LVBP, va="center", ha="right", family=num)
        return y0

    y = seccion(0.80, "AL BATE", "BASES GANADAS", dest.get("bateo", []),
                "Nadie llegó a 3 bases ganadas")
    y = seccion(y - 0.02, "EN LA LOMA", "GAME SCORE", dest.get("pitcheo", []),
                "Ninguna salida de 3+ entradas con Game Score de 50 o más")

    hrs = dest.get("jonrones", [])
    if hrs and y - 0.02 > 0.16:
        txt = "  ·  ".join(f"{h['nombre']} ({h['equipo']}){' x' + str(h['cantidad']) if h['cantidad'] > 1 else ''}"
                           for h in hrs[:6])
        if len(hrs) > 6:
            txt += f"  y {len(hrs) - 6} más"
        fig.text(0.06, y - 0.045, "JONRONES", fontsize=11, color=theme.MUTED, va="center",
                 family=num)
        fig.text(0.06, y - 0.075, txt, fontsize=12, color=theme.TEXT, va="center", wrap=True)

    _pie(fig, num, fecha, handle, "Bases ganadas: totales + boletos + pelotazos + robos.  "
                                  "Game Score: nota de la salida (3+ IL, 50 o más).")
    return _guardar(fig, out_path)
