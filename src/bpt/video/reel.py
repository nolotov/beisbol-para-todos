"""Reels: video vertical (1080x1920) con las láminas de una pieza y la voz del guion.

El guion del redactor ya viene marcado con [LÁMINA 1], [LÁMINA 2]…: cada tramo se lee con
voz sintética venezolana (edge-tts, voces es-VE) mientras se ve su lámina, con subtítulos
abajo. Sin voz (edge-tts caído o apagado) sale igual, mudo, con 4 s por lámina y los
subtítulos del guion: sirve para publicar con música desde la app.

Zonas seguras de Reels: arriba ~220 px (perfil) y abajo ~420 px (caption y botones).
La lámina va arriba y los subtítulos justo debajo, fuera de la franja de los botones.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bpt import theme

W, H = 1080, 1920
FPS = 30
VOZ = os.environ.get("BPT_VOZ", "es-VE-SebastianNeural")   # o es-VE-PaolaNeural
VELOCIDAD = os.environ.get("BPT_VOZ_VELOCIDAD", "+8%")
SEG_SIN_VOZ = 4.0
Y_LAMINA = 150                  # la lámina (1080x1350) ocupa de 150 a 1500
Y_SUBS = 1530                   # subtítulos: de 1530 a ~1700
PALABRAS_POR_SUB = 9
MARCA = re.compile(r"\[\s*L[ÁA]MINA\s*(\d+)\s*\]", re.I)


class ReelError(RuntimeError):
    pass


@dataclass
class Tramo:
    lamina: int          # índice 0-based de la lámina
    texto: str


def tramos(guion: str, n_laminas: int) -> list[Tramo]:
    """Parte el guion por las marcas [LÁMINA n]. Lo que va antes de la primera marca es de
    la lámina 1; una marca fuera de rango usa la última lámina."""
    partes = MARCA.split(guion)
    salida: list[Tramo] = []
    if len(partes) > 1 and partes[0].strip():
        salida.append(Tramo(0, partes[0].strip()))
    for k in range(1, len(partes) - 1, 2):
        texto = partes[k + 1].strip()
        if texto:
            idx = min(max(int(partes[k]) - 1, 0), n_laminas - 1)
            salida.append(Tramo(idx, texto))
    if not salida and guion.strip():
        # Guion sin marcas: las frases se reparten en orden entre las láminas
        frases = [f for f in re.split(r"(?<=[.!?])\s+", guion.strip()) if f]
        n = max(1, min(n_laminas, len(frases)))
        for i in range(n):
            grupo = frases[i * len(frases) // n:(i + 1) * len(frases) // n]
            salida.append(Tramo(i, " ".join(grupo)))
    return salida


def subtitulos(texto: str, n: int = PALABRAS_POR_SUB) -> list[str]:
    """Trozos de hasta `n` palabras, cortando de preferencia en signos de puntuación."""
    palabras = texto.split()
    trozos, actual = [], []
    for p in palabras:
        actual.append(p)
        if len(actual) >= n or (len(actual) >= n // 2 and p[-1] in ".!?;:"):
            trozos.append(" ".join(actual))
            actual = []
    if actual:
        trozos.append(" ".join(actual))
    return trozos


# --- Herramientas externas -------------------------------------------------------------

def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise ReelError("falta ffmpeg: instálalo o `pip install imageio-ffmpeg`") from None


def _correr(args: list[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise ReelError(f"ffmpeg falló: {r.stderr[-500:]}")
    return r


def duracion(audio: Path) -> float:
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(audio)], capture_output=True,
                       text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise ReelError(f"no pude medir {audio.name}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def tts(texto: str, destino: Path, voz: str = VOZ) -> Path:
    """Voz sintética con edge-tts. Lanza ReelError si no está o falla la red."""
    try:
        import edge_tts
    except ImportError:
        raise ReelError("falta edge-tts (pip install edge-tts)") from None

    async def _hablar():
        await edge_tts.Communicate(texto, voz, rate=VELOCIDAD).save(str(destino))

    try:
        asyncio.run(_hablar())
    except Exception as e:  # noqa: BLE001
        raise ReelError(f"edge-tts falló: {e}") from None
    if not destino.exists() or destino.stat().st_size == 0:
        raise ReelError("edge-tts no devolvió audio")
    return destino


# --- Cuadros ----------------------------------------------------------------------------

def _fuente(negrita: bool, tamano: int) -> ImageFont.FreeTypeFont:
    from matplotlib import font_manager
    familia = theme.TITLE_FONTS
    try:
        ruta = font_manager.findfont(font_manager.FontProperties(
            family=familia, weight="bold" if negrita else "normal"), fallback_to_default=True)
        return ImageFont.truetype(ruta, tamano)
    except (OSError, ValueError):
        return ImageFont.load_default()


def _envolver(draw, texto: str, fuente, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for p in texto.split():
        prueba = f"{actual} {p}".strip()
        if draw.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def cuadro(lamina: Path, sub: str, progreso: float, destino: Path,
           handle: str = theme.HANDLE) -> Path:
    lienzo = Image.new("RGB", (W, H), theme.BG)
    with Image.open(lamina) as im:
        im = im.convert("RGB")
        if im.size != (1080, 1350):
            im.thumbnail((1080, 1350))
        lienzo.paste(im, ((W - im.width) // 2, Y_LAMINA))
    d = ImageDraw.Draw(lienzo)
    # Barra de progreso arriba y la marca
    d.rectangle([0, 0, W, 10], fill=theme.SURFACE)
    d.rectangle([0, 0, int(W * max(0.0, min(progreso, 1.0))), 10], fill=theme.ACCENT)
    d.text((W // 2, 70), "MBP · BÉISBOL PARA TODOS", font=_fuente(True, 34),
           fill=theme.ACCENT, anchor="ma")
    if sub:
        f = _fuente(True, 50)
        y = Y_SUBS
        for linea in _envolver(d, sub, f, W - 120)[:3]:
            d.text((W // 2, y), linea, font=f, fill=theme.TEXT, anchor="ma",
                   stroke_width=3, stroke_fill=theme.BG)
            y += 62
    lienzo.save(destino)
    return destino


# --- Armado -------------------------------------------------------------------------------

def armar(laminas: list[Path], guion: str, salida: Path, voz: bool = True,
          handle: str = theme.HANDLE) -> dict:
    """Arma el reel. Devuelve {"archivo", "duracion", "voz": bool, "aviso"}."""
    if not laminas:
        raise ReelError("no hay láminas")
    partes = tramos(guion, len(laminas)) or [Tramo(i, "") for i in range(len(laminas))]
    salida = Path(salida)
    aviso = ""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        audios: list[Path] = []
        duraciones: list[float] = []
        con_voz = voz
        if voz:
            try:
                for i, t in enumerate(partes):
                    a = tts(t.texto, tmp / f"voz_{i:02d}.mp3")
                    audios.append(a)
                    duraciones.append(duracion(a) + 0.25)
            except ReelError as e:
                con_voz, audios, duraciones = False, [], []
                aviso = f"sin voz ({e})"
        if not con_voz:
            duraciones = [max(SEG_SIN_VOZ, 0.42 * len(t.texto.split())) for t in partes]

        total = sum(duraciones)
        lista, t0 = [], 0.0
        for i, (t, dur) in enumerate(zip(partes, duraciones)):
            subs = subtitulos(t.texto) or [""]
            palabras = [max(len(s.split()), 1) for s in subs]
            for j, (s, n) in enumerate(zip(subs, palabras)):
                d = dur * n / sum(palabras)
                img = cuadro(laminas[t.lamina], s, (t0 + d) / total, tmp / f"c_{i:02d}_{j:02d}.png",
                             handle)
                lista.append((img, d))
                t0 += d
        concat = tmp / "cuadros.txt"
        lineas = [f"file '{img.as_posix()}'\nduration {d:.3f}" for img, d in lista]
        lineas.append(f"file '{lista[-1][0].as_posix()}'")      # el demuxer ignora la última duración
        concat.write_text("\n".join(lineas) + "\n", encoding="utf-8")

        args = [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat)]
        if con_voz:
            pausa = tmp / "pausa.mp3"
            _correr([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                     "anullsrc=r=48000:cl=mono", "-t", "0.25", str(pausa)])
            alista = tmp / "audios.txt"
            alista.write_text("".join(f"file '{a.as_posix()}'\nfile '{pausa.as_posix()}'\n"
                                      for a in audios), encoding="utf-8")
            args += ["-f", "concat", "-safe", "0", "-i", str(alista)]
        else:
            args += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        args += ["-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "20", "-profile:v", "high", "-c:a", "aac", "-b:a", "128k",
                 "-ar", "48000", "-t", f"{total:.3f}", "-movflags", "+faststart",
                 str(salida)]
        salida.parent.mkdir(parents=True, exist_ok=True)
        _correr(args)
    return {"archivo": salida.name, "duracion": round(total, 1), "voz": con_voz,
            "aviso": aviso}


def armar_paquete(carpeta: Path, voz: bool = True, handle: str = theme.HANDLE) -> list[dict]:
    """Un reel por cada pieza del paquete que tenga guion: reel_<id>.mp4. Anota los reels en
    resumen.json ("reels": {id: {...}}) para que Telegram ofrezca publicarlos."""
    from bpt.publicar import piezas as P
    carpeta = Path(carpeta)
    tp = carpeta / "textos.json"
    if not tp.exists():
        return []
    textos = json.loads(tp.read_text(encoding="utf-8"))
    por_pk = {str(r["game_pk"]): r for r in textos}
    resumen_p = carpeta / "resumen.json"
    resumen = json.loads(resumen_p.read_text(encoding="utf-8"))
    hechos = []
    for p in P.piezas(carpeta):
        if p.tipo != "post":
            continue
        r = _textos_de_pieza(resumen, por_pk, p.id)
        guion = ((r or {}).get("textos") or {}).get("guion", "")
        if not guion.strip():
            continue
        with theme.deporte(resumen.get("deporte")):     # misma paleta que las láminas
            info = armar(p.imagenes, guion, carpeta / f"reel_{p.id}.mp4", voz=voz,
                         handle=handle)
        info["pieza"] = p.id
        hechos.append(info)
    if hechos:
        resumen["reels"] = {h["pieza"]: h for h in hechos}
        resumen_p.write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    return hechos


def _textos_de_pieza(resumen: dict, por_pk: dict, pieza_id: str) -> dict | None:
    if resumen.get("formato") == "especial":
        return por_pk.get("especial")
    if pieza_id == "jornada":
        return por_pk.get("jornada")
    juegos = resumen.get("juegos", [])
    n = int(pieza_id) - 1
    return por_pk.get(str(juegos[n]["game_pk"])) if 0 <= n < len(juegos) else None
