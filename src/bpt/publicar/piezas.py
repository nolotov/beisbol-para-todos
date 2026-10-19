"""Qué se puede publicar de un paquete del día y cómo dejarlo listo para Instagram.

Una pieza es un carrusel con su caption:
  - MLB: una por juego, con id "1", "2"... (el orden del paquete de Telegram).
  - LVBP: una sola, la de la jornada, con id "jornada".
  - Historia del día (juegos de hoy): una sola, id "1" y sin caption (las historias no
    llevan). Usa "1" para que el relé de Telegram no necesite cambios.

Instagram solo acepta JPEG, así que las láminas (PNG) se convierten antes de subirlas.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

JORNADA = "jornada"
HISTORIA = "historia"
ID_VALIDO = re.compile(r"^(\d{1,2}|jornada)$")


class PiezaError(ValueError):
    pass


@dataclass
class Pieza:
    id: str
    titular: str
    imagenes: list[Path]
    caption: str
    alertas: list[str] = field(default_factory=list)
    tipo: str = "post"            # "post" (imagen o carrusel) o "historia"
    hilo: list[str] = field(default_factory=list)   # hilo_x del redactor (X y Threads)

    @property
    def tiene_alertas(self) -> bool:
        return bool(self.alertas)

    def redes(self, activas: str) -> str:
        """De las redes activas, a cuáles puede ir esta pieza (letras i, t, x).

        La historia solo existe en Instagram. Instagram necesita caption; Threads y X, el hilo.
        """
        if self.tipo == HISTORIA:
            return "i" if "i" in activas else ""
        sirve = {"i": bool(self.caption.strip()), "t": bool(self.hilo), "x": bool(self.hilo)}
        return "".join(c for c in "itx" if c in activas and sirve[c])


def _alertas(r: dict) -> list[str]:
    v = r.get("validacion") or {}
    salida = list(v.get("alertas") or [])
    if v.get("cifras_sin_respaldo"):
        salida.append("cifras sin respaldo: " + ", ".join(v["cifras_sin_respaldo"]))
    return salida


def piezas(carpeta: Path) -> list[Pieza]:
    """Todas las piezas publicables del paquete (las que tienen láminas y caption)."""
    carpeta = Path(carpeta)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    if resumen.get("formato") == HISTORIA:
        imgs = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
        if not imgs:
            return []                       # día sin juegos: no hay historia
        from bpt.historia import titular
        return [Pieza("1", f"Historia · {titular(resumen)}", imgs[:1], "", tipo=HISTORIA)]
    tp = carpeta / "textos.json"
    redactados = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else []
    por_pk = {r["game_pk"]: r for r in redactados}

    salida: list[Pieza] = []
    if resumen.get("formato") == "jornada":
        r = por_pk.get(JORNADA)
        imgs = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
        if r and imgs:
            liga = resumen.get("liga", "LVBP")
            salida.append(Pieza(JORNADA, f"{liga} · Jornada del {resumen['fecha']}", imgs,
                                r["textos"]["instagram"], _alertas(r),
                                hilo=list(r["textos"].get("hilo_x") or [])))
        return salida

    for n, j in enumerate(resumen.get("juegos", []), 1):
        r = por_pk.get(j["game_pk"])
        imgs = [carpeta / t for t in j.get("tarjetas", []) if (carpeta / t).exists()]
        if r and imgs:
            salida.append(Pieza(str(n), j["titular"], imgs, r["textos"]["instagram"],
                                _alertas(r), hilo=list(r["textos"].get("hilo_x") or [])))
    return salida


def buscar(carpeta: Path, pieza_id: str) -> Pieza:
    if not ID_VALIDO.match(pieza_id or ""):
        raise PiezaError(f"id de pieza inválido: {pieza_id!r}")
    for p in piezas(carpeta):
        if p.id == pieza_id:
            return p
    raise PiezaError(f"la pieza {pieza_id} no está en el paquete (sin láminas o sin caption)")


def a_jpeg(origen: Path, destino: Path, calidad: int = 95) -> Path:
    """PNG (o lo que sea) -> JPEG RGB sin transparencia."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(origen) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            fondo = Image.new("RGB", im.size, (0, 0, 0))
            fondo.paste(im, mask=im.split()[-1])
            im = fondo
        else:
            im = im.convert("RGB")
        im.save(destino, "JPEG", quality=calidad, optimize=True)
    return destino


def preparar(pieza: Pieza, destino: Path, prefijo: str) -> dict:
    """Convierte las láminas a JPEG en `destino/prefijo/` (lo único que se hace público).

    Devuelve el plan: {"pieza", "titular", "caption", "alertas", "archivos": [rutas
    relativas a destino]}. El plan no se guarda dentro de `destino`: lo escribe quien llama.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", prefijo):
        raise PiezaError(f"prefijo inválido: {prefijo!r}")
    destino = Path(destino)
    archivos = []
    for i, img in enumerate(pieza.imagenes, 1):
        rel = f"{prefijo}/{i:02d}_{img.stem}.jpg"
        a_jpeg(img, destino / rel)
        archivos.append(rel)
    return {"pieza": pieza.id, "tipo": pieza.tipo, "titular": pieza.titular,
            "caption": pieza.caption, "hilo": pieza.hilo, "alertas": pieza.alertas,
            "archivos": archivos}
