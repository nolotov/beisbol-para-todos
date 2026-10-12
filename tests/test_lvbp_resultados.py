"""Jornada LVBP con datos REALES de la MLB Stats API (15 y 16 de octubre de 2025)."""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bpt import lvbp_resultados as L
from bpt.data import mlb_box, mlb_stats
from bpt.notificar import telegram
from bpt.redactor import agente, prompt
from bpt.redactor.validador import validar

FX = Path(__file__).parent / "fixtures"


@pytest.fixture
def sched():
    return json.loads((FX / "lvbp_calendario_2025-10-15_16.json").read_text(encoding="utf-8"))


@pytest.fixture
def box():
    return json.loads((FX / "lvbp_boxscore_829812.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    def falla(*a, **k):
        raise ConnectionError("sin red en tests")
    monkeypatch.setattr(mlb_box, "fetch_boxscore", falla)


def test_nuestras_siglas_y_nombres_con_tilde(sched):
    juegos = {j.game_pk: j for j in mlb_stats.all_games(sched)}
    j = juegos[829812]                      # Tigres 8 @ Cardenales 3
    assert (j.visitante.abrev, j.local.abrev) == ("TIG", "CAR")   # la API dice ARA y LAR
    assert j.local.nombre == "Cardenales de Lara"
    assert (j.visitante.record, j.local.record) == ("1-0", "0-1")
    assert j.ganador_pitcher == "Daniel Juarez" and j.perdedor_pitcher == "Max Castillo"
    leones = next(x for x in juegos.values() if 695 in (x.visitante.id, x.local.id))
    eq = leones.visitante if leones.visitante.id == 695 else leones.local
    assert eq.abrev == "LEO"                # la API le dice CAR a Caracas
    aguilas = next(x for x in juegos.values() if 692 in (x.visitante.id, x.local.id))
    assert "Águilas del Zulia" in (aguilas.visitante.nombre, aguilas.local.nombre)


def test_figuras_reales_y_minimo_de_entradas(box):
    f = mlb_box.figuras(box)
    # Sin el mínimo, la "mejor salida" de Lara era un relevo de 1 entrada (GS 48)
    assert f.mejor_pitcheo["CAR"].outs >= 9 and f.mejor_pitcheo["CAR"].nombre == "Max Castillo"
    assert f.mejor_bateo["CAR"].nombre == "Danry Vasquez"
    assert f.mejor_bateo["CAR"].texto() == "de 4-1, HR, 2 CI, 1 CA"
    assert [(h.nombre, h.equipo) for h in f.jonrones] == [("Danry Vasquez", "CAR")]


def test_destacados_con_minimos(sched, box):
    juegos = [j for j in mlb_stats.all_games(sched) if j.fecha == "2025-10-15"]
    d = L.destacados(juegos, {829812: box})
    assert [x["nombre"] for x in d["bateo"]][:2] == ["Danry Vasquez", "José A. Martínez"]
    assert all(x["valor"] >= L.MIN_BASES_GANADAS for x in d["bateo"])
    assert d["bateo"][0]["rival"] == "TIG"
    # Las salidas largas de ese día fueron malas (GS 35 y 28): no son "destacadas"
    assert d["pitcheo"] == []
    assert d["jonrones"] == [{"nombre": "Danry Vasquez", "equipo": "CAR", "cantidad": 1}]


def test_jornada_completa(sched, box, tmp_path):
    r = L.generar("2025-10-15", salida=tmp_path, schedule=sched, boxscores={829812: box})
    assert r["formato"] == "jornada" and r["liga"] == "LVBP"
    assert r["temporada_label"] == "2025-26" and r["fase"] == "Temporada regular"
    assert r["tarjetas"] == ["lvbp_1_jornada.png", "lvbp_2_destacados.png"]
    assert r["extras"] == ["lvbp_extra_TIG-CAR_resultado.png", "lvbp_extra_TIG-CAR_figuras.png"]
    for t in r["tarjetas"] + r["extras"]:
        assert (tmp_path / "2025-10-15" / t).stat().st_size > 20_000


def test_jornada_sin_box_scores(sched, tmp_path):
    r = L.generar("2025-10-16", salida=tmp_path, schedule=sched)
    assert len(r["juegos"]) == 4 and r["tarjetas"] == ["lvbp_1_jornada.png"]
    assert r["destacados"]["bateo"] == [] and len(r["extras"]) == 4   # solo resultados


def test_temporada_y_ayer():
    assert L.temporada_de("2026-10-12") == 2026 and L.temporada_de("2027-01-15") == 2026
    t = datetime(2026, 10, 13, 0, 30, tzinfo=ZoneInfo("America/Santiago"))  # 23:30 en Caracas
    assert L.ayer_ven(t) == "2026-10-11"


# --- Redactor y Telegram en modo jornada ---------------------------------------

class Cliente:
    def __init__(self, textos):
        self.textos, self.llamadas, self.messages = textos, [], self

    def create(self, **kw):
        self.llamadas.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text",
                                                        text=json.dumps(self.textos))],
                               stop_reason="end_turn")


GUION = ("[LÁMINA 1] " + "Arrancó la zafra con todo. " * 12 + "[LÁMINA 2] Danry Vasquez se "
         "fue de 4-1 con jonrón y 2 impulsadas. ¿Quién la rompe mañana?")
TEXTOS = {"instagram": "Los Tigres le ganaron 8-3 a los Cardenales y quedan 1-0.",
          "hilo_x": ["Tigres 8, Cardenales 3.", "Los Tigres quedan 1-0.",
                     "Danry Vasquez se fue de 4-1 con jonrón."],
          "guion": GUION, "angulo": "Arranque de zafra"}


def test_redactor_jornada(sched, box, tmp_path):
    L.generar("2025-10-15", salida=tmp_path, schedule=sched, boxscores={829812: box})
    cli = Cliente(TEXTOS)
    res = agente.redactar_dia(tmp_path / "2025-10-15", client=cli)
    assert len(res) == 1 and res[0]["game_pk"] == "jornada"
    assert res[0]["validacion"]["ok"], res[0]["validacion"]
    kw = cli.llamadas[0]
    assert "MODO JORNADA LVBP" in kw["system"]
    assert "Danry Vasquez" in kw["messages"][0]["content"]


def test_validador_jornada_marca_cifras_inventadas(sched, box, tmp_path):
    r = L.generar("2025-10-15", salida=tmp_path, schedule=sched, boxscores={829812: box})
    d = prompt.datos_jornada(r)
    v = validar(dict(TEXTOS, instagram="Los Tigres llevan 12 victorias seguidas."), d)
    assert v.cifras_sin_respaldo == ["12"]


class Http:
    def __init__(self):
        self.llamadas = []

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas.append((url.rsplit("/", 1)[-1], data or {}, sorted(files or {})))
        return SimpleNamespace(json=lambda: {"ok": True, "result": {}})


def test_telegram_jornada(sched, box, tmp_path):
    carpeta = tmp_path / "2025-10-15"
    L.generar("2025-10-15", salida=tmp_path, schedule=sched, boxscores={829812: box})
    agente.redactar_dia(carpeta, client=Cliente(TEXTOS))
    http = Http()
    assert telegram.enviar_dia(carpeta, telegram.Telegram("1:x", "42", pausa=0, http=http)) == 1
    metodos = [m for m, _, _ in http.llamadas]
    assert metodos == ["sendMessage",       # encabezado con marcadores
                       "sendMediaGroup",    # carrusel
                       "sendMediaGroup",    # originales
                       "sendMediaGroup",    # extras (2 archivos)
                       "sendMessage", "sendMessage", "sendMessage", "sendMessage",
                       "sendMessage"]
    assert "TIG le gana 8-3 a CAR" in http.llamadas[0][1]["text"]


def test_telegram_un_solo_archivo_no_usa_album(tmp_path):
    """sendMediaGroup exige 2-10 elementos: con 1 archivo va sendDocument."""
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG")
    http = Http()
    telegram.Telegram("1:x", "42", pausa=0, http=http).album([png], como_archivo=True)
    assert http.llamadas[0][0] == "sendDocument" and http.llamadas[0][2] == ["document"]
