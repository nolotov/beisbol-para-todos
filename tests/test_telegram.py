"""Bot de Telegram con un cliente HTTP falso (sin red)."""
import json
from pathlib import Path

import pytest

from bpt import resultados
from bpt.notificar import telegram

FX = Path(__file__).parent / "fixtures"
TOKEN = "123456789:AAHsecretoSecretoSecretoSecretoXYZ"
PERSONAS = {int(k): v for k, v in json.loads(
    (FX / "mlb_people_sintetico.json").read_text(encoding="utf-8")).items() if k.isdigit()}


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def json(self):
        return self.cuerpo


class HttpFalso:
    def __init__(self, respuestas=None):
        self.llamadas = []
        self.respuestas = list(respuestas or [])

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas.append({"metodo": url.rsplit("/", 1)[-1], "data": data or {},
                              "files": sorted(files) if files else []})
        if self.respuestas:
            r = self.respuestas.pop(0)
            if isinstance(r, Exception):
                raise r
            return Resp(r)
        return Resp({"ok": True, "result": {}})


def tg(http):
    return telegram.Telegram(TOKEN, "42", pausa=0, http=http)


TEXTOS = {"instagram": "Caption de prueba", "angulo": "Duelo de bullpens",
          "hilo_x": ["Tuit uno", "Tuit dos", "Tuit tres"], "guion": "[LÁMINA 1] Guion"}


@pytest.fixture
def dia(tmp_path):
    sched = json.loads((FX / "mlb_postemporada_sintetico.json").read_text(encoding="utf-8"))
    box = json.loads((FX / "mlb_boxscore_sintetico_900002.json").read_text(encoding="utf-8"))
    resultados.generar("2026-10-12", salida=tmp_path, schedule=sched, boxscores={900002: box},
                       personas=PERSONAS)
    return tmp_path / "2026-10-12"


def _con_textos(carpeta, ok=True):
    val = {"ok": ok, "cifras_sin_respaldo": [] if ok else ["37"],
           "alertas": [] if ok else ["guion: 120 palabras"]}
    (carpeta / "textos.json").write_text(json.dumps([{
        "game_pk": 900002, "titular": "LAD le gana 3-2 a MIL en 11 entradas",
        "textos": TEXTOS, "validacion": val,
        "estado": "para revisar" if ok else "con alertas"}], ensure_ascii=False),
        encoding="utf-8")


def test_paquete_completo_en_orden(dia):
    _con_textos(dia)
    http = HttpFalso()
    assert telegram.enviar_dia(dia, tg(http)) == 1
    metodos = [c["metodo"] for c in http.llamadas]
    assert metodos == ["sendMessage",           # portada del día
                       "sendMessage",           # encabezado del juego
                       "sendMediaGroup",        # álbum (vista previa)
                       "sendMediaGroup",        # originales como archivo
                       "sendMessage",           # instagram
                       "sendMessage", "sendMessage", "sendMessage",  # 3 tuits
                       "sendMessage"]           # guion
    album, originales = http.llamadas[2], http.llamadas[3]
    assert album["files"] == ["f0", "f1", "f2"]
    assert all(m["type"] == "photo" for m in json.loads(album["data"]["media"]))
    assert all(m["type"] == "document" for m in json.loads(originales["data"]["media"]))
    textos = [c["data"].get("text", "") for c in http.llamadas if c["metodo"] == "sendMessage"]
    assert textos[1].startswith("⚾ 1/1 · LAD le gana 3-2") and "✅ Para revisar" in textos[1]
    assert textos[2] == "📸 INSTAGRAM\n\nCaption de prueba"
    assert textos[3] == "𝕏 1/3\n\nTuit uno"
    assert all(c["data"]["chat_id"] == "42" for c in http.llamadas)


def test_alertas_en_el_encabezado(dia):
    _con_textos(dia, ok=False)
    http = HttpFalso()
    telegram.enviar_dia(dia, tg(http), originales=False)
    enc = http.llamadas[1]["data"]["text"]
    assert "⚠️ Con alertas" in enc and "37" in enc and "120 palabras" in enc
    assert [c["metodo"] for c in http.llamadas].count("sendMediaGroup") == 1


def test_sin_textos_igual_manda_laminas(dia):
    http = HttpFalso()
    telegram.enviar_dia(dia, tg(http))
    metodos = [c["metodo"] for c in http.llamadas]
    assert metodos == ["sendMessage", "sendMessage", "sendMediaGroup", "sendMediaGroup"]
    assert "Sin textos" in http.llamadas[1]["data"]["text"]


def test_dia_sin_juegos(tmp_path):
    (tmp_path / "resumen.json").write_text(json.dumps({
        "fecha": "2026-10-13", "juegos": [],
        "pendientes": [{"partido": "CLE @ TB", "estado": "Pospuesto"}]}), encoding="utf-8")
    http = HttpFalso()
    assert telegram.enviar_dia(tmp_path, tg(http)) == 0
    assert "no hubo juegos" in http.llamadas[0]["data"]["text"]
    assert "CLE @ TB (Pospuesto)" in http.llamadas[0]["data"]["text"]


def test_reintenta_si_telegram_pide_esperar(monkeypatch):
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    http = HttpFalso([{"ok": False, "description": "Too Many Requests",
                       "parameters": {"retry_after": 1}}, {"ok": True, "result": {}}])
    tg(http).texto("hola")
    assert len(http.llamadas) == 2


def test_el_token_nunca_sale_en_los_errores(monkeypatch):
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    http = HttpFalso([ConnectionError(f"Max retries exceeded with url: {url}")] * 3)
    with pytest.raises(telegram.TelegramError) as e:
        tg(http).texto("hola")
    assert TOKEN not in str(e.value) and "<token>" in str(e.value)

    http = HttpFalso([{"ok": False, "description": "Unauthorized"}])
    with pytest.raises(telegram.TelegramError, match="Unauthorized"):
        tg(http).texto("hola")


def test_partir_textos_largos():
    texto = "\n".join(["x" * 100] * 100)          # ~10.100 caracteres
    trozos = telegram.partir(texto)
    assert len(trozos) == 3 and all(len(t) <= telegram.LIMITE_TEXTO for t in trozos)


def test_chats_recientes():
    http = HttpFalso([{"ok": True, "result": [
        {"update_id": 1, "message": {"chat": {"id": 555, "type": "private",
                                              "first_name": "Noe", "username": "noe"}}},
        {"update_id": 2, "message": {"chat": {"id": 555, "type": "private",
                                              "first_name": "Noe"}}}]}])
    assert telegram.chats_recientes(TOKEN, http=http) == [
        {"id": 555, "tipo": "private", "nombre": "Noe", "usuario": ""}]


@pytest.mark.parametrize("token,ok", [(TOKEN, True), ("123:abc", False), ("", False),
                                      ("sk-ant-api03-xxx", False)])
def test_forma_del_token(token, ok):
    assert telegram.es_token_valido(token) is ok


def test_faltan_credenciales(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(telegram.TelegramError, match="TELEGRAM_BOT_TOKEN"):
        telegram.credenciales()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(telegram.TelegramError, match="telegram-chat"):
        telegram.credenciales()
