"""Redes de destino y el menú de botones de Telegram.

Cada red tiene una letra que viaja en el botón: i = Instagram, t = Threads, x = X.
El botón lleva `accion:run:pieza:destino:quedan`, por ejemplo `pub:123:2:x:itx`
("publicar la pieza 2 del run 123 en X; en el menú quedaban Instagram, Threads y X").

Si la única red activa es Instagram se usa el formato corto de siempre (`pub:123:2`), así
los mensajes y el relé de antes siguen funcionando igual.

El relé (infra/telegram-relay/worker.js) arma el mismo menú: si cambias aquí un texto o una
letra, cámbialo allá también.
"""
from __future__ import annotations

import os
import re

ORDEN = "itx"
NOMBRES = {"i": "Instagram", "t": "Threads", "x": "X"}
BOTON = {"i": "📸 Instagram", "t": "🧵 Threads", "x": "𝕏 X"}
TODAS = "🚀 Todas"
VARIABLES = {"i": "BPT_PUBLICAR_INSTAGRAM", "t": "BPT_PUBLICAR_THREADS", "x": "BPT_PUBLICAR_X"}
DESTINO = re.compile(r"^[itx]{1,3}$")


def normalizar(letras: str) -> str:
    """Sin repetidos y en el orden canónico (i, t, x)."""
    return "".join(c for c in ORDEN if c in (letras or ""))


def menos(a: str, b: str) -> str:
    return normalizar("".join(c for c in a if c not in b))


def nombres(letras: str) -> str:
    """'itx' -> 'Instagram, Threads y X'."""
    n = [NOMBRES[c] for c in normalizar(letras)]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " y " + n[-1]


def _encendida(letra: str) -> bool:
    v = os.environ.get(VARIABLES[letra], "").strip().lower()
    return v in ("1", "true", "si", "sí", "yes")


def activas() -> str:
    """Redes con su interruptor encendido (variables del repo PUBLICAR_*)."""
    return "".join(c for c in ORDEN if _encendida(c))


def callback(accion: str, run_id: str, pieza: str, destino: str, quedan: str) -> str:
    if quedan == "i" and destino == "i":
        data = f"{accion}:{run_id}:{pieza}"          # formato corto (solo Instagram)
    else:
        data = f"{accion}:{run_id}:{pieza}:{destino}:{quedan}"
    if len(data.encode()) > 64:                       # límite de Telegram
        raise ValueError(f"callback demasiado largo: {data}")
    return data


def menu(run_id: str, pieza: str, quedan: str, historia: bool = False) -> list[list[dict]]:
    """Botones para las redes que quedan. Una sola: botón ancho; varias: una fila por red
    (de a dos) y abajo "Todas"."""
    quedan = normalizar(quedan)
    if not quedan:
        return []
    if len(quedan) == 1:
        if quedan == "i" and pieza.startswith("r"):
            texto = "🎬 Publicar Reel en Instagram"
        elif quedan == "i":
            texto = "📲 Publicar historia en Instagram" if historia else "📸 Publicar en Instagram"
        else:
            texto = f"{BOTON[quedan]}: publicar"
        return [[{"text": texto, "callback_data": callback("pub", run_id, pieza, quedan, quedan)}]]
    botones = [{"text": BOTON[c], "callback_data": callback("pub", run_id, pieza, c, quedan)}
               for c in quedan]
    filas = [botones[k:k + 2] for k in range(0, len(botones), 2)]
    filas.append([{"text": TODAS, "callback_data": callback("pub", run_id, pieza, quedan, quedan)}])
    return filas


def pregunta(quedan: str) -> str:
    quedan = normalizar(quedan)
    if len(quedan) == 1:
        return f"¿La subo a {NOMBRES[quedan]}? Te pido confirmación antes."
    return "¿Dónde la publico? Te pido confirmación antes."
