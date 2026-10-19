"""Cliente mínimo de la API de Threads (host graph.threads.net).

Publicar es igual que en Instagram: contenedor (Threads descarga la imagen de una URL
pública), espera a que termine de procesar y publicación. Un hilo es el primer post (imagen o
carrusel de hasta 20) y luego cada parte como respuesta a la anterior (`reply_to_id`).

Necesita THREADS_ACCESS_TOKEN (token de larga duración, 60 días, se renueva) y opcionalmente
THREADS_USER_ID (si falta, se pregunta a /me). El token nunca se imprime: los errores se limpian.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

HOST = "https://graph.threads.net"
VERSION = os.environ.get("THREADS_API_VERSION", "v1.0")
MAX_TEXTO = 500
MAX_CARRUSEL = 20

EXPLICACIONES = {
    190: "el token de Threads venció o es inválido: genera uno nuevo en el panel de Meta "
         "y actualiza el secreto THREADS_ACCESS_TOKEN",
    10: "a la app le falta el permiso threads_content_publish",
    200: "a la app le falta el permiso threads_content_publish",
    4: "demasiadas llamadas a la API en poco tiempo: reintenta en unos minutos",
}


class ThreadsError(RuntimeError):
    pass


class PublicacionParcial(ThreadsError):
    """El hilo quedó a medias: el primer post salió, alguna respuesta no."""

    def __init__(self, mensaje: str, permalink: str):
        super().__init__(mensaje)
        self.permalink = permalink


@dataclass
class Publicado:
    media_id: str
    permalink: str
    duplicado: bool = False


def _limpiar(texto: str, token: str) -> str:
    return texto.replace(token, "<token>") if token else texto


def credenciales() -> tuple[str, str | None]:
    from bpt.redactor.agente import cargar_env

    cargar_env()
    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        raise ThreadsError("falta el secreto THREADS_ACCESS_TOKEN")
    return token, (os.environ.get("THREADS_USER_ID", "").strip() or None)


def explicar(error: dict) -> str:
    base = EXPLICACIONES.get(error.get("code"))
    detalle = error.get("error_user_msg") or error.get("message") or "error desconocido"
    return f"{base} ({detalle})" if base else detalle


def revisar(textos: list[str]) -> list[str]:
    problemas = []
    if not textos or not textos[0].strip():
        problemas.append("no hay texto para Threads (hace falta el hilo del redactor)")
    for i, t in enumerate(textos, 1):
        if len(t) > MAX_TEXTO:
            problemas.append(f"la parte {i} tiene {len(t)} caracteres (máx. {MAX_TEXTO} en Threads)")
    return problemas


class Threads:
    def __init__(self, token: str, user_id: str | None = None, http=requests,
                 pausa: float = 3.0, espera_max: float = 120.0):
        self.token, self._user_id, self.http = token, user_id, http
        self.pausa, self.espera_max = pausa, espera_max

    def _url(self, ruta: str) -> str:
        return f"{HOST}/{VERSION}/{ruta.lstrip('/')}"

    def _llamar(self, verbo: str, ruta: str, params: dict | None = None) -> dict:
        datos = dict(params or {}, access_token=self.token)
        try:
            if verbo == "GET":
                r = self.http.get(self._url(ruta), params=datos, timeout=60)
            else:
                r = self.http.post(self._url(ruta), data=datos, timeout=60)
            cuerpo = r.json()
        except Exception as e:  # noqa: BLE001
            raise ThreadsError(_limpiar(f"{ruta}: {e}", self.token)) from None
        if isinstance(cuerpo, dict) and "error" in cuerpo:
            raise ThreadsError(_limpiar(f"{ruta}: {explicar(cuerpo['error'])}", self.token))
        return cuerpo

    # --- Cuenta ---------------------------------------------------------------

    def cuenta(self) -> dict:
        return self._llamar("GET", "me", {"fields": "id,username"})

    @property
    def user_id(self) -> str:
        if not self._user_id:
            self._user_id = str(self.cuenta()["id"])
        return self._user_id

    def limite(self) -> dict:
        datos = self._llamar("GET", f"{self.user_id}/threads_publishing_limit",
                             {"fields": "quota_usage,config"}).get("data") or [{}]
        return datos[0]

    def recientes(self, n: int = 10) -> list[dict]:
        return self._llamar("GET", f"{self.user_id}/threads",
                            {"fields": "id,text,permalink", "limit": n}).get("data", [])

    # --- Publicación ----------------------------------------------------------

    def _contenedor(self, params: dict) -> str:
        return self._llamar("POST", f"{self.user_id}/threads", params)["id"]

    def esperar(self, contenedor: str) -> None:
        inicio = time.monotonic()
        while True:
            r = self._llamar("GET", contenedor, {"fields": "status,error_message"})
            estado = r.get("status")
            if estado in ("FINISHED", "PUBLISHED"):
                return
            if estado in ("ERROR", "EXPIRED"):
                motivo = r.get("error_message") or estado
                raise ThreadsError(f"el contenedor {contenedor} quedó en {estado} ({motivo})")
            if time.monotonic() - inicio > self.espera_max:
                raise ThreadsError(f"el contenedor {contenedor} sigue en {estado} tras "
                                   f"{int(self.espera_max)} s")
            time.sleep(self.pausa)

    def _publicar(self, contenedor: str) -> str:
        self.esperar(contenedor)
        return self._llamar("POST", f"{self.user_id}/threads_publish",
                            {"creation_id": contenedor})["id"]

    def permalink(self, media_id: str) -> str:
        return self._llamar("GET", media_id, {"fields": "permalink"}).get("permalink", "")

    def ya_publicado(self, texto: str) -> dict | None:
        clave = texto.strip()
        for m in self.recientes():
            if (m.get("text") or "").strip() == clave:
                return m
        return None

    def publicar_hilo(self, urls: list[str], textos: list[str]) -> Publicado:
        """Primer post con la(s) imagen(es) y el primer texto; el resto, como respuestas."""
        problemas = revisar(textos)
        if problemas:
            raise ThreadsError("; ".join(problemas))
        urls = urls[:MAX_CARRUSEL]
        previo = self.ya_publicado(textos[0])
        if previo:
            return Publicado(previo["id"], previo.get("permalink", ""), duplicado=True)

        if not urls:
            raiz_c = self._contenedor({"media_type": "TEXT", "text": textos[0]})
        elif len(urls) == 1:
            raiz_c = self._contenedor({"media_type": "IMAGE", "image_url": urls[0],
                                       "text": textos[0]})
        else:
            hijos = []
            for u in urls:
                h = self._contenedor({"media_type": "IMAGE", "image_url": u,
                                      "is_carousel_item": "true"})
                self.esperar(h)
                hijos.append(h)
            raiz_c = self._contenedor({"media_type": "CAROUSEL", "children": ",".join(hijos),
                                       "text": textos[0]})
        raiz = self._publicar(raiz_c)
        enlace = self.permalink(raiz)

        anterior = raiz
        for i, t in enumerate(textos[1:], 2):
            try:
                c = self._contenedor({"media_type": "TEXT", "text": t, "reply_to_id": anterior})
                anterior = self._publicar(c)
            except ThreadsError as e:
                raise PublicacionParcial(
                    f"hilo incompleto: salieron {i - 1} de {len(textos)} partes ({e})",
                    enlace) from None
        return Publicado(raiz, enlace)
