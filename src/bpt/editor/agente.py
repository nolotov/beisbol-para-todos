"""Agente editor: busca la historia, consulta los datos y arma el especial.

Bucle de tool use con Claude (sin forzar herramientas: Sonnet 5.5 rechazó `tool_choice`
forzado, ver la wiki). En cada vuelta el modelo pide consultas, el programa las ejecuta y
guarda la evidencia; cuando entrega el especial, el verificador revisa cada cifra contra esa
evidencia y, si algo no cuadra, se lo devuelve para que corrija (hasta 2 veces). Si aun así
quedan observaciones, el especial sale "con alertas": el humano decide.

Salida: el especial (dict listo para `bpt.especial.generar_datos`), la evidencia y el uso.
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field

from bpt import especial as E
from bpt import verificador
from bpt.editor import prompt
from bpt.editor.herramientas import Caja
from bpt.redactor import agente as R

MODELO = os.environ.get("BPT_MODELO_EDITOR", "claude-sonnet-5-5")
ESFUERZO = os.environ.get("BPT_ESFUERZO_EDITOR", "medium")
MAX_TOKENS = 32000
MAX_VUELTAS = 30          # llamadas al modelo
MAX_CONSULTAS = 40        # herramientas de datos ejecutadas
MAX_CORRECCIONES = 2      # veces que el verificador devuelve el especial
MAX_EMPUJONES = 2         # veces que se le recuerda entregar si termina sin hacerlo


class EditorError(RuntimeError):
    pass


@dataclass
class Resultado:
    especial: dict
    evidencia: list[dict]
    por_que: str
    otras_ideas: list[str]
    verificacion: verificador.Verificacion
    uso: dict
    vueltas: int
    correcciones: int
    bitacora: list[str] = field(default_factory=list)


def slug(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60] or "especial"


def normalizar(entrega: dict, fecha: str) -> dict:
    e = copy.deepcopy(entrega)
    if e.get("tipo") == "carrusel":
        e.pop("tipo")
    e["slug"] = f"editor-{fecha}-{slug(e.get('slug') or e.get('titular', ''))}"
    e["fecha"] = fecha
    if not e.get("equipos"):
        e.pop("equipos", None)
    return e


def revisar_entrega(e: dict, evidencia: list[dict]) -> tuple[list[str], verificador.Verificacion | None]:
    """Problemas de estructura o de verificación (sin consultar la red: eso va al final)."""
    try:
        E.validar_estructura(e)
    except (E.EspecialError, KeyError, TypeError) as err:
        return [f"estructura: {err}"], None
    v = verificador.verificar(e, evidencia=evidencia, hechos=False)
    problemas = []
    if v.cifras_sin_respaldo:
        problemas.append("Cifras sin respaldo en tus consultas: "
                         + ", ".join(v.cifras_sin_respaldo)
                         + ". Consúltalas, calcúlalas con `calcular` o quítalas.")
    problemas += v.alertas
    if e.get("textos"):
        problemas += E.revisar_textos(e["textos"])
        n = len(e["textos"].get("hilo_x") or [])
        if not 3 <= n <= 5:
            problemas.append(f"hilo_x: {n} tuits (deben ser entre 3 y 5)")
    return problemas, v


def _llamar_modelo(client, **kw):
    """Con max_tokens alto el SDK exige streaming (si no, lanza ValueError: "Streaming is
    required for operations that may take longer than 10 minutes"). Se usa stream y se
    espera el mensaje completo; los clientes de prueba sin stream usan create."""
    stream = getattr(client.messages, "stream", None)
    if stream is None:
        return client.messages.create(**kw)
    with stream(**kw) as s:
        return s.get_final_message()


def _marcar_cache(mensajes: list[dict]) -> None:
    """Un punto de caché en el último bloque del último mensaje (y solo ahí): cada vuelta
    relee todo lo anterior al 5 % del precio."""
    for m in mensajes:
        if isinstance(m["content"], list):
            for b in m["content"]:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
    ultimo = mensajes[-1]["content"]
    if isinstance(ultimo, str):
        mensajes[-1]["content"] = [{"type": "text", "text": ultimo}]
        ultimo = mensajes[-1]["content"]
    if isinstance(ultimo[-1], dict):
        ultimo[-1]["cache_control"] = {"type": "ephemeral"}


def editar(fecha: str, tema: str | None = None, *, client=None, caja: Caja | None = None,
           modelo: str | None = None, ya_publicados: list[str] | None = None,
           aprendizajes: str | None = None, log=print) -> Resultado:
    client = client or R._cliente()
    caja = caja or Caja()
    modelo = modelo or MODELO
    herramientas = caja.definiciones() + [prompt.ENTREGA]
    sistema = [{"type": "text", "text": prompt.SISTEMA, "cache_control": {"type": "ephemeral"}}]
    mensajes: list[dict] = [{"role": "user", "content": prompt.mensaje_inicial(
        fecha, tema, ya_publicados or [], aprendizajes)}]
    recordatorio_tema = (f"\n\nRecuerda: el tema obligatorio es «{tema}». Si te desviaste, "
                         "vuelve a él." if tema else "")
    uso = {"entrada": 0, "salida": 0, "cache_escrito": 0, "cache_leido": 0}
    consultas = correcciones = empujones = 0
    bitacora: list[str] = []
    ultima: tuple[dict, dict, verificador.Verificacion | None] | None = None

    for vuelta in range(1, MAX_VUELTAS + 1):
        _marcar_cache(mensajes)
        r = _llamar_modelo(client, model=modelo, max_tokens=MAX_TOKENS, system=sistema,
                           tools=herramientas, messages=mensajes,
                           output_config={"effort": ESFUERZO})
        uso = R.sumar_uso(uso, R.uso_de(r))
        mensajes.append({"role": "assistant", "content": r.content})
        if r.stop_reason == "max_tokens":
            raise EditorError("el modelo se quedó sin espacio (max_tokens)")
        if r.stop_reason == "refusal":
            raise EditorError("el modelo se negó a continuar")
        llamadas = [b for b in r.content if b.type == "tool_use"]
        if not llamadas:
            if ultima is not None:          # ya entregó antes: se acepta la última versión
                break
            if empujones >= MAX_EMPUJONES:
                raise EditorError("el modelo terminó sin entregar el especial")
            empujones += 1
            mensajes.append({"role": "user", "content": "Aún no entregas. Termina las "
                             "consultas que falten y llama a `entregar_especial`."
                             + recordatorio_tema})
            continue

        resultados = []
        aceptado = False
        for b in llamadas:
            if b.name == "entregar_especial":
                entrada = dict(b.input)
                e = normalizar(entrada.get("especial") or {}, fecha)
                problemas, v = revisar_entrega(e, caja.evidencia)
                ultima = (e, entrada, v)
                if problemas and correcciones < MAX_CORRECCIONES:
                    correcciones += 1
                    bitacora.append(f"vuelta {vuelta}: devuelto ({len(problemas)} obs.)")
                    log(f"  ↩️ entrega devuelta: {len(problemas)} observación(es)")
                    resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                       "is_error": True, "content": "Corrige y vuelve a "
                                       "entregar:\n- " + "\n- ".join(problemas)
                                       + recordatorio_tema})
                else:
                    aceptado = True
                    bitacora.append(f"vuelta {vuelta}: entregado"
                                    + (" con observaciones" if problemas else ""))
                    resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                       "content": "Recibido. Gracias."})
                continue
            if consultas >= MAX_CONSULTAS:
                resultados.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                   "content": "Se acabó el presupuesto de consultas: entrega "
                                              "con lo que tienes."})
                continue
            consultas += 1
            texto, error = caja.ejecutar(b.name, dict(b.input))
            log(f"  🔧 {b.name}({json.dumps(dict(b.input), ensure_ascii=False)[:90]})"
                + (" ✗" if error else ""))
            resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": texto,
                               **({"is_error": True} if error else {})})
        mensajes.append({"role": "user", "content": resultados})
        if aceptado:
            break
    else:
        if ultima is None:
            raise EditorError(f"sin entrega tras {MAX_VUELTAS} vueltas")

    if ultima is None:
        raise EditorError("el modelo terminó sin entregar el especial")
    e, entrada, v = ultima
    uso["costo_usd"] = R.costo_usd(uso, modelo)
    uso["modelo"] = modelo
    if v is None:
        raise EditorError("la última entrega no tiene una estructura válida")
    return Resultado(especial=e, evidencia=caja.evidencia,
                     por_que=entrada.get("por_que", ""),
                     otras_ideas=list(entrada.get("otras_ideas") or []),
                     verificacion=v, uso=uso, vueltas=vuelta, correcciones=correcciones,
                     bitacora=bitacora)
