"""Métricas: qué funcionó en redes y qué aprende el editor de eso (fase 5).

Circuito:
1. `publicar.yml` anota cada publicación (red, id, formato, hora) en la rama `metricas`,
   archivo `publicaciones.jsonl`.
2. El workflow "Métricas MBP" (semanal) lee ese registro, pide a cada red los números de
   las publicaciones de los últimos 28 días, guarda la foto (`fotos/AAAA-MM-DD.json`),
   arma el informe para Telegram con una lámina, y escribe `aprendizajes.md`.
3. El editor lee `aprendizajes.md` antes de elegir la historia del día.

Las métricas se normalizan para comparar redes y formatos:
  alcance        Instagram reach · Threads views · X impresiones
  interacciones  me gusta + comentarios/respuestas + compartidos/reposts + guardados/citas
  tasa           interacciones / alcance
Permisos: Instagram necesita instagram_business_manage_insights y Threads,
threads_manage_insights (se agregan en la app de Meta y se regenera el token).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

TZ_VEN = ZoneInfo("America/Caracas")
VENTANA_DIAS = 28

NOMBRES_FORMATO = {"resultado": "Resultado MLB", "jornada": "Jornada LVBP",
                   "especial": "Especial", "editor": "Propuesta del editor",
                   "historia_dia": "Historia del día", "historia_especial": "Historia especial",
                   "reel": "Reel"}
NOMBRES_RED = {"i": "Instagram", "t": "Threads", "x": "X"}

IG_FEED = ["reach", "likes", "comments", "saved", "shares", "total_interactions", "views"]
IG_FEED_MIN = ["reach", "likes", "comments", "saved", "shares"]
IG_HISTORIA = ["reach", "views", "replies", "shares", "total_interactions"]
IG_REEL = ["reach", "likes", "comments", "saved", "shares", "views", "total_interactions"]
THREADS = ["views", "likes", "replies", "reposts", "quotes", "shares"]


# --- Registro -----------------------------------------------------------------------

def leer_registro(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    filas = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea:
            try:
                filas.append(json.loads(linea))
            except ValueError:
                continue
    return filas


def recientes(filas: list[dict], dias: int = VENTANA_DIAS,
              ahora: datetime | None = None) -> list[dict]:
    ahora = ahora or datetime.now(timezone.utc)
    corte = ahora - timedelta(days=dias)
    return [f for f in filas if _fecha(f) >= corte]


def _fecha(f: dict) -> datetime:
    return datetime.fromisoformat(f["fecha_utc"].replace("Z", "+00:00"))


# --- Lectura de cada red --------------------------------------------------------------

def _valores(cuerpo: dict) -> dict[str, int]:
    """Insights de Meta: {"data": [{"name", "values": [{"value"}]} o "total_value"}]}."""
    out = {}
    for m in cuerpo.get("data", []):
        if "total_value" in m:
            v = (m["total_value"] or {}).get("value")
        else:
            v = ((m.get("values") or [{}])[0]).get("value")
        if isinstance(v, (int, float)):
            out[m["name"]] = int(v)
    return out


def leer_instagram(ig, fila: dict) -> dict[str, int]:
    from bpt.publicar.instagram import InstagramError
    if fila.get("tipo") == "historia":
        metricas = [IG_HISTORIA]
    elif fila.get("formato") == "reel":
        metricas = [IG_REEL, IG_FEED_MIN]
    else:
        metricas = [IG_FEED, IG_FEED_MIN]
    ultimo = None
    for lista in metricas:
        try:
            cuerpo = ig._llamar("GET", f"{fila['media_id']}/insights",
                                {"metric": ",".join(lista)})
            return _valores(cuerpo)
        except InstagramError as e:     # métrica no soportada: se prueba la lista corta
            ultimo = e
    raise ultimo  # type: ignore[misc]


def leer_threads(th, fila: dict) -> dict[str, int]:
    return _valores(th._llamar("GET", f"{fila['media_id']}/insights",
                               {"metric": ",".join(THREADS)}))


def leer_x(cliente, ids: list[str]) -> dict[str, dict[str, int]]:
    """public_metrics de hasta 100 tuits por llamada (X cobra cada lectura)."""
    from bpt.publicar.x import API, XError
    out: dict[str, dict[str, int]] = {}
    for k in range(0, len(ids), 100):
        lote = ids[k:k + 100]
        try:
            r = cliente.http.get(f"{API}/tweets", auth=cliente.auth, timeout=60,
                                 params={"ids": ",".join(lote),
                                         "tweet.fields": "public_metrics"})
        except Exception as e:  # noqa: BLE001
            raise XError(cliente._limpiar(f"tweets: {e}")) from None
        cuerpo = cliente._respuesta(r, "tweets")
        for t in cuerpo.get("data", []):
            out[t["id"]] = {k2: int(v) for k2, v in (t.get("public_metrics") or {}).items()}
    return out


def normalizar(red: str, m: dict[str, int]) -> dict:
    if red == "i":
        alcance = m.get("reach") or m.get("views") or 0
        inter = m.get("total_interactions") or sum(m.get(k, 0) for k in (
            "likes", "comments", "saved", "shares", "replies"))
        guardados, compartidos = m.get("saved", 0), m.get("shares", 0)
    elif red == "t":
        alcance = m.get("views", 0)
        inter = sum(m.get(k, 0) for k in ("likes", "replies", "reposts", "quotes", "shares"))
        guardados, compartidos = 0, m.get("reposts", 0) + m.get("shares", 0)
    else:
        alcance = m.get("impression_count", 0)
        inter = sum(m.get(k, 0) for k in ("like_count", "reply_count", "retweet_count",
                                          "quote_count", "bookmark_count"))
        guardados, compartidos = m.get("bookmark_count", 0), m.get("retweet_count", 0)
    return {"alcance": alcance, "interacciones": inter, "guardados": guardados,
            "compartidos": compartidos,
            "tasa": round(inter / alcance, 4) if alcance else None, "crudo": m}


@dataclass
class Foto:
    fecha: str
    filas: list[dict] = field(default_factory=list)       # registro + métricas
    errores: dict[str, str] = field(default_factory=dict)  # red -> motivo

    def to_dict(self) -> dict:
        return {"fecha": self.fecha, "filas": self.filas, "errores": self.errores}


def tomar_foto(filas: list[dict], clientes: dict, fecha: str) -> Foto:
    """Pide las métricas de cada publicación. `clientes` = {letra: fábrica del cliente};
    una red sin permiso o sin secretos queda en `errores` y no frena a las demás."""
    foto = Foto(fecha)
    por_red = defaultdict(list)
    for f in filas:
        por_red[f["red"]].append(f)
    for red, lista in por_red.items():
        try:
            cliente = clientes[red]()
        except Exception as e:  # noqa: BLE001
            foto.errores[red] = f"sin credenciales ({e})"
            continue
        if red == "x":
            try:
                datos = leer_x(cliente, [f["media_id"] for f in lista])
            except Exception as e:  # noqa: BLE001
                foto.errores[red] = str(e)[:300]
                continue
            for f in lista:
                if f["media_id"] in datos:
                    foto.filas.append({**f, **normalizar(red, datos[f["media_id"]])})
            continue
        fallos = []
        for f in lista:
            try:
                m = leer_instagram(cliente, f) if red == "i" else leer_threads(cliente, f)
            except Exception as e:  # noqa: BLE001
                fallos.append(str(e))
                continue
            foto.filas.append({**f, **normalizar(red, m)})
        if fallos and len(fallos) == len(lista):
            foto.errores[red] = _explicar_fallo(red, fallos[0])
        elif fallos:
            foto.errores[red] = f"{len(fallos)} de {len(lista)} sin datos (p. ej. {fallos[0][:160]})"
    return foto


def _explicar_fallo(red: str, motivo: str) -> str:
    bajo = motivo.lower()
    if "permission" in bajo or "permiso" in bajo or "(#10)" in bajo or "(#200)" in bajo:
        permiso = ("instagram_business_manage_insights" if red == "i"
                   else "threads_manage_insights")
        return f"falta el permiso {permiso} en la app de Meta (y regenerar el token)"
    return motivo[:300]


# --- Informe ------------------------------------------------------------------------

def _num(n: float | int | None) -> str:
    if n is None:
        return "–"
    return f"{n:,.0f}".replace(",", ".")


def _pct(t: float | None) -> str:
    return "–" if t is None else f"{t * 100:.1f} %".replace(".", ",")


def por_formato(filas: list[dict], red: str) -> list[dict]:
    grupos = defaultdict(list)
    for f in filas:
        if f["red"] == red:
            grupos[f.get("formato", "resultado")].append(f)
    salida = []
    for formato, lista in grupos.items():
        tasas = [f["tasa"] for f in lista if f.get("tasa") is not None]
        salida.append({"formato": formato, "piezas": len(lista),
                       "alcance": round(mean(f["alcance"] for f in lista)),
                       "tasa": round(mean(tasas), 4) if tasas else None,
                       "guardados": round(mean(f["guardados"] for f in lista), 1)})
    return sorted(salida, key=lambda g: -g["alcance"])


def por_franja(filas: list[dict], red: str) -> list[dict]:
    """Franjas de publicación en hora de Venezuela."""
    franjas = [("madrugada", 0, 7), ("mañana", 7, 12), ("tarde", 12, 18), ("noche", 18, 24)]
    salida = []
    for nombre, a, b in franjas:
        lista = [f for f in filas if f["red"] == red
                 and a <= _fecha(f).astimezone(TZ_VEN).hour < b]
        if lista:
            salida.append({"franja": nombre, "piezas": len(lista),
                           "alcance": round(mean(f["alcance"] for f in lista))})
    return sorted(salida, key=lambda g: -g["alcance"])


def top(filas: list[dict], n: int = 3) -> list[dict]:
    return sorted(filas, key=lambda f: (-f["interacciones"], -f["alcance"]))[:n]


def informe(foto: Foto, ahora: datetime | None = None) -> str:
    """Texto para Telegram."""
    ahora = ahora or datetime.now(timezone.utc)
    semana = [f for f in foto.filas if _fecha(f) >= ahora - timedelta(days=7)]
    lineas = [f"📈 MBP · Métricas al {foto.fecha}", ""]
    if not foto.filas:
        lineas.append("Sin datos de publicaciones en los últimos 28 días.")
    else:
        lineas.append("Últimos 7 días")
        for red in "itx":
            lista = [f for f in semana if f["red"] == red]
            if lista:
                lineas.append(f"• {NOMBRES_RED[red]}: {len(lista)} publicaciones · alcance "
                              f"{_num(sum(f['alcance'] for f in lista))} · "
                              f"{_num(sum(f['interacciones'] for f in lista))} interacciones")
        if len(lineas) == 3:
            lineas.append("• Nada publicado esta semana.")
        for red in "itx":
            grupos = por_formato(foto.filas, red)
            if not grupos:
                continue
            lineas += ["", f"{NOMBRES_RED[red]} por formato (28 días, promedio por pieza)"]
            for g in grupos:
                lineas.append(f"• {NOMBRES_FORMATO.get(g['formato'], g['formato'])}: "
                              f"alcance {_num(g['alcance'])} · tasa {_pct(g['tasa'])} · "
                              f"{g['piezas']} pieza{'s' if g['piezas'] != 1 else ''}")
        lineas += ["", "🏆 Lo que más movió (28 días)"]
        for f in top(foto.filas):
            lineas.append(f"• {NOMBRES_RED[f['red']]} · {f['titular']}: "
                          f"{_num(f['interacciones'])} interacciones, alcance "
                          f"{_num(f['alcance'])}")
    for red, motivo in foto.errores.items():
        lineas.append(f"\n⚠️ {NOMBRES_RED.get(red, red)}: {motivo}")
    return "\n".join(lineas)


def aprendizajes(foto: Foto) -> str:
    """Pocas líneas, solo con lo que tiene muestra suficiente (3+ piezas): lo lee el editor."""
    lineas = []
    for red in "itx":
        grupos = [g for g in por_formato(foto.filas, red) if g["piezas"] >= 3]
        if len(grupos) >= 2:
            a, z = grupos[0], grupos[-1]
            lineas.append(f"- {NOMBRES_RED[red]}: el formato con más alcance por pieza es "
                          f"{NOMBRES_FORMATO.get(a['formato'], a['formato'])} "
                          f"({_num(a['alcance'])}, {a['piezas']} piezas); el de menos, "
                          f"{NOMBRES_FORMATO.get(z['formato'], z['formato'])} "
                          f"({_num(z['alcance'])}).")
        con_tasa = [g for g in grupos if g["tasa"] is not None]
        if con_tasa:
            g = max(con_tasa, key=lambda g: g["tasa"])
            lineas.append(f"- {NOMBRES_RED[red]}: la mejor tasa de interacción la tiene "
                          f"{NOMBRES_FORMATO.get(g['formato'], g['formato'])} ({_pct(g['tasa'])}).")
        franjas = [f for f in por_franja(foto.filas, red) if f["piezas"] >= 3]
        if len(franjas) >= 2:
            lineas.append(f"- {NOMBRES_RED[red]}: publicar en la {franjas[0]['franja']} "
                          f"(hora de Venezuela) rinde más alcance que en la "
                          f"{franjas[-1]['franja']}.")
    mejores = top([f for f in foto.filas if f.get("formato") in ("especial", "editor")], 3)
    if mejores:
        lineas.append("- Especiales que más movieron: " +
                      "; ".join(f["titular"] for f in mejores) + ".")
    if not lineas:
        return ""
    return (f"Métricas al {foto.fecha} (últimos {VENTANA_DIAS} días):\n" + "\n".join(lineas))


def lamina(foto: Foto, out_path: Path, red: str = "i") -> Path | None:
    """Lámina de barras: alcance promedio por formato en una red (la de más datos)."""
    from bpt.viz.carrusel_card import render_lamina
    grupos = por_formato(foto.filas, red)
    if not grupos:
        for otra in "itx":
            grupos = por_formato(foto.filas, otra)
            if grupos:
                red = otra
                break
    if not grupos:
        return None
    barras = [{"etiqueta": NOMBRES_FORMATO.get(g["formato"], g["formato"]),
               "detalle": f"{g['piezas']} piezas · tasa {_pct(g['tasa'])}",
               "valor": max(g["alcance"], 1), "texto": _num(g["alcance"])}
              for g in grupos[:6]]
    return render_lamina({"tipo": "barras", "etiqueta": f"MBP  ·  MÉTRICAS  ·  {foto.fecha}",
                          "titulo": "¿QUÉ\nFUNCIONA?",
                          "subtitulo": f"Alcance promedio por pieza en {NOMBRES_RED[red]} "
                                       f"· últimos {VENTANA_DIAS} días",
                          "barras": barras,
                          "nota": "Alcance: cuentas únicas que lo vieron. Tasa: interacciones "
                                  "entre alcance."}, {},
                         out_path, fuente="Datos: Instagram, Threads y X", pagina="")


def ejecutar(registro: Path, salida: Path, clientes: dict, imagen: Path | None = None,
             ahora: datetime | None = None) -> tuple[Foto, str, str, Path | None]:
    """`salida` es la carpeta de la rama metricas (fotos/ y aprendizajes.md); la lámina va a
    `imagen`, fuera de la rama, para no versionar binarios cada semana."""
    ahora = ahora or datetime.now(timezone.utc)
    fecha = ahora.astimezone(TZ_VEN).date().isoformat()
    filas = recientes(leer_registro(registro), ahora=ahora)
    foto = tomar_foto(filas, clientes, fecha)
    salida = Path(salida)
    (salida / "fotos").mkdir(parents=True, exist_ok=True)
    (salida / "fotos" / f"{fecha}.json").write_text(
        json.dumps(foto.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    texto = informe(foto, ahora)
    apr = aprendizajes(foto)
    if apr:
        (salida / "aprendizajes.md").write_text(apr + "\n", encoding="utf-8")
    img = lamina(foto, Path(imagen)) if imagen else None
    return foto, texto, apr, img
