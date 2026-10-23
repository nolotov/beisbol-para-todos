"""Pronóstico de series: pitagórica + log5 + localía, formato 2-3-2."""
import pytest

from bpt.editor import series as S
from bpt.editor.herramientas import Caja


def test_equipos_iguales_sin_localia_da_la_tabla_clasica():
    r = S.probabilidades(700, 700, 700, 700, ventaja_local=0.5)
    assert r["prob_por_juegos"] == {"4": 12.5, "5": 25.0, "6": 31.2, "7": 31.2}
    assert r["prob_gana_serie"] == {"A": 50.0, "B": 50.0}


def test_las_probabilidades_suman_100():
    r = S.probabilidades(820, 610, 760, 650)
    assert sum(r["prob_por_juegos"].values()) == pytest.approx(100, abs=0.2)
    assert sum(r["prob_resultado_exacto"].values()) == pytest.approx(100, abs=0.3)
    assert sum(r["prob_gana_serie"].values()) == pytest.approx(100, abs=0.1)


def test_el_mejor_equipo_es_favorito_y_la_serie_se_acorta():
    pareja = S.probabilidades(700, 700, 700, 700)
    dispareja = S.probabilidades(850, 600, 650, 800)
    assert dispareja["prob_gana_serie"]["A"] > 70
    assert dispareja["prob_por_juegos"]["4"] > pareja["prob_por_juegos"]["4"]
    assert dispareja["prob_por_juegos"]["7"] < pareja["prob_por_juegos"]["7"]


def test_la_localia_favorece_a_quien_tiene_la_ventaja():
    r = S.probabilidades(700, 700, 700, 700)
    assert r["prob_juego_A"] == {"en_casa": 54.0, "de_visita": 46.0}
    assert r["prob_gana_serie"]["A"] > 50


def test_serie_empezada():
    r = S.probabilidades(700, 700, 700, 700, ganados_a=3, ganados_b=0)
    # el juego 4 es de visita para A (2-3-2): A lo gana el 46 % de las veces
    assert r["prob_por_juegos"]["4"] == 46.0
    assert r["prob_resultado_exacto"]["A en 4"] == 46.0
    assert r["desde_marcador"] == "3-0"


def test_herramienta_del_editor_y_errores():
    c = Caja(get=lambda *_: {})
    texto, error = c.ejecutar("probabilidad_serie", {
        "equipo_a": "Cerveceros", "carreras_anotadas_a": 800, "carreras_permitidas_a": 620,
        "equipo_b": "Rays", "carreras_anotadas_b": 760, "carreras_permitidas_b": 640,
        "ganados_a": 0, "ganados_b": 0})
    assert not error and '"A":"Cerveceros"' in texto and "prob_por_juegos" in texto
    assert c.evidencia[-1]["herramienta"] == "probabilidad_serie"
    texto, error = c.ejecutar("probabilidad_serie", {
        "equipo_a": "X", "carreras_anotadas_a": 0, "carreras_permitidas_a": 620,
        "equipo_b": "Y", "carreras_anotadas_b": 760, "carreras_permitidas_b": 640,
        "ganados_a": 0, "ganados_b": 0})
    assert error
