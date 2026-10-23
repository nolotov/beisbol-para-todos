"""Agente editor: herramientas (con MLB Stats API simulada) y bucle con un modelo de mentira."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from bpt import editor
from bpt.editor import agente
from bpt.editor.herramientas import Caja, HerramientaError, _evaluar, hora_ven


def _juego(pk, fecha, v, l, cv, cl, estado="Final", inicio="2026-10-21T23:30:00Z"):
    return {"gamePk": pk, "officialDate": fecha, "gameDate": inicio, "gameType": "R",
            "seriesDescription": "Regular Season", "seriesGameNumber": 1, "gamesInSeries": 1,
            "status": {"abstractGameState": estado, "detailedState": estado},
            "venue": {"name": "Estadio Antonio Herrera Gutiérrez"},
            "teams": {"away": {"team": {"id": v, "name": "x"}, "score": cv, "isWinner": cv > cl,
                               "leagueRecord": {"wins": 7, "losses": 3}},
                      "home": {"team": {"id": l, "name": "y"}, "score": cl, "isWinner": cl > cv,
                               "leagueRecord": {"wins": 4, "losses": 6}}},
            "linescore": {"teams": {"away": {"runs": cv}, "home": {"runs": cl}},
                          "innings": [{"num": i} for i in range(1, 10)]},
            "decisions": {"winner": {"fullName": "Ganador"}, "loser": {"fullName": "Perdedor"}}}


class FakeMLB:
    def __init__(self):
        self.rutas = []

    def __call__(self, ruta, params):
        self.rutas.append((ruta, params))
        if ruta == "schedule":
            return {"dates": [{"games": [_juego(1, "2026-10-20", 693, 696, 8, 2)]}]}
        if ruta == "standings":
            return {"records": [{"division": {"id": 0}, "teamRecords": [
                {"team": {"id": 696, "name": "Magallanes"}, "wins": 4, "losses": 6,
                 "winningPercentage": ".400", "gamesBack": "3.0", "runsScored": 40,
                 "runsAllowed": 50, "runDifferential": -10, "streak": {"streakCode": "L2"}},
                {"team": {"id": 693, "name": "Lara"}, "wins": 7, "losses": 3,
                 "winningPercentage": ".700", "gamesBack": "-", "runsScored": 61,
                 "runsAllowed": 38, "runDifferential": 23, "streak": {"streakCode": "W4"}}]}]}
        if ruta == "teams/stats":
            return {"stats": [{"splits": [
                {"team": {"id": 693, "name": "Lara"}, "stat": {"ops": ".801", "era": "3.10"}},
                {"team": {"id": 696, "name": "Magallanes"}, "stat": {"ops": ".655", "era": "4.90"}},
                {"team": {"id": 695, "name": "Caracas"}, "stat": {"ops": ".720", "era": "4.00"}}]}]}
        if ruta == "people/search":
            return {"people": [{"id": 650, "fullName": "Jugador Lara", "birthCountry": "Venezuela",
                                "primaryPosition": {"abbreviation": "RF"},
                                "currentTeam": {"name": "Cardenales"}, "currentAge": 27}]}
        if ruta == "people/650/stats":
            return {"stats": [{"splits": [{"team": {"name": "Cardenales"},
                                           "stat": {"homeRuns": 6, "ops": "1.112", "avg": ".356",
                                                    "rbi": 18}}]}]}
        if ruta == "stats/leaders":
            return {"leagueLeaders": [{"leaders": [
                {"rank": 1, "person": {"id": 650, "fullName": "Jugador Lara"},
                 "team": {"name": "Cardenales"}, "value": "6"}]}]}
        raise ConnectionError(ruta)


# --- Herramientas -------------------------------------------------------------------

def test_hora_de_venezuela():
    assert hora_ven("2026-10-24T00:03:00Z") == "8:03 p. m."
    assert hora_ven("2026-10-21T15:00:00Z") == "11:00 a. m."


def test_calendario_lvbp_usa_la_liga_135_y_nombres_con_tilde():
    fake = FakeMLB()
    c = Caja(get=fake)
    (j,) = c.calendario("lvbp", "2026-10-18", "2026-10-21")
    assert fake.rutas[0][1]["leagueId"] == 135 and fake.rutas[0][1]["sportId"] == 17
    assert j["visitante"]["nombre"] == "Cardenales de Lara"
    assert j["local"]["nombre"] == "Navegantes del Magallanes"
    assert (j["visitante"]["carreras"], j["local"]["carreras"]) == (8, 2)
    assert j["ganador_pitcher"] == "Ganador" and j["hora_ven"] == "7:30 p. m."


def test_calendario_no_acepta_rangos_largos():
    with pytest.raises(HerramientaError):
        Caja(get=FakeMLB()).calendario("mlb", "2026-10-01", "2026-10-30")


def test_tabla_ordenada_y_ranking_con_puestos():
    c = Caja(get=FakeMLB())
    tabla = c.tabla_posiciones("lvbp", 2026)
    assert [f["equipo"] for f in tabla] == ["Cardenales de Lara", "Navegantes del Magallanes"]
    r = c.ranking_equipos("lvbp", 2026, "hitting", ["ops"], "R")
    puestos = {f["equipo"]: f["puesto_ops"] for f in r["filas"]}
    assert puestos == {"Cardenales de Lara": 1, "Leones del Caracas": 2,
                       "Navegantes del Magallanes": 3}
    # En pitcheo, la efectividad más baja es la primera
    r = c.ranking_equipos("lvbp", 2026, "pitching", ["era"], "R")
    assert {f["equipo"]: f["puesto_era"] for f in r["filas"]}["Cardenales de Lara"] == 1


def test_ejecutar_guarda_evidencia_solo_de_lo_que_salio_bien():
    c = Caja(get=FakeMLB())
    texto, err = c.ejecutar("buscar_jugador", {"nombre": "Jugador Lara"})
    assert not err and json.loads(texto)[0]["id"] == 650
    _, err = c.ejecutar("box_score", {"game_pk": 404})          # la fuente falla
    assert err
    _, err = c.ejecutar("no_existe", {})
    assert err
    _, err = c.ejecutar("calendario", {"liga": "nhl", "desde": "2026-10-20",
                                       "hasta": "2026-10-21"})
    assert err
    assert [e["herramienta"] for e in c.evidencia] == ["buscar_jugador"]


def test_calculadora_segura():
    assert _evaluar("round(264/422*100)") == 63
    assert _evaluar("(61-38)") == 23
    for malo in ("__import__('os')", "open('x')", "2**1000", "1/0", "x+1"):
        with pytest.raises(HerramientaError):
            _evaluar(malo)


def test_definiciones_estrictas_y_entrega():
    defs = Caja(get=FakeMLB()).definiciones()
    assert all(d["strict"] and d["input_schema"]["additionalProperties"] is False for d in defs)
    assert {d["name"] for d in defs} >= {"calendario", "box_score", "calcular", "lideres"}


# --- Bucle del agente con un modelo de mentira ----------------------------------------

def _uso():
    return NS(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0,
              cache_read_input_tokens=800)


def _tool(id_, nombre, entrada):
    return NS(type="tool_use", id=id_, name=nombre, input=entrada)


def _resp(*bloques, stop="tool_use"):
    return NS(content=list(bloques), stop_reason=stop, usage=_uso())


ESPECIAL = {
    "slug": "el-canonero-de-lara", "titular": "El cañonero de Lara",
    "fuente": "Datos: MLB Stats API (LVBP)",
    "laminas": [
        {"tipo": "portada_tema", "etiqueta": "MBP  ·  LVBP 2026-27",
         "titulo": "EL CAÑONERO\nDE LARA", "subtitulo": "Lo que va de zafra",
         "dato": {"cifra": "1.112", "texto": "OPS (embase + slugging)", "venezolano": True},
         "puntos": [{"cifra": "6", "texto": "jonrones"}, {"cifra": ".356", "texto": "promedio"},
                    {"cifra": "18", "texto": "impulsadas"}]},
        {"tipo": "cifras", "titulo": "LARA\nMANDA", "items": [
            {"cifra": "7-3", "texto": "récord de los Cardenales"},
            {"cifra": "+23", "texto": "diferencial de carreras"},
            {"cifra": "63 %", "texto": "INVENTADO"}]}],
    "textos": {"instagram": "⚾ El venezolano lleva 6 jonrones y OPS de 1.112. ¿Lo viste? "
                            "#LVBP #Béisbol #Lara",
               "hilo_x": ["6 jonrones y OPS (embase + slugging) de 1.112.",
                          "Lara va 7-3, diferencial +23.", "¿Quién lo para?"],
               "guion": "[LÁMINA 1] Seis jonrones. [LÁMINA 2] Lara manda."},
    "verificar": [{"tipo": "record", "equipo_id": 693, "temporada": 2026, "valor": "7-3",
                   "liga_id": 135}],
}


class FakeClient:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []
        self.messages = self

    def create(self, **kw):
        self.pedidos.append({**kw, "messages": list(kw["messages"])})   # foto del momento
        return self.respuestas.pop(0)


def _guion_del_modelo():
    corregido = json.loads(json.dumps(ESPECIAL))
    corregido["laminas"][1]["items"][2] = {"cifra": "W4", "texto": "racha de 4 triunfos"}
    entrega = {"por_que": "Lara lidera y su cañonero es venezolano.",
               "otras_ideas": ["Magallanes y su mala racha", "Previa del Juego 1"]}
    return [
        _resp(NS(type="text", text="Miro el calendario."),
              _tool("t1", "calendario", {"liga": "lvbp", "desde": "2026-10-18",
                                         "hasta": "2026-10-21"}),
              _tool("t2", "tabla_posiciones", {"liga": "lvbp", "temporada": 2026})),
        _resp(_tool("t3", "buscar_jugador", {"nombre": "Jugador Lara"})),
        _resp(_tool("t4", "stats_jugador", {"jugador_id": 650, "liga": "lvbp",
                                            "temporada": 2026, "grupo": "hitting",
                                            "tipo_juego": "R"})),
        _resp(_tool("t5", "entregar_especial", {"especial": ESPECIAL, **entrega})),
        _resp(_tool("t6", "entregar_especial", {"especial": corregido, **entrega})),
    ]


def test_el_agente_consulta_corrige_y_entrega():
    client = FakeClient(_guion_del_modelo())
    caja = Caja(get=FakeMLB())
    r = agente.editar("2026-10-21", client=client, caja=caja, log=lambda *_: None)
    assert r.correcciones == 1 and r.vueltas == 5
    devuelto = client.pedidos[4]["messages"][-1]["content"][0]
    assert devuelto["is_error"] and "63" in devuelto["content"]
    assert r.verificacion.ok, r.verificacion.to_dict()
    assert r.especial["slug"] == "editor-2026-10-21-el-canonero-de-lara"
    assert r.especial["fecha"] == "2026-10-21"
    assert [e["herramienta"] for e in r.evidencia] == [
        "calendario", "tabla_posiciones", "buscar_jugador", "stats_jugador"]
    assert r.uso["cache_leido"] == 4000 and r.uso["costo_usd"] is not None
    # Herramientas estrictas + la de entrega; esfuerzo y caché del sistema
    p = client.pedidos[0]
    assert p["tools"][-1]["name"] == "entregar_especial"
    assert p["output_config"] == {"effort": agente.ESFUERZO}
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_solo_un_punto_de_cache_en_los_mensajes():
    client = FakeClient(_guion_del_modelo())
    agente.editar("2026-10-21", client=client, caja=Caja(get=FakeMLB()), log=lambda *_: None)
    ultimo = client.pedidos[-1]["messages"]
    marcas = [b for m in ultimo if isinstance(m["content"], list)
              for b in m["content"] if isinstance(b, dict) and "cache_control" in b]
    assert len(marcas) == 1


def test_si_termina_sin_entregar_se_le_recuerda_y_luego_falla():
    texto = _resp(NS(type="text", text="Listo."), stop="end_turn")
    client = FakeClient([texto, texto, texto])
    with pytest.raises(agente.EditorError, match="sin entregar"):
        agente.editar("2026-10-21", client=client, caja=Caja(get=FakeMLB()),
                      log=lambda *_: None)
    assert "Aún no entregas" in client.pedidos[1]["messages"][-1]["content"][0]["text"]


def test_con_observaciones_persistentes_sale_con_alertas():
    malo = {"especial": ESPECIAL, "por_que": "x", "otras_ideas": []}
    client = FakeClient([_resp(_tool(f"t{i}", "entregar_especial", malo)) for i in range(3)])
    r = agente.editar("2026-10-21", client=client, caja=Caja(get=FakeMLB()),
                      log=lambda *_: None)
    assert r.correcciones == agente.MAX_CORRECCIONES
    assert not r.verificacion.ok


def test_ejecutar_deja_el_paquete_listo(tmp_path, monkeypatch):
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    client = FakeClient(_guion_del_modelo())
    r = editor.ejecutar("2026-10-21", salida=tmp_path, client=client,
                        caja=Caja(get=FakeMLB()), log=lambda *_: None)
    carpeta = Path(r["carpeta"])
    assert r["tarjetas"] == ["01_portada_tema.png", "02_cifras.png"]
    slug = "editor-2026-10-21-el-canonero-de-lara"
    guardado = json.loads((carpeta / f"{slug}.json").read_text(encoding="utf-8"))
    assert guardado["evidencia_archivo"] == f"{slug}.evidencia.json"
    assert len(json.loads((carpeta / f"{slug}.evidencia.json").read_text(encoding="utf-8"))) == 4
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["editor"]["otras_ideas"][0] == "Magallanes y su mala racha"
    assert resumen["verificacion"]["consultas"] == 4 and resumen["verificacion"]["ok"]
    # El especial guardado se puede volver a cargar con su evidencia
    from bpt import especial
    assert especial.cargar(carpeta / f"{slug}.json")["evidencia"]


def test_telegram_muestra_la_propuesta(tmp_path, monkeypatch):
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    from bpt.notificar import telegram
    r = editor.ejecutar("2026-10-21", salida=tmp_path, client=FakeClient(_guion_del_modelo()),
                        caja=Caja(get=FakeMLB()), log=lambda *_: None)

    class TG:
        def __init__(self):
            self.textos = []

        def texto(self, t):
            self.textos.append(t)

        def album(self, *a, **k):
            pass

        def botones(self, *a, **k):
            pass

    tg = TG()
    telegram.enviar_dia(Path(r["carpeta"]), tg=tg)
    cabeza = tg.textos[0]
    assert cabeza.startswith("🧠 Propuesta del editor · El cañonero de Lara")
    assert "🔎" in cabeza and "Por qué ahora: Lara lidera" in cabeza
    assert "• Magallanes y su mala racha" in cabeza


def test_ya_publicados_ignora_la_evidencia(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"fecha": "2026-10-20", "titular": "A"}),
                                     encoding="utf-8")
    (tmp_path / "a.evidencia.json").write_text("[]", encoding="utf-8")
    assert editor.ya_publicados(tmp_path) == ["2026-10-20 · A"]


def test_con_el_sdk_real_usa_streaming(monkeypatch):
    """El SDK rechaza max_tokens alto sin streaming (ValueError antes de llamar a la API)."""
    import anthropic

    client = anthropic.Anthropic(api_key="sk-ant-prueba-sin-red", max_retries=0,
                                 base_url="http://127.0.0.1:9")
    with pytest.raises(ValueError, match="Streaming is required"):
        client.messages.create(model=agente.MODELO, max_tokens=agente.MAX_TOKENS,
                               messages=[{"role": "user", "content": "hola"}])
    # Por stream no hay ValueError: falla recién al conectarse (no hay servidor)
    with pytest.raises(anthropic.APIConnectionError):
        agente._llamar_modelo(client, model=agente.MODELO, max_tokens=agente.MAX_TOKENS,
                              messages=[{"role": "user", "content": "hola"}],
                              output_config={"effort": "low"})


def test_cliente_con_stream_devuelve_el_mensaje_final():
    final = _resp(NS(type="text", text="x"), stop="end_turn")

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return final

    class Cliente:
        def __init__(self):
            self.messages = NS(stream=lambda **kw: Stream())

    assert agente._llamar_modelo(Cliente(), model="m") is final


def test_tema_pedido_es_obligatorio():
    from bpt.editor import prompt
    m = prompt.mensaje_inicial("2026-10-22", "duelo de abridores del Juego 1", ["2026-10-20 · Previa"])
    assert "TEMA OBLIGATORIO" in m and "«duelo de abridores del Juego 1»" in m
    assert "otro ángulo" in m and "no los repitas" not in m
    libre = prompt.mensaje_inicial("2026-10-22", None, ["2026-10-20 · Previa"])
    assert "TEMA OBLIGATORIO" not in libre and "no los repitas" in libre


def test_la_devolucion_recuerda_el_tema():
    client = FakeClient(_guion_del_modelo())
    agente.editar("2026-10-21", "el cañonero de Lara", client=client, caja=Caja(get=FakeMLB()),
                  log=lambda *_: None)
    devuelto = client.pedidos[4]["messages"][-1]["content"][0]["content"]
    assert "«el cañonero de Lara»" in devuelto


def test_telegram_dice_el_tema_y_las_consultas(tmp_path, monkeypatch):
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    from bpt.notificar import telegram
    r = editor.ejecutar("2026-10-21", "el cañonero de Lara", salida=tmp_path,
                        client=FakeClient(_guion_del_modelo()), caja=Caja(get=FakeMLB()),
                        log=lambda *_: None)
    textos = []
    tg = NS(texto=textos.append, album=lambda *a, **k: None, botones=lambda *a, **k: None,
            video=lambda *a, **k: None)
    telegram.enviar_dia(Path(r["carpeta"]), tg=tg)
    assert "Tema pedido: el cañonero de Lara" in textos[0]
    assert "Consultó: calendario, tabla_posiciones, buscar_jugador, stats_jugador" in textos[0]


def test_texto_largo_no_se_sale_del_recuadro():
    import matplotlib.pyplot as plt
    from bpt.viz import carrusel_card as C
    fig = plt.figure(figsize=(C.W, C.H), dpi=100)
    largo = ("percentil en velocidad de salida promedio: le pega más duro que casi cualquier "
             "bateador de las Grandes Ligas esta temporada")
    t = C._ajustado(fig, 0.3, 0.5, largo, 0.6, 0.1, fontsize=15.5, va="center")
    caja = t.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted())
    assert caja.width <= 0.6 and caja.height <= 0.1
    assert "\n" in t.get_text()
    corto = C._ajustado(fig, 0.3, 0.3, "promedio", 0.6, 0.1, fontsize=15.5)
    assert corto.get_text() == "promedio" and corto.get_fontsize() == 15.5
    plt.close(fig)


def test_cifra_ancha_no_pisa_su_texto():
    """Caso real (lámina 3 del editor): "2.27 vs. 1.30" pisaba la explicación."""
    from bpt.viz.carrusel_card import render_lamina
    l = {"tipo": "barras", "titulo": "PERO EL\nESTILO MANDA", "subtitulo": "Ponches por 9",
         "barras": [{"etiqueta": "Martinez", "valor": 5.45, "texto": "5.45"},
                    {"etiqueta": "Misiorowski", "valor": 12.98, "texto": "12.98"}],
         "conclusion": {"cifra": "2.27 vs. 1.30",
                        "texto": "boletos por 9 entradas: Misiorowski vs. Martinez"}}
    p = []
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        render_lamina(l, {}, Path(d) / "a.png", problemas=p)
        cif = {"tipo": "cifras", "titulo": "X", "items": [
            {"cifra": "103-59 vs. 98-64", "texto": "récord de la temporada regular de cada uno"}]}
        render_lamina(cif, {}, Path(d) / "b.png", problemas=p)
    assert p == []


def test_el_control_detecta_textos_encimados():
    import matplotlib.pyplot as plt
    from bpt.viz import carrusel_card as C
    fig = plt.figure(figsize=(C.W, C.H), dpi=100)
    fig.text(0.1, 0.5, "2.27 vs. 1.30", fontsize=48)
    fig.text(0.3, 0.5, "boletos por 9 entradas", fontsize=16)
    fig.text(0.9, 0.2, "se sale por la derecha de la lámina", fontsize=16)
    p = C.textos_encimados(fig)
    plt.close(fig)
    assert any("pisa a" in x for x in p) and any("se sale" in x for x in p)


def test_especial_con_textos_encimados_llega_con_alertas(tmp_path, monkeypatch):
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    from bpt import especial
    from bpt.viz import carrusel_card as C
    real = C.textos_encimados
    monkeypatch.setattr(C, "textos_encimados", lambda fig: ["«a» pisa a «b»"] + real(fig))
    e = {"slug": "x", "titular": "X", "laminas": [{"tipo": "cifras", "titulo": "X",
                                                  "items": [{"cifra": "1", "texto": "uno"}]}],
         "textos": {"instagram": "Uno 1 ⚾", "hilo_x": ["1", "1", "1"]}}
    r = especial.generar_datos(e, tmp_path)
    assert "lámina 1: «a» pisa a «b»" in r["alertas"]


def test_ningun_especial_del_repo_tiene_textos_encimados(tmp_path, monkeypatch):
    """Guardia de regresión: un arreglo de diseño no puede encimar textos en lo que ya existe."""
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    from bpt import especial
    for archivo in sorted(Path("content/especiales").glob("*.json")):
        if archivo.name.endswith(".evidencia.json"):
            continue
        r = especial.generar(archivo, tmp_path)
        assert not [a for a in r["alertas"] if a.startswith("lámina")], archivo.name
