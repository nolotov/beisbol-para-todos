"""Especiales: láminas de roster, pieza publicable y envío a Telegram (sin red)."""
import json
from pathlib import Path

import pytest
from PIL import Image

from bpt import especial
from bpt.notificar import telegram
from bpt.publicar import flujo, piezas

REAL = Path(__file__).parents[1] / "content" / "especiales" / "latinos-serie-mundial.json"


@pytest.fixture(scope="module")
def paquete(tmp_path_factory):
    salida = tmp_path_factory.mktemp("esp")
    r = especial.generar(REAL, salida)
    return Path(r["carpeta"]), r


def test_el_especial_real_pasa_las_revisiones_de_las_tres_redes(paquete):
    _, r = paquete
    assert r["alertas"] == []
    assert r["tarjetas"] == ["01_portada.png", "02_nacional.png", "03_americana.png"]


def test_laminas_1080x1350(paquete):
    carpeta, r = paquete
    for t in r["tarjetas"]:
        with Image.open(carpeta / t) as im:
            assert im.size == (1080, 1350)


def test_rosters_completos_y_un_latino_por_posicion():
    datos = especial.cargar(REAL)
    nac, ame = datos["rosters"]
    posiciones = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "SP", "RP"}
    assert {j["pos"] for j in nac["jugadores"]} == posiciones           # sin DH
    assert {j["pos"] for j in ame["jugadores"]} == posiciones | {"DH"}
    nombres = [j["nombre"] for r in datos["rosters"] for j in r["jugadores"]]
    assert len(nombres) == len(set(nombres))                              # nadie repetido
    assert sum(n for _, n in especial.paises(datos["rosters"])) == 21


def test_conteo_por_pais_venezuela_primero_en_empates():
    rosters = [{"jugadores": [{"pais": "Puerto Rico"}, {"pais": "Venezuela"}, {"pais": "Cuba"},
                              {"pais": "Cuba"}]}]
    assert especial.paises(rosters) == [("Cuba", 2), ("Venezuela", 1), ("Puerto Rico", 1)]


def test_especial_es_una_pieza_con_caption_e_hilo(paquete):
    carpeta, _ = paquete
    (p,) = piezas.piezas(carpeta)
    assert p.id == "1" and p.tipo == "post" and len(p.imagenes) == 3
    assert p.caption.startswith("⚾") and len(p.hilo) == 4
    assert p.redes("itx") == "itx"


def test_preparar_para_publicar(paquete, tmp_path):
    carpeta, _ = paquete
    plan = flujo.preparar(carpeta, "1", tmp_path / "pub", "77-1", tmp_path / "plan.json")
    assert len(plan["archivos"]) == 3 and plan["hilo"]


def test_falta_texto_se_rechaza(tmp_path):
    malo = tmp_path / "x.json"
    malo.write_text(json.dumps({"slug": "x", "titular": "t", "rosters": [],
                                "textos": {"instagram": "", "hilo_x": []}}), encoding="utf-8")
    with pytest.raises(especial.EspecialError):
        especial.cargar(malo)


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def json(self):
        return self.cuerpo


class TgFalso:
    def __init__(self):
        self.llamadas = []

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas.append({"metodo": url.rsplit("/", 1)[-1], "data": data or {}})
        return Resp({"ok": True, "result": {"message_id": 5}})


def test_telegram_manda_el_especial_con_el_menu(paquete, monkeypatch):
    carpeta, _ = paquete
    for v in ("BPT_PUBLICAR_INSTAGRAM", "BPT_PUBLICAR_THREADS", "BPT_PUBLICAR_X"):
        monkeypatch.setenv(v, "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "4242")
    http = TgFalso()
    tg = telegram.Telegram("123456789:AAHsecretoSecretoSecretoSecretoXYZ", "42", pausa=0,
                           http=http)
    assert telegram.enviar_dia(carpeta, tg) == 1
    assert http.llamadas[0]["data"]["text"].startswith("⭐ Especial · Los mejores latinos")
    ultimo = http.llamadas[-1]["data"]
    assert ultimo["text"].startswith("📸 Los mejores latinos")
    filas = json.loads(ultimo["reply_markup"])["inline_keyboard"]
    assert filas[-1][0]["callback_data"] == "pub:4242:1:itx:itx"


# --- Historia especial (content/especiales con "tipo": "historia") -------------------------

HISTORIA = Path(__file__).parents[1] / "content" / "especiales" / "rays-banderin-2026.json"


@pytest.fixture(scope="module")
def historia(tmp_path_factory):
    r = especial.generar(HISTORIA, tmp_path_factory.mktemp("hist"))
    return Path(r["carpeta"]), r


def test_historia_especial_una_lamina_1080x1920(historia):
    carpeta, r = historia
    assert r["formato"] == "historia" and r["tarjetas"] == ["historia.png"]
    assert Image.open(carpeta / "historia.png").size == (1080, 1920)


def test_historia_especial_es_pieza_de_historia_solo_instagram(historia):
    carpeta, _ = historia
    [p] = piezas.piezas(carpeta)
    assert p.id == "1" and p.tipo == piezas.HISTORIA and p.caption == ""
    assert p.titular == "Historia · Rays a la Serie Mundial"
    assert p.redes("itx") == "i"


def test_historia_especial_sin_marcador_se_rechaza(tmp_path):
    malo = tmp_path / "malo.json"
    malo.write_text(json.dumps({"slug": "x", "tipo": "historia", "titular": "x",
                                "historia": {"titulo": ["x"]}}), encoding="utf-8")
    with pytest.raises(especial.EspecialError):
        especial.generar(malo, tmp_path)


def test_telegram_manda_la_historia_especial_con_su_boton(historia, monkeypatch):
    carpeta, _ = historia
    for v in ("BPT_PUBLICAR_INSTAGRAM", "BPT_PUBLICAR_THREADS", "BPT_PUBLICAR_X"):
        monkeypatch.setenv(v, "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "4343")
    http = TgFalso()
    tg = telegram.Telegram("123456789:AAHsecretoSecretoSecretoSecretoXYZ", "42", pausa=0,
                           http=http)
    assert telegram.enviar_dia(carpeta, tg) == 1
    ultimo = http.llamadas[-1]["data"]
    assert ultimo["text"].startswith("📲 Historia · Rays a la Serie Mundial")
    filas = json.loads(ultimo["reply_markup"])["inline_keyboard"]
    assert any("pub:4343:1" in b["callback_data"] for f in filas for b in f)


# --- Carrusel por bloques (content/especiales con "laminas") ---------------------------------

PREVIA = Path(__file__).parents[1] / "content" / "especiales" / "previa-serie-mundial-2026.json"


@pytest.fixture(scope="module")
def previa(tmp_path_factory):
    r = especial.generar(PREVIA, tmp_path_factory.mktemp("previa"))
    return Path(r["carpeta"]), r


def test_previa_pasa_las_revisiones_y_dibuja_cada_lamina(previa):
    carpeta, r = previa
    assert r["alertas"] == []
    datos = json.loads(PREVIA.read_text(encoding="utf-8"))
    assert len(r["tarjetas"]) == len(datos["laminas"])
    assert r["tarjetas"][0] == "01_portada.png"
    for t in r["tarjetas"]:
        assert Image.open(carpeta / t).size == (1080, 1350)


def test_previa_es_un_carrusel_publicable_en_las_tres_redes(previa):
    carpeta, r = previa
    [p] = piezas.piezas(carpeta)
    assert p.id == "1" and p.tipo != piezas.HISTORIA
    assert len(p.imagenes) == len(r["tarjetas"])
    assert p.redes("itx") == "itx"


def test_lamina_de_tipo_desconocido_se_rechaza(tmp_path):
    datos = json.loads(PREVIA.read_text(encoding="utf-8"))
    datos["laminas"] = [{"tipo": "inventada", "titulo": "x"}]
    malo = tmp_path / "malo.json"
    malo.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(especial.EspecialError):
        especial.generar(malo, tmp_path)


# --- MBP Deportes: paleta por deporte ----------------------------------------------------

def _historia_futbol(**extra):
    datos = {"slug": "clasico-prueba", "tipo": "historia", "deporte": "fútbol",
             "titular": "Clásico", "fuente": "Datos: LaLiga",
             "historia": {"liga": "LaLiga", "antetitulo": "MBP · FÚTBOL",
                          "titulo": ["EL CLÁSICO"], "titulo_figuras": "FIGURAS DEL PARTIDO",
                          "marcador": {"visitante": "Real Madrid", "local": "Barcelona",
                                       "goles_v": 1, "goles_l": 1, "nota": "Final"}}}
    datos.update(extra)
    return datos


def test_deporte_cambia_la_paleta_y_la_restaura():
    from bpt import theme
    ambar = theme.ACCENT
    with theme.deporte("Fútbol") as paleta:
        assert theme.ACCENT == paleta["ACCENT"] != ambar
        assert theme.BG == theme.DEPORTES["futbol"]["BG"]
    assert theme.ACCENT == ambar and theme.BG == theme.DEPORTES["beisbol"]["BG"]


def test_deporte_desconocido_se_rechaza(tmp_path):
    from bpt import especial
    with pytest.raises(especial.EspecialError, match="deporte desconocido"):
        especial.validar_estructura(_historia_futbol(deporte="curling"))


def test_otro_deporte_exige_fuente():
    from bpt import especial
    datos = _historia_futbol()
    del datos["fuente"]
    with pytest.raises(especial.EspecialError, match="fuente"):
        especial.validar_estructura(datos)


def test_historia_de_futbol_con_goles_y_fondo_del_deporte(tmp_path, monkeypatch):
    from bpt import especial, theme
    monkeypatch.setenv("BPT_VERIFICAR_HECHOS", "0")
    r = especial.generar_datos(_historia_futbol(), salida=tmp_path)
    carpeta = tmp_path / "clasico-prueba"
    img = Image.open(carpeta / "historia.png").convert("RGB")
    assert img.size == (1080, 1920)
    fondo = "#%02X%02X%02X" % img.getpixel((5, 5))
    assert fondo == theme.DEPORTES["futbol"]["BG"]
    assert r["deporte"] == "futbol"
    assert json.loads((carpeta / "resumen.json").read_text())["deporte"] == "futbol"
    assert theme.BG == theme.DEPORTES["beisbol"]["BG"]      # la casa queda intacta
