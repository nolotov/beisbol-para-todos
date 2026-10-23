"""Fase 4: publicación en Instagram con dobles de prueba (sin red)."""
import json
from pathlib import Path

import pytest
from PIL import Image

from bpt.notificar import telegram
from bpt.publicar import flujo, instagram, piezas

TOKEN_IG = "IGAAsecretoSecretoSecretoSecreto123"
TOKEN_TG = "123456789:AAHsecretoSecretoSecretoSecretoXYZ"


# --- Dobles -----------------------------------------------------------------------

class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def json(self):
        return self.cuerpo


class GraphFalso:
    """Imita graph.instagram.com: contenedores, estados, publicación y lista de posts."""

    def __init__(self, estados=None, recientes=None, error_en=None):
        self.llamadas = []
        self.n = 0
        self.estados = list(estados or [])          # status_code que irá devolviendo
        self.recientes = recientes or []
        self.error_en = error_en or {}              # ruta-sufijo -> objeto error

    def _registrar(self, verbo, url, datos):
        ruta = url.split("/v25.0/", 1)[1]
        self.llamadas.append({"verbo": verbo, "ruta": ruta, "datos": dict(datos)})
        for sufijo, err in self.error_en.items():
            if ruta.endswith(sufijo):
                return Resp({"error": err})
        return None

    def get(self, url, params=None, timeout=None):
        r = self._registrar("GET", url, params)
        if r:
            return r
        ruta = self.llamadas[-1]["ruta"]
        if ruta == "me":
            return Resp({"user_id": "1789", "username": "mbp.deportes",
                         "account_type": "MEDIA_CREATOR"})
        if ruta.endswith("/media"):
            return Resp({"data": self.recientes})
        if ruta.endswith("content_publishing_limit"):
            return Resp({"data": [{"quota_usage": 2, "config": {"quota_total": 100}}]})
        if params.get("fields") == "permalink":
            return Resp({"permalink": f"https://www.instagram.com/p/{ruta}/"})
        return Resp({"status_code": self.estados.pop(0) if self.estados else "FINISHED"})

    def post(self, url, data=None, timeout=None):
        r = self._registrar("POST", url, data)
        if r:
            return r
        self.n += 1
        prefijo = "pub" if url.endswith("media_publish") else "c"
        return Resp({"id": f"{prefijo}{self.n}"})

    def posts(self, sufijo):
        return [c for c in self.llamadas if c["verbo"] == "POST" and c["ruta"].endswith(sufijo)]


class TgFalso:
    def __init__(self):
        self.llamadas = []

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas.append({"metodo": url.rsplit("/", 1)[-1], "data": data or {}})
        return Resp({"ok": True, "result": {"message_id": 99}})


def ig(http, **kw):
    return instagram.Instagram(TOKEN_IG, http=http, pausa=0, **kw)


def tg(http):
    return telegram.Telegram(TOKEN_TG, "42", pausa=0, http=http)


# --- Paquetes de prueba -----------------------------------------------------------

def _png(ruta: Path, color=(30, 42, 71, 255)):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (108, 135), color).save(ruta)


VAL_OK = {"ok": True, "cifras_sin_respaldo": [], "alertas": []}


@pytest.fixture
def jornada(tmp_path):
    d = tmp_path / "2026-10-15"
    for n in ("lvbp_1_jornada.png", "lvbp_2_destacados.png", "x_resultado.png"):
        _png(d / n)
    (d / "resumen.json").write_text(json.dumps({
        "formato": "jornada", "liga": "LVBP", "fecha": "2026-10-15",
        "juegos": [{"titular": "MAG 5-3 CAR"}],
        "tarjetas": ["lvbp_1_jornada.png", "lvbp_2_destacados.png"],
        "extras": ["x_resultado.png"]}), encoding="utf-8")
    (d / "textos.json").write_text(json.dumps([{
        "game_pk": "jornada", "titular": "Jornada LVBP", "textos": {"instagram": "Jornada caliente ⚾ #LVBP",
                                         "hilo_x": ["a"], "guion": "g", "angulo": "x"},
        "validacion": VAL_OK}], ensure_ascii=False), encoding="utf-8")
    return d


@pytest.fixture
def mlb(tmp_path):
    d = tmp_path / "2026-10-12"
    juegos = []
    textos = []
    for i, pk in enumerate((111, 222), 1):
        cards = [f"j{i}_1_resultado.png", f"j{i}_2_figuras.png"]
        for c in cards:
            _png(d / c)
        juegos.append({"game_pk": pk, "titular": f"Juego {i}", "tarjetas": cards})
        val = VAL_OK if i == 1 else {"ok": False, "cifras_sin_respaldo": ["37"],
                                     "alertas": ["guion: 120 palabras"]}
        textos.append({"game_pk": pk, "titular": f"Juego {i}", "textos": {"instagram": f"Caption {i}", "hilo_x": [],
                                                  "guion": "g", "angulo": ""},
                       "validacion": val})
    juegos.append({"game_pk": 333, "titular": "Juego sin textos", "tarjetas": []})
    (d / "resumen.json").write_text(json.dumps({"fecha": "2026-10-12", "juegos": juegos}),
                                    encoding="utf-8")
    (d / "textos.json").write_text(json.dumps(textos), encoding="utf-8")
    return d


# --- Piezas -------------------------------------------------------------------------

def test_piezas_de_mlb_una_por_juego_con_caption(mlb):
    lista = piezas.piezas(mlb)
    assert [p.id for p in lista] == ["1", "2"]          # el 3 no tiene láminas ni textos
    assert lista[0].caption == "Caption 1" and not lista[0].tiene_alertas
    assert lista[1].tiene_alertas and "cifras sin respaldo: 37" in lista[1].alertas


def test_pieza_de_jornada_solo_el_carrusel(jornada):
    (p,) = piezas.piezas(jornada)
    assert p.id == "jornada" and p.titular == "LVBP · Jornada del 2026-10-15"
    assert [i.name for i in p.imagenes] == ["lvbp_1_jornada.png", "lvbp_2_destacados.png"]


@pytest.mark.parametrize("malo", ["../x", "3; rm", "", "100", "JORNADA"])
def test_ids_raros_se_rechazan(jornada, malo):
    with pytest.raises(piezas.PiezaError):
        piezas.buscar(jornada, malo)


def test_preparar_convierte_a_jpeg_rgb(jornada, tmp_path):
    plan = flujo.preparar(jornada, "jornada", tmp_path / "pub", "777-jornada",
                          tmp_path / "plan.json")
    assert plan["archivos"] == ["777-jornada/01_lvbp_1_jornada.jpg",
                                "777-jornada/02_lvbp_2_destacados.jpg"]
    with Image.open(tmp_path / "pub" / plan["archivos"][0]) as im:
        assert im.format == "JPEG" and im.mode == "RGB" and im.size == (108, 135)
    assert json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))["caption"]
    assert not (tmp_path / "pub" / "plan.json").exists()   # el plan no se hace público


# --- Cliente de Instagram ------------------------------------------------------------

def test_carrusel_tres_pasos_y_permalink():
    http = GraphFalso()
    hecho = ig(http).publicar(["https://x/1.jpg", "https://x/2.jpg"], "Hola #MBP")
    hijos = http.posts("1789/media")[:2]
    assert [h["datos"]["image_url"] for h in hijos] == ["https://x/1.jpg", "https://x/2.jpg"]
    assert all(h["datos"]["is_carousel_item"] == "true" for h in hijos)
    assert all("caption" not in h["datos"] for h in hijos)
    carrusel = http.posts("1789/media")[2]["datos"]
    assert carrusel["media_type"] == "CAROUSEL" and carrusel["children"] == "c1,c2"
    assert carrusel["caption"] == "Hola #MBP"
    assert http.posts("media_publish")[0]["datos"]["creation_id"] == "c3"
    assert hecho.media_id == "pub4" and hecho.permalink.endswith("/p/pub4/")
    assert not hecho.duplicado


def test_una_sola_imagen_es_post_simple():
    http = GraphFalso()
    ig(http).publicar(["https://x/1.jpg"], "Solo una")
    (c,) = http.posts("1789/media")
    assert c["datos"]["caption"] == "Solo una" and "is_carousel_item" not in c["datos"]


def test_usa_ig_user_id_si_viene_sin_preguntar_a_me():
    http = GraphFalso()
    ig(http, user_id="555").publicar(["https://x/1.jpg"], "x")
    assert not any(c["ruta"] == "me" for c in http.llamadas)
    assert http.posts("555/media")


def test_espera_mientras_procesa(monkeypatch):
    monkeypatch.setattr(instagram.time, "sleep", lambda s: None)
    http = GraphFalso(estados=["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
    ig(http).publicar(["https://x/1.jpg"], "x")
    consultas = [c for c in http.llamadas if c["datos"].get("fields") == "status_code,status"]
    assert len(consultas) == 3


def test_contenedor_con_error_no_se_publica():
    http = GraphFalso(estados=["ERROR"])
    with pytest.raises(instagram.InstagramError, match="ERROR"):
        ig(http).publicar(["https://x/1.jpg", "https://x/2.jpg"], "x")
    assert not http.posts("media_publish")


def test_no_publica_dos_veces_el_mismo_caption():
    previo = {"id": "777", "caption": "Ya salió ", "permalink": "https://www.instagram.com/p/777/"}
    http = GraphFalso(recientes=[previo])
    hecho = ig(http).publicar(["https://x/1.jpg"], "Ya salió")
    assert hecho.duplicado and hecho.permalink.endswith("/p/777/")
    assert not http.posts("/media") and not http.posts("media_publish")


def test_caption_invalido_se_frena_antes_de_llamar():
    http = GraphFalso()
    with pytest.raises(instagram.InstagramError, match="2201 caracteres"):
        ig(http).publicar(["https://x/1.jpg"], "x" * 2201)
    with pytest.raises(instagram.InstagramError, match="31 hashtags"):
        ig(http).publicar(["https://x/1.jpg"], " ".join(f"#t{i}" for i in range(31)))
    with pytest.raises(instagram.InstagramError, match="11 imágenes"):
        ig(http).publicar([f"https://x/{i}.jpg" for i in range(11)], "x")
    assert http.llamadas == []


def test_errores_explicados_y_sin_token():
    err = {"message": f"Invalid OAuth access token {TOKEN_IG}", "code": 190}
    http = GraphFalso(error_en={"me": err})
    with pytest.raises(instagram.InstagramError) as e:
        ig(http).publicar(["https://x/1.jpg"], "x")
    assert "venció" in str(e.value) and TOKEN_IG not in str(e.value)

    err = {"message": "Media download has failed", "code": 9004, "error_subcode": 2207052}
    http = GraphFalso(error_en={"1789/media": err})
    with pytest.raises(instagram.InstagramError, match="no pudo descargar la imagen"):
        ig(http).publicar(["https://x/1.jpg"], "x")


def test_red_caida_tampoco_muestra_el_token():
    class Caido:
        def get(self, url, params=None, timeout=None):
            raise ConnectionError(f"fallo con access_token={TOKEN_IG}")
    with pytest.raises(instagram.InstagramError) as e:
        ig(Caido()).cuenta()
    assert TOKEN_IG not in str(e.value) and "<token>" in str(e.value)


def test_limite_de_publicacion():
    assert ig(GraphFalso()).limite() == {"quota_usage": 2, "config": {"quota_total": 100}}


# --- Flujo completo ---------------------------------------------------------------

def test_publicar_y_avisar_en_telegram(jornada, tmp_path):
    plan = flujo.preparar(jornada, "jornada", tmp_path / "pub", "9-jornada", tmp_path / "p.json")
    graph, tele = GraphFalso(), TgFalso()
    hecho = flujo.publicar_instagram(plan, "https://raw.githubusercontent.com/o/r/abc/",
                                     ig(graph), tg(tele), "55")
    urls = [c["datos"]["image_url"] for c in graph.posts("1789/media")[:2]]
    assert urls == ["https://raw.githubusercontent.com/o/r/abc/9-jornada/01_lvbp_1_jornada.jpg",
                    "https://raw.githubusercontent.com/o/r/abc/9-jornada/02_lvbp_2_destacados.jpg"]
    (ed,) = tele.llamadas
    assert ed["metodo"] == "editMessageText" and ed["data"]["message_id"] == "55"
    assert ed["data"]["text"].startswith("📸 LVBP · Jornada del 2026-10-15\n\n✅ Publicado")
    assert hecho.permalink in ed["data"]["text"]
    assert json.loads(ed["data"]["reply_markup"]) == {"inline_keyboard": []}


def test_url_base_debe_ser_https(jornada, tmp_path):
    plan = flujo.preparar(jornada, "jornada", tmp_path / "pub", "9-j", tmp_path / "p.json")
    with pytest.raises(instagram.InstagramError, match="https"):
        flujo.publicar_instagram(plan, "http://inseguro/", ig(GraphFalso()))


def test_aviso_de_fallo_ofrece_reintentar():
    tele = TgFalso()
    flujo.avisar_fallo(tg(tele), "55", "123", "2", "token vencido", titular="Juego 2",
                       url_run="https://github.com/x/runs/1")
    (ed,) = tele.llamadas
    assert ed["data"]["text"].startswith("📸 Juego 2\n\n❌ No se publicó en Instagram: token vencido")
    teclado = json.loads(ed["data"]["reply_markup"])["inline_keyboard"]
    assert teclado[0][0]["callback_data"] == "pub:123:2"


# --- Botón en el paquete de Telegram ----------------------------------------------

def test_sin_variable_no_hay_boton(jornada, monkeypatch):
    monkeypatch.delenv("BPT_PUBLICAR_INSTAGRAM", raising=False)
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    tele = TgFalso()
    telegram.enviar_dia(jornada, tg(tele), originales=False)
    assert not any("reply_markup" in c["data"] for c in tele.llamadas)


def test_fuera_de_actions_no_hay_boton(jornada, monkeypatch):
    monkeypatch.setenv("BPT_PUBLICAR_INSTAGRAM", "1")
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    tele = TgFalso()
    telegram.enviar_dia(jornada, tg(tele), originales=False)
    assert not any("reply_markup" in c["data"] for c in tele.llamadas)


def test_boton_al_final_de_la_jornada(jornada, monkeypatch):
    monkeypatch.setenv("BPT_PUBLICAR_INSTAGRAM", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "18519887654")
    tele = TgFalso()
    telegram.enviar_dia(jornada, tg(tele), originales=False)
    ultimo = tele.llamadas[-1]["data"]
    assert ultimo["text"].startswith("📸 LVBP · Jornada del 2026-10-15\n\n¿La subo")
    boton = json.loads(ultimo["reply_markup"])["inline_keyboard"][0][0]
    assert boton["callback_data"] == "pub:18519887654:jornada"


def test_un_boton_por_juego_y_aviso_de_alertas(mlb, monkeypatch):
    monkeypatch.setenv("BPT_PUBLICAR_INSTAGRAM", "true")
    monkeypatch.setenv("GITHUB_RUN_ID", "9")
    tele = TgFalso()
    telegram.enviar_dia(mlb, tg(tele), originales=False)
    con_boton = [c["data"] for c in tele.llamadas if "reply_markup" in c["data"]]
    datos = [json.loads(c["reply_markup"])["inline_keyboard"][0][0]["callback_data"]
             for c in con_boton]
    assert datos == ["pub:9:1", "pub:9:2"]                 # el juego sin textos no lleva botón
    assert "⚠️ con alertas" not in con_boton[0]["text"]
    assert con_boton[1]["text"].startswith("📸 Juego 2 · ⚠️ con alertas")


def test_webhook_valida_url_y_secreto():
    with pytest.raises(telegram.TelegramError, match="https"):
        telegram.poner_webhook(TOKEN_TG, "http://x", "s" * 32, http=TgFalso())
    with pytest.raises(telegram.TelegramError, match="secreto"):
        telegram.poner_webhook(TOKEN_TG, "https://x", "corto", http=TgFalso())
    tele = TgFalso()
    telegram.poner_webhook(TOKEN_TG, "https://relay.workers.dev", "s" * 32, http=tele)
    (c,) = tele.llamadas
    assert c["metodo"] == "setWebhook" and c["data"]["secret_token"] == "s" * 32
    assert json.loads(c["data"]["allowed_updates"]) == ["callback_query", "message"]


# --- Historia del día ---------------------------------------------------------------

def test_historia_un_contenedor_stories_sin_caption():
    http = GraphFalso()
    hecho = ig(http).publicar_historia("https://x/h.jpg")
    (c,) = http.posts("1789/media")
    assert c["datos"]["media_type"] == "STORIES" and c["datos"]["image_url"] == "https://x/h.jpg"
    assert "caption" not in c["datos"]
    assert http.posts("media_publish")[0]["datos"]["creation_id"] == "c1"
    assert hecho.media_id == "pub2" and hecho.permalink


def test_historia_sin_permalink_usa_el_perfil():
    http = GraphFalso(error_en={"pub2": {"code": 100, "message": "no permalink"}})
    hecho = ig(http).publicar_historia("https://x/h.jpg")
    assert hecho.permalink == instagram.PERFIL_HISTORIAS


def test_flujo_publica_historia_y_avisa(tmp_path):
    plan = {"pieza": "1", "tipo": "historia", "titular": "Historia · Juegos de hoy · lunes",
            "caption": "", "alertas": [], "archivos": ["9-1/01_historia.jpg"]}
    http, t = GraphFalso(), TgFalso()
    flujo.publicar_instagram(plan, "https://raw.example/abc", ig(http), tg(t), "55")
    assert http.posts("1789/media")[0]["datos"]["media_type"] == "STORIES"
    texto = t.llamadas[-1]["data"]["text"]
    assert texto.startswith("📲 Historia") and "Historia publicada" in texto
