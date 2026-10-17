"""Cliente mínimo de la API de Instagram (Instagram Login, host graph.instagram.com).

Publicar una imagen o un carrusel son tres pasos: crear un contenedor por imagen (Instagram
descarga la foto desde una URL pública), crear el contenedor del carrusel con esos hijos y
publicarlo. Un carrusel cuenta como un solo post para el límite diario.

Necesita IG_ACCESS_TOKEN (token de larga duración, 60 días, se renueva) y opcionalmente
IG_USER_ID (si falta, se pregunta a /me). El token nunca se imprime: los errores se limpian.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

HOST = "https://graph.instagram.com"
VERSION = os.environ.get("IG_API_VERSION", "v25.0")
MAX_CARRUSEL = 10
MAX_CAPTION = 2200
MAX_HASHTAGS = 30

# Códigos de error de Meta que conviene explicar en castellano
EXPLICACIONES = {
    190: "el token de Instagram venció o es inválido: genera uno nuevo en el panel de Meta "
         "y actualiza el secreto IG_ACCESS_TOKEN",
    10: "a la app le falta el permiso instagram_business_content_publish",
    200: "a la app le falta el permiso instagram_business_content_publish",
    9: "se alcanzó el límite de publicaciones por API de las últimas 24 horas",
    4: "demasiadas llamadas a la API en poco tiempo: reintenta en unos minutos",
}
SUBCODIGOS = {
    2207052: "Instagram no pudo descargar la imagen desde la URL pública",
    2207026: "formato de imagen no aceptado (Instagram solo acepta JPEG)",
    2207009: "proporción de imagen no aceptada (debe estar entre 4:5 y 1.91:1)",
    2207042: "se alcanzó el límite de publicaciones por API de las últimas 24 horas",
    2207008: "el contenedor venció (pasaron más de 24 horas sin publicarlo)",
    2207023: "tipo de contenido desconocido",
}


class InstagramError(RuntimeError):
    pass


def _limpiar(texto: str, token: str) -> str:
    return texto.replace(token, "<token>") if token else texto


def credenciales() -> tuple[str, str | None]:
    from bpt.redactor.agente import cargar_env

    cargar_env()
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        raise InstagramError("Falta IG_ACCESS_TOKEN (en el .env o como secreto de GitHub)")
    return token, (os.environ.get("IG_USER_ID", "").strip() or None)


def explicar(error: dict) -> str:
    """Mensaje legible a partir del objeto `error` de la Graph API."""
    sub = error.get("error_subcode")
    base = SUBCODIGOS.get(sub) or EXPLICACIONES.get(error.get("code"))
    detalle = error.get("error_user_msg") or error.get("message") or "error desconocido"
    return f"{base} ({detalle})" if base else detalle


def revisar_caption(caption: str) -> list[str]:
    """Problemas que harían que Instagram rechace el caption (lista vacía = OK)."""
    problemas = []
    if not caption.strip():
        problemas.append("el caption está vacío")
    if len(caption) > MAX_CAPTION:
        problemas.append(f"el caption tiene {len(caption)} caracteres (máx. {MAX_CAPTION})")
    n_tags = sum(1 for p in caption.split() if p.startswith("#") and len(p) > 1)
    if n_tags > MAX_HASHTAGS:
        problemas.append(f"el caption tiene {n_tags} hashtags (máx. {MAX_HASHTAGS})")
    return problemas


@dataclass
class Publicado:
    media_id: str
    permalink: str
    duplicado: bool = False   # ya estaba publicado: no se volvió a subir


class Instagram:
    def __init__(self, token: str, user_id: str | None = None, http=requests,
                 pausa: float = 3.0, espera_max: float = 90.0):
        self.token, self._user_id, self.http = token, user_id, http
        self.pausa, self.espera_max = pausa, espera_max

    # --- HTTP -----------------------------------------------------------------

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
        except Exception as e:  # noqa: BLE001  (red caída, JSON roto...)
            raise InstagramError(_limpiar(f"{ruta}: {e}", self.token)) from None
        if isinstance(cuerpo, dict) and "error" in cuerpo:
            raise InstagramError(_limpiar(f"{ruta}: {explicar(cuerpo['error'])}", self.token))
        return cuerpo

    # --- Cuenta ---------------------------------------------------------------

    def cuenta(self) -> dict:
        return self._llamar("GET", "me", {"fields": "user_id,username,account_type"})

    @property
    def user_id(self) -> str:
        if not self._user_id:
            self._user_id = str(self.cuenta()["user_id"])
        return self._user_id

    def limite(self) -> dict:
        """Uso de la cuota de publicación en las últimas 24 horas."""
        datos = self._llamar("GET", f"{self.user_id}/content_publishing_limit",
                             {"fields": "quota_usage,config"}).get("data") or [{}]
        return datos[0]

    def recientes(self, n: int = 10) -> list[dict]:
        return self._llamar("GET", f"{self.user_id}/media",
                            {"fields": "id,caption,permalink,timestamp",
                             "limit": n}).get("data", [])

    # --- Publicación ----------------------------------------------------------

    def contenedor_imagen(self, url: str, carrusel: bool = False,
                          caption: str | None = None) -> str:
        params = {"image_url": url}
        if carrusel:
            params["is_carousel_item"] = "true"
        elif caption:
            params["caption"] = caption
        return self._llamar("POST", f"{self.user_id}/media", params)["id"]

    def contenedor_carrusel(self, hijos: list[str], caption: str) -> str:
        return self._llamar("POST", f"{self.user_id}/media",
                            {"media_type": "CAROUSEL", "children": ",".join(hijos),
                             "caption": caption})["id"]

    def esperar(self, contenedor: str) -> None:
        """Espera a que Instagram termine de procesar el contenedor."""
        inicio = time.monotonic()
        while True:
            estado = self._llamar("GET", contenedor,
                                  {"fields": "status_code,status"}).get("status_code")
            if estado in ("FINISHED", "PUBLISHED"):
                return
            if estado in ("ERROR", "EXPIRED"):
                raise InstagramError(f"el contenedor {contenedor} quedó en {estado}")
            if time.monotonic() - inicio > self.espera_max:
                raise InstagramError(f"el contenedor {contenedor} sigue en {estado} tras "
                                     f"{int(self.espera_max)} s")
            time.sleep(self.pausa)

    def permalink(self, media_id: str) -> str:
        return self._llamar("GET", media_id, {"fields": "permalink"}).get("permalink", "")

    def ya_publicado(self, caption: str) -> dict | None:
        """Post reciente con el mismo caption (evita publicar dos veces lo mismo)."""
        clave = caption.strip()
        for m in self.recientes():
            if (m.get("caption") or "").strip() == clave:
                return m
        return None

    def publicar(self, urls: list[str], caption: str) -> Publicado:
        """Una imagen = post simple; de 2 a 10 = carrusel."""
        if not urls:
            raise InstagramError("no hay imágenes para publicar")
        if len(urls) > MAX_CARRUSEL:
            raise InstagramError(f"{len(urls)} imágenes: el carrusel admite {MAX_CARRUSEL}")
        problemas = revisar_caption(caption)
        if problemas:
            raise InstagramError("; ".join(problemas))
        previo = self.ya_publicado(caption)
        if previo:
            return Publicado(previo["id"], previo.get("permalink", ""), duplicado=True)

        if len(urls) == 1:
            final = self.contenedor_imagen(urls[0], caption=caption)
        else:
            hijos = []
            for u in urls:
                hijo = self.contenedor_imagen(u, carrusel=True)
                self.esperar(hijo)
                hijos.append(hijo)
            final = self.contenedor_carrusel(hijos, caption)
        self.esperar(final)
        media_id = self._llamar("POST", f"{self.user_id}/media_publish",
                                {"creation_id": final})["id"]
        return Publicado(media_id, self.permalink(media_id))
