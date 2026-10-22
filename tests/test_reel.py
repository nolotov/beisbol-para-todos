"""Reels: guion por láminas, video mudo de respaldo, pieza "r1", publicación y Telegram."""
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from bpt.publicar import flujo, piezas, redes
from bpt.video import reel


def _hay_ffmpeg() -> bool:
    try:
        reel.ffmpeg()
        return True
    except reel.ReelError:
        return False


def test_tramos_con_marcas():
    t = reel.tramos("Arranque. [LÁMINA 2] Segunda. [lamina 7] Fuera de rango.", 3)
    assert [(x.lamina, x.texto) for x in t] == [(0, "Arranque."), (1, "Segunda."),
                                                (2, "Fuera de rango.")]


def test_tramos_sin_marcas_reparte_las_frases():
    t = reel.tramos("Uno. Dos. Tres. Cuatro.", 2)
    assert [(x.lamina, x.texto) for x in t] == [(0, "Uno. Dos."), (1, "Tres. Cuatro.")]


def test_subtitulos_cortos():
    subs = reel.subtitulos("Los Rays casi no se ponchan. Milwaukee anota sin jonrones y "
                           "con mucha velocidad en las bases cada noche.")
    assert subs[0] == "Los Rays casi no se ponchan."
    assert all(len(s.split()) <= reel.PALABRAS_POR_SUB for s in subs)


def _paquete(tmp_path, guion="[LÁMINA 1] Hola. [LÁMINA 2] Chao."):
    carpeta = tmp_path / "esp"
    carpeta.mkdir()
    for i, color in enumerate(("#0B1426", "#16233D"), 1):
        Image.new("RGB", (1080, 1350), color).save(carpeta / f"0{i}.png")
    (carpeta / "resumen.json").write_text(json.dumps(
        {"formato": "especial", "titular": "Prueba", "tarjetas": ["01.png", "02.png"]}),
        encoding="utf-8")
    (carpeta / "textos.json").write_text(json.dumps([{"game_pk": "especial", "titular": "Prueba", "textos": {
        "instagram": "Caption ⚾", "hilo_x": ["uno"], "guion": guion},
        "validacion": {"ok": True, "cifras_sin_respaldo": [], "alertas": []}}]),
        encoding="utf-8")
    return carpeta


@pytest.mark.skipif(not _hay_ffmpeg(), reason="sin ffmpeg")
def test_reel_mudo_cuando_no_hay_voz(tmp_path, monkeypatch):
    def sin_red(*a, **k):
        raise reel.ReelError("sin red")
    monkeypatch.setattr(reel, "tts", sin_red)
    carpeta = _paquete(tmp_path)
    (h,) = reel.armar_paquete(carpeta)
    assert h["pieza"] == "1" and not h["voz"] and "sin red" in h["aviso"]
    assert (carpeta / "reel_1.mp4").stat().st_size > 1000
    assert reel.duracion(carpeta / "reel_1.mp4") == pytest.approx(h["duracion"], abs=0.5)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["reels"]["1"]["archivo"] == "reel_1.mp4"


@pytest.mark.skipif(not _hay_ffmpeg(), reason="sin ffmpeg")
def test_reel_con_voz_usa_la_duracion_del_audio(tmp_path, monkeypatch):
    def voz_falsa(texto, destino, voz=reel.VOZ):
        reel._correr([reel.ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                      "sine=frequency=440:sample_rate=48000", "-t", "1.5", str(destino)])
        return destino
    monkeypatch.setattr(reel, "tts", voz_falsa)
    info = reel.armar([_paquete(tmp_path) / "01.png"] * 2, "[LÁMINA 1] A. [LÁMINA 2] B.",
                      tmp_path / "r.mp4")
    assert info["voz"] and info["duracion"] == pytest.approx(2 * 1.75, abs=0.25)


def test_pieza_reel_y_su_plan(tmp_path):
    carpeta = _paquete(tmp_path)
    with pytest.raises(piezas.PiezaError, match="no tiene Reel"):
        piezas.buscar(carpeta, "r1")
    (carpeta / "reel_1.mp4").write_bytes(b"\x00" * 2048)
    p = piezas.buscar(carpeta, "r1")
    assert p.tipo == "reel" and p.formato == "reel" and p.caption == "Caption ⚾"
    assert p.redes("itx") == "i"
    plan = piezas.preparar(p, tmp_path / "publico", "77-r1")
    assert plan["archivos"] == ["77-r1/reel_1.mp4"] and plan["tipo"] == "reel"
    assert (tmp_path / "publico" / "77-r1" / "reel_1.mp4").read_bytes() == b"\x00" * 2048


def test_menu_del_reel():
    assert redes.menu("5", "r1", "i")[0][0]["text"] == "🎬 Publicar Reel en Instagram"


class FakeIG:
    def __init__(self, recientes=()):
        self.llamadas, self.recientes_ = [], list(recientes)
        self.pausa, self.espera_max = 3.0, 90.0
        self.user_id = "9"

    def _llamar(self, verbo, ruta, params=None):
        self.llamadas.append((verbo, ruta, dict(params or {})))
        if ruta == "9/media" and verbo == "GET":
            return {"data": self.recientes_}
        if ruta == "9/media":
            return {"id": "cont1"}
        if ruta == "cont1":
            return {"status_code": "FINISHED"}
        if ruta == "9/media_publish":
            return {"id": "m1"}
        if ruta == "m1":
            return {"permalink": "https://instagram.com/reel/m1"}
        raise AssertionError(ruta)


def _ig(fake):
    from bpt.publicar.instagram import Instagram
    ig = Instagram("tok", "9", pausa=0)
    ig._llamar = fake._llamar
    return ig


def test_publicar_reel_en_instagram(tmp_path):
    fake = FakeIG(recientes=[{"id": "c0", "caption": "Caption ⚾", "media_type": "CAROUSEL_ALBUM"}])
    plan = {"pieza": "r1", "tipo": "reel", "titular": "Reel", "caption": "Caption ⚾",
            "archivos": ["77-r1/reel_1.mp4"], "formato": "reel"}
    (r_i, r_t) = flujo.publicar_redes(plan, "it", "https://raw.example/abc", tmp_path,
                                      {"i": lambda: _ig(fake), "t": lambda: None})
    assert r_i.ok and r_i.permalink.endswith("/reel/m1") and r_i.media_id == "m1"
    assert not r_t.ok and "solo van a Instagram" in r_t.motivo
    crear = [c for c in fake.llamadas if c[0] == "POST" and c[1] == "9/media"][0][2]
    assert crear == {"media_type": "REELS", "video_url": "https://raw.example/abc/77-r1/reel_1.mp4",
                     "caption": "Caption ⚾", "share_to_feed": "true"}


def test_un_reel_ya_publicado_no_se_repite_pero_el_carrusel_no_cuenta():
    fake = FakeIG(recientes=[{"id": "v0", "caption": "Caption ⚾", "media_type": "VIDEO",
                              "permalink": "https://instagram.com/reel/v0"}])
    hecho = _ig(fake).publicar_reel("https://x/y.mp4", "Caption ⚾")
    assert hecho.duplicado and hecho.media_id == "v0"


def test_telegram_manda_el_reel_con_su_boton(tmp_path, monkeypatch):
    from bpt.notificar import telegram
    monkeypatch.setenv("GITHUB_RUN_ID", "321")
    monkeypatch.setenv("BPT_PUBLICAR_INSTAGRAM", "1")
    carpeta = _paquete(tmp_path)
    (carpeta / "reel_1.mp4").write_bytes(b"\x00" * 2048)
    r = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    r["reels"] = {"1": {"duracion": 36.4, "voz": True}}
    (carpeta / "resumen.json").write_text(json.dumps(r), encoding="utf-8")

    class TG:
        def __init__(self):
            self.eventos = []

        def texto(self, t):
            self.eventos.append(("texto", t))

        def album(self, *a, **k):
            self.eventos.append(("album",))

        def video(self, archivo, leyenda=None):
            self.eventos.append(("video", Path(archivo).name, leyenda))

        def botones(self, texto, filas, **k):
            self.eventos.append(("botones", texto, filas))

    tg = TG()
    telegram.enviar_dia(carpeta, tg=tg)
    video = [e for e in tg.eventos if e[0] == "video"]
    assert video == [("video", "reel_1.mp4", "🎬 Reel · 36 s · con voz")]
    ultimo = tg.eventos[-1]
    assert ultimo[0] == "botones" and ultimo[1].startswith("🎬 Reel · Prueba")
    assert ultimo[2][0][0]["callback_data"] == "pub:321:r1"
