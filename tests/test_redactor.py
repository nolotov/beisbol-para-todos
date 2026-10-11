"""Agente redactor y validador, con un cliente falso (sin llamar a la API)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bpt import resultados
from bpt.redactor import agente, prompt
from bpt.redactor.validador import numeros_en, numeros_permitidos, validar

FX = Path(__file__).parent / "fixtures"

GUION_OK = ("[LÁMINA 1] Juego 2 de la Serie de Campeonato. Los Dodgers le ganaron 3-2 a "
            "Milwaukee en 11 entradas y empataron la serie 1-1. " + "Partido apretado. " * 20 +
            "[LÁMINA 2] El relevo de Milwaukee lanzó 4.2 entradas en blanco, con Game Score de "
            "68, la nota de su salida en la loma. ¿Quién se lleva el Juego 3?")


def textos(instagram="LAD le gana 3-2 a MIL en 11 entradas. ¿Y ahora?\n#Béisbol #MLB",
           hilo=None, guion=GUION_OK):
    return {"instagram": instagram,
            "hilo_x": hilo or ["LAD le gana 3-2 a MIL en 11 entradas.",
                               "La serie queda 1-1.", "Game Score de 68 para el relevo."],
            "guion": guion, "angulo": "Duelo de bullpens"}


@pytest.fixture
def dia(tmp_path):
    sched = json.loads((FX / "mlb_postemporada_sintetico.json").read_text(encoding="utf-8"))
    box = json.loads((FX / "mlb_boxscore_sintetico_900002.json").read_text(encoding="utf-8"))
    resultados.generar("2026-10-12", salida=tmp_path, schedule=sched, boxscores={900002: box})
    return tmp_path / "2026-10-12"


@pytest.fixture
def juego_y_resumen(dia):
    r = json.loads((dia / "resumen.json").read_text(encoding="utf-8"))
    return r["juegos"][0], r


class ClienteFalso:
    """Devuelve las respuestas en orden y guarda lo que se le pidió."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.messages = self

    def create(self, **kw):
        self.llamadas.append(kw)
        t = self.respuestas.pop(0)
        bloque = SimpleNamespace(type="tool_use", id=f"tu_{len(self.llamadas)}", input=t)
        return SimpleNamespace(content=[bloque])


# --- Validador ----------------------------------------------------------------

def test_extrae_numeros_sin_hashtags_ni_marcas():
    assert numeros_en("Ganó 3-2 en 4.2 entradas. #MLB2026 [LÁMINA 2] @mbp.deportes") == \
        ["3", "2", "4.2"]


def test_permitidos_incluye_innings_y_constantes(juego_y_resumen):
    j, r = juego_y_resumen
    p = numeros_permitidos(prompt.datos_juego(j, r))
    assert {"3", "2", "11", "68", "4.2", "4", "60", "9"} <= p


def test_texto_correcto_pasa(juego_y_resumen):
    j, r = juego_y_resumen
    v = validar(textos(), prompt.datos_juego(j, r))
    assert v.ok, v.to_dict()


def test_cifra_inventada_se_marca(juego_y_resumen):
    j, r = juego_y_resumen
    v = validar(textos(instagram="LAD ganó 3-2 y lleva 37 jonrones en la postemporada"),
                prompt.datos_juego(j, r))
    assert v.cifras_sin_respaldo == ["37"]


def test_alertas_de_marca(juego_y_resumen):
    j, r = juego_y_resumen
    v = validar(textos(instagram="El mejor pitcher del juego. Buen pick para mañana.",
                       hilo=["x" * 300, "a", "b"], guion="muy corto"),
                prompt.datos_juego(j, r))
    a = " ".join(v.alertas)
    assert "apuestas" in a and "el mejor" in a and "300 caracteres" in a
    assert "guion:" in a and "LÁMINA 2" in a


def test_el_mejor_con_criterio_no_alerta(juego_y_resumen):
    j, r = juego_y_resumen
    v = validar(textos(instagram="El mejor por Game Score fue el relevo: 68."),
                prompt.datos_juego(j, r))
    assert not any("el mejor" in a for a in v.alertas)


# --- Agente -------------------------------------------------------------------

def test_redacta_y_pide_herramienta(juego_y_resumen):
    j, r = juego_y_resumen
    cli = ClienteFalso(textos())
    res = agente.redactar_juego(j, r, client=cli, modelo="modelo-x")
    assert res["estado"] == "para revisar" and res["intentos"] == 1
    kw = cli.llamadas[0]
    assert kw["model"] == "modelo-x"
    assert kw["tool_choice"] == {"type": "tool", "name": "entregar_textos"}
    assert "Bateador LAD Uno" in kw["messages"][0]["content"]  # le llegan las figuras
    assert "game_pk" not in kw["messages"][0]["content"]       # sin campos técnicos


def test_corrige_cifra_inventada_en_segundo_intento(juego_y_resumen):
    j, r = juego_y_resumen
    malo = textos(instagram="LAD ganó 3-2 con 15 hits combinados")
    cli = ClienteFalso(malo, textos())
    res = agente.redactar_juego(j, r, client=cli)
    assert res["intentos"] == 2 and res["validacion"]["ok"]
    feedback = cli.llamadas[1]["messages"][-1]["content"][0]
    assert feedback["type"] == "tool_result" and feedback["tool_use_id"] == "tu_1"
    assert "15" in feedback["content"]


def test_si_insiste_queda_con_alertas(juego_y_resumen):
    j, r = juego_y_resumen
    malo = textos(instagram="LAD ganó 3-2 con 15 hits combinados")
    res = agente.redactar_juego(j, r, client=ClienteFalso(malo, malo))
    assert res["estado"] == "con alertas"
    assert res["validacion"]["cifras_sin_respaldo"] == ["15"]


def test_redactar_dia_escribe_archivos(dia):
    res = agente.redactar_dia(dia, client=ClienteFalso(textos()))
    assert len(res) == 1
    md = (dia / "textos.md").read_text(encoding="utf-8")
    assert "## Instagram" in md and "## Hilo de X" in md and "## Guion" in md
    assert json.loads((dia / "textos.json").read_text(encoding="utf-8"))[0]["estado"] == \
        "para revisar"


def test_sin_llave_error_claro(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        agente._cliente()
