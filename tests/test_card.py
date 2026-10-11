"""Tests offline con un CSV sintético (no son datos reales de jugadores)."""
from pathlib import Path

import pytest

from bpt.cli import main
from bpt.data import savant

FIXTURE = Path(__file__).parent / "fixtures" / "percentiles_pitcher_sample.csv"


def test_busqueda_por_nombre_flexible():
    df = savant.load_percentiles("pitcher", 2025, source_csv=FIXTURE)
    assert savant.find_player(df, "lanzador prueba")["player_id"] == 100001
    assert savant.find_player(df, "Zurdo")["player_id"] == 100002


def test_jugador_inexistente():
    df = savant.load_percentiles("pitcher", 2025, source_csv=FIXTURE)
    with pytest.raises(LookupError):
        savant.find_player(df, "Nadie")


def test_metricas_omiten_nulos():
    df = savant.load_percentiles("pitcher", 2025, source_csv=FIXTURE)
    keys = [m[0] for m in savant.player_metrics(savant.find_player(df, "Zurdo"), "pitcher")]
    assert "fb_spin" not in keys and "xera" in keys


def test_cli_genera_png(tmp_path):
    rc = main(["card", "Lanzador Prueba", "--csv", str(FIXTURE), "--salida", str(tmp_path)])
    assert rc == 0
    pngs = list(tmp_path.glob("*.png"))
    assert len(pngs) == 1 and pngs[0].stat().st_size > 10_000


def test_backend_sin_ventanas():
    import matplotlib

    import bpt  # noqa: F401

    assert matplotlib.get_backend().lower() == "agg"
