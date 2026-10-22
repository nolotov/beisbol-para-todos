"""Especiales: publicaciones armadas a mano (no salen de un resultado del día).

Un especial es un JSON en `content/especiales/` con la portada, uno o más rosters y los textos
(caption de Instagram, hilo para X/Threads y guion). En vez de rosters puede traer
"laminas" (carrusel por bloques: portada, cifras, barras, cara_a_cara, camino, figuras; ver
`bpt.viz.carrusel_card`) con los dos "equipos" del duelo. Con `"tipo": "historia"` es, en cambio,
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
    """Lee y valida un especial. Si trae "evidencia_archivo" (ruta relativa al JSON), la
    evidencia se carga de ahí."""
    archivo = Path(archivo)
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    if datos.get("evidencia_archivo") and "evidencia" not in datos:
        ruta = archivo.parent / datos["evidencia_archivo"]
        datos["evidencia"] = json.loads(ruta.read_text(encoding="utf-8"))
    return validar_estructura(datos)


def validar_estructura(datos: dict) -> dict:
    if datos.get("tipo") == HISTORIA:
        for campo in ("slug", "titular", "historia"):
            if campo not in datos:
                raise EspecialError(f"a la historia especial le falta '{campo}'")
        h = datos["historia"]
        for campo in ("titulo", "marcador"):
            if campo not in h:
                raise EspecialError(f"a la historia especial le falta 'historia.{campo}'")
        return datos
    for campo in ("slug", "titular", "textos"):
        if campo not in datos:
            raise EspecialError(f"al especial le falta '{campo}'")
    if not datos.get("rosters") and not datos.get("laminas"):
        raise EspecialError("al especial le faltan 'rosters' o 'laminas'")
    if datos.get("laminas"):
        from bpt.viz.carrusel_card import CON_EQUIPOS, tipos_validos
        for i, l in enumerate(datos["laminas"], 1):
            if l.get("tipo") not in tipos_validos():
                raise EspecialError(f"lámina {i}: tipo desconocido '{l.get('tipo')}'")
        usa_equipos = any(l["tipo"] in CON_EQUIPOS for l in datos["laminas"])
        if (usa_equipos or datos.get("equipos")) and set(datos.get("equipos", {})) != {"A", "B"}:
            raise EspecialError("un especial con duelo necesita 'equipos' con A y B")
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


def verificar(datos: dict, evidencia: list | None = None):
    """Verificador de cifras (bpt.verificador). Los hechos contra MLB Stats API se pueden
    apagar con BPT_VERIFICAR_HECHOS=0 (sin red)."""
    import os

    from bpt import verificador
    hechos = os.environ.get("BPT_VERIFICAR_HECHOS", "1") != "0"
    return verificador.verificar(datos, evidencia=evidencia, hechos=hechos)


def _generar_historia(datos: dict, carpeta: Path, handle: str,
                      evidencia: list | None = None) -> dict:
    """Historia especial: una lámina 1080x1920 con formato "historia" (sin caption), así el
    envío a Telegram y el botón 📲 funcionan igual que con la historia del día."""
    from bpt.viz.historia_especial_card import render_historia_especial
    render_historia_especial(datos["historia"], carpeta / ARCHIVO_HISTORIA,
                             fuente=datos.get("fuente", "Datos: MLB Stats API"), handle=handle)
    ver = verificar(datos, evidencia)
    resumen = {"formato": HISTORIA, "especial": True, "slug": datos["slug"],
               "fecha": datos.get("fecha", ""), "titular": datos["titular"], "total": 1,
               "tarjetas": [ARCHIVO_HISTORIA], "ligas": {}, "verificacion": ver.to_dict()}
    if datos.get("editor"):
        resumen["editor"] = datos["editor"]
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    resumen["carpeta"] = str(carpeta)
    resumen["alertas"] = _alertas_verificacion(ver)
    return resumen


def _alertas_verificacion(ver) -> list[str]:
    salida = list(ver.alertas)
    if ver.cifras_sin_respaldo:
        salida.append("cifras sin respaldo: " + ", ".join(ver.cifras_sin_respaldo))
    return salida


def generar(archivo: Path, salida: Path = SALIDA, handle: str = theme.HANDLE,
            evidencia: list | None = None) -> dict:
    """Dibuja el especial y lo deja listo para Telegram. `evidencia` (lista de datos
    consultados) reemplaza a la que traiga el JSON; con ella, cada cifra se contrasta."""
    datos = cargar(archivo)
    return generar_datos(datos, salida, handle, evidencia)


def generar_datos(datos: dict, salida: Path = SALIDA, handle: str = theme.HANDLE,
                  evidencia: list | None = None) -> dict:
    from bpt.viz.roster_card import render_portada, render_roster

    validar_estructura(datos)
    carpeta = Path(salida) / datos["slug"]
    carpeta.mkdir(parents=True, exist_ok=True)
    if datos.get("tipo") == HISTORIA:
        return _generar_historia(datos, carpeta, handle, evidencia)
    fuente = datos.get("fuente", "Datos: Baseball-Reference")
    tarjetas = []

    if datos.get("portada"):
        p = datos["portada"]
        cuenta = paises(datos.get("rosters", []))
        render_portada(p["titulo"], p.get("subtitulo", ""), cuenta,
                       sum(n for _, n in cuenta), carpeta / "01_portada.png",
                       pie=p.get("pie"), fuente=fuente, handle=handle)
        tarjetas.append("01_portada.png")
    laminas = datos.get("laminas", [])
    if laminas:
        from bpt.viz.carrusel_card import render_lamina
        total = len(laminas)
        for i, l in enumerate(laminas, 1):
            nombre = f"{i:02d}_{l['tipo']}.png"
            render_lamina(l, datos.get("equipos", {}), carpeta / nombre, pagina=f"{i}/{total}",
                          fuente=fuente, handle=handle)
            tarjetas.append(nombre)
    for r in datos.get("rosters", []):
        render_roster(r["titulo"], r.get("subtitulo", ""), r["jugadores"],
                      carpeta / r["archivo"], nota_pie=r.get("nota_pie"), fuente=fuente,
                      handle=handle)
        tarjetas.append(r["archivo"])

    ver = verificar(datos, evidencia)
    alertas = revisar_textos(datos["textos"]) + ver.alertas
    sin = ver.cifras_sin_respaldo
    resumen = {"formato": "especial", "slug": datos["slug"], "fecha": datos.get("fecha", ""),
               "titular": datos["titular"], "tarjetas": tarjetas,
               "verificacion": ver.to_dict()}
    if datos.get("editor"):
        resumen["editor"] = datos["editor"]
    textos = [{"game_pk": "especial", "titular": datos["titular"], "textos": datos["textos"],
               "validacion": {"ok": not (alertas or sin), "cifras_sin_respaldo": sin,
                              "alertas": alertas}}]
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (carpeta / "textos.json").write_text(json.dumps(textos, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    resumen["carpeta"] = str(carpeta)
    resumen["alertas"] = alertas + (["cifras sin respaldo: " + ", ".join(sin)] if sin else [])
    return resumen
