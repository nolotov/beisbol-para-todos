"""Tests de la ingesta LVBP.

Los fixtures HTML son las respuestas crudas de stats.lvbp.com (temporada 2025-26,
página 1), tal como las envía el servidor: con <thead> y SIN <tbody>. Las pruebas
de percentiles usan datos sintéticos.
"""
from pathlib import Path

import pandas as pd
import pytest

from bpt.cli import main
from bpt.data import lvbp

FIX = Path(__file__).parent / "fixtures"
BAT_HTML = (FIX / "lvbp_leaders_hittings_2025_p1.html").read_text(encoding="utf-8")
PIT_HTML = (FIX / "lvbp_leaders_pitchings_2025_p1.html").read_text(encoding="utf-8")


def test_parse_bateo_une_las_tres_tablas():
    df = lvbp.parse_leaders(BAT_HTML)
    assert len(df) == 30
    for col in ["jugador", "equipo", "posicion", "mano", "AVE", "OPS", "wOBA", "ISO", "LD%", "AL"]:
        assert col in df.columns, col
    assert df["jugador"].str.len().gt(0).all()
    assert set(df["mano"]) <= {"D", "Z", "A"}
    assert df["LD%"].dropna().between(0, 1).all()  # '21.3%' -> 0.213


def test_parse_pitcheo_une_tradicional_y_avanzada():
    df = lvbp.parse_leaders(PIT_HTML)
    assert len(df) == 30
    for col in ["EFE", "IP", "WHIP", "FIP", "K%", "BB%"]:
        assert col in df.columns, col


def test_mano_y_posicion():
    html = BAT_HTML.replace("Gabriel Rodriguez", "* Gabriel Rodriguez", 1)
    row = lvbp.parse_leaders(html).iloc[0]
    assert row["jugador"] == "Gabriel Rodriguez"
    assert row["mano"] == "Z" and row["posicion"] == "DH"


def test_ultima_pagina():
    assert lvbp.last_page(BAT_HTML) == 7
    assert lvbp.last_page("<div></div>") == 1


@pytest.mark.parametrize("ip,esperado", [(45.2, 45 + 2 / 3), (0.1, 1 / 3), (12.0, 12), (None, 0)])
def test_innings(ip, esperado):
    assert lvbp.innings(ip) == pytest.approx(esperado)


def test_season_label():
    assert lvbp.season_label(2025) == "2025-26"
    assert lvbp.season_label(2099) == "2099-00"


def _pool_bateo():
    rows = [{"jugador": f"J{i}", "equipo": "X", "AL": 150, "wOBA": 0.300 + i * 0.01,
             "K%": 0.30 - i * 0.02} for i in range(10)]
    rows.append({"jugador": "Chiquito", "equipo": "X", "AL": 10, "wOBA": 0.900, "K%": 0.0})
    return pd.DataFrame(rows)


def test_percentiles_respetan_direccion_y_muestra():
    df = _pool_bateo()
    mejor = dict(lvbp.percentiles(df, df.iloc[9], "bateo"))
    peor = dict(lvbp.percentiles(df, df.iloc[0], "bateo"))
    assert mejor["woba"] > 90 and peor["woba"] < 10
    assert mejor["k_pct"] > 90  # menos ponches = mejor
    assert "Chiquito" not in set(lvbp.qualified_pool(df, "bateo")["jugador"])


class _Resp:
    def __init__(self, text):
        self.text, self.encoding = text, "utf-8"

    def raise_for_status(self):
        pass


class _FakeSession:
    """Simula 2 páginas: la 1 anuncia 'loadPage(2)', la 2 trae otros jugadores."""

    def __init__(self):
        self.headers, self.calls = {}, []

    def post(self, url, data, timeout):
        self.calls.append(data["page"])
        if data["page"] == 1:
            return _Resp(BAT_HTML.replace("loadPage(7)", "loadPage(2)")
                         .replace("loadPage(3)", "").replace("loadPage(4)", "")
                         .replace("loadPage(5)", ""))
        return _Resp(BAT_HTML.replace("Gabriel Rodriguez", "Otro Jugador")
                     .replace("loadPage(", "x("))


def test_fetch_pagina_dedup_y_cachea(tmp_path, monkeypatch):
    monkeypatch.setattr(lvbp, "CACHE_DIR", tmp_path)
    s = _FakeSession()
    df = lvbp.fetch_leaders(2025, "bateo", session=s, delay=0)
    assert s.calls == [1, 2]
    assert "Otro Jugador" in set(df["jugador"])
    assert len(df) == 31  # 30 + 30, todos repetidos menos "Otro Jugador"
    assert (df["temporada"] == "2025-26").all()
    # segunda llamada sale de la caché, sin red
    s2 = _FakeSession()
    lvbp.fetch_leaders(2025, "bateo", session=s2, delay=0)
    assert s2.calls == []


def test_cli_lvbp_card(tmp_path, monkeypatch):
    df = _pool_bateo()
    df["equipo"] = "Tigres"
    monkeypatch.setattr(lvbp, "fetch_leaders", lambda *a, **k: df)
    rc = main(["lvbp-card", "J7", "--salida", str(tmp_path)])
    assert rc == 0
    assert len(list(tmp_path.glob("lvbp_j7_bateo_2025.png"))) == 1


def test_pitcheo_k_pct_es_strike_pct_en_la_fuente():
    """En stats.lvbp.com, 'K%' de pitcheo = S/NP. Nuestro K% debe salir de K/AL."""
    df = lvbp.parse_leaders(PIT_HTML)
    con_np = df[df["NP"] > 0]
    # la fuente redondea a 2 decimales (0.625 -> .63), de ahí la tolerancia
    assert ((con_np["S"] / con_np["NP"]) - con_np["K%"]).abs().max() <= 0.0051
    assert lvbp.PITCHER_METRICS["K/AL"][0] == "k_pct"
    assert lvbp.PITCHER_METRICS["K%"][0] == "strike_pct"


def test_html_crudo_sin_tbody():
    """Regresión: el servidor no envía <tbody>; el parser no puede depender de él."""
    assert "<tbody" not in BAT_HTML and "<thead" in BAT_HTML
    assert len(lvbp.parse_leaders(BAT_HTML)) == 30
