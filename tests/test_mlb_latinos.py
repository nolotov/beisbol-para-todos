"""Latinos en el juego, con box score y países SINTÉTICOS."""
import json
from pathlib import Path

import pytest

from bpt import resultados
from bpt.data import mlb_box, mlb_people
from bpt.viz.latinos_card import resumen_paises

FX = Path(__file__).parent / "fixtures"
DECISIONES = {"ganador": "Pitcher Ganador Dos", "perdedor": "Pitcher Perdedor Dos",
              "salvado": None}


@pytest.fixture
def box():
    return json.loads((FX / "mlb_boxscore_sintetico_900002.json").read_text(encoding="utf-8"))


@pytest.fixture
def personas():
    d = json.loads((FX / "mlb_people_sintetico.json").read_text(encoding="utf-8"))
    return {int(k): v for k, v in d.items() if k.isdigit()}


def test_quienes_y_en_que_orden(box, personas):
    lat = mlb_box.latinos(box, personas, DECISIONES)
    assert [(a.nombre, a.codigo) for a in lat] == [
        ("Relevo MIL A", "CUW"),          # figura de MIL, Game Score 68
        ("Pitcher Ganador Dos", "VEN"),   # GS 50, pero se llevó la victoria
        ("Bateador LAD Uno", "VEN"),      # jonrón, 7 bases ganadas
        ("Bateador MIL Dos", "PUR"),      # jonrón, 5
        ("Bateador LAD Dos", "DOM"),      # 2 hits, 4
        ("Bateador MIL Tres", "CUB"),     # 3 hits, 3
        ("Pitcher Perdedor Dos", "MEX"),  # sin nada destacado: va al final
    ]
    por_nombre = {a.nombre: a for a in lat}
    assert por_nombre["Relevo MIL A"].motivo == "mejor salida en la loma de su equipo"
    assert por_nombre["Pitcher Ganador Dos"].motivo == "se llevó la victoria"
    assert por_nombre["Bateador LAD Uno"].motivo == "jonrón"
    assert por_nombre["Bateador MIL Tres"].motivo == "3 hits"
    assert not por_nombre["Pitcher Perdedor Dos"].destacada
    assert por_nombre["Pitcher Perdedor Dos"].linea.endswith("perdedor")
    assert por_nombre["Bateador LAD Uno"].pais == "Venezuela"


def test_no_latinos_quedan_fuera(box, personas):
    nombres = {a.nombre for a in mlb_box.latinos(box, personas, DECISIONES)}
    assert "Relevo LAD A" not in nombres      # Japón
    assert "Bateador LAD Tres" not in nombres  # EE. UU.


def test_caribe_neerlandes_es_opcional(box, personas):
    lat = mlb_box.latinos(box, personas, DECISIONES, incluir_caribe_neerlandes=False)
    assert "CUW" not in {a.codigo for a in lat} and len(lat) == 6


def test_resumen_de_paises(box, personas):
    lat = mlb_box.latinos(box, personas, DECISIONES)
    assert resumen_paises(lat) == ("7 peloteros  ·  VEN 2  ·  CUB 1  ·  CUW 1  ·  DOM 1  ·  "
                                   "MEX 1  ·  PUR 1")


def test_sin_aparicion_al_plato_no_cuenta(box, personas):
    p = box["teams"]["away"]["players"]["ID104"]["stats"]["batting"]
    p.update(atBats=0, hits=0, doubles=0, baseOnBalls=0, plateAppearances=0)
    personas[104] = {"pais_api": "Venezuela"}
    assert "Bateador LAD Cuatro" not in {a.nombre for a in mlb_box.latinos(box, personas)}


def test_fetch_people_usa_cache_y_pide_solo_faltantes(tmp_path, monkeypatch):
    llamadas = []

    def falso(path, params):
        llamadas.append(params["personIds"])
        ids = params["personIds"].split(",")
        return {"people": [{"id": int(i), "fullName": f"J{i}", "birthCountry": "Venezuela",
                            "birthCity": "Barquisimeto"} for i in ids]}

    monkeypatch.setattr(mlb_people, "_get", falso)
    cache = tmp_path / "people.json"
    assert mlb_people.fetch_people([1, 2], cache=cache)[1]["pais_api"] == "Venezuela"
    mlb_people.fetch_people([1, 2, 3], cache=cache)
    assert llamadas == ["1,2", "3"]


def test_pipeline_lamina_y_json(box, personas, tmp_path):
    sched = json.loads((FX / "mlb_postemporada_sintetico.json").read_text(encoding="utf-8"))
    r = resultados.generar("2026-10-12", salida=tmp_path, schedule=sched,
                           boxscores={900002: box}, personas=personas)
    j = r["juegos"][0]
    assert j["tarjetas"][-1] == "scln_j2_LAD-MIL_3_latinos.png"
    assert (tmp_path / "2026-10-12" / j["tarjetas"][-1]).stat().st_size > 20_000
    assert j["latinos"][0]["nombre"] == "Relevo MIL A" and j["latinos"][0]["valor"] == 68


def test_sin_latinos_no_hay_lamina(box, tmp_path):
    sched = json.loads((FX / "mlb_postemporada_sintetico.json").read_text(encoding="utf-8"))
    r = resultados.generar("2026-10-12", salida=tmp_path, schedule=sched,
                           boxscores={900002: box}, personas={})
    j = r["juegos"][0]
    assert j["latinos"] == [] and len(j["tarjetas"]) == 2
