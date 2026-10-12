"""Figuras del juego con un box score SINTÉTICO (forma de la MLB Stats API, datos inventados)."""
import json
from pathlib import Path

import pytest

from bpt import resultados
from bpt.data import mlb_box

FX = Path(__file__).parent / "fixtures"
PERSONAS = {int(k): v for k, v in json.loads(
    (FX / "mlb_people_sintetico.json").read_text(encoding="utf-8")).items() if k.isdigit()}


@pytest.fixture
def box():
    return json.loads((FX / "mlb_boxscore_sintetico_900002.json").read_text(encoding="utf-8"))


@pytest.fixture
def sched():
    return json.loads((FX / "mlb_postemporada_sintetico.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("ip,outs", [("6.0", 18), ("5.1", 16), ("4.2", 14), ("0.0", 0),
                                     (None, 0), ("7", 21)])
def test_innings_a_outs(ip, outs):
    assert mlb_box.ip_a_outs(ip) == outs


def test_game_score_formula():
    # Ejemplo de referencia: 9 IL, 0 H, 0 C, 0 BB, 10 K -> 40 + 54 + 10 = 104
    assert mlb_box.game_score(27, 10, 0, 0, 0, 0) == 104
    assert mlb_box.game_score(18, 8, 1, 4, 2, 2) == 56


def test_lineas_cuadran_con_la_pizarra(box):
    """Hits y carreras del box score = pizarra del juego 900002 (LAD 3-9, MIL 2-6)."""
    lad_b, mil_b = mlb_box.bateo(box, "away"), mlb_box.bateo(box, "home")
    lad_p, mil_p = mlb_box.pitcheo(box, "away"), mlb_box.pitcheo(box, "home")
    assert sum(b.h for b in lad_b) == 9 == sum(p.h for p in mil_p)
    assert sum(b.h for b in mil_b) == 6 == sum(p.h for p in lad_p)
    assert sum(p.c for p in mil_p) == 3 and sum(p.c for p in lad_p) == 2
    assert sum(p.outs for p in lad_p) == sum(p.outs for p in mil_p) == 33  # 11 entradas


def test_figuras(box):
    f = mlb_box.figuras(box)
    # El relevista gana por Game Score al abridor que permitió 2 jonrones
    assert f.mejor_pitcheo["LAD"].nombre == "Relevo LAD A"
    assert f.mejor_pitcheo["LAD"].game_score == 60
    assert f.mejor_pitcheo["MIL"].nombre == "Relevo MIL A"
    assert f.mejor_pitcheo["MIL"].game_score == 68
    assert f.mejor_pitcheo["MIL"].ip == "4.2" and not f.mejor_pitcheo["MIL"].abridor
    assert f.mejor_bateo["LAD"].nombre == "Bateador LAD Uno"
    assert f.mejor_bateo["LAD"].bases_totales == 7 and f.mejor_bateo["LAD"].bases_ganadas == 7
    # MIL Uno (2-5, HR: 5 BT) y MIL Dos (1-4, HR, BB: 4 BT + 1 BB) empatan en 5 bases ganadas,
    # impulsadas y anotadas: gana el de menos turnos
    assert f.mejor_bateo["MIL"].nombre == "Bateador MIL Dos"
    assert f.mejor_bateo["MIL"].bases_ganadas == 5
    assert {(h.equipo, h.nombre) for h in f.jonrones} == {
        ("LAD", "Bateador LAD Uno"), ("MIL", "Bateador MIL Uno"), ("MIL", "Bateador MIL Dos")}


def test_textos_de_linea(box):
    f = mlb_box.figuras(box)
    assert f.mejor_bateo["LAD"].texto() == "de 5-3, 2B, HR, 2 CI, 1 CA"
    assert f.mejor_bateo["MIL"].texto() == "de 4-1, HR, 1 CI, 1 CA, BB"
    assert f.mejor_pitcheo["MIL"].texto() == "4.2 IL, 2 H, 0 C, 0 CL, 1 BB, 6 K"


def test_pipeline_con_figuras(sched, box, tmp_path):
    r = resultados.generar("2026-10-12", salida=tmp_path, schedule=sched,
                           boxscores={900002: box},
                           personas=PERSONAS)
    j = r["juegos"][0]
    assert j["tarjetas"] == ["scln_j2_LAD-MIL_1_resultado.png", "scln_j2_LAD-MIL_2_figuras.png",
                             "scln_j2_LAD-MIL_3_latinos.png"]
    assert (tmp_path / "2026-10-12" / j["tarjetas"][1]).stat().st_size > 20_000
    fig = j["figuras"]
    assert fig["mejor_pitcheo"]["MIL"]["game_score"] == 68
    assert "Game Score" in fig["criterios"]["pitcheo"]


def test_sin_box_score_igual_sale_el_resultado(sched, tmp_path, monkeypatch):
    def falla(*a, **k):
        raise ConnectionError("sin red")
    monkeypatch.setattr(mlb_box, "fetch_boxscore", falla)
    r = resultados.generar("2026-10-12", salida=tmp_path, schedule=sched)
    j = r["juegos"][0]
    assert j["tarjetas"] == ["scln_j2_LAD-MIL_1_resultado.png"] and j["figuras"] is None
