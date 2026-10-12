"""Agente redactor: resumen.json -> caption de Instagram, hilo de X y guion de Short.

Flujo por juego:
1. Pide las tres piezas a Claude con salida estructurada (output_config, JSON Schema).
2. Las valida contra los datos.
3. Si hay cifras sin respaldo, le devuelve la lista al modelo y le pide corregir (1 vez).
4. Guarda todo con su validación. Nada se publica solo: el estado es siempre
   "para revisar" o "con alertas".

Necesita ANTHROPIC_API_KEY en el entorno (en GitHub Actions, como secreto).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from bpt.redactor import prompt
from bpt.redactor.validador import validar

MODELO = os.environ.get("BPT_MODELO", "claude-sonnet-5-5")
# El razonamiento interno del modelo cuenta dentro de max_tokens: hay que dejar espacio.
MAX_TOKENS = 16000
# Esfuerzo de razonamiento: para redactar captions alcanza con "low" (más rápido y barato).
ESFUERZO = os.environ.get("BPT_ESFUERZO", "low")


ORIGEN_LLAVE = "entorno"  # de dónde salió la llave: ".env" o "entorno"


def cargar_env(path: Path = Path(".env")) -> None:
    """Carga KEY=VALOR de un archivo .env (no versionado).

    El .env manda sobre el entorno: si en la ventana de PowerShell quedó una variable vieja
    (por ejemplo de un `$env:ANTHROPIC_API_KEY = ...` de prueba), se reemplaza y se avisa.
    """
    global ORIGEN_LLAVE
    if not path.exists():
        return
    for linea in path.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        previo = os.environ.get(k)
        if previo is not None and previo != v and k == "ANTHROPIC_API_KEY":
            print(f"[aviso] Había otra ANTHROPIC_API_KEY en el entorno ({cola(previo)}); "
                  f"uso la del .env ({cola(v)})", file=sys.stderr)
        os.environ[k] = v
        if k == "ANTHROPIC_API_KEY":
            ORIGEN_LLAVE = ".env"


def cola(llave: str) -> str:
    """Solo los últimos 4 caracteres, como los muestra la Consola: '…AbCd'."""
    return f"…{llave[-4:]}" if llave and len(llave) > 8 else "(vacía o muy corta)"


class LlaveInvalida(RuntimeError):
    pass


def _cliente():
    import anthropic

    cargar_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("Falta ANTHROPIC_API_KEY: ponla en un archivo .env en la raíz del "
                           "proyecto (ANTHROPIC_API_KEY=sk-ant-...) o en el entorno")
    return anthropic.Anthropic()


def _pedir(client, mensajes: list[dict], modelo: str,
           sistema: str = prompt.SISTEMA) -> tuple[dict, object]:
    try:
        r = _crear(client, mensajes, modelo, sistema)
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError"):
            llave = os.environ.get("ANTHROPIC_API_KEY", "")
            raise LlaveInvalida(
                f"La API rechazó la llave {cola(llave)} (tomada de: {ORIGEN_LLAVE}, "
                f"{len(llave)} caracteres). Compárala con la lista de Settings → API keys en "
                "platform.claude.com: si los últimos 4 no coinciden o la llave no aparece, "
                "crea una nueva y pégala completa en el .env") from None
        raise
    texto = "".join(b.text for b in r.content if b.type == "text")
    try:
        return json.loads(texto), r
    except json.JSONDecodeError as e:
        motivo = getattr(r, "stop_reason", "?")
        pista = (" Se quedó sin espacio: sube MAX_TOKENS o baja BPT_ESFUERZO."
                 if motivo == "max_tokens" else "")
        raise RuntimeError(f"El modelo no devolvió JSON válido (stop_reason={motivo})."
                           f"{pista} Inicio: {texto[:200]!r}") from e


def _crear(client, mensajes: list[dict], modelo: str, sistema: str = prompt.SISTEMA):
    return client.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        system=sistema,
        output_config={"format": {"type": "json_schema", "schema": prompt.ESQUEMA},
                       "effort": ESFUERZO},
        messages=mensajes,
    )


def verificar_llave() -> str:
    """Prueba la llave con una llamada que no consume créditos (listar modelos)."""
    client = _cliente()
    llave = os.environ.get("ANTHROPIC_API_KEY", "")
    try:
        modelos = [m.id for m in client.models.list(limit=20)]
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError"):
            raise LlaveInvalida(f"La API rechazó la llave {cola(llave)} (tomada de: "
                                f"{ORIGEN_LLAVE}, {len(llave)} caracteres)") from None
        raise
    ok = MODELO in modelos
    return (f"Llave {cola(llave)} válida (tomada de: {ORIGEN_LLAVE}). "
            f"Modelo {MODELO}: {'disponible' if ok else 'NO aparece en tu cuenta'}")


def _redactar(datos: dict, mensaje: str, client, modelo: str, reintentos: int,
              sistema: str = prompt.SISTEMA):
    """Pide las piezas, valida y reintenta si hay cifras sin respaldo."""
    mensajes = [{"role": "user", "content": mensaje}]
    textos, resp = _pedir(client, mensajes, modelo, sistema)
    val = validar(textos, datos)
    intentos = 1
    while val.cifras_sin_respaldo and intentos <= reintentos:
        mensajes += [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": (
                "Estas cifras no aparecen en los datos: "
                f"{', '.join(val.cifras_sin_respaldo)}. Quítalas o reemplázalas por cifras que "
                "sí estén en los datos (sin sumas ni cálculos propios) y entrega de nuevo las "
                "tres piezas completas.")},
        ]
        textos, resp = _pedir(client, mensajes, modelo, sistema)
        val = validar(textos, datos)
        intentos += 1
    return textos, val, intentos


def redactar_jornada(resumen: dict, client=None, modelo: str | None = None,
                     reintentos: int = 1) -> dict:
    """LVBP: un caption, un hilo y un guion para toda la jornada."""
    client = client or _cliente()
    modelo = modelo or MODELO
    datos = prompt.datos_jornada(resumen)
    textos, val, intentos = _redactar(datos, prompt.mensaje_jornada(resumen), client, modelo,
                                      reintentos, prompt.SISTEMA + prompt.SISTEMA_JORNADA)
    n = len(resumen["juegos"])
    return {
        "game_pk": "jornada",
        "partido": f"Jornada LVBP {resumen['fecha']}",
        "titular": f"LVBP · {n} juego{'s' if n != 1 else ''} el {resumen['fecha']}",
        "tarjetas": resumen.get("tarjetas", []),
        "textos": textos,
        "validacion": val.to_dict(),
        "estado": "para revisar" if val.ok else "con alertas",
        "intentos": intentos,
        "modelo": modelo,
    }


def redactar_juego(juego: dict, resumen: dict, client=None, modelo: str | None = None,
                   reintentos: int = 1) -> dict:
    client = client or _cliente()
    modelo = modelo or MODELO
    datos = prompt.datos_juego(juego, resumen)
    textos, val, intentos = _redactar(datos, prompt.mensaje_usuario(juego, resumen), client,
                                      modelo, reintentos)
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
    if resumen.get("formato") == "jornada":
        resultados = [redactar_jornada(resumen, client=client, modelo=modelo)]
    else:
        resultados = [redactar_juego(j, resumen, client=client, modelo=modelo)
                      for j in resumen["juegos"]]
    (carpeta / "textos.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "textos.md").write_text(
        "\n\n---\n\n".join(a_markdown(r) for r in resultados), encoding="utf-8")
    return resultados
