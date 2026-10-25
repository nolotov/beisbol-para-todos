"""Qué se puede publicar de un paquete del día y cómo dejarlo listo para Instagram.

Una pieza es un carrusel con su caption:
  - MLB: una por juego, con id "1", "2"... (el orden del paquete de Telegram).
  - LVBP: la de la jornada, con id "jornada", y los extras de cada juego (resultado +
    figuras): como post con id "1", "2"... (orden de la jornada) y como historia con id
    "51", "52"... (50 + el mismo número). Ids numéricos para que el relé no cambie.
  - Especial (content/especiales/*.json): una sola, id "1", con caption e hilo.
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
ESPECIAL = "especial"
REEL = "reel"
HISTORIA_EXTRA = 50                     # id de la historia del juego n = 50 + n
ID_VALIDO = re.compile(r"^r?(\d{1,2}|jornada)$")     # "r1", "rjornada": el reel de esa pieza


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
    # Para las métricas: resultado (MLB), jornada (LVBP), especial, editor, historia_dia,
    # historia_especial
    formato: str = "resultado"

    @property
    def tiene_alertas(self) -> bool:
        return bool(self.alertas)

    def redes(self, activas: str) -> str:
        """De las redes activas, a cuáles puede ir esta pieza (letras i, t, x).

        La historia solo existe en Instagram. Instagram necesita caption; Threads y X, el hilo.
        """
        if self.tipo in (HISTORIA, REEL):
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
    if resumen.get("formato") == ESPECIAL:
        r = por_pk_especial(carpeta)
        imgs = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
        if not (r and imgs):
            return []
        return [Pieza("1", resumen["titular"], imgs, r["textos"]["instagram"], _alertas(r),
                      hilo=list(r["textos"].get("hilo_x") or []),
                      formato="editor" if resumen.get("editor") else "especial")]
    if resumen.get("formato") == HISTORIA:
        imgs = [carpeta / t for t in resumen.get("tarjetas", []) if (carpeta / t).exists()]
        if not imgs:
            return []                       # día sin juegos: no hay historia
        if resumen.get("titular"):           # historia especial (content/especiales)
            nombre = resumen["titular"]
        else:
            from bpt.historia import titular
            nombre = titular(resumen)
        formato = "historia_especial" if resumen.get("titular") else "historia_dia"
        return [Pieza("1", f"Historia · {nombre}", imgs[:1], "", tipo=HISTORIA,
                      formato=formato)]
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
                                hilo=list(r["textos"].get("hilo_x") or []), formato=JORNADA))
        salida += extras_lvbp(carpeta, resumen)
        return salida

    for n, j in enumerate(resumen.get("juegos", []), 1):
        r = por_pk.get(j["game_pk"])
        imgs = [carpeta / t for t in j.get("tarjetas", []) if (carpeta / t).exists()]
        if r and imgs:
            salida.append(Pieza(str(n), j["titular"], imgs, r["textos"]["instagram"],
                                _alertas(r), hilo=list(r["textos"].get("hilo_x") or [])))
    return salida


def _laminas_extra(carpeta: Path, resumen: dict, j: dict) -> list[Path]:
    nombres = j.get("extras")
    if nombres is None:                 # paquetes anteriores a 0.17.0: por el nombre
        if not (j.get("visitante") and j.get("local")):
            return []
        base = f"lvbp_extra_{j['visitante']['abrev']}-{j['local']['abrev']}_"
        nombres = [t for t in resumen.get("extras", []) if t.startswith(base)]
    return [carpeta / t for t in nombres if (carpeta / t).exists()]


def extras_lvbp(carpeta: Path, resumen: dict) -> list[Pieza]:
    """Por cada juego de la jornada con láminas extra: su post y su historia."""
    from bpt.publicar import textos_extra
    liga = resumen.get("liga", "LVBP")
    posts, historias = [], []
    for n, j in enumerate(resumen.get("juegos", []), 1):
        imgs = _laminas_extra(carpeta, resumen, j)
        if not imgs or n >= HISTORIA_EXTRA:
            continue
        titular = f"{liga} · {j['titular']}"
        posts.append(Pieza(str(n), titular, imgs, textos_extra.caption(j),
                           hilo=textos_extra.hilo(j), formato="extra_juego"))
        historias.append(Pieza(str(HISTORIA_EXTRA + n), f"Historia · {titular}", imgs, "",
                               tipo=HISTORIA, formato="historia_extra"))
    return posts + historias


def por_pk_especial(carpeta: Path) -> dict | None:
    tp = Path(carpeta) / "textos.json"
    if not tp.exists():
        return None
    return next((r for r in json.loads(tp.read_text(encoding="utf-8"))
                 if r.get("game_pk") == ESPECIAL), None)


def reel_de(carpeta: Path, base: Pieza) -> Pieza | None:
    """El Reel de una pieza (reel_<id>.mp4, armado por bpt.video.reel), con su caption."""
    video = Path(carpeta) / f"reel_{base.id}.mp4"
    if not video.exists() or not base.caption.strip():
        return None
    return Pieza(f"r{base.id}", f"Reel · {base.titular}", [video], base.caption,
                 base.alertas, tipo=REEL, formato=REEL)


def buscar(carpeta: Path, pieza_id: str) -> Pieza:
    if not ID_VALIDO.match(pieza_id or ""):
        raise PiezaError(f"id de pieza inválido: {pieza_id!r}")
    if pieza_id.startswith("r"):
        base = buscar(carpeta, pieza_id[1:])
        reel = reel_de(carpeta, base)
        if reel is None:
            raise PiezaError(f"la pieza {pieza_id[1:]} no tiene Reel en el paquete")
        return reel
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


HISTORIA_W, HISTORIA_H = 1080, 1920


def a_historia(origen: Path, destino: Path, calidad: int = 95) -> Path:
    """Como a_jpeg, pero en 9:16: si la lámina no lo es (las extra son 1080x1350), se centra
    sobre un lienzo 1080x1920 del color de su propia esquina (el fondo de la marca), en vez de
    dejar que Instagram la recorte o le ponga su fondo."""
    a_jpeg(origen, destino, calidad)
    with Image.open(destino) as im:
        if im.width * HISTORIA_H == im.height * HISTORIA_W:
            return destino
        escala = min(HISTORIA_W / im.width, HISTORIA_H / im.height)
        chica = im.resize((round(im.width * escala), round(im.height * escala)),
                          Image.LANCZOS)
        lienzo = Image.new("RGB", (HISTORIA_W, HISTORIA_H), im.getpixel((0, 0)))
    lienzo.paste(chica, ((HISTORIA_W - chica.width) // 2, (HISTORIA_H - chica.height) // 2))
    lienzo.save(destino, "JPEG", quality=calidad, optimize=True)
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
    if pieza.tipo == REEL:                      # el video va tal cual
        import shutil
        rel = f"{prefijo}/{pieza.imagenes[0].name}"
        (destino / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pieza.imagenes[0], destino / rel)
        archivos.append(rel)
    for i, img in enumerate(pieza.imagenes if pieza.tipo != REEL else [], 1):
        rel = f"{prefijo}/{i:02d}_{img.stem}.jpg"
        (a_historia if pieza.tipo == HISTORIA else a_jpeg)(img, destino / rel)
        archivos.append(rel)
    return {"pieza": pieza.id, "tipo": pieza.tipo, "titular": pieza.titular,
            "caption": pieza.caption, "hilo": pieza.hilo, "alertas": pieza.alertas,
            "formato": pieza.formato, "archivos": archivos}
