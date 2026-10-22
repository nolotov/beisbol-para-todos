"""Verificador de especiales: cifras, evidencia, hechos contra MLB Stats API (simulada) y reglas."""
import json
from pathlib import Path

import pytest

from bpt import especial
from bpt import verificador as vf

ESPECIALES = Path(__file__).parents[1] / "content" / "especiales"


def _especial(**extra):
    base = {
        "slug": "prueba", "titular": "Prueba",
        "equipos": {"A": {"nombre": "Rays", "color": "#7FB2E5"},
                    "B": {"nombre": "Cerveceros", "color": "#F5B700"}},
        "laminas": [{"tipo": "cifras", "titulo": "DATOS", "items": [
            {"cifra": "98-64", "texto": "récord de los Rays"},
            {"cifra": "$110 M", "texto": "nómina: puesto 28 de 30", "tamano": 32}]}],
        "textos": {"instagram": "Los Rays fueron 98-64 con $110 M. ¿Y tú?",
                   "hilo_x": ["Los Rays: 98-64.", "Nómina: puesto 28 de 30.", "¿Quién gana?"]},
    }
    base.update(extra)
    return base


class FakeMLB:
    """Responde como MLB Stats API a las rutas que usa el verificador."""

    def __init__(self):
        self.llamadas = []

    def __call__(self, ruta, params):
        self.llamadas.append((ruta, params))
        if ruta == "standings":
            return {"records": [{"teamRecords": [
                {"team": {"id": 139}, "wins": 98, "losses": 64},
                {"team": {"id": 158}, "wins": 103, "losses": 59}]}]}
        if ruta == "game/777/boxscore":
            return {"teams": {
                "away": {"teamStats": {"batting": {"runs": 3}}, "players": {}},
                "home": {"teamStats": {"batting": {"runs": 7}}, "players": {
                    "ID665": {"stats": {"batting": {"atBats": 4, "hits": 2, "homeRuns": 1,
                                                    "rbi": 2},
                                        "pitching": {}}},
                    "ID111": {"stats": {"batting": {}, "pitching": {
                        "inningsPitched": "5.1", "strikeOuts": 3, "earnedRuns": 1}}}}}}}
        if ruta == "people/665/stats":
            return {"stats": [{"splits": [{"stat": {"homeRuns": 44, "avg": ".281"}}]}]}
        raise ConnectionError(ruta)


# --- Capas 1 y 2: cifras ----------------------------------------------------------------

def test_especial_coherente_sin_evidencia_es_parcial_pero_ok():
    v = vf.verificar(_especial())
    assert v.ok and v.parcial
    assert "verificación parcial" in v.resumen()


def test_cifra_del_texto_que_no_esta_en_las_laminas():
    e = _especial()
    e["textos"]["hilo_x"][0] = "Los Rays ganaron 101 juegos."
    v = vf.verificar(e)
    assert v.cifras_sin_respaldo == ["101"]


def test_la_tamano_de_letra_no_es_una_cifra():
    """`tamano` es diseño: un 32 en el texto no queda respaldado por él."""
    e = _especial()
    e["textos"]["instagram"] += " Son 32 equipos."
    assert vf.verificar(e).cifras_sin_respaldo == ["32"]


def test_con_evidencia_cada_cifra_de_las_laminas_debe_aparecer():
    evidencia = [{"herramienta": "tabla_mlb", "resultado": {"Rays": {"w": 98, "l": 64}}}]
    v = vf.verificar(_especial(), evidencia=evidencia)
    assert not v.parcial and v.consultas == 1
    # 110, 28 y 30 no están en la evidencia
    assert v.cifras_sin_respaldo == ["28", "30", "110"]


def test_evidencia_completa_deja_todo_en_orden():
    evidencia = [{"resultado": {"Rays": "98-64", "nomina_musd": 110, "puesto": 28,
                                "equipos": 30}}]
    assert vf.verificar(_especial(), evidencia=evidencia).ok


def test_horas_como_una_sola_cifra():
    e = _especial()
    e["laminas"][0]["subtitulo"] = "Juego 1: 8:03 p. m. hora de Venezuela"
    v = vf.verificar(e, evidencia=[{"resultado": {"hora_ven": "8:03 p. m.", "juego": 1, "r": "98-64",
                                                  "n": 110, "p": "28 de 30"}}])
    assert v.ok
    v = vf.verificar(e, evidencia=[{"resultado": {"juego": 1, "r": "98-64", "n": 110,
                                                  "p": "28 de 30"}}])
    assert v.cifras_sin_respaldo == ["8:03"]


def test_los_especiales_reales_pasan():
    for archivo in sorted(ESPECIALES.glob("*.json")):
        v = vf.verificar(especial.cargar(archivo), hechos=False)
        assert v.ok, (archivo.name, v.to_dict())


# --- Capa 3: hechos -----------------------------------------------------------------

def test_hechos_confirmados_y_desmentidos():
    fake = FakeMLB()
    hechos = [
        {"tipo": "record", "equipo_id": 139, "temporada": 2026, "valor": "98-64"},
        {"tipo": "record", "equipo_id": 158, "temporada": 2026, "valor": "102-60",
         "nota": "récord de Milwaukee"},
        {"tipo": "marcador", "game_pk": 777, "carreras_v": 3, "carreras_l": 7},
        {"tipo": "linea", "game_pk": 777, "jugador_id": 665, "vb": 4, "h": 2, "hr": 1, "ci": 2},
        {"tipo": "linea", "game_pk": 777, "jugador_id": 111, "ip": "5.1", "k": 3, "cl": 1},
        {"tipo": "stat_jugador", "id": 665, "temporada": 2026, "grupo": "hitting",
         "campo": "homeRuns", "valor": 44},
        {"tipo": "stat_jugador", "id": 665, "temporada": 2026, "campo": "avg",
         "valor": ".281"},
    ]
    ok, alertas = vf.comprobar_hechos(hechos, fake)
    assert ok == 6
    assert alertas == ["récord de Milwaukee: el especial dice 102-60 y MLB Stats API dice 103-59"]


def test_marcador_invertido_se_detecta():
    ok, alertas = vf.comprobar_hechos(
        [{"tipo": "marcador", "game_pk": 777, "carreras_v": 7, "carreras_l": 3}], FakeMLB())
    assert ok == 0 and "dice 7-3 y MLB Stats API dice 3-7" in alertas[0]


def test_fuente_caida_o_hecho_raro_son_alertas_no_errores():
    ok, alertas = vf.comprobar_hechos([
        {"tipo": "marcador", "game_pk": 999, "carreras_v": 1, "carreras_l": 0},
        {"tipo": "linea", "game_pk": 777, "jugador_id": 42, "h": 1},
        {"tipo": "inventado"}], FakeMLB())
    assert ok == 0 and len(alertas) == 3
    assert "no respondió" in alertas[0]
    assert "no jugó" in alertas[1]
    assert "desconocido" in alertas[2]


def test_el_marcador_de_una_historia_con_game_pk_se_comprueba_solo():
    datos = especial.cargar(ESPECIALES / "rays-banderin-2026.json")
    datos["historia"]["marcador"]["game_pk"] = 777
    v = vf.verificar(datos, get=FakeMLB())
    assert v.hechos_total == 1 and v.hechos_ok == 1 and v.ok
    assert "1/1 hechos confirmados" in v.resumen()


def test_hechos_declarados_en_el_especial():
    e = _especial(verificar=[{"tipo": "record", "equipo_id": 139, "temporada": 2026,
                              "valor": "98-64"}])
    v = vf.verificar(e, get=FakeMLB())
    assert v.hechos_ok == 1 and v.ok
    assert vf.verificar(e, hechos=False).hechos_total == 0


# --- Capa 4: reglas -----------------------------------------------------------------

@pytest.mark.parametrize("texto,alerta", [
    ("Mi pick: los Rays.", "apuestas"),
    ("Caminero, el mejor de la serie.", "el mejor"),
    ("Lanzó 5.1 entradas.", "decimal"),
    ("Caminero se fue 2-4 con jonrón.", "gringo"),
])
def test_reglas_de_marca(texto, alerta):
    e = _especial()
    e["textos"]["hilo_x"][2] = texto
    v = vf.verificar(e, hechos=False)
    assert any(alerta in a for a in v.alertas), v.alertas


def test_el_mejor_con_la_metrica_no_es_a_secas():
    assert vf.reglas_marca({"x": "Empatados con el mejor promedio de MLB."}) == []


def test_mas_de_10_laminas():
    e = _especial()
    e["laminas"] = e["laminas"] * 11
    assert any("10" in a for a in vf.verificar(e, hechos=False).alertas)


# --- Integración con el especial ------------------------------------------------------

def test_generar_guarda_la_verificacion_y_marca_las_cifras(tmp_path, monkeypatch):
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    e = _especial()
    e["textos"]["instagram"] = "Los Rays ganaron 101. ¿Y tú?"
    r = especial.generar_datos(e, tmp_path)
    carpeta = Path(r["carpeta"])
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["verificacion"]["cifras_sin_respaldo"] == ["101"]
    (t,) = json.loads((carpeta / "textos.json").read_text(encoding="utf-8"))
    assert t["validacion"]["ok"] is False
    assert t["validacion"]["cifras_sin_respaldo"] == ["101"]
    assert "cifras sin respaldo: 101" in r["alertas"]


def test_evidencia_en_archivo_aparte(tmp_path):
    e = _especial(evidencia_archivo="evidencia.json")
    (tmp_path / "evidencia.json").write_text(json.dumps([{"r": "98-64 110 28 30"}]),
                                             encoding="utf-8")
    (tmp_path / "e.json").write_text(json.dumps(e), encoding="utf-8")
    datos = especial.cargar(tmp_path / "e.json")
    assert datos["evidencia"] == [{"r": "98-64 110 28 30"}]
    assert vf.verificar(datos, hechos=False).ok
