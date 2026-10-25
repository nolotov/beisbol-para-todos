"""Extras de la jornada LVBP: post e historia por juego (0.17.0), con datos REALES."""
import json
from pathlib import Path

import pytest
from PIL import Image

from bpt import lvbp_resultados as L
from bpt.data import mlb_box
from bpt.notificar import telegram
from bpt.publicar import flujo, instagram, piezas, textos_extra
from bpt.publicar.x import MAX_TUIT, largo

FX = Path(__file__).parent / "fixtures"
TOKEN_TG = "123456789:AAHsecretoSecretoSecretoSecretoXYZ"


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def json(self):
        return self.cuerpo


class TgFalso:
    def __init__(self):
        self.llamadas = []

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas.append({"metodo": url.rsplit("/", 1)[-1], "data": data or {}})
        return Resp({"ok": True, "result": {"message_id": 99}})


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    def falla(*a, **k):
        raise ConnectionError("sin red en tests")
    monkeypatch.setattr(mlb_box, "fetch_boxscore", falla)


@pytest.fixture
def paquete(tmp_path):
    sched = json.loads((FX / "lvbp_calendario_2025-10-15_16.json").read_text(encoding="utf-8"))
    box = json.loads((FX / "lvbp_boxscore_829812.json").read_text(encoding="utf-8"))
    L.generar("2025-10-15", salida=tmp_path, refresh=False, schedule=sched,
              boxscores={829812: box})
    return tmp_path / "2025-10-15"


def test_cada_juego_trae_sus_extras(paquete):
    r = json.loads((paquete / "resumen.json").read_text(encoding="utf-8"))
    j = next(x for x in r["juegos"] if x["game_pk"] == 829812)
    assert j["extras"] == ["lvbp_extra_TIG-CAR_resultado.png", "lvbp_extra_TIG-CAR_figuras.png"]


def test_post_e_historia_por_juego_aun_sin_textos(paquete):
    # Sin textos.json no hay pieza "jornada", pero los extras no dependen del redactor
    todas = {p.id: p for p in piezas.piezas(paquete)}
    assert "jornada" not in todas
    post, hist = todas["1"], todas["51"]
    assert post.tipo == "post" and post.formato == "extra_juego"
    assert post.titular == "LVBP · TIG le gana 8-3 a CAR"
    assert [i.name for i in post.imagenes] == [i.name for i in hist.imagenes]
    assert post.redes("itx") == "itx"
    assert hist.tipo == piezas.HISTORIA and hist.redes("itx") == "i"
    assert hist.titular.startswith("Historia · ")
    assert piezas.buscar(paquete, "51").id == "51"


def test_paquete_viejo_sin_campo_extras_los_encuentra_por_nombre(paquete):
    rp = paquete / "resumen.json"
    r = json.loads(rp.read_text(encoding="utf-8"))
    for j in r["juegos"]:
        j.pop("extras")
    rp.write_text(json.dumps(r), encoding="utf-8")
    assert {p.id for p in piezas.piezas(paquete)} == {"1", "51"}


def test_caption_e_hilo_salen_del_box_score(paquete):
    p = piezas.buscar(paquete, "1")
    assert p.caption.startswith("⚾ Tigres 8, Cardenales 3\n")
    assert "Quedan 1-0; los Cardenales, 0-1." in p.caption
    assert "• TIG: José A. Martínez, de 3-2, 1 CI, 2 CA, 2 BB" in p.caption
    assert "💣 Jonrones: Danry Vasquez (CAR)" in p.caption
    assert "G: Daniel Juarez · P: Max Castillo" in p.caption
    assert "Game Score" not in p.caption            # ninguna salida llegó a 50
    assert "http" not in p.caption and "#LVBP" in p.caption
    (tuit,) = p.hilo
    assert largo(tuit) <= MAX_TUIT and "http" not in tuit


def test_nombres_cortos():
    assert textos_extra.corto("Leones del Caracas") == "Leones"
    assert textos_extra.corto("Tiburones de La Guaira") == "Tiburones"
    assert textos_extra.corto("Navegantes del Magallanes") == "Navegantes"


def test_hilo_largo_suelta_detalles():
    j = {"visitante": {"nombre": "Tigres de Aragua", "abrev": "TIG", "carreras": 9,
                       "ganador": True},
         "local": {"nombre": "Cardenales de Lara", "abrev": "CAR", "carreras": 8},
         "entradas": [[i, 0, 0] for i in range(1, 13)], "extra_innings": 3,
         "ganador_pitcher": "A" * 60, "perdedor_pitcher": "B" * 60, "salvado_pitcher": "C" * 60,
         "figuras": {"jonrones": [{"nombre": "J" * 30, "equipo": "TIG", "cantidad": 1}] * 5,
                     "mejor_bateo": {"TIG": {"nombre": "N" * 30, "linea": "de 6-5, 2 HR"}}}}
    (tuit,) = textos_extra.hilo(j)
    assert largo(tuit) <= MAX_TUIT and "(12 entradas)" in tuit


def test_historia_queda_en_9_16_sin_tocar_el_post(paquete, tmp_path):
    plan = piezas.preparar(piezas.buscar(paquete, "51"), tmp_path / "pub", "9-51")
    assert len(plan["archivos"]) == 2 and plan["tipo"] == piezas.HISTORIA
    for rel in plan["archivos"]:
        with Image.open(tmp_path / "pub" / rel) as im:
            assert im.size == (1080, 1920)
            assert im.getpixel((5, 5)) == im.getpixel((540, 200))   # relleno con el fondo
    plan = piezas.preparar(piezas.buscar(paquete, "1"), tmp_path / "pub", "9-1")
    with Image.open(tmp_path / "pub" / plan["archivos"][0]) as im:
        assert im.size == (1080, 1350)


class IgFalso:
    def __init__(self, falla_en=None):
        self.urls, self.falla_en = [], falla_en

    def publicar_historia(self, url):
        if len(self.urls) == self.falla_en:
            raise instagram.InstagramError("se cayó Meta")
        self.urls.append(url)
        return instagram.Publicado(f"m{len(self.urls)}", f"https://ig/{len(self.urls)}")


def test_las_dos_historias_salen_en_orden():
    ig = IgFalso()
    hecho = flujo.historias(ig, ["https://a/1.jpg", "https://a/2.jpg"])
    assert ig.urls == ["https://a/1.jpg", "https://a/2.jpg"] and hecho.media_id == "m1"


def test_segunda_historia_falla_no_ofrece_reintentar(tmp_path):
    plan = {"pieza": "51", "tipo": piezas.HISTORIA, "titular": "Historia · LVBP · X",
            "archivos": ["a/1.jpg", "a/2.jpg"], "caption": "", "hilo": []}
    (r,) = flujo.publicar_redes(plan, "i", "https://raw/x", tmp_path,
                                {"i": lambda: IgFalso(falla_en=1)})
    assert not r.ok and r.parcial and "salieron 1 de 2" in r.motivo
    (r,) = flujo.publicar_redes(plan, "i", "https://raw/x", tmp_path,
                                {"i": lambda: IgFalso(falla_en=0)})
    assert not r.ok and not r.parcial                 # nada salió: sí se puede reintentar


def test_telegram_ofrece_post_e_historia_por_juego(paquete, monkeypatch):
    monkeypatch.setenv("BPT_PUBLICAR_INSTAGRAM", "1")
    monkeypatch.setenv("BPT_PUBLICAR_X", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "77")
    tele = TgFalso()
    tg = telegram.Telegram(TOKEN_TG, "42", pausa=0, http=tele)
    assert telegram.ofrecer_extras(tg, paquete) == 1
    textos = [c["data"]["text"] for c in tele.llamadas]
    assert textos[0].startswith("🗂️ EXTRA · LVBP · TIG le gana 8-3 a CAR")
    assert textos[1].startswith("📸 LVBP · TIG le gana 8-3 a CAR")
    assert textos[2].startswith("📲 Historia · LVBP · TIG le gana 8-3 a CAR")
    menu_post = json.loads(tele.llamadas[1]["data"]["reply_markup"])["inline_keyboard"]
    assert [b["callback_data"] for b in menu_post[0]] == ["pub:77:1:i:ix", "pub:77:1:x:ix"]
    (boton,), = json.loads(tele.llamadas[2]["data"]["reply_markup"])["inline_keyboard"]
    assert boton == {"text": "📲 Publicar historia en Instagram", "callback_data": "pub:77:51"}


def test_sin_interruptor_no_hay_menus(paquete, monkeypatch):
    for v in ("BPT_PUBLICAR_INSTAGRAM", "BPT_PUBLICAR_THREADS", "BPT_PUBLICAR_X"):
        monkeypatch.delenv(v, raising=False)
    tele = TgFalso()
    assert telegram.ofrecer_extras(telegram.Telegram(TOKEN_TG, "42", pausa=0, http=tele),
                                   paquete) == 0
    assert tele.llamadas == []
