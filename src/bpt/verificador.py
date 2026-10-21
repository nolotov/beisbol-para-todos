"""Verificador de especiales: ninguna cifra sale sin respaldo.

El redactor diario ya tiene su validador (`bpt.redactor.validador`), que compara los textos
contra el `resumen.json`. Los especiales no tenían nada: las cifras se copiaban a mano o las
escribe el agente editor. Este módulo los revisa en cuatro capas:

1. Coherencia: cada cifra de los textos (caption, hilo y guion) tiene que estar en las
   láminas o en la evidencia. Las láminas son lo que el público ve: el texto no puede decir
   algo que la imagen no respalda.
2. Evidencia: si el especial trae evidencia (las respuestas de las consultas del agente
   editor, o notas con fuente escritas a mano), cada cifra de las láminas tiene que aparecer
   en ella. Sin evidencia la capa se salta y se avisa como verificación parcial.
3. Hechos: el bloque "verificar" del especial lista afirmaciones comprobables que se
   contrastan contra MLB Stats API (récord, marcador, línea de bateo o pitcheo, estadística
   de temporada de un jugador o un equipo). Si la fuente dice otra cosa, se marca.
4. Reglas de marca: lenguaje de apuestas, "el mejor" a secas, innings con decimal en el
   texto, línea al estilo gringo, más de 10 láminas.

Nada se bloquea aquí: el resultado deja la pieza "con alertas" y el editor decide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from bpt.redactor import validador as V

# Claves de las láminas que son diseño, no datos (no se verifican).
CLAVES_DISENO = {"tipo", "color", "tamano", "tamano_titulo", "ancho_cifra", "archivo",
                 "slug", "fecha", "fuente", "venezolano", "mejor", "equipo", "liga_id"}
MAX_LAMINAS = 10

# "el mejor promedio", "el mejor récord": la métrica ya es el criterio (en los especiales se
# compara por renglones; el redactor diario usa la regla estricta del validador).
_MEJOR_CON_METRICA = re.compile(
    r"\bel mejor\s+(promedio|r[ée]cord|diferencial|porcentaje|ops|ops\+|wrc\+|war|fip|era|"
    r"efectividad|whip|xwoba|woba|game score|marca|registro|n[úu]mero|puesto)\b", re.I)

# "8:03 p. m." -> la hora va entera en la evidencia ("8:03"), no como 8 y 3 sueltos.
_HORA = re.compile(r"\b\d{1,2}:\d{2}\b")


def _cifras_texto(texto: str) -> list[str]:
    """Cifras de un texto, con las horas como una sola cifra ("8:03")."""
    horas = _HORA.findall(texto)
    resto = _HORA.sub(" ", texto)
    return horas + V.numeros_en(resto)


def cifras_de(x, ignorar: set[str] = CLAVES_DISENO) -> set[str]:
    """Todas las cifras de una estructura (dicts, listas, textos), salvo claves de diseño."""
    out: set[str] = set()

    def walk(v, clave=None):
        if clave in ignorar or isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.add(V._norm(str(v)))
        elif isinstance(v, str):
            out.update(_cifras_texto(v))
        elif isinstance(v, dict):
            for k, w in v.items():
                walk(w, k)
        elif isinstance(v, (list, tuple)):
            for w in v:
                walk(w, clave)

    walk(x)
    return out


def permitidas(evidencia) -> set[str]:
    """Cifras que respalda la evidencia: las del validador más las horas enteras."""
    base = V.numeros_permitidos(evidencia)
    horas: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            horas.update(_HORA.findall(v))
        elif isinstance(v, dict):
            for w in v.values():
                walk(w)
        elif isinstance(v, (list, tuple)):
            for w in v:
                walk(w)

    walk(evidencia)
    return base | horas


def contenido_visible(especial: dict) -> dict:
    """Lo que se dibuja: portada, láminas, rosters o el bloque de la historia."""
    return {k: especial[k] for k in ("portada", "laminas", "rosters", "historia", "equipos",
                                     "titular") if k in especial}


def textos_de(especial: dict) -> dict[str, str]:
    t = especial.get("textos") or {}
    piezas = {"instagram": t.get("instagram", ""), "guion": t.get("guion", "")}
    for i, tuit in enumerate(t.get("hilo_x") or [], 1):
        piezas[f"tuit {i}"] = tuit
    return {k: v for k, v in piezas.items() if v}


# --- Capa 3: hechos contra MLB Stats API --------------------------------------------

Fuente = Callable[[str, dict], dict]


def _fuente_mlb() -> Fuente:
    from bpt.data.mlb_stats import _get
    return _get


class HechoError(ValueError):
    pass


def _record(h: dict, get: Fuente) -> tuple[str, str]:
    data = get("standings", {"leagueId": h.get("liga_id", "103,104"),
                             "season": h["temporada"], "standingsTypes": "regularSeason"})
    for div in data.get("records", []):
        for t in div.get("teamRecords", []):
            if t["team"]["id"] == int(h["equipo_id"]):
                return f"{t['wins']}-{t['losses']}", str(h["valor"])
    raise HechoError(f"el equipo {h['equipo_id']} no aparece en la tabla de {h['temporada']}")


def _box(h: dict, get: Fuente) -> dict:
    return get(f"game/{int(h['game_pk'])}/boxscore", {})


def _marcador(h: dict, get: Fuente) -> tuple[str, str]:
    box = _box(h, get)
    v = box["teams"]["away"]["teamStats"]["batting"]["runs"]
    l = box["teams"]["home"]["teamStats"]["batting"]["runs"]
    return f"{v}-{l}", f"{h['carreras_v']}-{h['carreras_l']}"


# Campos de una línea en el box score: nombre en el especial -> (grupo, campo de la API)
CAMPOS_LINEA = {"vb": ("batting", "atBats"), "h": ("batting", "hits"),
                "hr": ("batting", "homeRuns"), "ci": ("batting", "rbi"),
                "ca": ("batting", "runs"), "bb": ("batting", "baseOnBalls"),
                "ip": ("pitching", "inningsPitched"), "k": ("pitching", "strikeOuts"),
                "cl": ("pitching", "earnedRuns"), "hp": ("pitching", "hits"),
                "bbp": ("pitching", "baseOnBalls")}


def _linea(h: dict, get: Fuente) -> tuple[str, str]:
    box = _box(h, get)
    clave = f"ID{int(h['jugador_id'])}"
    for lado in ("away", "home"):
        p = box["teams"][lado]["players"].get(clave)
        if p:
            stats = p.get("stats", {})
            pedidos = [k for k in CAMPOS_LINEA if k in h]
            if not pedidos:
                raise HechoError("la línea no dice qué comprobar (vb, h, hr, ci, ip, k...)")
            real = " ".join(f"{k}={stats.get(CAMPOS_LINEA[k][0], {}).get(CAMPOS_LINEA[k][1])}"
                            for k in pedidos)
            dice = " ".join(f"{k}={h[k]}" for k in pedidos)
            return real, dice
    raise HechoError(f"el jugador {h['jugador_id']} no jugó el juego {h['game_pk']}")


def _stat(h: dict, get: Fuente) -> tuple[str, str]:
    """Estadística de temporada: {"tipo": "stat_jugador"|"stat_equipo", "id", "temporada",
    "grupo": "hitting"|"pitching", "campo": "homeRuns", "valor": 44}."""
    ruta = "people" if h["tipo"] == "stat_jugador" else "teams"
    params = {"stats": "season", "group": h.get("grupo", "hitting"),
              "season": h["temporada"], "gameType": h.get("game_type", "R")}
    if h.get("liga_id"):
        params["leagueId"] = h["liga_id"]
    data = get(f"{ruta}/{int(h['id'])}/stats", params)
    for bloque in data.get("stats", []):
        for s in bloque.get("splits", []):
            if h["campo"] in s.get("stat", {}):
                return str(s["stat"][h["campo"]]), str(h["valor"])
    raise HechoError(f"sin '{h['campo']}' para {ruta} {h['id']} en {h['temporada']}")


HECHOS = {"record": _record, "marcador": _marcador, "linea": _linea,
          "stat_jugador": _stat, "stat_equipo": _stat}


def _igual(real: str, dice: str) -> bool:
    try:
        return V._norm(real) == V._norm(dice)
    except ValueError:
        return real.strip().lower() == dice.strip().lower()


def comprobar_hechos(hechos: list[dict], get: Fuente | None = None) -> tuple[int, list[str]]:
    """Devuelve (comprobados bien, alertas). Un fallo de red es una alerta, no un error."""
    get = get or _fuente_mlb()
    ok, alertas = 0, []
    for i, h in enumerate(hechos, 1):
        nombre = h.get("nota") or f"hecho {i} ({h.get('tipo')})"
        f = HECHOS.get(h.get("tipo"))
        if f is None:
            alertas.append(f"{nombre}: tipo de hecho desconocido")
            continue
        try:
            real, dice = f(h, get)
        except (HechoError, KeyError, TypeError, ValueError) as e:
            alertas.append(f"{nombre}: no se pudo comprobar ({e})")
            continue
        except Exception as e:  # noqa: BLE001 - red caída, API cambiada
            alertas.append(f"{nombre}: la fuente no respondió ({type(e).__name__})")
            continue
        if _igual(real, dice):
            ok += 1
        else:
            alertas.append(f"{nombre}: el especial dice {dice} y MLB Stats API dice {real}")
    return ok, alertas


def hechos_implicitos(especial: dict) -> list[dict]:
    """Afirmaciones que se pueden comprobar sin declararlas: el marcador de una historia
    especial que trae su game_pk."""
    m = (especial.get("historia") or {}).get("marcador") or {}
    if m.get("game_pk") and "carreras_v" in m and "carreras_l" in m:
        return [{"tipo": "marcador", "game_pk": m["game_pk"], "carreras_v": m["carreras_v"],
                 "carreras_l": m["carreras_l"], "nota": "marcador de la historia"}]
    return []


# --- Todo junto ---------------------------------------------------------------------

@dataclass
class Verificacion:
    cifras_sin_respaldo: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    cifras_revisadas: int = 0
    consultas: int = 0          # piezas de evidencia
    hechos_ok: int = 0
    hechos_total: int = 0
    parcial: bool = False       # sin evidencia: solo coherencia, hechos y reglas

    @property
    def ok(self) -> bool:
        return not self.cifras_sin_respaldo and not self.alertas

    def resumen(self) -> str:
        """Una línea para Telegram y la consola."""
        partes = [f"{self.cifras_revisadas} cifras revisadas"]
        if self.parcial:
            partes.append("sin evidencia (verificación parcial)")
        else:
            partes.append(f"contra {self.consultas} consulta{'s' if self.consultas != 1 else ''}")
        if self.hechos_total:
            partes.append(f"{self.hechos_ok}/{self.hechos_total} hechos confirmados en "
                          "MLB Stats API")
        return "🔎 " + " · ".join(partes)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "cifras_sin_respaldo": self.cifras_sin_respaldo,
                "alertas": self.alertas, "cifras_revisadas": self.cifras_revisadas,
                "consultas": self.consultas, "hechos_ok": self.hechos_ok,
                "hechos_total": self.hechos_total, "parcial": self.parcial,
                "resumen": self.resumen()}


def reglas_marca(textos: dict[str, str]) -> list[str]:
    alertas = []
    for nombre, texto in textos.items():
        m = V.PROHIBIDAS.search(texto)
        if m:
            alertas.append(f"{nombre}: lenguaje de apuestas ('{m.group(0)}')")
        if V.MEJOR_A_SECAS.search(_MEJOR_CON_METRICA.sub(" ", texto)):
            alertas.append(f"{nombre}: dice 'el mejor' sin el criterio")
        m = V.INNING_DECIMAL.search(texto)
        if m:
            alertas.append(f"{nombre}: innings con decimal; van en palabras: '{m.group(0)}'")
        m = V.LINEA_GRINGA.search(texto)
        if m and int(m.group(1)) <= int(m.group(2)):
            alertas.append(f"{nombre}: línea al estilo gringo '{m.group(0)}'; va 'se fue de "
                           f"{m.group(2)}-{m.group(1)}'")
    return alertas


def verificar(especial: dict, evidencia: list | None = None, get: Fuente | None = None,
              hechos: bool = True) -> Verificacion:
    """Revisa un especial ya cargado. `evidencia` reemplaza a la que traiga el especial."""
    if evidencia is None:
        evidencia = especial.get("evidencia")
    v = Verificacion(parcial=not evidencia, consultas=len(evidencia or []))
    visible = contenido_visible(especial)
    en_laminas = cifras_de(visible)
    textos = textos_de(especial)
    en_textos: list[str] = []
    for t in textos.values():
        en_textos += [n for n in _cifras_texto(t) if n not in en_textos]
    v.cifras_revisadas = len(en_laminas | set(en_textos))

    respaldo = permitidas(evidencia) if evidencia else set()
    sin: list[str] = []
    # Capa 2: láminas contra la evidencia
    if evidencia:
        sin += sorted((n for n in en_laminas if n not in respaldo), key=_orden)
    # Capa 1: textos contra láminas (o evidencia)
    base_textos = (en_laminas | {n.split(".")[0] for n in en_laminas if "." in n}
                   | V.CONSTANTES | respaldo)
    sin += [n for n in en_textos if n not in base_textos and n not in sin]
    v.cifras_sin_respaldo = sin

    # Capa 3
    lista = list(especial.get("verificar") or []) + hechos_implicitos(especial)
    if hechos and lista:
        v.hechos_total = len(lista)
        v.hechos_ok, alertas = comprobar_hechos(lista, get)
        v.alertas += alertas

    # Capa 4
    v.alertas += reglas_marca(textos)
    n = len(especial.get("laminas") or [])
    if n > MAX_LAMINAS:
        v.alertas.append(f"{n} láminas: el carrusel de Instagram admite {MAX_LAMINAS}")
    return v


def _orden(n: str):
    try:
        return (0, float(n.replace(":", ".")))
    except ValueError:
        return (1, n)
