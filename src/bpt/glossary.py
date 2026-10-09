"""Glosario de métricas: sigla, nombre en español (pelota venezolana), pista corta y explicación.

Las tarjetas se pueden etiquetar en tres modos:
- "siglas":  ERA, OBP, wOBA...                     (compacto)
- "espanol": Efectividad, Embasado, wOBA...        (para el fanático tradicional)
- "mixto":   nombre en español y debajo la sigla; si la métrica no tiene traducción
             usual (wOBA, FIP), debajo va una pista de qué mide.       (por defecto)

La `explicacion` es una frase para captions, guiones y el agente redactor.
"""
from __future__ import annotations

from dataclasses import dataclass

MODES = ("mixto", "espanol", "siglas")


@dataclass(frozen=True)
class Metric:
    sigla: str
    nombre: str
    pista: str
    explicacion: str


M = Metric
GLOSARIO: dict[str, Metric] = {
    # --- Bateo tradicional ---
    "avg": M("AVG", "Promedio", "hits por turno",
             "Hits divididos entre turnos al bate. El número de toda la vida."),
    "obp": M("OBP", "Embasado", "veces que llega a base",
             "Qué tan seguido se embasa: hits, boletos y pelotazos."),
    "slg": M("SLG", "Slugging", "bases por turno",
             "Bases totales por turno: premia los extrabases."),
    "ops": M("OPS", "OPS", "embasado + slugging",
             "Embasado más slugging: resume en un número embasarse y pegar duro."),
    "hr": M("HR", "Jonrones", "cuadrangulares", "Cuadrangulares conectados."),
    "sb": M("BR", "Bases robadas", "robos", "Bases robadas."),
    "bb_pct": M("BB%", "% de boletos", "boletos por turno",
                "Porcentaje de apariciones que terminan en base por bolas."),
    "k_pct": M("K%", "% de ponches", "ponches por turno",
               "Porcentaje de apariciones que terminan en ponche."),
    # --- Bateo sabermétrico ---
    "woba": M("wOBA", "wOBA", "valor de cada turno",
              "Como el OBP, pero le da a cada forma de llegar a base su valor real: "
              "un doble vale más que un boleto."),
    "iso": M("ISO", "Poder aislado", "solo extrabases",
             "Slugging menos promedio: mide el poder puro, sin contar sencillos."),
    "ld_pct": M("LD%", "% de líneas", "batazos de línea",
                "Porcentaje de batazos que salen en línea, los que más se convierten en hit."),
    "hr_pa": M("HR/AP", "Jonrones por turno", "frecuencia de jonrón",
               "Cada cuántas apariciones conecta jonrón."),
    # --- Pitcheo tradicional ---
    "era": M("ERA", "Efectividad", "carreras limpias x 9",
             "Carreras limpias permitidas por cada 9 innings."),
    "whip": M("WHIP", "WHIP", "embasados por inning",
              "Hits más boletos permitidos por inning lanzado."),
    "avg_opp": M("AVG opp", "Promedio en contra", "le batean para",
                 "Promedio de bateo que le hacen los rivales."),
    "sv": M("SV", "Salvados", "juegos salvados", "Juegos salvados."),
    "hr9": M("HR/9", "Jonrones x 9 IP", "jonrones permitidos",
             "Jonrones permitidos por cada 9 innings."),
    "k_bb": M("K/BB", "Ponches por boleto", "control y dominio",
              "Cuántos ponches propina por cada boleto que regala."),
    "strike_pct": M("Strike%", "% de strikes", "lanzamientos en strike",
                    "Porcentaje de lanzamientos que terminan en strike."),
    # --- Pitcheo sabermétrico ---
    "fip": M("FIP", "FIP", "efectividad sin la defensa",
             "Efectividad calculada solo con lo que controla el pitcher: ponches, boletos "
             "y jonrones. Le quita la suerte y la defensa."),
    # --- Statcast ---
    "xera": M("xERA", "Efectividad esperada", "según la calidad de contacto",
              "La efectividad que 'merecía' según qué tan duro y en qué ángulo le batearon."),
    "xwoba": M("xwOBA", "wOBA esperado", "según la calidad de contacto",
               "El wOBA que corresponde a la calidad de contacto, sin la suerte ni la defensa."),
    "xwoba_opp": M("xwOBA opp", "wOBA esperado en contra", "contacto que permite",
                   "El wOBA esperado de los bateadores que enfrenta."),
    "xba": M("xBA", "Promedio esperado", "según el contacto",
             "El promedio que corresponde a la calidad de sus batazos."),
    "xslg": M("xSLG", "Slugging esperado", "según el contacto",
              "El slugging que corresponde a la calidad de sus batazos."),
    "fb_velo": M("Velo", "Velocidad de la recta", "millas por hora",
                 "Velocidad promedio de la recta."),
    "fb_spin": M("Spin", "Giro de la recta", "revoluciones por minuto",
                 "Revoluciones por minuto de la recta: más giro, más 'sube'."),
    "whiff_pct": M("Whiff%", "% de abanicados", "swings sin contacto",
                   "Porcentaje de swings en los que el bateador no toca la pelota."),
    "chase_pct": M("Chase%", "Persecución", "swings a bolas malas",
                   "Porcentaje de swings a lanzamientos fuera de la zona."),
    "ev": M("EV", "Velocidad de salida", "qué tan duro batea",
            "Velocidad promedio de la pelota al salir del bate."),
    "ev_opp": M("EV opp", "Velocidad de salida en contra", "qué tan duro le batean",
                "Velocidad promedio de los batazos que permite."),
    "hardhit_pct": M("HardHit%", "% de batazos duros", "95+ mph",
                     "Porcentaje de batazos a 95 mph o más."),
    "hardhit_opp": M("HardHit% opp", "Batazos duros en contra", "95+ mph permitidos",
                     "Porcentaje de batazos a 95 mph o más que permite."),
    "barrel_pct": M("Barrel%", "% de barriles", "contacto perfecto",
                    "Porcentaje de batazos con la combinación ideal de velocidad y ángulo."),
    "barrel_opp": M("Barrel% opp", "Barriles en contra", "contacto perfecto permitido",
                    "Porcentaje de barriles que le conectan."),
    "bat_speed": M("Bat Speed", "Velocidad de bate", "millas por hora",
                   "Velocidad del bate en el swing."),
    "sprint_speed": M("Sprint", "Velocidad en bases", "pies por segundo",
                      "Velocidad máxima corriendo entre bases."),
}


def get(key: str) -> Metric:
    try:
        return GLOSARIO[key]
    except KeyError:
        raise KeyError(f"Métrica '{key}' no está en el glosario") from None


def label(key: str, mode: str = "mixto") -> tuple[str, str | None]:
    """(texto principal, texto secundario o None) según el modo."""
    if mode not in MODES:
        raise ValueError(f"modo debe ser uno de {MODES}")
    m = get(key)
    if mode == "siglas":
        return m.sigla, None
    if mode == "espanol":
        return m.nombre, None
    secondary = m.sigla if m.nombre != m.sigla else m.pista
    return m.nombre, secondary
