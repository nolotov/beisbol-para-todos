"""Threads y X: clientes, menú de botones y publicación en varias redes (sin red)."""
import json
from pathlib import Path

import pytest
from PIL import Image

from bpt.notificar import telegram
from bpt.publicar import flujo, piezas, redes
from bpt.publicar import threads as th
from bpt.publicar import x as xx

TOKEN_TH = "THAAsecretoSecretoSecretoSecreto999"
TOKEN_TG = "123456789:AAHsecretoSecretoSecretoSecretoXYZ"


class Resp:
    def __init__(self, cuerpo, status_code=200):
        self.cuerpo, self.status_code = cuerpo, status_code

    def json(self):
        return self.cuerpo


# --- Threads -------------------------------------------------------------------------

class ThreadsFalso:
    def __init__(self, recientes=None, falla_respuesta_n=None):
        self.llamadas, self.n = [], 0
        self.recientes = recientes or []
        self.falla_respuesta_n = falla_respuesta_n
        self.respuestas = 0

    def get(self, url, params=None, timeout=None):
        ruta = url.split("/v1.0/", 1)[1]
        self.llamadas.append(("GET", ruta, dict(params)))
        if ruta == "me":
            return Resp({"id": "777", "username": "mbp.deportes"})
        if ruta.endswith("/threads"):
            return Resp({"data": self.recientes})
        if params.get("fields") == "permalink":
            return Resp({"permalink": f"https://www.threads.net/@mbp.deportes/post/{ruta}"})
        return Resp({"status": "FINISHED"})

    def post(self, url, data=None, timeout=None):
        ruta = url.split("/v1.0/", 1)[1]
        self.llamadas.append(("POST", ruta, dict(data)))
        if "reply_to_id" in data:
            self.respuestas += 1
            if self.respuestas == self.falla_respuesta_n:
                return Resp({"error": {"code": 1, "message": "boom " + TOKEN_TH}})
        self.n += 1
        return Resp({"id": ("p" if ruta.endswith("threads_publish") else "c") + str(self.n)})

    def posts(self, sufijo):
        return [d for v, r, d in self.llamadas if v == "POST" and r.endswith(sufijo)]


def cliente_th(http):
    return th.Threads(TOKEN_TH, http=http, pausa=0)


def test_threads_carrusel_y_respuestas_encadenadas():
    http = ThreadsFalso()
    hecho = cliente_th(http).publicar_hilo(["https://x/1.jpg", "https://x/2.jpg"],
                                           ["Primero ⚾", "Segundo", "Tercero"])
    cont = http.posts("777/threads")
    assert [c.get("is_carousel_item") for c in cont[:2]] == ["true", "true"]
    assert cont[2]["media_type"] == "CAROUSEL" and cont[2]["children"] == "c1,c2"
    assert cont[2]["text"] == "Primero ⚾"
    # cada respuesta cuelga de la anterior
    assert cont[3]["reply_to_id"] == "p4" and cont[3]["text"] == "Segundo"
    assert cont[4]["reply_to_id"] == "p6"
    assert hecho.media_id == "p4" and "threads.net" in hecho.permalink


def test_threads_una_imagen_y_no_repite():
    http = ThreadsFalso(recientes=[{"id": "9", "text": "Hola", "permalink": "https://t/9"}])
    hecho = cliente_th(http).publicar_hilo(["https://x/1.jpg"], ["Hola", "x"])
    assert hecho.duplicado and hecho.permalink == "https://t/9"
    assert not http.posts("threads_publish")


def test_threads_hilo_a_medias_es_parcial_y_sin_token():
    http = ThreadsFalso(falla_respuesta_n=2)
    with pytest.raises(th.PublicacionParcial) as e:
        cliente_th(http).publicar_hilo(["https://x/1.jpg"], ["a", "b", "c"])
    assert "salieron 2 de 3" in str(e.value) and TOKEN_TH not in str(e.value)
    assert e.value.permalink


def test_threads_texto_largo_se_frena():
    with pytest.raises(th.ThreadsError, match="máx. 500"):
        cliente_th(ThreadsFalso()).publicar_hilo([], ["x" * 501])


# --- X -------------------------------------------------------------------------------

class XFalso:
    def __init__(self, error_en_tuit=None, estado=403, detalle="Forbidden"):
        self.llamadas, self.n = [], 0
        self.error_en_tuit, self.estado, self.detalle = error_en_tuit, estado, detalle
        self.tuits = 0

    def post(self, url, auth=None, timeout=None, json=None, files=None, data=None):
        self.llamadas.append({"url": url, "json": json, "files": files, "data": data})
        self.n += 1
        if url.endswith("/media/upload"):
            return Resp({"data": {"id": f"m{self.n}"}})
        self.tuits += 1
        if self.tuits == self.error_en_tuit:
            return Resp({"title": "Forbidden", "detail": self.detalle}, self.estado)
        return Resp({"data": {"id": f"t{self.n}"}}, 201)

    def get(self, url, auth=None, timeout=None):
        return Resp({"data": {"id": "1", "username": "mbpdeportes", "name": "MBP"}})


@pytest.fixture
def jpgs(tmp_path):
    rutas = []
    for i in range(5):
        r = tmp_path / f"{i}.jpg"
        Image.new("RGB", (10, 10)).save(r)
        rutas.append(r)
    return rutas


def test_x_hilo_con_hasta_4_imagenes_en_el_primero(jpgs):
    http = XFalso()
    hecho = xx.X(http=http).publicar_hilo(jpgs, ["Uno ⚾", "Dos", "Tres"])
    subidas = [c for c in http.llamadas if c["url"].endswith("/media/upload")]
    assert len(subidas) == 4 and subidas[0]["data"]["media_category"] == "tweet_image"
    tuits = [c["json"] for c in http.llamadas if c["url"].endswith("/tweets")]
    assert tuits[0] == {"text": "Uno ⚾", "media": {"media_ids": ["m1", "m2", "m3", "m4"]}}
    assert tuits[1] == {"text": "Dos", "reply": {"in_reply_to_tweet_id": "t5"}}
    assert tuits[2]["reply"] == {"in_reply_to_tweet_id": "t6"}
    assert hecho.permalink == "https://x.com/i/web/status/t5"


def test_x_rechaza_enlaces_antes_de_gastar(jpgs):
    http = XFalso()
    with pytest.raises(xx.XError, match="enlace"):
        xx.X(http=http).publicar_hilo(jpgs, ["Mira https://mbp.com", "b"])
    assert http.llamadas == []


def test_x_largo_ponderado():
    assert xx.largo("ábc") == 3
    assert xx.largo("⚾") == 2
    assert xx.revisar(["a" * 281]) and not xx.revisar(["á" * 280])


def test_x_errores_explicados_y_secretos_ocultos(jpgs):
    http = XFalso(error_en_tuit=1, estado=402, detalle="no credits for KEY123")
    with pytest.raises(xx.XError) as e:
        xx.X(http=http, secretos=("KEY123",)).publicar_hilo(jpgs[:1], ["a"])
    assert "créditos" in str(e.value) and "KEY123" not in str(e.value)


def test_x_hilo_a_medias(jpgs):
    with pytest.raises(xx.PublicacionParcial) as e:
        xx.X(http=XFalso(error_en_tuit=2)).publicar_hilo(jpgs[:1], ["a", "b", "c"])
    assert "salieron 1 de 3" in str(e.value) and e.value.permalink.endswith("t2")


def test_x_repetido_se_explica(jpgs):
    http = XFalso(error_en_tuit=1, detalle="You are not allowed to create a Tweet with duplicate content.")
    with pytest.raises(xx.XError, match="repetido"):
        xx.X(http=http).publicar_hilo(jpgs[:1], ["a"])


# --- Menú y botones ----------------------------------------------------------------------

def test_solo_instagram_mantiene_el_formato_corto():
    (fila,) = redes.menu("123", "2", "i")
    assert fila == [{"text": "📸 Publicar en Instagram", "callback_data": "pub:123:2"}]


def test_menu_de_tres_redes():
    filas = redes.menu("18519887654", "jornada", "xti")
    datos = [[b["callback_data"] for b in f] for f in filas]
    assert datos == [["pub:18519887654:jornada:i:itx", "pub:18519887654:jornada:t:itx"],
                     ["pub:18519887654:jornada:x:itx"],
                     ["pub:18519887654:jornada:itx:itx"]]
    assert all(len(d.encode()) <= 64 for f in datos for d in f)
    assert redes.nombres("ti") == "Instagram y Threads"
    assert redes.pregunta("tx").startswith("¿Dónde")


VAL_OK = {"ok": True, "cifras_sin_respaldo": [], "alertas": []}


@pytest.fixture
def jornada(tmp_path):
    d = tmp_path / "2026-10-15"
    for n in ("lvbp_1_jornada.png", "lvbp_2_destacados.png"):
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (108, 135), (30, 42, 71, 255)).save(d / n)
    (d / "resumen.json").write_text(json.dumps({
        "formato": "jornada", "liga": "LVBP", "fecha": "2026-10-15",
        "juegos": [{"titular": "MAG 5-3 CAR"}],
        "tarjetas": ["lvbp_1_jornada.png", "lvbp_2_destacados.png"]}), encoding="utf-8")
    (d / "textos.json").write_text(json.dumps([{
        "game_pk": "jornada", "titular": "Jornada",
        "textos": {"instagram": "Caption #LVBP", "hilo_x": ["Tuit 1", "Tuit 2"],
                   "guion": "g", "angulo": ""},
        "validacion": VAL_OK}], ensure_ascii=False), encoding="utf-8")
    return d


class TgFalso:
    def __init__(self):
        self.llamadas = []

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas.append({"metodo": url.rsplit("/", 1)[-1], "data": data or {}})
        return Resp({"ok": True, "result": {"message_id": 99}})


def tg(http):
    return telegram.Telegram(TOKEN_TG, "42", pausa=0, http=http)


def test_pieza_trae_el_hilo_y_sus_redes(jornada):
    (p,) = piezas.piezas(jornada)
    assert p.hilo == ["Tuit 1", "Tuit 2"]
    assert p.redes("itx") == "itx" and p.redes("x") == "x" and p.redes("") == ""


def test_boton_por_red_en_telegram(jornada, monkeypatch):
    for v in ("BPT_PUBLICAR_INSTAGRAM", "BPT_PUBLICAR_THREADS", "BPT_PUBLICAR_X"):
        monkeypatch.setenv(v, "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "555")
    tele = TgFalso()
    telegram.enviar_dia(jornada, tg(tele), originales=False)
    ultimo = tele.llamadas[-1]["data"]
    assert ultimo["text"].endswith("¿Dónde la publico? Te pido confirmación antes.")
    filas = json.loads(ultimo["reply_markup"])["inline_keyboard"]
    assert [b["text"] for f in filas for b in f] == ["📸 Instagram", "🧵 Threads", "𝕏 X", "🚀 Todas"]


def test_solo_x_encendido(jornada, monkeypatch):
    monkeypatch.delenv("BPT_PUBLICAR_INSTAGRAM", raising=False)
    monkeypatch.delenv("BPT_PUBLICAR_THREADS", raising=False)
    monkeypatch.setenv("BPT_PUBLICAR_X", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "555")
    tele = TgFalso()
    telegram.enviar_dia(jornada, tg(tele), originales=False)
    (fila,) = json.loads(tele.llamadas[-1]["data"]["reply_markup"])["inline_keyboard"]
    assert fila[0]["callback_data"] == "pub:555:jornada:x:x"
    assert "¿La subo a X?" in tele.llamadas[-1]["data"]["text"]


# --- Publicar en varias redes --------------------------------------------------------

def _plan(tmp_path, jornada):
    return flujo.preparar(jornada, "jornada", tmp_path / "pub", "1-jornada", tmp_path / "plan.json")


class Falso:
    def __init__(self, red, falla=None, parcial=False):
        self.red, self.falla, self.parcial, self.llamadas = red, falla, parcial, []

    def _hecho(self, *a):
        self.llamadas.append(a)
        if self.parcial:
            raise xx.PublicacionParcial("hilo incompleto: salieron 1 de 2 tuits", "https://x/1")
        if self.falla:
            raise self.falla
        return th.Publicado("1", f"https://{self.red}/1")

    publicar = publicar_hilo = publicar_historia = _hecho


def test_publica_en_las_tres_y_edita_el_mensaje(tmp_path, jornada):
    plan = _plan(tmp_path, jornada)
    cl = {c: Falso(c) for c in "itx"}
    res = flujo.publicar_redes(plan, "itx", "https://raw/abc", tmp_path / "pub",
                               {c: (lambda c=c: cl[c]) for c in "itx"})
    assert [r.ok for r in res] == [True, True, True]
    urls, textos = cl["t"].llamadas[0]
    assert urls[0] == "https://raw/abc/1-jornada/01_lvbp_1_jornada.jpg" and textos == ["Tuit 1", "Tuit 2"]
    rutas, _ = cl["x"].llamadas[0]
    assert Path(rutas[0]).exists()                  # a X se le suben los archivos locales
    tele = TgFalso()
    flujo.avisar_resultados(tg(tele), plan, res, "1", "70", "itx", "itx")
    (ed,) = tele.llamadas
    assert ed["metodo"] == "editMessageText"
    assert "✅ Instagram: publicado" in ed["data"]["text"] and "✅ X: publicado" in ed["data"]["text"]
    assert json.loads(ed["data"]["reply_markup"])["inline_keyboard"] == []


def test_una_red_falla_las_otras_salen_y_se_ofrece_reintentar(tmp_path, jornada):
    plan = _plan(tmp_path, jornada)
    fabricas = {"i": lambda: Falso("i"), "t": lambda: Falso("t"),
                "x": lambda: (_ for _ in ()).throw(xx.XError("faltan los secretos X_API_KEY"))}
    res = flujo.publicar_redes(plan, "itx", "https://raw/abc", tmp_path / "pub", fabricas)
    assert [r.ok for r in res] == [True, True, False]
    tele = TgFalso()
    flujo.avisar_resultados(tg(tele), plan, res, "9", "70", "itx", "itx")
    teclado = json.loads(tele.llamadas[0]["data"]["reply_markup"])["inline_keyboard"]
    assert teclado[0][0]["callback_data"] == "pub:9:jornada:x:x"
    assert "❌ X: faltan los secretos" in tele.llamadas[0]["data"]["text"]


def test_si_quedan_redes_el_resultado_va_como_respuesta(tmp_path, jornada):
    plan = _plan(tmp_path, jornada)
    res = flujo.publicar_redes(plan, "x", None, tmp_path / "pub", {"x": lambda: Falso("x")})
    tele = TgFalso()
    flujo.avisar_resultados(tg(tele), plan, res, "9", "70", "x", "itx")
    (m,) = tele.llamadas
    assert m["metodo"] == "sendMessage"
    assert json.loads(m["data"]["reply_parameters"])["message_id"] == 70


def test_hilo_parcial_no_ofrece_reintentar(tmp_path, jornada):
    plan = _plan(tmp_path, jornada)
    res = flujo.publicar_redes(plan, "x", None, tmp_path / "pub",
                               {"x": lambda: Falso("x", parcial=True)})
    assert res[0].parcial and res[0].permalink == "https://x/1"
    tele = TgFalso()
    flujo.avisar_resultados(tg(tele), plan, res, "9", "70", "x", "x")
    assert json.loads(tele.llamadas[0]["data"]["reply_markup"])["inline_keyboard"] == []
    assert "⚠️ X: hilo incompleto" in tele.llamadas[0]["data"]["text"]


def test_threads_sin_url_publica_no_sale(tmp_path, jornada):
    plan = _plan(tmp_path, jornada)
    (r,) = flujo.publicar_redes(plan, "t", None, tmp_path / "pub", {"t": lambda: Falso("t")})
    assert not r.ok and "https" in r.motivo


def test_fallo_previo_con_otras_redes_responde_sin_borrar_el_menu():
    tele = TgFalso()
    flujo.avisar_fallo(tg(tele), "70", "9", "2", "no encontré el paquete", titular="Juego 2",
                       destino="t", quedan="itx")
    (m,) = tele.llamadas
    assert m["metodo"] == "sendMessage" and "No se publicó en Threads" in m["data"]["text"]
    teclado = json.loads(m["data"]["reply_markup"])["inline_keyboard"]
    assert teclado[0][0]["callback_data"] == "pub:9:2:t:t"
