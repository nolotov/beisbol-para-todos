"""Herramientas de datos del agente editor.

Cada herramienta es una consulta a una fuente real (MLB Stats API, que también cubre la LVBP,
y Baseball Savant) o un cálculo. Todo lo que devuelven queda en la EVIDENCIA: la lista que
el verificador usa para comprobar que cada cifra del especial salió de una consulta y no de
la memoria del modelo. Por eso también hay una calculadora: un porcentaje o una diferencia
que el agente calcula con ella queda respaldado; uno que calcula "de cabeza", no.

Las respuestas se recortan para no llenar el contexto del modelo (y la factura).
"""
from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from bpt.data import mlb_stats as M

Fuente = Callable[[str, dict], dict]
TZ_VEN = ZoneInfo("America/Caracas")
MAX_CARACTERES = 14000           # por respuesta de herramienta
LIGAS = {"mlb": {"sportId": 1}, "lvbp": {"sportId": M.WINTER_SPORT_ID,
                                         "leagueId": M.LVBP_LEAGUE_ID}}
TIPOS_JUEGO = ["R", "F", "D", "L", "W"]


class HerramientaError(ValueError):
    """Error que el modelo puede corregir (parámetro malo, jugador no encontrado)."""


def hora_ven(inicio_utc: str) -> str:
    """'2026-10-24T00:03:00Z' -> '8:03 p. m.' (hora de Venezuela)."""
    if not inicio_utc:
        return ""
    t = datetime.fromisoformat(inicio_utc.replace("Z", "+00:00")).astimezone(TZ_VEN)
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'a. m.' if t.hour < 12 else 'p. m.'}"


def _liga(liga: str) -> dict:
    if liga not in LIGAS:
        raise HerramientaError("liga debe ser 'mlb' o 'lvbp'")
    return dict(LIGAS[liga])


def _schema(props: dict, requeridos: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": requeridos,
            "additionalProperties": False}


_LIGA = {"type": "string", "enum": ["mlb", "lvbp"],
         "description": "mlb o lvbp (la LVBP usa la temporada del año en que arranca: 2026 = 2026-27)"}
_TEMP = {"type": "integer", "description": "Temporada, p. ej. 2026"}
_GRUPO = {"type": "string", "enum": ["hitting", "pitching"]}
_TIPO_JUEGO = {"type": "string", "enum": TIPOS_JUEGO,
               "description": "R temporada regular, F comodín, D divisional, L campeonato, W Serie Mundial"}


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    esquema: dict
    funcion: Callable[..., object]
    estricta: bool = True

    def definicion(self) -> dict:
        d = {"name": self.nombre, "description": self.descripcion,
             "input_schema": self.esquema}
        if self.estricta:
            d["strict"] = True
        return d


@dataclass
class Caja:
    """Las herramientas con su fuente de datos y la evidencia que van dejando."""
    get: Fuente | None = None
    percentiles: Callable | None = None
    evidencia: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.get = self.get or M._get
        self.herramientas = {h.nombre: h for h in self._definir()}

    # --- API para el agente ---------------------------------------------------------

    def definiciones(self) -> list[dict]:
        return [h.definicion() for h in self.herramientas.values()]

    def ejecutar(self, nombre: str, entrada: dict) -> tuple[str, bool]:
        """Devuelve (texto para el modelo, es_error). Solo lo que salió bien es evidencia."""
        h = self.herramientas.get(nombre)
        if h is None:
            return f"No existe la herramienta '{nombre}'", True
        try:
            resultado = h.funcion(**entrada)
        except HerramientaError as e:
            return str(e), True
        except TypeError as e:
            return f"Parámetros inválidos: {e}", True
        except Exception as e:  # noqa: BLE001 - red, API cambiada
            return f"La fuente falló ({type(e).__name__}): {str(e)[:200]}", True
        self.evidencia.append({"herramienta": nombre, "entrada": entrada,
                               "resultado": resultado})
        texto = json.dumps(resultado, ensure_ascii=False, separators=(",", ":"))
        if len(texto) > MAX_CARACTERES:
            texto = (texto[:MAX_CARACTERES] + ' …[recortado: pide menos datos o filtra]')
        return texto, False

    # --- Herramientas ------------------------------------------------------------------

    def _definir(self) -> list[Herramienta]:
        return [
            Herramienta(
                "calendario",
                "Juegos de un rango de fechas (máx. 10 días) con marcador, estado, serie, "
                "récord de cada equipo, pitchers de la decisión y hora de Venezuela. Sirve "
                "para resultados, para lo que viene y para el estado de una serie.",
                _schema({"liga": _LIGA,
                         "desde": {"type": "string", "description": "AAAA-MM-DD"},
                         "hasta": {"type": "string", "description": "AAAA-MM-DD"}},
                        ["liga", "desde", "hasta"]),
                self.calendario),
            Herramienta(
                "box_score",
                "Box score de un juego: línea de cada bateador y pitcher, jonrones, y las "
                "figuras por criterio (Game Score para pitchers, bases ganadas para bateadores).",
                _schema({"game_pk": {"type": "integer"}}, ["game_pk"]),
                self.box_score),
            Herramienta(
                "tabla_posiciones",
                "Tabla de posiciones de la temporada regular: ganados, perdidos, porcentaje, "
                "juegos detrás, carreras anotadas y permitidas, diferencial y racha.",
                _schema({"liga": _LIGA, "temporada": _TEMP}, ["liga", "temporada"]),
                self.tabla_posiciones),
            Herramienta(
                "ranking_equipos",
                "Estadísticas de temporada de TODOS los equipos de la liga con el puesto de "
                "cada uno en los campos pedidos (1 = el más alto; para efectividad, WHIP y "
                "similares, 1 = el más bajo). Campos de la API: avg, obp, slg, ops, homeRuns, "
                "runs, strikeOuts, stolenBases, era, whip, saves...",
                _schema({"liga": _LIGA, "temporada": _TEMP, "grupo": _GRUPO,
                         "campos": {"type": "array", "items": {"type": "string"}},
                         "tipo_juego": _TIPO_JUEGO},
                        ["liga", "temporada", "grupo", "campos", "tipo_juego"]),
                self.ranking_equipos),
            Herramienta(
                "buscar_jugador",
                "Busca un jugador por nombre: id, país de nacimiento, posición, equipo actual "
                "y edad. Necesario antes de stats_jugador.",
                _schema({"nombre": {"type": "string"}}, ["nombre"]),
                self.buscar_jugador),
            Herramienta(
                "stats_jugador",
                "Estadísticas de temporada de un jugador (MLB o LVBP), de temporada regular o "
                "de una fase de postemporada.",
                _schema({"jugador_id": {"type": "integer"}, "liga": _LIGA, "temporada": _TEMP,
                         "grupo": _GRUPO, "tipo_juego": _TIPO_JUEGO},
                        ["jugador_id", "liga", "temporada", "grupo", "tipo_juego"]),
                self.stats_jugador),
            Herramienta(
                "lideres",
                "Los 10 primeros de una categoría (homeRuns, battingAverage, onBasePlusSlugging, "
                "runsBattedIn, stolenBases, earnedRunAverage, strikeouts, wins, saves, whip...).",
                _schema({"liga": _LIGA, "temporada": _TEMP, "categoria": {"type": "string"},
                         "grupo": _GRUPO, "tipo_juego": _TIPO_JUEGO},
                        ["liga", "temporada", "categoria", "grupo", "tipo_juego"]),
                self.lideres),
            Herramienta(
                "percentiles_statcast",
                "Percentiles de Statcast (Baseball Savant, solo MLB) de un jugador: velocidad "
                "de salida, xwOBA, barriles, chase, whiff, etc. 99 = élite, 50 = promedio.",
                _schema({"nombre": {"type": "string"},
                         "tipo": {"type": "string", "enum": ["batter", "pitcher"]},
                         "temporada": _TEMP}, ["nombre", "tipo", "temporada"]),
                self.percentiles_statcast),
            Herramienta(
                "calcular",
                "Calculadora. TODA cifra derivada (porcentaje, diferencia, suma, promedio) se "
                "calcula aquí; si la calculas de cabeza, el verificador la marca sin respaldo. "
                "Operaciones: + - * / ** ( ) round(x, n).",
                _schema({"expresion": {"type": "string", "description": "p. ej. round(264/422*100)"},
                         "que_es": {"type": "string", "description": "qué representa el resultado"}},
                        ["expresion", "que_es"]),
                self.calcular),
        ]

    def calendario(self, liga: str, desde: str, hasta: str) -> list[dict]:
        d0, d1 = (datetime.fromisoformat(x).date() for x in (desde, hasta))
        if not 0 <= (d1 - d0).days <= 10:
            raise HerramientaError("el rango va de 0 a 10 días (desde <= hasta)")
        params = _liga(liga) | {"startDate": desde, "endDate": hasta,
                                "hydrate": M.HYDRATE + ",probablePitcher"}
        if liga == "mlb":
            params["gameType"] = ",".join(TIPOS_JUEGO)
        data = self.get("schedule", params)
        salida = []
        for dia in data.get("dates", []):
            for g in dia.get("games", []):
                j = M.parse_game(g)
                fila = {"game_pk": j.game_pk, "fecha": j.fecha, "estado": j.estado,
                        "fase": j.serie_es or j.tipo, "hora_ven": hora_ven(j.inicio_utc),
                        "estadio": j.estadio,
                        "visitante": {"nombre": M.nombre_es(j.visitante.nombre),
                                      "id": j.visitante.id, "carreras": j.visitante.carreras,
                                      "record": j.visitante.record},
                        "local": {"nombre": M.nombre_es(j.local.nombre), "id": j.local.id,
                                  "carreras": j.local.carreras, "record": j.local.record}}
                if j.juegos_en_serie > 1:
                    fila["juego"] = f"{j.juego_n} de {j.juegos_en_serie}"
                if j.final:
                    fila |= {"ganador_pitcher": j.ganador_pitcher,
                             "perdedor_pitcher": j.perdedor_pitcher,
                             "salvado": j.salvado_pitcher, "entradas": len(j.entradas)}
                else:
                    prob = {lado: ((g["teams"][lado].get("probablePitcher") or {})
                                   .get("fullName")) for lado in ("away", "home")}
                    if any(prob.values()):
                        fila["abridores_probables"] = {"visitante": prob["away"],
                                                       "local": prob["home"]}
                salida.append(fila)
        return salida

    def box_score(self, game_pk: int) -> dict:
        from bpt.data import mlb_box as B
        box = self.get(f"game/{int(game_pk)}/boxscore", {})
        out = {"game_pk": game_pk}
        for lado, clave in (("away", "visitante"), ("home", "local")):
            t = box["teams"][lado]
            bats = [b for b in B.bateo(box, lado) if b.ap]
            pits = B.pitcheo(box, lado)
            out[clave] = {
                "equipo": M.nombre_es(t.get("team", {}).get("name", "?")),
                "carreras": (t.get("teamStats", {}).get("batting", {}) or {}).get("runs"),
                "bateo": [{"nombre": b.nombre, "id": b.id, "linea": b.texto(), "vb": b.vb,
                           "h": b.h, "hr": b.hr, "ci": b.ci, "bases_ganadas": b.bases_ganadas}
                          for b in bats],
                "pitcheo": [{"nombre": p.nombre, "id": p.id, "linea": p.texto(),
                             "game_score": p.game_score, "abridor": p.abridor,
                             "lanzamientos": p.lanzamientos} for p in pits]}
        f = B.figuras(box).to_dict()
        out["figuras"] = {"jonrones": f["jonrones"],
                          "mejor_bateo": {k: v["nombre"] + ": " + v["linea"]
                                          for k, v in f["mejor_bateo"].items()},
                          "mejor_pitcheo": {k: f"{v['nombre']}: {v['linea']} (Game Score "
                                               f"{v['game_score']})"
                                            for k, v in f["mejor_pitcheo"].items()},
                          "criterios": f["criterios"]}
        return out

    def tabla_posiciones(self, liga: str, temporada: int) -> list[dict]:
        params = {"season": temporada, "standingsTypes": "regularSeason",
                  "leagueId": "103,104" if liga == "mlb" else M.LVBP_LEAGUE_ID}
        _liga(liga)
        data = self.get("standings", params)
        filas = []
        for div in data.get("records", []):
            for t in div.get("teamRecords", []):
                filas.append({
                    "equipo": M.LVBP_NOMBRES.get(t["team"]["id"],
                                                 M.nombre_es(t["team"].get("name", "?"))),
                    "id": t["team"]["id"], "division": (div.get("division") or {}).get("id"),
                    "g": t.get("wins"), "p": t.get("losses"),
                    "pct": t.get("winningPercentage"), "jd": t.get("gamesBack"),
                    "ca": t.get("runsScored"), "cp": t.get("runsAllowed"),
                    "diferencial": t.get("runDifferential"),
                    "racha": (t.get("streak") or {}).get("streakCode")})
        return sorted(filas, key=lambda f: (-(f["g"] or 0), f["p"] or 0))

    def ranking_equipos(self, liga: str, temporada: int, grupo: str, campos: list[str],
                        tipo_juego: str = "R") -> dict:
        if not campos or len(campos) > 8:
            raise HerramientaError("pide entre 1 y 8 campos")
        params = {"season": temporada, "group": grupo, "stats": "season",
                  "gameType": tipo_juego}
        lg = _liga(liga)
        params["sportIds"] = lg["sportId"]
        if "leagueId" in lg:
            params["leagueIds"] = lg["leagueId"]
        data = self.get("teams/stats", params)
        filas = []
        for bloque in data.get("stats", []):
            for s in bloque.get("splits", []):
                fila = {"equipo": M.LVBP_NOMBRES.get(s["team"]["id"],
                                                     M.nombre_es(s["team"].get("name", "?"))),
                        "id": s["team"]["id"]}
                fila |= {c: s["stat"].get(c) for c in campos}
                filas.append(fila)
        if not filas:
            raise HerramientaError("la API no devolvió equipos para esa consulta")
        bajos = {"era", "whip", "hits", "runs", "earnedRuns", "baseOnBalls", "homeRuns",
                 "avg", "obp", "slg", "ops"} if grupo == "pitching" else {"strikeOuts",
                                                                           "groundIntoDoublePlay",
                                                                           "caughtStealing"}
        for c in campos:
            def valor(f, c=c):
                try:
                    return float(str(f[c]).replace(",", ""))
                except (TypeError, ValueError):
                    return None
            orden = sorted((f for f in filas if valor(f) is not None),
                           key=lambda f: valor(f), reverse=c not in bajos)
            for i, f in enumerate(orden, 1):
                f[f"puesto_{c}"] = i
        return {"equipos": len(filas), "nota": "puesto 1 = el mejor en ese renglón",
                "filas": filas}

    def buscar_jugador(self, nombre: str) -> list[dict]:
        data = self.get("people/search", {"names": nombre, "hydrate": "currentTeam"})
        gente = data.get("people", [])[:5]
        if not gente:
            raise HerramientaError(f"no encontré a '{nombre}': prueba sin tildes o con el "
                                   "nombre completo")
        return [{"id": p["id"], "nombre": p.get("fullName"),
                 "pais": p.get("birthCountry"), "posicion": (p.get("primaryPosition") or {})
                 .get("abbreviation"), "equipo": (p.get("currentTeam") or {}).get("name"),
                 "edad": p.get("currentAge"), "activo": p.get("active")} for p in gente]

    def stats_jugador(self, jugador_id: int, liga: str, temporada: int, grupo: str,
                      tipo_juego: str = "R") -> dict:
        params = {"stats": "season", "group": grupo, "season": temporada,
                  "gameType": tipo_juego} | _liga(liga)
        data = self.get(f"people/{int(jugador_id)}/stats", params)
        splits = [s for b in data.get("stats", []) for s in b.get("splits", [])]
        if not splits:
            raise HerramientaError("sin estadísticas para esa combinación (¿liga, fase o "
                                   "temporada?)")
        return {"jugador_id": jugador_id, "temporada": temporada, "grupo": grupo,
                "tipo_juego": tipo_juego,
                "por_equipo": [{"equipo": (s.get("team") or {}).get("name"),
                                **s.get("stat", {})} for s in splits]}

    def lideres(self, liga: str, temporada: int, categoria: str, grupo: str,
                tipo_juego: str = "R") -> list[dict]:
        params = {"leaderCategories": categoria, "season": temporada, "statGroup": grupo,
                  "gameTypes": tipo_juego, "limit": 10} | _liga(liga)
        data = self.get("stats/leaders", params)
        bloques = data.get("leagueLeaders", [])
        if not bloques or not bloques[0].get("leaders"):
            raise HerramientaError(f"sin líderes para '{categoria}' (revisa el nombre de la "
                                   "categoría)")
        return [{"puesto": l.get("rank"), "nombre": (l.get("person") or {}).get("fullName"),
                 "id": (l.get("person") or {}).get("id"),
                 "equipo": (l.get("team") or {}).get("name"), "valor": l.get("value")}
                for l in bloques[0]["leaders"]]

    def percentiles_statcast(self, nombre: str, tipo: str, temporada: int) -> dict:
        from bpt.data import savant
        cargar = self.percentiles or savant.load_percentiles
        df = cargar(tipo, temporada)
        try:
            fila = savant.find_player(df, nombre)
        except (KeyError, ValueError, LookupError) as e:
            raise HerramientaError(str(e)) from None
        return {"jugador": savant.display_name(fila["player_name"]), "temporada": temporada,
                "percentiles": {k: int(v) for k, v in savant.player_metrics(fila, tipo)}}

    def calcular(self, expresion: str, que_es: str) -> dict:
        valor = _evaluar(expresion)
        if isinstance(valor, float) and valor.is_integer():
            valor = int(valor)
        return {"que_es": que_es, "expresion": expresion, "resultado": valor}


# --- Calculadora segura (sin eval) ---------------------------------------------------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.UAdd: operator.pos, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}


def _evaluar(expr: str):
    if len(expr) > 200:
        raise HerramientaError("expresión demasiado larga")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 10:
                raise HerramientaError("exponente demasiado grande")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in ("round", "abs", "min", "max") and not n.keywords):
            return {"round": round, "abs": abs, "min": min, "max": max}[n.func.id](
                *[ev(a) for a in n.args])
        raise HerramientaError("solo números, + - * / ** ( ) y round/abs/min/max")

    try:
        return ev(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        raise HerramientaError("división entre cero") from None
    except SyntaxError:
        raise HerramientaError("expresión inválida") from None
