"""Especiales: publicaciones armadas a mano (no salen de un resultado del día).

Un especial es un JSON en `content/especiales/` con la portada, uno o más rosters y los textos
(caption de Instagram, hilo para X/Threads y guion). Con `"tipo": "historia"` es, en cambio,
una historia de Instagram de una sola lámina 1080x1920 (bloque "historia": titular, marcador,
figuras, dato y lo que viene), sin caption ni hilo. `generar` dibuja las láminas y deja la
carpeta igual que un paquete diario: resumen.json (formato "especial") y textos.json. Desde
ahí el envío a Telegram y el botón de publicar funcionan como siempre (pieza "1").
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from bpt import theme

SALIDA = Path("output/especiales")
PIEZA = "1"


class EspecialError(ValueError):
    pass


HISTORIA = "historia"
ARCHIVO_HISTORIA = "historia.png"


def cargar(archivo: Path) -> dict:
    datos = json.loads(Path(archivo).read_text(encoding="utf-8"))
    if datos.get("tipo") == HISTORIA:
        for campo in ("slug", "titular", "historia"):
            if campo not in datos:
                raise EspecialError(f"a la historia especial le falta '{campo}'")
        h = datos["historia"]
        for campo in ("titulo", "marcador"):
            if campo not in h:
                raise EspecialError(f"a la historia especial le falta 'historia.{campo}'")
        return datos
    for campo in ("slug", "titular", "rosters", "textos"):
        if campo not in datos:
            raise EspecialError(f"al especial le falta '{campo}'")
    t = datos["textos"]
    if not t.get("instagram") or not t.get("hilo_x"):
        raise EspecialError("el especial necesita caption de Instagram e hilo")
    return datos


def revisar_textos(t: dict) -> list[str]:
    """Las mismas comprobaciones que hacen los clientes antes de publicar."""
    from bpt.publicar import instagram, threads, x
    return (instagram.revisar_caption(t["instagram"]) + x.revisar(t["hilo_x"])
            + threads.revisar(t["hilo_x"]))


def paises(rosters: list[dict]) -> list[tuple[str, int]]:
    c = Counter(j["pais"] for r in rosters for j in r["jugadores"])
    # En los empates, Venezuela primero (regla de marca)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0].lower() != "venezuela", kv[0]))


def _generar_historia(datos: dict, carpeta: Path, handle: str) -> dict:
    """Historia especial: una lámina 1080x1920 con formato "historia" (sin caption), así el
    envío a Telegram y el botón 📲 funcionan igual que con la historia del día."""
    from bpt.viz.historia_especial_card import render_historia_especial
    render_historia_especial(datos["historia"], carpeta / ARCHIVO_HISTORIA,
                             fuente=datos.get("fuente", "Datos: MLB Stats API"), handle=handle)
    resumen = {"formato": HISTORIA, "especial": True, "slug": datos["slug"],
               "fecha": datos.get("fecha", ""), "titular": datos["titular"], "total": 1,
               "tarjetas": [ARCHIVO_HISTORIA], "ligas": {}}
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    resumen["carpeta"] = str(carpeta)
    resumen["alertas"] = []
    return resumen


def generar(archivo: Path, salida: Path = SALIDA, handle: str = theme.HANDLE) -> dict:
    from bpt.viz.roster_card import render_portada, render_roster

    datos = cargar(archivo)
    carpeta = Path(salida) / datos["slug"]
    carpeta.mkdir(parents=True, exist_ok=True)
    if datos.get("tipo") == HISTORIA:
        return _generar_historia(datos, carpeta, handle)
    fuente = datos.get("fuente", "Datos: Baseball-Reference")
    tarjetas = []

    if datos.get("portada"):
        p = datos["portada"]
        cuenta = paises(datos["rosters"])
        render_portada(p["titulo"], p.get("subtitulo", ""), cuenta,
                       sum(n for _, n in cuenta), carpeta / "01_portada.png",
                       pie=p.get("pie"), fuente=fuente, handle=handle)
        tarjetas.append("01_portada.png")
    for r in datos["rosters"]:
        render_roster(r["titulo"], r.get("subtitulo", ""), r["jugadores"],
                      carpeta / r["archivo"], nota_pie=r.get("nota_pie"), fuente=fuente,
                      handle=handle)
        tarjetas.append(r["archivo"])

    alertas = revisar_textos(datos["textos"])
    resumen = {"formato": "especial", "slug": datos["slug"], "fecha": datos.get("fecha", ""),
               "titular": datos["titular"], "tarjetas": tarjetas}
    textos = [{"game_pk": "especial", "titular": datos["titular"], "textos": datos["textos"],
               "validacion": {"ok": not alertas, "cifras_sin_respaldo": [], "alertas": alertas}}]
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (carpeta / "textos.json").write_text(json.dumps(textos, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    resumen["carpeta"] = str(carpeta)
    resumen["alertas"] = alertas
    return resumen
