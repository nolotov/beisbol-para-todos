"""Especiales: láminas de roster, pieza publicable y envío a Telegram (sin red)."""
import json
from pathlib import Path

import pytest
from PIL import Image

from bpt import especial
from bpt.notificar import telegram
from bpt.publicar import flujo, piezas

REAL = Path(__file__).parents[1] / "content" / "especiales" / "latinos-serie-mundial.json"


@pytest.fixture(scope="module")
def paquete(tmp_path_factory):
    salida = tmp_path_factory.mktemp("esp")
    r = especial.generar(REAL, salida)
    return Path(r["carpeta"]), r


def test_el_especial_real_pasa_las_revisiones_de_las_tres_redes(paquete):
    _, r = paquete
    assert r["alertas"] == []
    assert r["tarjetas"] == ["01_portada.png", "02_nacional.png", "03_americana.png"]


def test_laminas_1080x1350(paquete):
    carpeta, r = paquete
    for t in r["tarjetas"]:
        with Image.open(carpeta / t) as im:
            assert im.size == (1080, 1350)


def test_rosters_completos_y_un_latino_por_posicion():
    datos = especial.cargar(REAL)
    nac, ame = datos["rosters"]
    posiciones = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "SP", "RP"}
    assert {j["pos"] for j in nac["jugadores"]} == posiciones           # sin DH
    assert {j["pos"] for j in ame["jugadores"]} == posiciones | {"DH"}
    nombres = [j["nombre"] for r in datos["rosters"] for j in r["jugadores"]]
    assert len(nombres) == len(set(nombres))                              # nadie repetido
    assert sum(n for _, n in especial.paises(datos["rosters"])) == 21


def test_conteo_por_pais_venezuela_primero_en_empates():
    rosters = [{"jugadores": [{"pais": "Puerto Rico"}, {"pais": "Venezuela"}, {"pais": "Cuba"},
                              {"pais": "Cuba"}]}]
    assert especial.paises(rosters) == [("Cuba", 2), ("Venezuela", 1), ("Puerto Rico", 1)]


def test_especial_es_una_pieza_con_caption_e_hilo(paquete):
    carpeta, _ = paquete
    (p,) = piezas.piezas(carpeta)
    assert p.id == "1" and p.tipo == "post" and len(p.imagenes) == 3
    assert p.caption.startswith("⚾") and len(p.hilo) == 4
    assert p.redes("itx") == "itx"


def test_preparar_para_publicar(paquete, tmp_path):
    carpeta, _ = paquete
    plan = flujo.preparar(carpeta, "1", tmp_path / "pub", "77-1", tmp_path / "plan.json")
    assert len(plan["archivos"]) == 3 and plan["hilo"]


def test_falta_texto_se_rechaza(tmp_path):
    malo = tmp_path / "x.json"
    malo.write_text(json.dumps({"slug": "x", "titular": "t", "rosters": [],
                                "textos": {"instagram": "", "hilo_x": []}}), encoding="utf-8")
    with pytest.raises(especial.EspecialError):
        especial.cargar(malo)


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
        return Resp({"ok": True, "result": {"message_id": 5}})


def test_telegram_manda_el_especial_con_el_menu(paquete, monkeypatch):
    carpeta, _ = paquete
    for v in ("BPT_PUBLICAR_INSTAGRAM", "BPT_PUBLICAR_THREADS", "BPT_PUBLICAR_X"):
        monkeypatch.setenv(v, "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    http = TgFalso()
    tg = telegram.Telegram("123456789:AAHsecretoSecretoSecretoSecretoXYZ", "42", pausa=0,
                           http=http)
    assert telegram.enviar_dia(carpeta, tg) == 1
    assert http.llamadas[0]["data"]["text"].startswith("⭐ Especial · Los mejores latinos")
    ultimo = http.llamadas[-1]["data"]
    assert ultimo["text"].startswith("📸 Los mejores latinos")
    filas = json.loads(ultimo["reply_markup"])["inline_keyboard"]
    assert filas[-1][0]["callback_data"] == "pub:4242:1:itx:itx"
