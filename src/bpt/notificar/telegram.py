"""Envía el paquete del día a Telegram para revisarlo y publicarlo desde el celular.

Por juego: encabezado con estado y alertas, álbum de láminas (vista previa), las mismas
láminas como archivo (calidad original para subir a Instagram), el caption, cada tuit en
su propio mensaje (para copiar en orden) y el guion.

Necesita TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (en el .env o como secretos de GitHub).
El token nunca se imprime: los errores se limpian antes de mostrarlos.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE_TEXTO = 4096
PAUSA = 1.1          # segundos entre mensajes (límite de Telegram: ~1 msg/s por chat)


class TelegramError(RuntimeError):
    pass


def _limpiar(texto: str, token: str) -> str:
    """Quita el token de cualquier texto (las URLs de error lo traen)."""
    return texto.replace(token, "<token>") if token else texto


def credenciales() -> tuple[str, str]:
    from bpt.redactor.agente import cargar_env

    cargar_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise TelegramError("Falta TELEGRAM_BOT_TOKEN (en el .env o como secreto de GitHub)")
    if not chat:
        raise TelegramError("Falta TELEGRAM_CHAT_ID: escríbele /start a tu bot y corre "
                            "'bpt telegram-chat'")
    return token, chat


class Telegram:
    def __init__(self, token: str, chat_id: str, pausa: float = PAUSA, http=requests):
        self.token, self.chat_id, self.pausa, self.http = token, chat_id, pausa, http

    def _llamar(self, metodo: str, data: dict | None = None, files: dict | None = None,
                reintentos: int = 3) -> dict:
        url = API.format(token=self.token, metodo=metodo)
        for intento in range(reintentos):
            try:
                r = self.http.post(url, data=data, files=files, timeout=60)
                cuerpo = r.json()
            except Exception as e:  # noqa: BLE001
                if intento == reintentos - 1:
                    raise TelegramError(_limpiar(f"{metodo}: {e}", self.token)) from None
                time.sleep(2 * (intento + 1))
                continue
            if cuerpo.get("ok"):
                if self.pausa:
                    time.sleep(self.pausa)
                return cuerpo.get("result")
            espera = (cuerpo.get("parameters") or {}).get("retry_after")
            if espera and intento < reintentos - 1:     # 429: demasiado rápido
                time.sleep(float(espera) + 0.5)
                continue
            raise TelegramError(_limpiar(f"{metodo}: {cuerpo.get('description')}", self.token))
        raise TelegramError(f"{metodo}: sin respuesta")

    # --- Mensajes -------------------------------------------------------------

    def texto(self, texto: str) -> None:
        """Texto plano (sin formato, para copiar tal cual). Se parte si pasa el límite."""
        for trozo in partir(texto):
            self._llamar("sendMessage", {"chat_id": self.chat_id, "text": trozo,
                                         "disable_web_page_preview": "true"})

    def album(self, imagenes: list[Path], como_archivo: bool = False,
              leyenda: str | None = None) -> None:
        """Hasta 10 imágenes en un solo mensaje (fotos o documentos)."""
        imagenes = [Path(p) for p in imagenes][:10]
        if not imagenes:
            return
        if len(imagenes) == 1 and not como_archivo:
            with open(imagenes[0], "rb") as f:
                self._llamar("sendPhoto", {"chat_id": self.chat_id, "caption": leyenda or ""},
                             {"photo": f})
            return
        tipo = "document" if como_archivo else "photo"
        media = [{"type": tipo, "media": f"attach://f{i}"} for i in range(len(imagenes))]
        if leyenda:
            media[-1 if como_archivo else 0]["caption"] = leyenda
        abiertos = {f"f{i}": open(p, "rb") for i, p in enumerate(imagenes)}
        try:
            self._llamar("sendMediaGroup", {"chat_id": self.chat_id,
                                            "media": json.dumps(media)}, abiertos)
        finally:
            for f in abiertos.values():
                f.close()


def partir(texto: str, limite: int = LIMITE_TEXTO) -> list[str]:
    if len(texto) <= limite:
        return [texto]
    trozos, actual = [], ""
    for parrafo in texto.split("\n"):
        if len(actual) + len(parrafo) + 1 > limite:
            trozos.append(actual.rstrip())
            actual = ""
        actual += parrafo + "\n"
    if actual.strip():
        trozos.append(actual.rstrip())
    return trozos


# --- Paquete del día ------------------------------------------------------------

def encabezado(r: dict, n: int, total: int) -> str:
    v = r["validacion"]
    marca = "✅ Para revisar" if v["ok"] else "⚠️ Con alertas: revisar antes de publicar"
    lineas = [f"⚾ {n}/{total} · {r['titular']}", marca]
    if v["cifras_sin_respaldo"]:
        lineas.append("Cifras sin respaldo: " + ", ".join(v["cifras_sin_respaldo"]))
    lineas += [f"• {a}" for a in v["alertas"]]
    if r.get("textos", {}).get("angulo"):
        lineas += ["", f"Ángulo: {r['textos']['angulo']}"]
    return "\n".join(lineas)


def enviar_dia(carpeta: Path, tg: Telegram | None = None, originales: bool = True) -> int:
    """Envía todo lo de `carpeta`. Devuelve cuántos juegos se enviaron."""
    carpeta = Path(carpeta)
    if tg is None:
        tg = Telegram(*credenciales())
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    textos_path = carpeta / "textos.json"
    redactados = json.loads(textos_path.read_text(encoding="utf-8")) if textos_path.exists() else []
    por_pk = {r["game_pk"]: r for r in redactados}

    juegos = resumen.get("juegos", [])
    if not juegos:
        pend = resumen.get("pendientes", [])
        extra = ("\nPendientes: " + ", ".join(f"{p['partido']} ({p['estado']})" for p in pend)
                 if pend else "")
        tg.texto(f"MBP · {resumen['fecha']}: no hubo juegos terminados de postemporada.{extra}")
        return 0

    tg.texto(f"MBP · Resultados del {resumen['fecha']} · {len(juegos)} juego"
             f"{'s' if len(juegos) != 1 else ''}. Nada se publica sin tu ok. 👇")
    for n, j in enumerate(juegos, 1):
        r = por_pk.get(j["game_pk"])
        imagenes = [carpeta / t for t in j.get("tarjetas", []) if (carpeta / t).exists()]
        if r is None:
            tg.texto(f"⚾ {n}/{len(juegos)} · {j['titular']}\nSin textos (falta la llave de "
                     "Claude o falló el redactor): solo láminas.")
        else:
            tg.texto(encabezado(r, n, len(juegos)))
        tg.album(imagenes)
        if originales and imagenes:
            tg.album(imagenes, como_archivo=True, leyenda="Originales para subir a Instagram")
        if r is None:
            continue
        t = r["textos"]
        tg.texto("📸 INSTAGRAM\n\n" + t["instagram"])
        hilo = t.get("hilo_x", [])
        for i, tuit in enumerate(hilo, 1):
            tg.texto(f"𝕏 {i}/{len(hilo)}\n\n{tuit}")
        tg.texto("🎙️ GUION (30-45 s)\n\n" + t["guion"])
    return len(juegos)


def chats_recientes(token: str, http=requests) -> list[dict]:
    """Chats que le escribieron al bot (para obtener el TELEGRAM_CHAT_ID)."""
    tg = Telegram(token, "", pausa=0, http=http)
    vistos: dict[int, dict] = {}
    for u in tg._llamar("getUpdates", {"timeout": 0}) or []:
        msg = u.get("message") or u.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            vistos[chat["id"]] = {"id": chat["id"], "tipo": chat.get("type"),
                                  "nombre": chat.get("first_name") or chat.get("title") or "",
                                  "usuario": chat.get("username") or ""}
    return list(vistos.values())


def es_token_valido(token: str) -> bool:
    return bool(re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token or ""))
