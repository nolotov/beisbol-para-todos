"""Métricas: registro de lo publicado, lectura de cada red (simulada), informe y aprendizajes."""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

from PIL import Image

from bpt import metricas as Mx
from bpt.publicar import flujo
from bpt.publicar.instagram import InstagramError

AHORA = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)


def _fila(red, mid, formato, dia, hora=12, titular=None, tipo="post"):
    return {"fecha_utc": f"2026-10-{dia:02d}T{hora:02d}:00:00+00:00", "run_id": "1",
            "pieza": "1", "titular": titular or f"{formato} {dia}", "tipo": tipo,
            "formato": formato, "red": red, "media_id": mid, "permalink": "", "laminas": 3}


REGISTRO = [
    _fila("i", "ig1", "resultado", 20, 11), _fila("i", "ig2", "resultado", 21, 11),
    _fila("i", "ig3", "resultado", 22, 11), _fila("i", "ig4", "especial", 23, 23),
    _fila("i", "ig5", "especial", 24, 23, "Previa de la Serie Mundial"),
    _fila("i", "ig6", "especial", 25, 23), _fila("i", "ig7", "historia_dia", 25, 11,
                                                 tipo="historia"),
    _fila("t", "th1", "especial", 24, 23), _fila("x", "x1", "especial", 24, 23),
    {**_fila("i", "viejo", "resultado", 1), "fecha_utc": "2026-09-01T12:00:00+00:00"},
]   # el último queda fuera de la ventana de 28 días

ALCANCE_IG = {"ig1": 300, "ig2": 320, "ig3": 280, "ig4": 900, "ig5": 1500, "ig6": 1100,
              "ig7": 200}


class FakeIG:
    def __init__(self, sin_permiso=False):
        self.sin_permiso, self.pedidos = sin_permiso, []

    def _llamar(self, verbo, ruta, params):
        self.pedidos.append((ruta, params["metric"]))
        if self.sin_permiso:
            raise InstagramError("ig: (#10) Application does not have permission for this action")
        mid = ruta.split("/")[0]
        if "views" in params["metric"] and mid == "ig3":      # simula métrica no soportada
            raise InstagramError("métrica inválida")
        r = ALCANCE_IG[mid]
        return {"data": [{"name": "reach", "values": [{"value": r}]},
                         {"name": "saved", "values": [{"value": r // 50}]},
                         {"name": "likes", "values": [{"value": r // 10}]},
                         {"name": "shares", "total_value": {"value": r // 100}}]}


class FakeTH:
    def _llamar(self, verbo, ruta, params):
        return {"data": [{"name": "views", "values": [{"value": 400}]},
                         {"name": "likes", "values": [{"value": 12}]},
                         {"name": "reposts", "values": [{"value": 3}]}]}


class FakeX:
    def __init__(self):
        self.auth = None
        self.http = self

    def get(self, url, **kw):
        assert kw["params"]["tweet.fields"] == "public_metrics"
        return NS(status_code=200, json=lambda: {"data": [
            {"id": "x1", "public_metrics": {"impression_count": 800, "like_count": 20,
                                            "retweet_count": 4, "bookmark_count": 6}}]})

    def _respuesta(self, r, que):
        return r.json()

    def _limpiar(self, t):
        return t


def _clientes(ig=None):
    return {"i": lambda: ig or FakeIG(), "t": FakeTH, "x": FakeX}


def test_registro_de_lo_publicado():
    plan = {"pieza": "1", "titular": "Especial", "tipo": "post", "formato": "editor",
            "archivos": ["a.jpg", "b.jpg"]}
    res = [flujo.Resultado("i", True, "https://ig/p/1", media_id="111"),
           flujo.Resultado("t", True, "https://th/1", duplicado=True, media_id="222"),
           flujo.Resultado("x", False, motivo="sin saldo")]
    filas = flujo.registro(plan, res, "99", ahora="2026-10-24T12:00:00+00:00")
    assert filas == [{"fecha_utc": "2026-10-24T12:00:00+00:00", "run_id": "99", "pieza": "1",
                      "titular": "Especial", "tipo": "post", "formato": "editor", "red": "i",
                      "media_id": "111", "permalink": "https://ig/p/1", "laminas": 2}]


def test_leer_registro_y_ventana(tmp_path):
    p = tmp_path / "publicaciones.jsonl"
    p.write_text("\n".join(json.dumps(f) for f in REGISTRO) + "\nbasura\n", encoding="utf-8")
    filas = Mx.leer_registro(p)
    assert len(filas) == len(REGISTRO)
    assert "viejo" not in [f["media_id"] for f in Mx.recientes(filas, ahora=AHORA)]


def test_normalizar_por_red():
    i = Mx.normalizar("i", {"reach": 1000, "likes": 50, "comments": 5, "saved": 20, "shares": 5})
    assert (i["alcance"], i["interacciones"], i["tasa"]) == (1000, 80, 0.08)
    x = Mx.normalizar("x", {"impression_count": 500, "like_count": 10, "bookmark_count": 5})
    assert (x["alcance"], x["interacciones"], x["guardados"]) == (500, 15, 5)
    assert Mx.normalizar("t", {})["tasa"] is None


def test_foto_completa_con_metrica_no_soportada():
    filas = Mx.recientes(REGISTRO, ahora=AHORA)
    ig = FakeIG()
    foto = Mx.tomar_foto(filas, _clientes(ig), "2026-10-26")
    assert foto.errores == {}
    assert len(foto.filas) == 9
    # ig3 no aceptó "views": se reintentó con la lista corta
    assert [m for r, m in ig.pedidos if r.startswith("ig3")][-1] == ",".join(Mx.IG_FEED_MIN)
    # La historia pide sus propias métricas
    assert [m for r, m in ig.pedidos if r.startswith("ig7")][0] == ",".join(Mx.IG_HISTORIA)


def test_sin_permiso_se_explica_y_no_frena_a_las_otras():
    filas = Mx.recientes(REGISTRO, ahora=AHORA)
    foto = Mx.tomar_foto(filas, _clientes(FakeIG(sin_permiso=True)), "2026-10-26")
    assert "instagram_business_manage_insights" in foto.errores["i"]
    assert {f["red"] for f in foto.filas} == {"t", "x"}
    assert "⚠️ Instagram: falta el permiso" in Mx.informe(foto, AHORA)


def test_informe_y_aprendizajes():
    foto = Mx.tomar_foto(Mx.recientes(REGISTRO, ahora=AHORA), _clientes(), "2026-10-26")
    texto = Mx.informe(foto, AHORA)
    assert texto.startswith("📈 MBP · Métricas al 2026-10-26")
    assert "Instagram por formato" in texto
    assert texto.index("Especial: alcance 1.167") < texto.index("Resultado MLB: alcance 300")
    assert "🏆" in texto and "Previa de la Serie Mundial" in texto
    apr = Mx.aprendizajes(foto)
    assert "el formato con más alcance por pieza es Especial" in apr
    assert "noche" in apr and "mañana" in apr           # franjas con 3+ piezas
    assert "Previa de la Serie Mundial" in apr


def test_sin_muestra_suficiente_no_hay_aprendizajes():
    foto = Mx.tomar_foto(Mx.recientes(REGISTRO[:2], ahora=AHORA), _clientes(), "2026-10-26")
    assert Mx.aprendizajes(foto) == ""


def test_ejecutar_escribe_la_rama_y_la_lamina(tmp_path):
    rama = tmp_path / "metricas"
    rama.mkdir()
    (rama / "publicaciones.jsonl").write_text(
        "\n".join(json.dumps(f) for f in REGISTRO), encoding="utf-8")
    foto, texto, apr, img = Mx.ejecutar(rama / "publicaciones.jsonl", rama, _clientes(),
                                        imagen=tmp_path / "informe.png", ahora=AHORA)
    assert (rama / "fotos" / "2026-10-26.json").exists()
    assert (rama / "aprendizajes.md").read_text(encoding="utf-8").startswith("Métricas al")
    assert not (rama / "informe.png").exists()
    with Image.open(img) as im:
        assert im.size == (1080, 1350)


def test_el_editor_lee_los_aprendizajes():
    from bpt.editor import prompt
    m = prompt.mensaje_inicial("2026-10-26", None, [], "- Instagram: Especial rinde más.")
    assert "Lo que ha funcionado en redes" in m and "Especial rinde más" in m


def test_formato_de_cada_pieza(tmp_path):
    from bpt.publicar import piezas
    carpeta = tmp_path / "p"
    carpeta.mkdir()
    Image.new("RGB", (10, 10)).save(carpeta / "a.png")
    (carpeta / "resumen.json").write_text(json.dumps(
        {"formato": "especial", "titular": "T", "tarjetas": ["a.png"], "editor": {"x": 1}}),
        encoding="utf-8")
    (carpeta / "textos.json").write_text(json.dumps([{"game_pk": "especial", "textos": {
        "instagram": "c", "hilo_x": ["a"]}, "validacion": {}}]), encoding="utf-8")
    (p,) = piezas.piezas(carpeta)
    assert p.formato == "editor"
    plan = piezas.preparar(p, tmp_path / "pub", "r1")
    assert plan["formato"] == "editor"
