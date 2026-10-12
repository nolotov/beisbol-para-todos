"""Agente redactor: resumen.json -> caption de Instagram, hilo de X y guion de Short.

Flujo por juego:
1. Pide las tres piezas a Claude con salida estructurada (herramienta obligatoria).
2. Las valida contra los datos.
3. Si hay cifras sin respaldo, le devuelve la lista al modelo y le pide corregir (1 vez).
4. Guarda todo con su validación. Nada se publica solo: el estado es siempre
   "para revisar" o "con alertas".

Necesita ANTHROPIC_API_KEY en el entorno (en GitHub Actions, como secreto).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from bpt.redactor import prompt
from bpt.redactor.validador import validar

MODELO = os.environ.get("BPT_MODELO", "claude-sonnet-5-5")
MAX_TOKENS = 2500


def cargar_env(path: Path = Path(".env")) -> None:
    """Carga KEY=VALOR de un archivo .env (no versionado) sin pisar variables ya definidas."""
    if not path.exists():
        return
    for linea in path.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _cliente():
    import anthropic

    cargar_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Falta ANTHROPIC_API_KEY: ponla en un archivo .env en la raíz del "
                           "proyecto (ANTHROPIC_API_KEY=sk-ant-...) o en el entorno")
    return anthropic.Anthropic()


def _pedir(client, mensajes: list[dict], modelo: str) -> tuple[dict, object, object]:
    r = client.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        system=prompt.SISTEMA,
        tools=[prompt.TOOL],
        tool_choice={"type": "tool", "name": prompt.TOOL["name"]},
        messages=mensajes,
    )
    bloque = next(b for b in r.content if b.type == "tool_use")
    return bloque.input, r, bloque


def redactar_juego(juego: dict, resumen: dict, client=None, modelo: str | None = None,
                   reintentos: int = 1) -> dict:
    client = client or _cliente()
    modelo = modelo or MODELO
    datos = prompt.datos_juego(juego, resumen)
    mensajes = [{"role": "user", "content": prompt.mensaje_usuario(juego, resumen)}]
    textos, resp, bloque = _pedir(client, mensajes, modelo)
    val = validar(textos, datos)
    intentos = 1

    while val.cifras_sin_respaldo and intentos <= reintentos:
        mensajes += [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": bloque.id,
                "is_error": True,
                "content": ("Estas cifras no aparecen en los datos del juego: "
                            f"{', '.join(val.cifras_sin_respaldo)}. Quítalas o reemplázalas "
                            "por cifras que sí estén en los datos (sin sumas ni cálculos "
                            "propios) y entrega de nuevo las tres piezas completas."),
            }]},
        ]
        textos, resp, bloque = _pedir(client, mensajes, modelo)
        val = validar(textos, datos)
        intentos += 1

    return {
        "game_pk": juego.get("game_pk"),
        "partido": f"{juego['visitante']['abrev']} @ {juego['local']['abrev']}",
        "titular": juego.get("titular"),
        "tarjetas": juego.get("tarjetas", []),
        "textos": textos,
        "validacion": val.to_dict(),
        "estado": "para revisar" if val.ok else "con alertas",
        "intentos": intentos,
        "modelo": modelo,
    }


def a_markdown(r: dict) -> str:
    v = r["validacion"]
    lineas = [f"# {r['titular']}", "",
              f"**Estado:** {r['estado']}  ·  tarjetas: {', '.join(r['tarjetas'])}", ""]
    if not v["ok"]:
        lineas.append("> ⚠️ **Revisar antes de publicar**")
        if v["cifras_sin_respaldo"]:
            lineas.append(f"> Cifras sin respaldo en los datos: {', '.join(v['cifras_sin_respaldo'])}")
        lineas += [f"> {a}" for a in v["alertas"]]
        lineas.append("")
    t = r["textos"]
    lineas += [f"_Ángulo: {t.get('angulo', '')}_", "", "## Instagram", "", t["instagram"], "",
               "## Hilo de X", ""]
    lineas += [f"{i}. {tw}\n" for i, tw in enumerate(t["hilo_x"], 1)]
    lineas += ["## Guion (30-45 s)", "", t["guion"], ""]
    return "\n".join(lineas)


def redactar_dia(carpeta: Path, client=None, modelo: str | None = None) -> list[dict]:
    """Lee `carpeta/resumen.json`, redacta cada juego y escribe textos.json y textos.md."""
    carpeta = Path(carpeta)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    if not resumen["juegos"]:
        return []
    client = client or _cliente()
    resultados = [redactar_juego(j, resumen, client=client, modelo=modelo)
                  for j in resumen["juegos"]]
    (carpeta / "textos.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "textos.md").write_text(
        "\n\n---\n\n".join(a_markdown(r) for r in resultados), encoding="utf-8")
    return resultados
