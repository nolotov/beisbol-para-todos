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
    s1 = mlb_stats.estado_series(sched, hasta="2026-10-11")["NL Championship Series|LAD-MIL"]
    assert s1.equipos == {"LAD": 0, "MIL": 1} and s1.texto == "MIL lidera 1-0"
    s2 = mlb_stats.estado_series(sched, hasta="2026-10-12")["NL Championship Series|LAD-MIL"]
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
    r = resultados.generar("2026-10-12", salida=tmp_path, schedule=sched, con_figuras=False)
    carpeta = tmp_path / "2026-10-12"
    assert (carpeta / "resumen.json").exists()
    assert len(r["juegos"]) == 1 and r["pendientes"] == []
    j = r["juegos"][0]
    assert j["titular"] == "LAD le gana 3-2 a MIL en 11 entradas"
    assert j["estado_serie"]["texto"] == "Serie empatada 1-1"
    assert (carpeta / j["tarjeta"]).stat().st_size > 20_000
    assert r["fuente"] == "Datos: MLB Stats API"


def test_generar_con_pendientes(sched, tmp_path):
    r = resultados.generar("2026-10-15", salida=tmp_path, schedule=sched, con_figuras=False)
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


def _ds_game(pk, fecha, n, away, home, ganador_local):
    def eq(ab, score, win):
        return {"team": {"id": hash(ab) % 1000, "name": ab, "abbreviation": ab},
                "score": score, "isWinner": win}
    return {"gamePk": pk, "gameType": "D", "officialDate": fecha,
            "gameDate": f"{fecha}T20:00:00Z",
            "status": {"abstractGameState": "Final", "detailedState": "Final"},
            "seriesDescription": "NL Division Series", "seriesGameNumber": n,
            "gamesInSeries": 5, "venue": {"name": "Estadio de prueba"},
            "teams": {"away": eq(away, 1 if ganador_local else 2, not ganador_local),
                      "home": eq(home, 2 if ganador_local else 1, ganador_local)}}


def test_dos_divisionales_simultaneas_no_se_mezclan(tmp_path):
    """Regresión: las dos NLDS comparten seriesDescription. LAD-ATL va 2-1, PHI-CHC 2-2."""
    juegos = [
        _ds_game(1, "2026-10-04", 1, "ATL", "LAD", True),   # LAD
        _ds_game(2, "2026-10-04", 1, "CHC", "PHI", True),   # PHI
        _ds_game(3, "2026-10-05", 2, "ATL", "LAD", False),  # ATL
        _ds_game(4, "2026-10-05", 2, "CHC", "PHI", True),   # PHI
        _ds_game(5, "2026-10-07", 3, "LAD", "ATL", False),  # LAD
        _ds_game(6, "2026-10-07", 3, "PHI", "CHC", True),   # CHC
        _ds_game(7, "2026-10-08", 4, "PHI", "CHC", True),   # CHC
    ]
    sched = {"dates": [{"date": "x", "games": juegos}]}
    series = mlb_stats.estado_series(sched, hasta="2026-10-08", tipo="D")
    lad = series["NL Division Series|ATL-LAD"]
    phi = series["NL Division Series|CHC-PHI"]
    assert lad.equipos == {"ATL": 1, "LAD": 2} and lad.texto == "LAD lidera 2-1"
    assert lad.para_ganar == 3
    assert phi.texto == "Serie empatada 2-2"

    r = resultados.generar("2026-10-07", tipo="D", salida=tmp_path, schedule=sched,
                           con_figuras=False)
    textos = {j["titular"]: j["estado_serie"]["texto"] for j in r["juegos"]}
    assert textos["LAD le gana 2-1 a ATL"] == "LAD lidera 2-1"



def test_avisa_si_la_fase_no_coincide(sched, tmp_path, monkeypatch, capsys):
    from bpt import cli
    from bpt.data import mlb_stats as ms
    monkeypatch.setattr(ms, "fetch_postseason", lambda *a, **k: sched)
    rc = cli.main(["mlb-resultados", "--fecha", "2026-10-11", "--fase", "D",
                   "--salida", str(tmp_path)])
    assert rc == 2
    assert "--fase L (Serie de Campeonato)" in capsys.readouterr().out


def test_rechaza_fecha_futura(tmp_path, capsys):
    from bpt import cli
    rc = cli.main(["mlb-resultados", "--fecha", "2099-12-10", "--salida", str(tmp_path)])
    assert rc == 1 and "fecha futura" in capsys.readouterr().err
