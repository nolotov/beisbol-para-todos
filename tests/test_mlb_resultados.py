"""Resultados MLB con un fixture SINTÉTICO que imita la forma de la MLB Stats API."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bpt import resultados
from bpt.data import mlb_stats

FIXTURE = Path(__file__).parent / "fixtures" / "mlb_postemporada_sintetico.json"


@pytest.fixture
def sched():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_juego_final(sched):
    j = mlb_stats.games_on(sched, "2026-10-11")[0]
    assert j.final and j.juego_n == 1 and j.serie_corto == "SCLN"
    assert j.serie_es == "Serie de Campeonato de la Liga Nacional"
    assert (j.visitante.abrev, j.visitante.carreras, j.visitante.hits, j.visitante.errores) == ("LAD", 1, 5, 1)
    assert (j.local.abrev, j.local.carreras) == ("MIL", 2)
    assert j.ganador.abrev == "MIL" and j.perdedor.abrev == "LAD"
    assert j.salvado_pitcher == "Cerrador Uno"
    # el local no batea la baja de la novena: la API omite sus carreras
    assert j.entradas[-1] == (9, 0, None)
    assert j.extra_innings == 0


def test_extrainnings_y_titular(sched):
    from bpt.viz.result_card import titular
    j = mlb_stats.games_on(sched, "2026-10-12")[0]
    assert j.extra_innings == 2
    assert titular(j) == "LAD le gana 3-2 a MIL en 11 entradas"
    assert j.salvado_pitcher is None


def test_estado_serie_por_fecha(sched):
    s1 = mlb_stats.estado_series(sched, hasta="2026-10-11")["NL Championship Series"]
    assert s1.equipos == {"LAD": 0, "MIL": 1} and s1.texto == "MIL lidera 1-0"
    s2 = mlb_stats.estado_series(sched, hasta="2026-10-12")["NL Championship Series"]
    assert s2.texto == "Serie empatada 1-1" and s2.lider is None
    assert s2.para_ganar == 4 and s2.ganador is None


def test_pospuesto_se_deduplica(sched):
    juegos = mlb_stats.all_games(sched)
    assert [j.game_pk for j in juegos].count(900004) == 1
    j4 = next(j for j in juegos if j.game_pk == 900004)
    assert j4.fecha == "2026-10-15" and j4.estado == "Programado"


def test_estado_pospuesto(sched):
    g = sched["dates"][2]["games"][1]
    assert mlb_stats.parse_game(g).estado == "Pospuesto"


def test_generar_tarjetas_y_resumen(sched, tmp_path):
    r = resultados.generar("2026-10-12", salida=tmp_path, schedule=sched)
    carpeta = tmp_path / "2026-10-12"
    assert (carpeta / "resumen.json").exists()
    assert len(r["juegos"]) == 1 and r["pendientes"] == []
    j = r["juegos"][0]
    assert j["titular"] == "LAD le gana 3-2 a MIL en 11 entradas"
    assert j["estado_serie"]["texto"] == "Serie empatada 1-1"
    assert (carpeta / j["tarjeta"]).stat().st_size > 20_000
    assert r["fuente"] == "Datos: MLB Stats API"


def test_generar_con_pendientes(sched, tmp_path):
    r = resultados.generar("2026-10-15", salida=tmp_path, schedule=sched)
    assert r["juegos"] == []
    assert r["pendientes"][0]["partido"] == "MIL @ LAD"


def test_juego_no_final_no_genera_tarjeta(sched, tmp_path):
    from bpt.viz.result_card import render_result_card
    j = mlb_stats.games_on(sched, "2026-10-15")[0]
    with pytest.raises(ValueError):
        render_result_card(j, None, tmp_path / "x.png")


def test_ayer_en_hora_del_este():
    # 00:30 del 12 en Santiago (UTC-3) = 23:30 del 11 en Nueva York -> ayer = 10 oct
    t = datetime(2026, 10, 12, 0, 30, tzinfo=ZoneInfo("America/Santiago"))
    assert resultados.ayer_mlb(t) == "2026-10-10"
