"""Prompt caching condicional y medición de uso/costo, con un cliente falso."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bpt import resultados
from bpt.redactor import agente

FX = Path(__file__).parent / "fixtures"
PERSONAS = {int(k): v for k, v in json.loads(
    (FX / "mlb_people_sintetico.json").read_text(encoding="utf-8")).items() if k.isdigit()}
GUION = ("[LÁMINA 1] Juego 2 de la Serie de Campeonato. " + "Partido apretado. " * 30 +
         "[LÁMINA 2] Cierre.")
TEXTOS = {"instagram": "LAD le gana 3-2 a MIL.", "hilo_x": ["LAD 3, MIL 2.", "Uno.", "Dos."],
          "guion": GUION, "angulo": "x"}


class Cliente:
    """Simula la API: la 1.ª llamada con caché escribe, las siguientes leen."""

    def __init__(self):
        self.llamadas, self.messages, self.cache = [], self, False

    def create(self, **kw):
        self.llamadas.append(kw)
        con_cache = isinstance(kw["system"], list)
        escrito = leido = 0
        if con_cache:
            leido, escrito = (1400, 0) if self.cache else (0, 1400)
            self.cache = True
        usage = SimpleNamespace(input_tokens=1600 + (0 if con_cache else 1400),
                                output_tokens=3000, cache_creation_input_tokens=escrito,
                                cache_read_input_tokens=leido)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(TEXTOS))],
                               stop_reason="end_turn", usage=usage)


def _dia(tmp_path, juegos=1):
    sched = json.loads((FX / "mlb_postemporada_sintetico.json").read_text(encoding="utf-8"))
    box = json.loads((FX / "mlb_boxscore_sintetico_900002.json").read_text(encoding="utf-8"))
    resultados.generar("2026-10-12", salida=tmp_path, schedule=sched, boxscores={900002: box},
                       personas=PERSONAS)
    carpeta = tmp_path / "2026-10-12"
    if juegos > 1:   # duplicamos el juego para simular una corrida con 2
        r = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
        r["juegos"].append(dict(r["juegos"][0], game_pk=900099))
        (carpeta / "resumen.json").write_text(json.dumps(r, ensure_ascii=False),
                                              encoding="utf-8")
    return carpeta


@pytest.mark.parametrize("llamadas,modo,esperado", [
    (1, "auto", False), (2, "auto", True), (4, "auto", True),
    (1, "si", True), (5, "no", False)])
def test_decidir_cache(llamadas, modo, esperado):
    assert agente.decidir_cache(llamadas, modo) is esperado


def test_un_juego_no_usa_cache(tmp_path):
    cli = Cliente()
    agente.redactar_dia(_dia(tmp_path), client=cli)
    assert isinstance(cli.llamadas[0]["system"], str)


def test_dos_juegos_escriben_y_leen_cache(tmp_path):
    cli = Cliente()
    res = agente.redactar_dia(_dia(tmp_path, juegos=2), client=cli)
    sistema = cli.llamadas[0]["system"]
    assert sistema[0]["cache_control"] == {"type": "ephemeral"}
    assert sistema == cli.llamadas[1]["system"]          # mismo prefijo exacto
    assert res[0]["uso"]["cache_escrito"] == 1400 and res[1]["uso"]["cache_leido"] == 1400
    total = json.loads((tmp_path / "2026-10-12" / "uso.json").read_text())
    assert total["cache_leido"] == 1400 and total["salida"] == 6000


def test_costo_y_ahorro():
    sin = {"entrada": 3000, "salida": 3000, "cache_escrito": 0, "cache_leido": 0}
    escribe = {"entrada": 1600, "salida": 3000, "cache_escrito": 1400, "cache_leido": 0}
    lee = {"entrada": 1600, "salida": 3000, "cache_escrito": 0, "cache_leido": 1400}
    m = "claude-sonnet-5-5"
    assert agente.costo_usd(sin, m) == pytest.approx(0.036)       # 3000*2 + 3000*10, /1e6
    assert agente.costo_usd(escribe, m) > agente.costo_usd(sin, m)  # escribir cuesta 1,25x
    ahorro_2 = 2 * agente.costo_usd(sin, m) - (agente.costo_usd(escribe, m)
                                               + agente.costo_usd(lee, m))
    assert ahorro_2 == pytest.approx(0.00196, abs=1e-5)           # ~0,2 centavos con 2 juegos
    assert agente.costo_usd(sin, "modelo-desconocido") is None


def test_uso_y_costo_en_textos_md(tmp_path):
    carpeta = _dia(tmp_path)
    agente.redactar_dia(carpeta, client=Cliente())
    md = (carpeta / "textos.md").read_text(encoding="utf-8")
    assert "_Uso: 3000 tokens de entrada (0 del caché), 3000 de salida · ~US$ 0.0360_" in md
