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
# Prompt caching del prompt de sistema: "auto" = solo si en la corrida habrá 2+ llamadas
# (escribir el caché cuesta 1,25x; si nadie lo lee después, sale más caro). "si" | "no".
CACHE = os.environ.get("BPT_CACHE", "auto")

# Precio de lista en US$ por millón de tokens (entrada, salida) y multiplicador de lectura
# del caché. Fuente: platform.claude.com/docs (models/overview y prompt-caching), oct-2026.
PRECIOS = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.05),
    "claude-opus-5-5": (4.0, 20.0, 0.05),
}
ESCRITURA_CACHE = 1.25   # caché de 5 minutos


def uso_de(resp) -> dict:
    u = getattr(resp, "usage", None)
    campo = lambda k: int(getattr(u, k, 0) or 0) if u is not None else 0  # noqa: E731
    return {"entrada": campo("input_tokens"), "salida": campo("output_tokens"),
            "cache_escrito": campo("cache_creation_input_tokens"),
            "cache_leido": campo("cache_read_input_tokens")}


def sumar_uso(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in ("entrada", "salida", "cache_escrito",
                                                   "cache_leido")}


def costo_usd(uso: dict, modelo: str) -> float | None:
    """Costo estimado con precios de lista (None si el modelo no está en la tabla)."""
    if modelo not in PRECIOS:
        return None
    pin, pout, lectura = PRECIOS[modelo]
    usd = (uso["entrada"] * pin + uso["cache_escrito"] * pin * ESCRITURA_CACHE
           + uso["cache_leido"] * pin * lectura + uso["salida"] * pout) / 1e6
    return round(usd, 5)


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
           sistema: str = prompt.SISTEMA, cachear: bool = False) -> tuple[dict, object]:
    try:
        r = _crear(client, mensajes, modelo, sistema, cachear)
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


def _crear(client, mensajes: list[dict], modelo: str, sistema: str = prompt.SISTEMA,
           cachear: bool = False):
    # Con caché, el sistema va como bloque con un punto de corte: las llamadas siguientes
    # (mismo modelo, mismo sistema, mismos parámetros) lo leen al 5 % del precio.
    system = ([{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]
              if cachear else sistema)
    return client.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        system=system,
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
              sistema: str = prompt.SISTEMA, cachear: bool = False):
    """Pide las piezas, valida y reintenta si hay cifras sin respaldo."""
    mensajes = [{"role": "user", "content": mensaje}]
    textos, resp = _pedir(client, mensajes, modelo, sistema, cachear)
    uso = uso_de(resp)
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
        textos, resp = _pedir(client, mensajes, modelo, sistema, cachear)
        uso = sumar_uso(uso, uso_de(resp))
        val = validar(textos, datos)
        intentos += 1
    uso["cache_activo"] = cachear
    uso["costo_usd"] = costo_usd(uso, modelo)
    return textos, val, intentos, uso


def redactar_jornada(resumen: dict, client=None, modelo: str | None = None,
                     reintentos: int = 1, cachear: bool = False) -> dict:
    """LVBP: un caption, un hilo y un guion para toda la jornada."""
    client = client or _cliente()
    modelo = modelo or MODELO
    datos = prompt.datos_jornada(resumen)
    textos, val, intentos, uso = _redactar(datos, prompt.mensaje_jornada(resumen), client,
                                           modelo, reintentos,
                                           prompt.SISTEMA + prompt.SISTEMA_JORNADA, cachear)
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
        "uso": uso,
    }


def redactar_juego(juego: dict, resumen: dict, client=None, modelo: str | None = None,
                   reintentos: int = 1, cachear: bool = False) -> dict:
    client = client or _cliente()
    modelo = modelo or MODELO
    datos = prompt.datos_juego(juego, resumen)
    textos, val, intentos, uso = _redactar(datos, prompt.mensaje_usuario(juego, resumen),
                                           client, modelo, reintentos, cachear=cachear)
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
        "uso": uso,
    }


def a_markdown(r: dict) -> str:
    v = r["validacion"]
    lineas = [f"# {r['titular']}", "",
              f"**Estado:** {r['estado']}  ·  tarjetas: {', '.join(r['tarjetas'])}", ""]
    u = r.get("uso")
    if u:
        costo = f" · ~US$ {u['costo_usd']:.4f}" if u.get("costo_usd") is not None else ""
        lineas += [f"_Uso: {u['entrada'] + u['cache_escrito'] + u['cache_leido']} tokens de "
                   f"entrada ({u['cache_leido']} del caché), {u['salida']} de salida{costo}_", ""]
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


def decidir_cache(llamadas: int, modo: str | None = None) -> bool:
    """El caché solo paga si alguien lo lee: con 1 llamada, escribirlo sale más caro."""
    modo = (modo or CACHE).lower()
    if modo in ("si", "sí", "1", "true"):
        return True
    if modo in ("no", "0", "false"):
        return False
    return llamadas >= 2


def resumen_uso(resultados: list[dict]) -> dict:
    total = {"entrada": 0, "salida": 0, "cache_escrito": 0, "cache_leido": 0}
    costo, sin_precio = 0.0, False
    for r in resultados:
        u = r.get("uso") or {}
        total = sumar_uso(total, u)
        if u.get("costo_usd") is None:
            sin_precio = True
        else:
            costo += u["costo_usd"]
    total["costo_usd"] = None if sin_precio else round(costo, 5)
    return total


def redactar_dia(carpeta: Path, client=None, modelo: str | None = None) -> list[dict]:
    """Lee `carpeta/resumen.json`, redacta cada juego y escribe textos.json y textos.md."""
    carpeta = Path(carpeta)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    if not resumen["juegos"]:
        return []
    client = client or _cliente()
    if resumen.get("formato") == "jornada":
        resultados = [redactar_jornada(resumen, client=client, modelo=modelo,
                                       cachear=decidir_cache(1))]
    else:
        cachear = decidir_cache(len(resumen["juegos"]))
        resultados = [redactar_juego(j, resumen, client=client, modelo=modelo, cachear=cachear)
                      for j in resumen["juegos"]]
    (carpeta / "textos.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    (carpeta / "textos.md").write_text(
        "\n\n---\n\n".join(a_markdown(r) for r in resultados), encoding="utf-8")
    (carpeta / "uso.json").write_text(json.dumps(resumen_uso(resultados), indent=2),
                                      encoding="utf-8")
    return resultados
