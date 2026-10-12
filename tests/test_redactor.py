"""Agente redactor y validador, con un cliente falso (sin llamar a la API)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bpt import resultados
from bpt.redactor import agente, prompt
from bpt.redactor.validador import numeros_en, numeros_permitidos, validar

FX = Path(__file__).parent / "fixtures"
PERSONAS = {int(k): v for k, v in json.loads(
    (FX / "mlb_people_sintetico.json").read_text(encoding="utf-8")).items() if k.isdigit()}

GUION_OK = ("[LÁMINA 1] Juego 2 de la Serie de Campeonato. Los Dodgers le ganaron 3-2 a "
            "Milwaukee en 11 entradas y empataron la serie 1-1. " + "Partido apretado. " * 20 +
            "[LÁMINA 2] El relevo de Milwaukee lanzó 4 entradas y dos tercios en blanco, con Game Score de "
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
    resultados.generar("2026-10-12", salida=tmp_path, schedule=sched, boxscores={900002: box},
                           personas=PERSONAS)
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
        bloque = SimpleNamespace(type="text", text=json.dumps(t, ensure_ascii=False))
        return SimpleNamespace(content=[bloque], stop_reason="end_turn")


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
    assert "tools" not in kw and "tool_choice" not in kw
    fmt = kw["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["additionalProperties"] is False
    assert kw["output_config"]["effort"] == "low" and kw["max_tokens"] >= 16000
    assert "Bateador LAD Uno" in kw["messages"][0]["content"]  # le llegan las figuras
    assert "game_pk" not in kw["messages"][0]["content"]       # sin campos técnicos


def test_corrige_cifra_inventada_en_segundo_intento(juego_y_resumen):
    j, r = juego_y_resumen
    malo = textos(instagram="LAD ganó 3-2 con 15 hits combinados")
    cli = ClienteFalso(malo, textos())
    res = agente.redactar_juego(j, r, client=cli)
    assert res["intentos"] == 2 and res["validacion"]["ok"]
    msgs = cli.llamadas[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "15" in msgs[-1]["content"]


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


def test_sin_llave_error_claro(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # sin .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        agente._cliente()


def test_carga_llave_desde_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")  # registra el valor original para restaurarlo
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    (tmp_path / ".env").write_text('# comentario\nANTHROPIC_API_KEY="sk-ant-prueba"\n',
                                   encoding="utf-8")
    agente.cargar_env(tmp_path / ".env")
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-prueba"


def test_prompt_recibe_latinos(juego_y_resumen):
    j, r = juego_y_resumen
    d = prompt.datos_juego(j, r)
    assert d["laminas"] == 3
    assert d["latinos_resumen"].startswith("7 peloteros")
    assert "LATINOS" in prompt.SISTEMA and "venezolano" in prompt.SISTEMA
    # el conteo de latinos es una cifra con respaldo
    v = validar(textos(instagram="7 latinos vieron acción. LAD ganó 3-2."), d)
    assert "7" not in v.cifras_sin_respaldo


def test_env_manda_sobre_variable_vieja(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-vieja-de-powershell-1111")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-nueva-del-env-2222\n",
                                   encoding="utf-8")
    agente.cargar_env(tmp_path / ".env")
    import os
    assert os.environ["ANTHROPIC_API_KEY"].endswith("2222")
    err = capsys.readouterr().err
    assert "…1111" in err and "…2222" in err and "vieja" not in err  # nunca la llave completa


class AuthenticationError(Exception):
    """Mismo nombre que la excepción del SDK."""


def test_llave_rechazada_da_mensaje_claro(juego_y_resumen, monkeypatch):
    j, r = juego_y_resumen
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-xxxxxxxxxxxxABCD")

    class Rechaza(ClienteFalso):
        def create(self, **kw):
            raise AuthenticationError("invalid x-api-key")

    with pytest.raises(agente.LlaveInvalida) as e:
        agente.redactar_juego(j, r, client=Rechaza())
    msg = str(e.value)
    assert "…ABCD" in msg and "Settings → API keys" in msg and "xxxx" not in msg


def test_hilo_fuera_de_rango_alerta(juego_y_resumen):
    j, r = juego_y_resumen
    v = validar(textos(hilo=["Uno.", "Dos."]), prompt.datos_juego(j, r))
    assert any("2 tuits" in a for a in v.alertas)


def test_json_invalido_error_claro(juego_y_resumen):
    j, r = juego_y_resumen

    class Roto(ClienteFalso):
        def create(self, **kw):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="{incompleto")],
                                   stop_reason="max_tokens")

    with pytest.raises(RuntimeError, match="max_tokens"):
        agente.redactar_juego(j, r, client=Roto())


@pytest.mark.parametrize("frase,alerta", [
    ("Y la diferencia la hizo un jonrón de Turang.", "decidió el juego"),
    ("Chourio se fue de 4-2 con 2 hits.", "redundante"),
    ("Chourio se fue 2-4.", "estilo gringo"),
    ("Skubal ponchó a 7 en 5.0 entradas.", "decimal"),
    ("Misiorowski lanzó 4.1 IL.", "decimal"),
])
def test_alertas_del_primer_borrador_real(juego_y_resumen, frase, alerta):
    """Frases tomadas del primer textos.md real (Juego 1 SCLN 2026)."""
    j, r = juego_y_resumen
    v = validar(textos(instagram=frase), prompt.datos_juego(j, r))
    assert any(alerta in a for a in v.alertas), v.alertas


def test_estilo_venezolano_no_alerta(juego_y_resumen):
    j, r = juego_y_resumen
    v = validar(textos(instagram="El criollo se fue de 4-2 y el relevo lanzó 4 entradas y "
                                 "dos tercios en blanco."), prompt.datos_juego(j, r))
    assert v.ok, v.alertas


def test_equipos_en_espanol(juego_y_resumen):
    j, r = juego_y_resumen
    d = prompt.datos_juego(j, r)
    assert d["equipos_es"] == {"LAD": "Dodgers de Los Ángeles", "MIL": "Cerveceros de Milwaukee"}


def test_criollo_solo_para_venezolanos(juego_y_resumen):
    """Del run real en GitHub Actions: 'Criollos al bate' con un dominicano adentro."""
    j, r = juego_y_resumen
    d = prompt.datos_juego(j, r)
    malo = validar(textos(instagram="Criollos al bate: Bateador LAD Uno se fue de 5-3. "
                                    "Bateador LAD Dos también."), d)
    assert any("criollo" in a for a in malo.alertas)
    bien = validar(textos(instagram="El criollo Bateador LAD Uno se fue de 5-3."), d)
    assert not any("criollo" in a for a in bien.alertas)
