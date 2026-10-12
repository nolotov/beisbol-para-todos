"""Tests de estadísticas por equipo con respuestas crudas de stats.lvbp.com (2025-26, sin <tbody>)."""
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
    assert len(list(tmp_path.glob("lvbp_equipo_*_2025.png"))) == 9  # portada + 8
    assert (tmp_path / "lvbp_equipo_00_portada_2025.png").exists()
    assert main(["lvbp-equipos", "--equipo", "XYZ", "--salida", str(tmp_path)]) == 1


def test_logo_opcional(tabla, tmp_path):
    from PIL import Image

    from bpt.viz.team_card import render_team_card
    logos = tmp_path / "logos"
    logos.mkdir()
    Image.new("RGBA", (100, 100), (200, 30, 30, 255)).save(logos / "car.png")
    con = render_team_card(tabla, "Cardenales", "2025-26", tmp_path / "con.png", logos_dir=logos)
    sin = render_team_card(tabla, "Cardenales", "2025-26", tmp_path / "sin.png",
                           logos_dir=tmp_path / "no-existe")
    a, b = Image.open(con).convert("RGB"), Image.open(sin).convert("RGB")
    assert a.size == b.size == (1080, 1350)
    assert a.getpixel((1000, 80)) != b.getpixel((1000, 80))  # el logo aparece arriba a la derecha


def test_previas_desde_contenido(tabla, tmp_path, monkeypatch):
    import json
    from pathlib import Path

    contenido = json.loads(Path("content/previas_2026-27.json").read_text(encoding="utf-8"))
    assert set(contenido["equipos"]) == set(lvbp.TEAMS)
    for code, d in contenido["equipos"].items():
        assert d["manager"] and len(d["cambios"]) == 3 and d["pregunta"].strip(), code
        assert d["fuentes"], code  # toda novedad lleva su fuente
    monkeypatch.setattr(lvbp, "fetch_team_stats", lambda *a, **k: tabla)
    assert main(["lvbp-previas", "--salida", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("lvbp_previa_*_2026-27.png"))) == 8


def test_resumen_temporada(tabla):
    from bpt.viz.preview_card import season_summary
    car = season_summary(tabla, "CAR")
    assert (car["G"], car["P"], car["dif"], car["ofensiva_rank"]) == (30, 26, 45, 1)
    assert season_summary(tabla, "MAG")["pitcheo_rank"] == 1
