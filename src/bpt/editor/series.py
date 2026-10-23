"""Probabilidades de una serie de postemporada (al mejor de 7, formato 2-3-2).

Método, a propósito sencillo y explicable en una lámina:
  1. Fuerza de cada equipo = porcentaje de victorias pitagórico de la temporada regular
     (carreras anotadas^1.83 / (anotadas^1.83 + permitidas^1.83)): lo que "merecía" ganar
     por sus carreras, más estable que el récord.
  2. Probabilidad de ganar UN juego en campo neutral = log5 (Bill James) entre las dos
     fuerzas.
  3. Ventaja de local: el local de MLB gana ~54 % de los juegos; se aplica por razón de
     momios (odds ratio) a cada juego según dónde se juegue.
  4. Se recorren todos los caminos posibles de la serie (2-3-2: juegos 1, 2, 6 y 7 en casa
     de quien tiene la ventaja) y se suman: quién gana, en cuántos juegos y cada resultado
     exacto. Admite una serie ya empezada (juegos ganados por cada uno).
"""
from __future__ import annotations

from functools import lru_cache

EXPONENTE = 1.83
VENTAJA_LOCAL = 0.54
PATRON_2_3_2 = ("A", "A", "B", "B", "B", "A", "A")   # quién es local en cada juego


def pitagorico(anotadas: float, permitidas: float) -> float:
    if anotadas <= 0 or permitidas <= 0:
        raise ValueError("las carreras deben ser mayores que cero")
    a, p = anotadas ** EXPONENTE, permitidas ** EXPONENTE
    return a / (a + p)


def log5(pa: float, pb: float) -> float:
    """Probabilidad de que A le gane un juego a B en campo neutral."""
    return (pa - pa * pb) / (pa + pb - 2 * pa * pb)


def con_localia(p: float, local: bool, h: float = VENTAJA_LOCAL) -> float:
    """Ajusta la probabilidad neutral de A por jugar en casa (local=True) o de visita."""
    f = h if local else 1 - h
    return p * f / (p * f + (1 - p) * (1 - f))


def probabilidades(ca_a: float, cp_a: float, ca_b: float, cp_b: float, ganados_a: int = 0,
                   ganados_b: int = 0, ventaja_local: float = VENTAJA_LOCAL) -> dict:
    """A es el equipo con la ventaja de local (juegos 1, 2, 6 y 7 en su casa)."""
    if not (0 <= ganados_a <= 3 and 0 <= ganados_b <= 3):
        raise ValueError("los juegos ganados van de 0 a 3 (si alguien tiene 4, ya terminó)")
    pa, pb = pitagorico(ca_a, cp_a), pitagorico(ca_b, cp_b)
    neutral = log5(pa, pb)
    p_juego = [con_localia(neutral, quien == "A", ventaja_local) for quien in PATRON_2_3_2]

    @lru_cache(maxsize=None)
    def caminos(a: int, b: int) -> tuple:
        """Probabilidad de cada final (ganador, juegos) desde el marcador a-b."""
        if a == 4:
            return ((("A", a + b), 1.0),)
        if b == 4:
            return ((("B", a + b), 1.0),)
        p = p_juego[a + b]
        out: dict = {}
        for final, q in caminos(a + 1, b):
            out[final] = out.get(final, 0) + p * q
        for final, q in caminos(a, b + 1):
            out[final] = out.get(final, 0) + (1 - p) * q
        return tuple(out.items())

    finales = dict(caminos(ganados_a, ganados_b))
    gana = {e: sum(q for (g, _), q in finales.items() if g == e) for e in ("A", "B")}
    juegos = {str(n): sum(q for (_, j), q in finales.items() if j == n) for n in range(4, 8)}
    exactos = {f"{g} en {j}": q for (g, j), q in sorted(finales.items())}
    (ganador, n_juegos), p_resultado = max(finales.items(), key=lambda kv: kv[1])
    dura, p_dura = max(juegos.items(), key=lambda kv: kv[1])
    pct = lambda x: round(100 * x, 1)  # noqa: E731
    ent = lambda x: round(100 * x)     # noqa: E731
    return {
        "metodo": "pitagórica (exp. 1.83) + log5 + ventaja de local por juego, formato 2-3-2",
        "pitagorico": {"A": round(pa, 3), "B": round(pb, 3)},
        "prob_juego_neutral_A": pct(neutral),
        "prob_juego_A": {"en_casa": pct(p_juego[0]), "de_visita": pct(p_juego[2])},
        "prob_gana_serie": {e: pct(q) for e, q in gana.items()},
        "prob_por_juegos": {n: pct(q) for n, q in juegos.items()},
        "prob_resultado_exacto": {k: pct(q) for k, q in exactos.items()},
        "resultado_mas_probable": {"resultado": f"{ganador} en {n_juegos}",
                                   "prob": pct(p_resultado)},
        "duracion_mas_probable": {"juegos": int(dura), "prob": pct(p_dura)},
        "desde_marcador": f"{ganados_a}-{ganados_b}",
        # Para las láminas: porcentajes redondeados y "X de cada 10" (en palabras)
        "redondeado": {
            "gana_serie": {e: ent(q) for e, q in gana.items()},
            "por_juegos": {n: ent(q) for n, q in juegos.items()},
            "resultado_exacto": {k: ent(q) for k, q in exactos.items()},
            "de_cada_10": {"gana_A": round(gana["A"] * 10), "gana_B": round(gana["B"] * 10),
                           "dura_mas_probable": round(p_dura * 10)},
        },
    }
