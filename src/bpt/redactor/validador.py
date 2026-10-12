"""Validador de los textos del redactor: ninguna cifra sin respaldo en los datos.

Revisa:
- Cifras: todo número escrito con dígitos debe aparecer en los datos del juego
  (o en las explicaciones de métricas que se le dieron al modelo). Una suma o un cálculo
  propio ("combinaron 15 hits") también se marca: lo revisa un humano.
- Palabras prohibidas: apuestas, picks, cuotas.
- "El mejor" a secas, sin decir con qué criterio.
- Largos: tuits, caption y palabras del guion.

Limitación conocida: los números escritos con letras ("dos jonrones") no se detectan;
por eso el prompt exige dígitos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Números que aparecen en las explicaciones de métricas del prompt (Game Score parte de 40,
# 60 bueno, 70 dominante, 50 promedio en la tarjeta) y la base del béisbol (9 entradas).
CONSTANTES = {"40", "50", "60", "70", "9"}

PROHIBIDAS = re.compile(r"\b(apuestas?|apost\w*|picks?|cuotas?|momios?|parlay|lock)\b", re.I)
MEJOR_A_SECAS = re.compile(r"\bel mejor\b(?![^.\n]{0,40}\b(por|con más|según)\b)", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_RUIDO = re.compile(r"[#@]\w+|\[L[ÁA]MINA \d+\]", re.I)

# Sin jugada por jugada no se puede afirmar qué carrera o batazo decidió el juego
CAUSAL = re.compile(r"(la diferencia la hizo|decidi[óo] el juego|defini[óo] el juego|"
                    r"carrera de la (victoria|ventaja)|remontad|dej[óo] en el terreno|"
                    r"walk-?off|batazo decisivo|jonr[óo]n decisivo)", re.I)
# "2-4 con 2 hits": redundante
REDUNDANTE = re.compile(r"\b\d+-\d+,? con \d+ hits?\b", re.I)
# Innings con decimal en el texto (".0" o ".1"/".2"): deben ir en palabras
INNING_DECIMAL = re.compile(r"\b\d+\.[012] (entradas?|innings?|IL)\b", re.I)

LIMITES = {"tuit": 280, "instagram": 1200, "guion_min": 75, "guion_max": 110}


def _norm(n: str) -> str:
    n = n.replace(",", ".")
    if "." in n:
        entero, frac = n.split(".", 1)
        n = f"{int(entero)}.{frac}"
    else:
        n = str(int(n))
    return n


def numeros_permitidos(datos) -> set[str]:
    """Todas las cifras presentes en los datos (recorre dicts, listas y textos)."""
    out: set[str] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            out.add(_norm(str(x)))
        elif isinstance(x, str):
            out.update(_norm(m) for m in _NUM.findall(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(datos)
    # Con "4.2" en los datos, también vale decir "4" (4 entradas y 2 outs)
    out |= {n.split(".")[0] for n in out if "." in n}
    return out | CONSTANTES


def numeros_en(texto: str) -> list[str]:
    limpio = _RUIDO.sub(" ", texto)
    # "3-2" y "2-1" son marcadores: se validan los dos números por separado (findall ya lo hace)
    # Un punto final de oración no es decimal: "ganó 3." -> "3"
    return [_norm(m.rstrip(".,")) for m in _NUM.findall(limpio)]


@dataclass
class Validacion:
    cifras_sin_respaldo: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.cifras_sin_respaldo and not self.alertas

    def to_dict(self) -> dict:
        return {"ok": self.ok, "cifras_sin_respaldo": self.cifras_sin_respaldo,
                "alertas": self.alertas}


def validar(textos: dict, datos) -> Validacion:
    permitidos = numeros_permitidos(datos)
    v = Validacion()
    piezas = {"instagram": textos.get("instagram", ""), "guion": textos.get("guion", "")}
    for i, t in enumerate(textos.get("hilo_x", []), 1):
        piezas[f"tuit {i}"] = t

    sin_respaldo: list[str] = []
    for nombre, texto in piezas.items():
        for n in numeros_en(texto):
            if n not in permitidos and n not in sin_respaldo:
                sin_respaldo.append(n)
        if PROHIBIDAS.search(texto):
            v.alertas.append(f"{nombre}: lenguaje de apuestas ('{PROHIBIDAS.search(texto).group(0)}')")
        for patron, msg in [(CAUSAL, "afirma qué decidió el juego (no hay jugada por jugada)"),
                            (REDUNDANTE, "línea redundante ('de 4-2' ya dice los hits)"),
                            (INNING_DECIMAL, "innings con decimal; van en palabras")]:
            m = patron.search(texto)
            if m:
                v.alertas.append(f"{nombre}: {msg}: '{m.group(0)}'")
        if MEJOR_A_SECAS.search(texto):
            v.alertas.append(f"{nombre}: dice 'el mejor' sin el criterio")
        if nombre.startswith("tuit") and len(texto) > LIMITES["tuit"]:
            v.alertas.append(f"{nombre}: {len(texto)} caracteres (máx. {LIMITES['tuit']})")

    v.cifras_sin_respaldo = sin_respaldo
    n_tuits = len(textos.get("hilo_x", []))
    if not 3 <= n_tuits <= 5:
        v.alertas.append(f"hilo_x: {n_tuits} tuits (deben ser entre 3 y 5)")
    if len(piezas["instagram"]) > LIMITES["instagram"]:
        v.alertas.append(f"instagram: {len(piezas['instagram'])} caracteres "
                         f"(máx. {LIMITES['instagram']})")
    palabras = len(_RUIDO.sub(" ", piezas["guion"]).split())
    if not LIMITES["guion_min"] <= palabras <= LIMITES["guion_max"]:
        v.alertas.append(f"guion: {palabras} palabras (entre {LIMITES['guion_min']} y "
                         f"{LIMITES['guion_max']} para 30-45 s)")
    if "[LÁMINA 2]" not in piezas["guion"].upper().replace("LAMINA", "LÁMINA"):
        v.alertas.append("guion: falta la marca [LÁMINA 2]")
    return v
