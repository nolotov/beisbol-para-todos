"""Historia diaria: cartelera de juegos de hoy (sin red, con calendarios de prueba)."""
import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from bpt import historia
from bpt.notificar import telegram
from bpt.publicar import flujo, piezas

FIX = Path(__file__).parent / "fixtures"
FECHA = "2026-10-15"


def _cal(nombre):
    return json.loads((FIX / nombre).read_text(encoding="utf-8"))


def _preview(g, fecha, hora_utc, abridores=(None, None)):
    g = copy.deepcopy(g)
    g["officialDate"] = fecha
    g["gameDate"] = f"{fecha}T{hora_utc}:00Z"
    g["status"] = {"abstractGameState": "Preview", "detailedState": "Scheduled",
                   "startTimeTBD": False}
    for lado, nombre in zip(("away", "home"), abridores):
        g["teams"][lado].pop("probablePitcher", None)
        g["teams"][lado].pop("isWinner", None)
        if nombre:
            g["teams"][lado]["probablePitcher"] = {"id": 1, "fullName": nombre}
    g.pop("linescore", None)
    g.pop("decisions", None)
    return g


def calendario_mlb(fecha=FECHA):
    post = _cal("mlb_postemporada_sintetico.json")
    base = next(g for d in post["dates"] for g in d["games"] if g["gamePk"] == 900004)
    g = _preview(base, fecha, "23:08", ("Freddy Peralta", "Yoshinobu Yamamoto"))
    return {"dates": [{"date": fecha, "games": [g]}]}, post


def calendario_lvbp(fecha=FECHA, n=4):
    cal = _cal("lvbp_calendario_2025-10-15_16.json")
    juegos = [g for d in cal["dates"] for g in d["games"]][:n]
    horas = ["22:00", "23:00", "23:30", "23:45"]
    return {"dates": [{"date": fecha, "games": [
        _preview(g, fecha, horas[i % 4], ("Eduardo Rodríguez", None) if i == 0 else (None, None))
        for i, g in enumerate(juegos)]}]}


VACIO = {"dates": []}


# --- Datos --------------------------------------------------------------------------

def test_hora_en_venezuela():
    assert historia.hora_ven("2026-10-15T23:08:00Z") == "7:08 p. m."
    assert historia.hora_ven("2026-10-16T00:00:00Z") == "8:00 p. m."
    assert historia.hora_ven("2026-10-15T16:05:00Z") == "12:05 p. m."


def test_cartelera_mlb_postemporada_con_serie_y_abridores():
    mlb, post = calendario_mlb()
    r = historia.juegos_de_hoy(FECHA, mlb, VACIO, post)
    (j,) = r["MLB"]
    assert j.liga == "MLB" and j.hora == "7:08 p. m." and j.estado == "Programado"
    assert j.abridores == "Peralta vs. Yamamoto"
    assert j.detalle.startswith("Serie de Campeonato") or "Juego" in j.detalle
    assert r["LVBP"] == []
    assert historia.fase(r["MLB"], "MLB") == "Postemporada"


def test_cartelera_lvbp_con_records_y_abridor_por_anunciar():
    r = historia.juegos_de_hoy(FECHA, VACIO, calendario_lvbp())
    assert len(r["LVBP"]) == 4
    j = r["LVBP"][0]
    assert j.abridores == "Rodríguez vs. Por anunciar"
    assert " vs. " in j.detalle                       # récords "1-0 vs. 0-1"
    assert r["LVBP"][1].abridores is None
    assert historia.fase(r["LVBP"], "LVBP") == "Temporada regular"


def test_hora_por_definir_y_cancelados_fuera():
    lv = calendario_lvbp(n=2)
    lv["dates"][0]["games"][0]["status"]["startTimeTBD"] = True
    lv["dates"][0]["games"][1]["status"] = {"abstractGameState": "Final",
                                            "detailedState": "Cancelled"}
    (j,) = historia.juegos_de_hoy(FECHA, VACIO, lv)["LVBP"]
    assert j.hora == "Por definir"


def test_juegos_de_otra_fecha_no_entran():
    lv = calendario_lvbp(fecha="2026-10-14")
    assert historia.juegos_de_hoy(FECHA, VACIO, lv)["LVBP"] == []


# --- Generar --------------------------------------------------------------------------

def test_sin_juegos_no_se_dibuja_nada(tmp_path):
    r = historia.generar(FECHA, tmp_path, calendarios=(VACIO, VACIO, None))
    assert r["total"] == 0 and r["tarjetas"] == [] and r["ligas"] == {}
    assert not (tmp_path / FECHA / historia.ARCHIVO).exists()
    assert piezas.piezas(tmp_path / FECHA) == []          # nada que publicar


@pytest.mark.parametrize("n_lvbp", [0, 4, 15])
def test_lamina_vertical_1080x1920(tmp_path, n_lvbp):
    mlb, post = calendario_mlb()
    lv = calendario_lvbp(n=4)
    lv["dates"][0]["games"] = [copy.deepcopy(g) for g in lv["dates"][0]["games"] * 4][:n_lvbp]
    for i, g in enumerate(lv["dates"][0]["games"]):
        g["gamePk"] = 800000 + i
    r = historia.generar(FECHA, tmp_path, calendarios=(mlb, lv, post))
    assert r["formato"] == "historia" and r["total"] == 1 + n_lvbp
    with Image.open(tmp_path / FECHA / historia.ARCHIVO) as im:
        assert im.size == (1080, 1920)


def test_solo_lvbp(tmp_path):
    r = historia.generar(FECHA, tmp_path, calendarios=(VACIO, calendario_lvbp(), None))
    assert list(r["ligas"]) == ["LVBP"] and r["tarjetas"] == [historia.ARCHIVO]


# --- Pieza publicable -------------------------------------------------------------------

@pytest.fixture
def paquete(tmp_path):
    mlb, post = calendario_mlb()
    historia.generar(FECHA, tmp_path, calendarios=(mlb, calendario_lvbp(), post))
    return tmp_path / FECHA


def test_la_historia_es_una_pieza_sin_caption(paquete):
    (p,) = piezas.piezas(paquete)
    assert p.id == "1" and p.tipo == "historia" and p.caption == ""
    assert p.titular == "Historia · Juegos de hoy · jueves 15 de octubre"
    assert [i.name for i in p.imagenes] == [historia.ARCHIVO]


def test_preparar_historia_lleva_el_tipo_en_el_plan(paquete, tmp_path):
    plan = flujo.preparar(paquete, "1", tmp_path / "pub", "55-1", tmp_path / "plan.json")
    assert plan["tipo"] == "historia" and plan["archivos"] == ["55-1/01_historia.jpg"]
    with Image.open(tmp_path / "pub" / plan["archivos"][0]) as im:
        assert im.format == "JPEG" and im.size == (1080, 1920)


# --- Telegram ---------------------------------------------------------------------------

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
        return Resp({"ok": True, "result": {"message_id": 7}})


def _tg(http):
    return telegram.Telegram("123456789:AAHsecretoSecretoSecretoSecretoXYZ", "42", pausa=0,
                             http=http)


def test_telegram_manda_la_historia_y_el_boton(paquete, monkeypatch):
    monkeypatch.setenv("BPT_PUBLICAR_INSTAGRAM", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "321")
    http = TgFalso()
    assert telegram.enviar_dia(paquete, _tg(http)) == 5
    metodos = [c["metodo"] for c in http.llamadas]
    assert metodos == ["sendPhoto", "sendDocument", "sendMessage"]
    assert "MLB" in http.llamadas[0]["data"]["caption"]
    boton = http.llamadas[-1]["data"]
    assert boton["text"].startswith("📲 Historia · Juegos de hoy")
    teclado = json.loads(boton["reply_markup"])["inline_keyboard"]
    assert teclado[0][0]["callback_data"] == "pub:321:1"
    assert "historia" in teclado[0][0]["text"].lower()


def test_telegram_sin_juegos_no_manda_nada(tmp_path):
    historia.generar(FECHA, tmp_path, calendarios=(VACIO, VACIO, None))
    http = TgFalso()
    assert telegram.enviar_dia(tmp_path / FECHA, _tg(http)) == 0
    assert http.llamadas == []
