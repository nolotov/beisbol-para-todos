import pytest

from bpt import glossary
from bpt.data import lvbp, savant


def _claves_usadas():
    keys = set(savant.PITCHER_METRICS.values()) | set(savant.BATTER_METRICS.values())
    keys |= {k for k, _ in lvbp.BATTER_METRICS.values()}
    keys |= {k for k, _ in lvbp.PITCHER_METRICS.values()}
    keys |= {k for _, k, _, _ in lvbp.TEAM_BATTING + lvbp.TEAM_PITCHING}
    return keys


def test_toda_metrica_usada_esta_en_el_glosario():
    faltan = _claves_usadas() - set(glossary.GLOSARIO)
    assert not faltan, faltan


def test_modos():
    assert glossary.label("era", "siglas") == ("ERA", None)
    assert glossary.label("era", "espanol") == ("Efectividad", None)
    assert glossary.label("era", "mixto") == ("Efectividad", "ERA")
    # sin traducción usual: en mixto va la pista de qué mide
    assert glossary.label("woba", "mixto") == ("wOBA", "valor de cada turno")
    with pytest.raises(ValueError):
        glossary.label("era", "otro")


def test_textos_completos_y_cortos():
    for key, m in glossary.GLOSARIO.items():
        assert m.sigla and m.nombre and m.explicacion, key
        assert len(m.nombre) <= 30 and len(m.pista) <= 30, key
