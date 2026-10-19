"""Cliente mínimo de la API de X (v2, pago por uso).

Un hilo es el primer post con hasta 4 imágenes y luego cada tuit como respuesta al anterior.
Las imágenes se suben como archivo (no hace falta URL pública).

Autenticación OAuth 1.0a de usuario (una sola cuenta, sin renovaciones): X_API_KEY,
X_API_SECRET, X_ACCESS_TOKEN y X_ACCESS_SECRET. La app debe tener permiso "Read and write"
y los tokens de acceso deben generarse DESPUÉS de dar ese permiso.

Costos (pago por uso, oct-2026): cada post se cobra; un post con enlace cuesta mucho más,
por eso aquí se rechazan los tuits con URL.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import requests

API = "https://api.x.com/2"
MAX_IMAGENES = 4
MAX_TUIT = 280
URL = re.compile(r"https?://|www\.", re.I)

EXPLICACIONES = {
    401: "X rechazó las credenciales: revisa X_API_KEY/X_API_SECRET/X_ACCESS_TOKEN/X_ACCESS_SECRET",
    402: "la cuenta de desarrollador de X no tiene créditos: recarga en console.x.com",
    403: "X no permite la acción: la app necesita permiso 'Read and write' y tokens generados "
         "después de darlo (o el tuit está repetido)",
    429: "límite de X alcanzado: reintenta más tarde",
}


class XError(RuntimeError):
    pass


class PublicacionParcial(XError):
    def __init__(self, mensaje: str, permalink: str):
        super().__init__(mensaje)
        self.permalink = permalink


@dataclass
class Publicado:
    media_id: str
    permalink: str
    duplicado: bool = False


def permalink(tuit_id: str) -> str:
    return f"https://x.com/i/web/status/{tuit_id}"


def credenciales() -> tuple[str, str, str, str]:
    from bpt.redactor.agente import cargar_env

    cargar_env()
    nombres = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
    valores = [os.environ.get(n, "").strip() for n in nombres]
    faltan = [n for n, v in zip(nombres, valores) if not v]
    if faltan:
        raise XError("faltan los secretos " + ", ".join(faltan))
    return tuple(valores)  # type: ignore[return-value]


def autenticacion(api_key: str, api_secret: str, token: str, secret: str):
    from requests_oauthlib import OAuth1

    return OAuth1(api_key, api_secret, token, secret)


def largo(texto: str) -> int:
    """Largo según X: las URL cuentan 23 y los emoji/CJK cuentan doble (aproximado)."""
    n = 0
    for ch in texto:
        o = ord(ch)
        if o in (0xFE0F, 0x200D):       # selector de variación y unión de emoji: no suman
            continue
        n += 1 if o <= 0x10FF or 0x2000 <= o <= 0x200D or 0x2010 <= o <= 0x201F \
            or 0x2032 <= o <= 0x2037 else 2
    return n


def revisar(tuits: list[str]) -> list[str]:
    problemas = []
    if not tuits or not tuits[0].strip():
        problemas.append("no hay hilo para X")
    for i, t in enumerate(tuits, 1):
        if URL.search(t):
            problemas.append(f"el tuit {i} trae un enlace (en X cada post con enlace cuesta "
                             "mucho más): quítalo y publícalo a mano")
        if largo(t) > MAX_TUIT:
            problemas.append(f"el tuit {i} pasa de {MAX_TUIT} caracteres")
    return problemas


class X:
    def __init__(self, auth=None, http=requests, secretos: tuple[str, ...] = ()):
        self.auth, self.http = auth, http
        self._secretos = [s for s in secretos if s]

    def _limpiar(self, texto: str) -> str:
        for s in self._secretos:
            texto = texto.replace(s, "<secreto>")
        return texto

    def _respuesta(self, r, que: str) -> dict:
        try:
            cuerpo = r.json()
        except Exception:  # noqa: BLE001
            cuerpo = {}
        estado = getattr(r, "status_code", 200)
        if estado >= 400 or (isinstance(cuerpo, dict) and cuerpo.get("errors")
                             and not cuerpo.get("data")):
            detalle = (cuerpo.get("detail") or cuerpo.get("title")
                       or "; ".join(e.get("message", "") for e in cuerpo.get("errors", []))
                       or f"HTTP {estado}")
            if "duplicate" in detalle.lower():
                raise XError(f"{que}: X lo rechaza por repetido (ya estaba publicado)")
            base = EXPLICACIONES.get(estado)
            raise XError(self._limpiar(f"{que}: {base} ({detalle})" if base else f"{que}: {detalle}"))
        return cuerpo

    def _post(self, url: str, que: str, **kw) -> dict:
        try:
            r = self.http.post(url, auth=self.auth, timeout=60, **kw)
        except Exception as e:  # noqa: BLE001
            raise XError(self._limpiar(f"{que}: {e}")) from None
        return self._respuesta(r, que)

    def cuenta(self) -> dict:
        try:
            r = self.http.get(f"{API}/users/me", auth=self.auth, timeout=60)
        except Exception as e:  # noqa: BLE001
            raise XError(self._limpiar(f"users/me: {e}")) from None
        return self._respuesta(r, "users/me").get("data", {})

    def subir(self, ruta: Path) -> str:
        with open(ruta, "rb") as f:
            cuerpo = self._post(f"{API}/media/upload", "media/upload",
                                files={"media": (Path(ruta).name, f, "image/jpeg")},
                                data={"media_category": "tweet_image"})
        return str(cuerpo["data"]["id"])

    def tuitear(self, texto: str, media_ids: list[str] | None = None,
                responde_a: str | None = None) -> str:
        cuerpo: dict = {"text": texto}
        if media_ids:
            cuerpo["media"] = {"media_ids": media_ids}
        if responde_a:
            cuerpo["reply"] = {"in_reply_to_tweet_id": responde_a}
        return str(self._post(f"{API}/tweets", "tweets", json=cuerpo)["data"]["id"])

    def publicar_hilo(self, imagenes: list[Path], tuits: list[str]) -> Publicado:
        problemas = revisar(tuits)
        if problemas:
            raise XError("; ".join(problemas))
        ids = [self.subir(p) for p in imagenes[:MAX_IMAGENES]]
        raiz = self.tuitear(tuits[0], ids)
        anterior = raiz
        for i, t in enumerate(tuits[1:], 2):
            try:
                anterior = self.tuitear(t, responde_a=anterior)
            except XError as e:
                raise PublicacionParcial(
                    f"hilo incompleto: salieron {i - 1} de {len(tuits)} tuits ({e})",
                    permalink(raiz)) from None
        return Publicado(raiz, permalink(raiz))
