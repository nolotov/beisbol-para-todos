"""Tests de estadísticas por equipo con respuestas reales de stats.lvbp.com (2025-26)."""
from pathlib import Path

import pytest

from bpt.cli import main
from bpt.data import lvbp

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tabla():
    bat = lvbp.parse_collectives(
        (FIX / "lvbp_collectives_hittings_2025.html").read_text(encoding="utf-8"),
        ("bat-tab-pane", "adv_bat-tab-pane"))
    pit = lvbp.parse_collectives(
        (FIX / "lvbp_collectives_pitchings_2025.html").read_text(encoding="utf-8"),
        ("pit-tab-pane", "adv_pit-tab-pane"))
    return lvbp.build_team_table(bat, pit)


def test_ocho_equipos_y_sin_splits(tabla):
    assert len(tabla) == 8
    assert set(tabla["codigo"]) == set(lvbp.TEAMS)
    assert (tabla["G"] + tabla["P"] == 56).all()  # totales, no En Casa/Visitante


def test_derivadas(tabla):
    mag = tabla.set_index("codigo").loc["MAG"]
    assert mag["dif"] == mag["CA"] - mag["CP"]
    assert mag["pit_K%"] == pytest.approx(mag["pit_K"] / mag["pit_BE"])
    assert mag["pit_K%"] < 0.30 < mag["pit_Strike%"]  # el 'K%' de la fuente es Strike%
    assert (tabla["pyth_G"] + tabla["pyth_P"] == 56).all()


def test_pitagorico_castiga_diferencial_negativo(tabla):
    agu = tabla.set_index("codigo").loc["AGU"]
    assert agu["dif"] < 0 and agu["pyth_G"] < agu["G"]


def test_ranking_direccion(tabla):
    era_rank = lvbp.team_rank(tabla, "pit_EFE", higher_better=False)
    assert tabla.loc[era_rank.idxmin(), "pit_EFE"] == tabla["pit_EFE"].min()
    ops_rank = lvbp.team_rank(tabla, "bat_OPS", higher_better=True)
    assert tabla.loc[ops_rank.idxmin(), "bat_OPS"] == tabla["bat_OPS"].max()


def test_cli_genera_las_ocho(tabla, tmp_path, monkeypatch):
    monkeypatch.setattr(lvbp, "fetch_team_stats", lambda *a, **k: tabla)
    assert main(["lvbp-equipos", "--salida", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("lvbp_equipo_*_2025.png"))) == 8
    assert main(["lvbp-equipos", "--equipo", "XYZ", "--salida", str(tmp_path)]) == 1
