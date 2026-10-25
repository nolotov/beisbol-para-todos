"""Caption e hilo de los extras de un juego de la LVBP (resultado + figuras).

Se arman con plantilla, sin el redactor: cada cifra sale tal cual del box score que ya está
en el resumen.json, así que no hay nada que inventar ni que verificar, y no cuesta llamadas
a Claude. La revisión humana sigue siendo el botón de Telegram.
"""
from __future__ import annotations

import re

from bpt.publicar.x import MAX_TUIT, largo

HASHTAGS = "#LVBP #BéisbolVenezolano #MBP"
GS_DESTACADO = 50          # el mismo mínimo de la lámina de destacados de la jornada


def corto(nombre: str) -> str:
    """"Leones del Caracas" -> "Leones"; "Tiburones de La Guaira" -> "Tiburones"."""
    return re.split(r"\s+del?\s+", nombre or "", maxsplit=1)[0] or nombre


def _marcador(j: dict) -> str:
    v, l = j["visitante"], j["local"]
    extra = f" ({len(j['entradas'])} entradas)" if j.get("extra_innings") else ""
    return f"{corto(v['nombre'])} {v['carreras']}, {corto(l['nombre'])} {l['carreras']}{extra}"


def _ganador_perdedor(j: dict) -> tuple[dict, dict]:
    v, l = j["visitante"], j["local"]
    return (v, l) if v.get("ganador") else (l, v)


def _decisiones(j: dict) -> str:
    partes = []
    for sigla, campo in (("G", "ganador_pitcher"), ("P", "perdedor_pitcher"),
                         ("S", "salvado_pitcher")):
        if j.get(campo):
            partes.append(f"{sigla}: {j[campo]}")
    return " · ".join(partes)


def _jonrones(f: dict) -> str:
    return ", ".join(f"{h['nombre']} ({h['equipo']})" + (f" ×{h['cantidad']}"
                                                         if h.get("cantidad", 1) > 1 else "")
                     for h in f.get("jonrones") or [])


def _orden(j: dict) -> list[str]:
    g, p = _ganador_perdedor(j)
    return [g["abrev"], p["abrev"]]


def caption(j: dict) -> str:
    g, p = _ganador_perdedor(j)
    lineas = [f"⚾ {_marcador(j)}", ""]
    frase = f"Los {corto(g['nombre'])} se llevan el juego"
    if j.get("estadio"):
        frase += f" en el {j['estadio']}"
    if g.get("record") and p.get("record"):
        frase += (f". Quedan {g['record']}; los {corto(p['nombre'])}, {p['record']}.")
    else:
        frase += "."
    lineas.append(frase)
    f = j.get("figuras") or {}
    bateo = f.get("mejor_bateo") or {}
    pitcheo = f.get("mejor_pitcheo") or {}
    figuras = [f"• {eq}: {bateo[eq]['nombre']}, {bateo[eq]['linea']}"
               for eq in _orden(j) if eq in bateo]
    figuras += [f"• {eq}: {pitcheo[eq]['nombre']}, {pitcheo[eq]['linea']}"
                for eq in _orden(j)
                if eq in pitcheo and pitcheo[eq].get("game_score", 0) >= GS_DESTACADO]
    if figuras:
        lineas += ["", "🔥 Figuras", *figuras]
    if _jonrones(f):
        lineas.append(f"💣 Jonrones: {_jonrones(f)}")
    if _decisiones(j):
        lineas.append(f"🧢 {_decisiones(j)}")
    lineas += ["", HASHTAGS]
    return "\n".join(lineas)


def hilo(j: dict) -> list[str]:
    """Un solo tuit (también va a Threads). Si no cabe, se van cayendo los detalles."""
    f = j.get("figuras") or {}
    bateo = f.get("mejor_bateo") or {}
    g, _ = _ganador_perdedor(j)
    partes = [f"⚾ LVBP | {_marcador(j)}"]
    detalles = []
    if g["abrev"] in bateo:
        b = bateo[g["abrev"]]
        detalles.append(f"🔥 {b['nombre']} ({g['abrev']}): {b['linea']}")
    if _jonrones(f):
        detalles.append(f"💣 HR: {_jonrones(f)}")
    if _decisiones(j):
        detalles.append(_decisiones(j))
    while True:
        cuerpo = "\n\n".join([partes[0], "\n".join(detalles)] if detalles else partes)
        tuit = f"{cuerpo}\n\n#LVBP"
        if largo(tuit) <= MAX_TUIT or not detalles:
            return [tuit]
        detalles.pop()
