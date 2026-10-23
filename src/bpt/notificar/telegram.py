"""Envía el paquete del día a Telegram para revisarlo y publicarlo desde el celular.

Por juego: encabezado con estado y alertas, álbum de láminas (vista previa), las mismas
láminas como archivo (calidad original para subir a Instagram), el caption, cada tuit en
su propio mensaje (para copiar en orden) y el guion.

Necesita TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID (en el .env o como secretos de GitHub).
El token nunca se imprime: los errores se limpian antes de mostrarlos.

Fase 4: si alguna red está encendida (BPT_PUBLICAR_INSTAGRAM, BPT_PUBLICAR_THREADS,
BPT_PUBLICAR_X) y el envío corre dentro de GitHub Actions (GITHUB_RUN_ID), cada pieza cierra
con un botón por red. Los atiende el relé (infra/telegram-relay), que pide confirmación y
dispara el workflow publicar.yml.
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

    def botones(self, texto: str, filas: list[list[dict]],
                responder_a: int | str | None = None) -> dict:
        """Mensaje con botones debajo (inline keyboard). Devuelve el mensaje enviado.
        Con `responder_a`, sale como respuesta a ese mensaje."""
        data = {"chat_id": self.chat_id, "text": texto, "disable_web_page_preview": "true",
                "reply_markup": json.dumps({"inline_keyboard": filas})}
        if responder_a:
            data["reply_parameters"] = json.dumps({"message_id": int(responder_a),
                                                   "allow_sending_without_reply": True})
        return self._llamar("sendMessage", data)

    def editar(self, message_id: int | str, texto: str,
               filas: list[list[dict]] | None = None, chat_id: str | None = None) -> None:
        """Reemplaza el texto (y los botones) de un mensaje ya enviado."""
        data = {"chat_id": chat_id or self.chat_id, "message_id": str(message_id),
                "text": texto, "disable_web_page_preview": "true",
                "reply_markup": json.dumps({"inline_keyboard": filas or []})}
        self._llamar("editMessageText", data)

    def video(self, archivo: Path, leyenda: str | None = None) -> None:
        """Un video (hasta 50 MB por la API de bots), reproducible en el chat."""
        with open(archivo, "rb") as f:
            self._llamar("sendVideo", {"chat_id": self.chat_id, "caption": leyenda or "",
                                       "supports_streaming": "true", "width": "1080",
                                       "height": "1920"}, {"video": f})

    def album(self, imagenes: list[Path], como_archivo: bool = False,
              leyenda: str | None = None) -> None:
        """Hasta 10 imágenes en un solo mensaje (fotos o documentos)."""
        imagenes = [Path(p) for p in imagenes][:10]
        if not imagenes:
            return
        if len(imagenes) == 1:  # sendMediaGroup exige entre 2 y 10 elementos
            metodo, campo = ("sendDocument", "document") if como_archivo else ("sendPhoto", "photo")
            with open(imagenes[0], "rb") as f:
                self._llamar(metodo, {"chat_id": self.chat_id, "caption": leyenda or ""},
                             {campo: f})
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


# --- Botón de publicar (fase 4) ---------------------------------------------------

def publicar_activo() -> bool:
    """Botones solo si hay alguna red encendida (variables del repo) y un run de Actions al
    que volver."""
    from bpt.publicar import redes
    return bool(redes.activas()) and bool(os.environ.get("GITHUB_RUN_ID"))


def callback_publicar(run_id: str, pieza: str, destino: str = "i", quedan: str = "i") -> str:
    from bpt.publicar import redes
    try:
        return redes.callback("pub", run_id, pieza, destino, quedan)
    except ValueError as e:
        raise TelegramError(str(e)) from None


def texto_publicar(titular: str, alertas: bool, historia: bool = False,
                   quedan: str = "i", reel: bool = False) -> str:
    """El primer párrafo es la "base" que el relé conserva al editar el mensaje."""
    from bpt.publicar import redes
    aviso = " · ⚠️ con alertas" if alertas else ""
    icono = "🎬" if reel else "📲" if historia else "📸"
    return f"{icono} {titular}{aviso}\n\n{redes.pregunta(quedan)}"


def ofrecer_publicar(tg: "Telegram", carpeta: Path, pieza_id: str) -> bool:
    """Manda el menú de redes de una pieza si hay redes activas y la pieza sirve para alguna."""
    if not publicar_activo():
        return False
    from bpt.publicar import piezas, redes
    try:
        p = piezas.buscar(carpeta, pieza_id)
    except piezas.PiezaError:
        return False
    quedan = p.redes(redes.activas())
    if not quedan:
        return False
    run_id = os.environ["GITHUB_RUN_ID"]
    historia = p.tipo == piezas.HISTORIA
    tg.botones(texto_publicar(p.titular, p.tiene_alertas, historia, quedan,
                              reel=p.tipo == piezas.REEL),
               redes.menu(run_id, p.id, quedan, historia))
    return True


def ofrecer_reel(tg: "Telegram", carpeta: Path, pieza_id: str) -> bool:
    """Si la pieza tiene Reel (reel_<id>.mp4), lo manda y ofrece publicarlo en Instagram."""
    carpeta = Path(carpeta)
    video = carpeta / f"reel_{pieza_id}.mp4"
    if not video.exists():
        return False
    info = {}
    try:
        resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
        info = (resumen.get("reels") or {}).get(pieza_id) or {}
    except (OSError, ValueError):
        pass
    detalle = f" · {info['duracion']:.0f} s" if info.get("duracion") else ""
    voz = "" if not info else (" · con voz" if info.get("voz") else " · sin voz: ponle música")
    tg.video(video, leyenda=f"🎬 Reel{detalle}{voz}")
    ofrecer_publicar(tg, carpeta, f"r{pieza_id}")
    return True


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

    if resumen.get("formato") == "jornada":
        return _enviar_jornada(carpeta, resumen, por_pk.get("jornada"), tg, originales)
    if resumen.get("formato") == "historia":
        return _enviar_historia(carpeta, resumen, tg, originales)
    if resumen.get("formato") == "especial":
        return _enviar_especial(carpeta, resumen, por_pk.get("especial"), tg, originales)

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
        ofrecer_publicar(tg, carpeta, str(n))
        ofrecer_reel(tg, carpeta, str(n))
    return len(juegos)


def _textos(tg: Telegram, t: dict) -> None:
    tg.texto("📸 INSTAGRAM\n\n" + t["instagram"])
    hilo = t.get("hilo_x", [])
    for i, tuit in enumerate(hilo, 1):
        tg.texto(f"𝕏 {i}/{len(hilo)}\n\n{tuit}")
    tg.texto("🎙️ GUION (30-45 s)\n\n" + t["guion"])


def _enviar_jornada(carpeta: Path, resumen: dict, r: dict | None, tg: Telegram,
                    originales: bool) -> int:
    juegos = resumen.get("juegos", [])
    liga = resumen.get("liga", "LVBP")
    if not juegos:
        pend = resumen.get("pendientes", [])
        extra = ("\nSin terminar: " + ", ".join(f"{p['partido']} ({p['estado']})" for p in pend)
                 if pend else "")
        tg.texto(f"MBP · {liga} {resumen['fecha']}: no hubo juegos terminados.{extra}")
        return 0
    marcadores = "\n".join(f"• {j['titular']}" for j in juegos)
    if r is None:
        enc = "Sin textos (falta la llave de Claude o falló el redactor): solo láminas."
    else:
        enc = encabezado(r, 1, 1).split("\n", 1)[1]   # sin la línea "1/1"
    tg.texto(f"⚾ {liga} · Jornada del {resumen['fecha']} · {len(juegos)} juego"
             f"{'s' if len(juegos) != 1 else ''}\n{marcadores}\n\n{enc}\n\n"
             "Nada se publica sin tu ok. 👇")
    carrusel = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
    tg.album(carrusel)
    if originales and carrusel:
        tg.album(carrusel, como_archivo=True, leyenda="Carrusel: originales para Instagram")
    extras = [carpeta / t for t in resumen.get("extras", []) if (carpeta / t).exists()]
    for k in range(0, len(extras), 10):
        tg.album(extras[k:k + 10], como_archivo=True,
                 leyenda="Extras para historias: resultado y figuras de cada juego")
    if r is not None:
        _textos(tg, r["textos"])
        ofrecer_publicar(tg, carpeta, "jornada")
        ofrecer_reel(tg, carpeta, "jornada")
    return len(juegos)


def _enviar_historia(carpeta: Path, resumen: dict, tg: Telegram, originales: bool) -> int:
    """Historia del día: vista previa, original y botón. Sin juegos no se manda nada."""
    imagenes = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
    if not resumen.get("total") or not imagenes:
        return 0
    if resumen.get("especial"):
        prefijo = "🧠 Propuesta del editor (historia)" if resumen.get("editor") else \
            "📲 Historia especial"
        leyenda = f"{prefijo} · {resumen['titular']}"
        if (resumen.get("editor") or {}).get("por_que"):
            leyenda += f"\nPor qué ahora: {resumen['editor']['por_que']}"
        ver = resumen.get("verificacion") or {}
        if ver.get("resumen"):
            leyenda += "\n" + ver["resumen"]
            if not ver.get("ok"):
                leyenda += "\n⚠️ " + "\n⚠️ ".join(_alertas_verificacion(ver))
    else:
        lineas = []
        for liga, datos in resumen.get("ligas", {}).items():
            n = len(datos["juegos"])
            lineas.append(f"{liga}: {n} juego{'s' if n != 1 else ''}")
        leyenda = "📲 Historia de hoy · " + " · ".join(lineas)
    tg.album(imagenes[:1], leyenda=leyenda)
    if originales:
        tg.album(imagenes[:1], como_archivo=True, leyenda="Original para la historia")
    ofrecer_publicar(tg, carpeta, "1")
    return resumen["total"]


def _alertas_verificacion(ver: dict) -> list[str]:
    salida = list(ver.get("alertas") or [])
    if ver.get("cifras_sin_respaldo"):
        salida.append("cifras sin respaldo: " + ", ".join(ver["cifras_sin_respaldo"]))
    return salida


def _enviar_especial(carpeta: Path, resumen: dict, r: dict | None, tg: Telegram,
                     originales: bool) -> int:
    """Especial: láminas, textos y menú de redes (igual que una pieza del día)."""
    imagenes = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
    if not imagenes:
        return 0
    if r is None:
        enc = "Sin textos: solo láminas."
    else:
        enc = encabezado(r, 1, 1).split("\n", 1)[1]
    ver = (resumen.get("verificacion") or {}).get("resumen")
    if ver:
        enc += "\n" + ver
    editor = resumen.get("editor") or {}
    cabeza = "🧠 Propuesta del editor" if editor else "⭐ Especial"
    extra = ""
    if editor:
        extra += (f"\n\nTema pedido: {editor['tema']}" if editor.get("tema")
                  else "\n\nTema: libre (lo eligió el editor)")
        if editor.get("herramientas"):
            extra += f"\nConsultó: {editor['herramientas']}"
    if editor.get("por_que"):
        extra += f"\n\nPor qué ahora: {editor['por_que']}"
    if editor.get("otras_ideas"):
        extra += "\n\nOtras ideas (pídelas con el workflow «Editor MBP» y el tema):\n" + \
            "\n".join(f"• {i}" for i in editor["otras_ideas"][:5])
    tg.texto(f"{cabeza} · {resumen['titular']}\n{enc}{extra}\n\nNada se publica sin tu ok. 👇")
    tg.album(imagenes)
    if originales:
        tg.album(imagenes, como_archivo=True, leyenda="Originales para subir")
    if r is not None:
        _textos(tg, r["textos"])
        ofrecer_publicar(tg, carpeta, "1")
        ofrecer_reel(tg, carpeta, "1")
    return 1


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


def poner_webhook(token: str, url: str, secreto: str, http=requests) -> None:
    """Telegram avisará de cada toque de botón a `url` (el relé), firmando con `secreto`."""
    if not url.startswith("https://"):
        raise TelegramError("la URL del relé debe empezar con https://")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", secreto or ""):
        raise TelegramError("el secreto debe tener 16 a 256 caracteres A-Z, a-z, 0-9, _ o -")
    Telegram(token, "", pausa=0, http=http)._llamar("setWebhook", {
        "url": url, "secret_token": secreto, "drop_pending_updates": "true",
        "allowed_updates": json.dumps(["callback_query"])})


def quitar_webhook(token: str, http=requests) -> None:
    """Vuelve al modo sin relé (necesario para que funcione 'bpt telegram-chat')."""
    Telegram(token, "", pausa=0, http=http)._llamar("deleteWebhook", {})


def info_webhook(token: str, http=requests) -> dict:
    return Telegram(token, "", pausa=0, http=http)._llamar("getWebhookInfo", {}) or {}


def es_token_valido(token: str) -> bool:
    return bool(re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token or ""))
